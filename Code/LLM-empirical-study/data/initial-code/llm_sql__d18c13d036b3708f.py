# EVOLVE-BLOCK-START
"""Prefix-aware prompt planner: greedy module ordering + grouped row schedule.

Source
------
paper      : LLM-SQL.md
pdf_id     : d18c13d036b3708f
solution   : LLM-generated from the LLM's own (search-enabled) related work,
             ``data/LLM_data/merged_llm_re_withsearch/d18c13d036b3708f.json``
             fields ``solution.idea`` and ``solution.implementation``.

What the LLM proposed
---------------------
Treat a batch of relational LLM invocations as a tree of shared prefixes and plan
the prompt's *physical* layout, because exact-prefix KV-cache reuse only happens
when the textual prefix is identical:

  * every prompt module is a self-contained fragment -- a single column value or
    a composite module that must never be split;
  * module ordering is greedy on the one-level reuse gain of putting ``m`` next,
    ``gain(m) = Σ_G Σ_v max(0, count_G(m,v) - 1) · len(m,v)``, over a partition of
    rows into *active groups* that already share the chosen prefix; after
    choosing ``m`` each active group splits by ``m``'s distinct values and
    subgroups of one row are dropped, since a singleton can contribute no
    further reuse;
  * rows are then issued in a depth-first traversal of the resulting prefix
    groups, so every row sharing a prefix is contiguous and each one after the
    first reuses the whole prefix;
  * unique high-cardinality fields (ids, free text) therefore sink to the tail
    where they cannot break reuse.

Fidelity note (adaptation to this benchmark)
--------------------------------------------
Two mappings were forced by this interface:

  * The benchmark's prompt serialization is a *bare concatenation* of cell
    values -- no column labels and no separators (``evaluate_df_prefix_hit_cnt``
    joins the row's values directly).  The LLM's "self-describing
    ``label: value``" rendering is therefore not expressible: adding labels would
    change the very characters whose reuse is being scored.  A module's length is
    the rendered value's own length.
  * ``col_merge`` supplies the LLM's composite modules.  They are kept *atomic
    and adjacent* in the emitted column order (the LLM: "never split"), with their
    internal order untouched, rather than being fused into one physical column --
    that preserves the table's contents exactly while honouring the atomicity.

The backend-facing parts of the design (RadixAttention interaction, module
registration for future invocations, eviction handling, integration into LOTUS /
DB-GPT plans) have no counterpart in a pure ``reorder`` call and are not faked.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from solver import Algorithm

MAX_PREFIX_MODULES = 3   # tail guard: never reorder away the entire schema


class Evolved(Algorithm):
    """Prefix-reuse-driven column and row ordering."""

    def __init__(self, df: pd.DataFrame = None):
        self.df = df

    # ------------------------------------------------------------------ #
    # module abstraction
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_modules(columns: List[str], col_merge) -> List[Tuple[str, ...]]:
        """Turn columns plus ``col_merge`` groups into atomic modules.

        A composite module replaces its member columns at the position of the
        first member, so its internal order is preserved.
        """
        composite_of = {}
        for group in col_merge or []:
            members = tuple(c for c in columns if c in set(group))
            if len(members) > 1:
                for member in members:
                    composite_of[member] = members

        modules: List[Tuple[str, ...]] = []
        emitted = set()
        for column in columns:
            if column in composite_of:
                members = composite_of[column]
                if members in emitted:
                    continue
                emitted.add(members)
                modules.append(members)
            else:
                modules.append((column,))
        return modules

    @staticmethod
    def _module_values(df: pd.DataFrame, module: Tuple[str, ...]) -> pd.Series:
        """Render one row's value for a module (concatenated for composites)."""
        if len(module) == 1:
            return df[module[0]].fillna("").astype(str)
        out = df[module[0]].fillna("").astype(str)
        for column in module[1:]:
            out = out + df[column].fillna("").astype(str)
        return out

    # ------------------------------------------------------------------ #
    # greedy prefix module ordering
    # ------------------------------------------------------------------ #
    def _order_modules(self, df: pd.DataFrame, modules, early_stop: int):
        """Return the chosen prefix modules, in order.

        Implements the LLM's step 3: repeatedly take the module with the largest
        positive one-level reuse gain, then split every active group by that
        module's values and drop subgroups of a single row.
        """
        n = len(df)
        group = np.full(n, -1)          # group id per row, -1 = no longer active
        live = np.ones(n, dtype=bool)   # rows still in the active partition
        chosen: List[int] = []
        remaining = set(range(len(modules)))

        while remaining and live.any():
            if len(chosen) >= max(1, len(modules) - MAX_PREFIX_MODULES):
                break

            live_idx = np.flatnonzero(live)
            best_gain, best_module = 0.0, None
            for index in remaining:
                values = self._module_values(df, modules[index])
                frame = pd.DataFrame(
                    {
                        "g": group[live_idx],
                        "v": values.to_numpy()[live_idx],
                        "L": values.str.len().to_numpy()[live_idx],
                    }
                )
                stats = frame.groupby(["g", "v"], sort=False)["L"].agg(["size", "max"])
                reusable = stats[stats["size"] > 1]
                if reusable.empty:
                    continue
                gain = float(((reusable["size"] - 1) * reusable["max"]).sum())
                if gain > best_gain:
                    best_gain, best_module = gain, index
            if best_module is None:
                break

            chosen.append(best_module)
            remaining.discard(best_module)

            # Split every active group by the chosen module's values and drop
            # singletons: a row alone in its group can contribute no further
            # reuse, so it leaves the active partition (the LLM's step 3).
            values = self._module_values(df, modules[best_module]).to_numpy()[live_idx]
            frame = pd.DataFrame({"g": group[live_idx], "v": values})
            keep = (frame.groupby(["g", "v"], sort=False)["v"].transform("size") > 1).to_numpy()
            new_ids = frame.groupby(["g", "v"], sort=False).ngroup().to_numpy()

            group = np.full(n, -1)
            group[live_idx[keep]] = new_ids[keep]
            live = np.zeros(n, dtype=bool)
            live[live_idx[keep]] = True

        return chosen

    # ------------------------------------------------------------------ #
    # row ordering
    # ------------------------------------------------------------------ #
    @staticmethod
    def _row_order(df: pd.DataFrame, modules, chosen) -> List[int]:
        """Depth-first traversal of the prefix groups.

        Rows sharing a prefix end up contiguous; sibling groups are visited in
        descending order of their descendant count, as the LLM specifies, so the
        largest reusable prefix groups run while they are hottest in the cache.
        """
        keys = [Evolved._module_values(df, modules[i]).to_numpy() for i in chosen]

        def walk(indices, depth):
            if depth == len(keys) or len(indices) <= 1:
                return list(indices)
            order: List[int] = []
            buckets: Dict[object, List[int]] = {}
            for position in indices:
                buckets.setdefault(keys[depth][position], []).append(position)
            for _value, members in sorted(buckets.items(), key=lambda kv: (-len(kv[1]), repr(kv[0]))):
                order.extend(walk(members, depth + 1))
            return order

        return walk(list(range(len(df))), 0)

    # ------------------------------------------------------------------ #
    # entry point
    # ------------------------------------------------------------------ #
    def reorder(
        self,
        df: pd.DataFrame,
        early_stop: int = 0,
        row_stop: int = None,
        col_stop: int = None,
        col_merge: List[List[str]] = [],
        one_way_dep=None,
        distinct_value_threshold: float = 0.8,
        parallel: bool = True,
    ) -> Tuple[pd.DataFrame, List[List[str]]]:
        """Plan the physical prompt layout of ``df``.

        Returns the table with its columns in prefix-optimal module order and its
        rows in the matching depth-first request schedule.
        """
        if df is None or len(df) == 0:
            return df, []

        columns = list(df.columns)
        modules = self._build_modules(columns, col_merge)
        chosen = self._order_modules(df, modules, early_stop)

        # column order: chosen prefix modules first, remaining modules after
        column_order: List[str] = []
        for index in chosen:
            column_order.extend(modules[index])
        for index, module in enumerate(modules):
            if index not in chosen:
                column_order.extend(module)
        column_order = [c for c in column_order if c in columns]

        row_order = self._row_order(df, modules, chosen)

        reordered = df.iloc[row_order][column_order]
        reordered = reordered.reset_index(drop=True)
        return reordered, [list(modules[i]) for i in chosen]


# EVOLVE-BLOCK-END
