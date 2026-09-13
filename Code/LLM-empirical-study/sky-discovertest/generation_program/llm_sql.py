"""
Prefix-aware prompt planner (LLM solution for the LLM-SQL paper).

The solution treats a batch of relational LLM invocations as a tree of shared prompt
prefixes and plans its physical layout:

  1. Relation and module abstraction -- every prompt module is a self-describing text
     fragment; a composite module (the evaluator's col_merge groups) is atomic and is
     never split, every other module is one column.
  2. Workload statistics -- per module, the value-frequency distribution and the
     rendered length len(m, v) of each distinct value, computed with the same
     rendering the cache-hit metric uses (fillna("") + str, values concatenated).
  3. Greedy prefix module ordering -- the planner keeps a partition of the rows into
     active groups that already share identical text, and repeatedly appends the module
     with the largest one-level reuse gain
         gain(m) = sum_G sum_{v in G} max(0, count_G(m, v) - 1) * len(m, v)
     splitting every active group by the chosen module and dropping the singletons
     (they can no longer contribute reuse). It stops when no module has a positive
     gain or no active group is left; the modules left over keep their input order as
     the tail of the prompt.
  4. Row ordering / request scheduling -- rows are emitted in a depth-first traversal
     of the prefix groups, i.e. sorted by (m_1, ..., m_k), so that rows sharing a
     prefix are issued contiguously and every row after the first in a leaf reuses the
     full prefix (the sibling ordering is only an optimisation, as the solution notes,
     and does not affect correctness).
  5. Backend cache interaction -- untouched: the planner only decides the textual
     prefix order, the existing RadixAttention/PagedAttention cache does the reuse.
  6. Integration -- no tuple is duplicated or dropped; only the field order and the
     request order change, so the semantics of the relational operator are preserved.
"""

import numpy as np
import pandas as pd

from solver import Algorithm
from typing import List, Tuple


class Evolved(Algorithm):
    """Physical prompt planner for LLM operators over relations."""

    def __init__(self, df: pd.DataFrame = None):
        super().__init__(df)

    def reorder(
        self,
        df: pd.DataFrame,
        early_stop: int = 100000,
        row_stop: int = 4,
        col_stop: int = 2,
        col_merge: List[List[str]] = [],
        distinct_value_threshold: float = 0.7,
        one_way_dep: List[Tuple[str, str]] = [],
        parallel: bool = True,
    ) -> Tuple[pd.DataFrame, List[List[str]]]:
        # ---- 1. relation and module abstraction -------------------------------
        work = df.copy()
        for group in col_merge or []:
            cols = [col for col in group if col in work.columns]
            if len(cols) < 2:
                continue
            try:  # a composite module stays adjacent, exactly as supplied
                work = self.merging_columns(work, cols, prepended=False)
            except ValueError:
                # the group is not mergeable here; keep the columns as separate modules
                continue
        modules = list(work.columns)

        # ---- 2. workload statistics (value frequencies and rendered lengths) ---
        rendered, lengths = {}, {}
        for col in modules:
            values = work[col].fillna("").astype(str)
            rendered[col] = values.to_numpy()
            lengths[col] = values.str.len().to_numpy()
        n = len(work)
        all_rows = np.arange(n)

        # ---- 3. greedy prefix module ordering --------------------------------
        active_groups = [all_rows] if n else []
        prefix_order, chosen = [], set()
        while active_groups:
            best_module, best_gain = None, 0.0
            for col in modules:
                if col in chosen:
                    continue
                values, value_lengths = rendered[col], lengths[col]
                gain = 0.0
                for group in active_groups:
                    group_values = values[group]
                    # per distinct value in this active group: (count - 1) * len(value)
                    sorter = np.argsort(group_values, kind="stable")
                    sorted_values = group_values[sorter]
                    _, starts, counts = np.unique(
                        sorted_values, return_index=True, return_counts=True)
                    if counts.size == counts.sum():
                        continue  # every value distinct in this group: no reuse
                    first_lengths = value_lengths[group][sorter[starts]]
                    gain += float(
                        np.sum(np.maximum(0, counts - 1) * first_lengths))
                if gain > best_gain:
                    best_gain, best_module = gain, col
            if best_module is None:  # no module has a positive gain
                break
            prefix_order.append(best_module)
            chosen.add(best_module)

            # split every active group by the chosen module, drop the singletons
            split_groups = []
            values = rendered[best_module]
            for group in active_groups:
                group_values = values[group]
                unique = np.unique(group_values)
                if unique.size == 1:
                    split_groups.append(group)
                    continue
                for value in unique:
                    subgroup = group[group_values == value]
                    if subgroup.size > 1:
                        split_groups.append(subgroup)
            active_groups = split_groups

        tail_order = [col for col in modules if col not in chosen]
        column_order = prefix_order + tail_order

        # ---- 4. row ordering: depth-first traversal of the prefix groups ------
        if prefix_order and n:
            # np.lexsort sorts by the last key first, so the primary module goes last
            keys = [rendered[col] for col in reversed(prefix_order)]
            row_order = np.lexsort(keys)
            reordered = work.iloc[row_order]
        else:
            reordered = work

        final_df = reordered[column_order].reset_index(drop=True)
        assert final_df.shape[0] == len(df)
        return final_df, []
