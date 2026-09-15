"""
LLM-SQL solution generated from the *human* related-work section
(merged_human_re/d18c13d036b3708f), adapted to the ADRS `Evolved.reorder` interface.

Solution text this file implements, verbatim where quoted:

  "The layer treats each row as a sequence of labeled field segments and chooses, for a given
   table and operator, (1) a field order inside the prompt and (2) a row emission order. Repeated
   and long shared values, correlated attributes, and RAG contexts should be moved to the left of
   unique values because KV-cache reuse is prefix-based ... Row order should be a depth-first
   traversal of the trie of common prefixes, ordered by prefix popularity, so the cache serves one
   group before another and does not evict a large common prefix before all of its rows have been
   processed."

  Module 2 profiler: "takes a bounded random sample S of R. For every field f in the prompt it
   records the distinct values and their observed frequencies, and it estimates the token cost of
   serializing each value, including field name, delimiter, and the value text. If an open
   tokenizer is available, the cost is obtained by tokenizing the sampled serialized value;
   otherwise a character-length proxy is used. The profiler additionally computes lightweight
   CORDS-style correlations among fields ..."

  Module 3 prefix layout planner: "It maintains a collection of live prefix groups. Initially
   there is one live group containing all sampled rows, representing the common static instruction
   and any system/RAG prefix. At each step it considers every unassigned field f. For each live
   group G and each distinct value v of f inside G, let n(G,v) be the number of sampled rows in G
   whose value of f is v, and let len(G,v) be the estimated token length of serialized substring
   for f=v. The candidate score is score(f) = sum over live groups G, sum over distinct values v
   of max(0, n(G,v)-1) * len(G,v). ... The planner appends the field with maximum score to the
   ordered prefix list. It then splits every live group by the values of the selected field;
   groups with fewer than tau_min sampled rows are removed from live consideration ... If the
   number of live groups exceeds G_max, splitting stops. If no remaining field has positive score,
   or all fields are assigned, the loop ends. All remaining fields are appended after the chosen
   prefix fields in their original schema order."

  Module 4 materializer and request streamer: "it computes, for every prefix level j from 1 to k,
   the relation C_j = group by the first j ordered fields and count rows. Let cnt_j be that count
   for a row's prefix value. The module performs an exchange and sort on the composite key
   (descending cnt_1, ascending value_o1, descending cnt_2, ascending value_o2, ..., descending
   cnt_k, ascending value_ok). Sorting first by group counts, then by the serialized prefix value,
   visits sibling prefix groups in decreasing popularity while keeping every group contiguous."

Interface mapping (`Evolved().reorder(df, early_stop=..., distinct_value_threshold=...,
row_stop=..., col_stop=..., col_merge=...)`, of which the evaluator reads the first return value):

* Module 1 (operator capture and safety classification) has no counterpart: the interface hands
  over the relation and its merged-column groups directly, and the harness serializes every row as
  the plain concatenation of its values, which is the "safe structured serialization" case the
  module would classify as rewritable. Row permutation is always safe, as the solution states.
* Module 2's fields are the columns of the relation, and the character-length proxy is used since
  no tokenizer is exposed: len(G,v) = len(str(v)). `col_merge` groups are merged first, exactly as
  the harness passes them, so the profiler sees the same relation the other programs are scored on.
* tau_min and G_max are the two parameters the solution names but does not quantify ("tau_min
  being a configuration parameter defaulting to a small multiple of the serving engine's cache
  block size": TAIL_MIN_ROWS; "a cap on live groups": MAX_LIVE_GROUPS). A fixed seed makes the
  profiler's sample reproducible.
* Module 4's "persist the sorted view as a Delta Lake table clustered by the ordered prefix
  columns" and "database-cracking-style adaptive repartitioning" are storage-level machinery with
  no counterpart in a single `reorder` call.
"""

from collections import Counter
from typing import List, Tuple

import pandas as pd

from solver import Algorithm

# Module 2: "takes a bounded random sample S of R"
PROFILE_SAMPLE_ROWS = 20000
PROFILE_SAMPLE_SEED = 0
# Module 3: the two unquantified planner parameters
TAIL_MIN_ROWS = 8            # groups with fewer sampled rows stop being live prefix groups
MAX_LIVE_GROUPS = 512        # cap on live groups


class Evolved(Algorithm):
    """
    Prefix-layout planner: a greedy, statistics-driven construction of the prompt field order and
    a depth-first, popularity-ordered row emission order.
    """

    def __init__(self, df: pd.DataFrame = None):
        self.df = df

    # -- Module 2: profiler --------------------------------------------------------------

    @staticmethod
    def _value_length(value) -> int:
        """Character-length proxy for the serialized substring of a single value."""
        return len(str(value))

    def profile(self, sample: pd.DataFrame, fields: List[str]):
        """
        For every field: distinct values, their frequencies per live group, and the samplable
        correlations (a field that functionally determines another is not independent of it).
        """
        per_field = {}
        for f in fields:
            counts = Counter(sample[f].tolist())
            lengths = {v: self._value_length(v) for v in counts}
            per_field[f] = (counts, lengths)

        # CORDS-style correlations: c -> c' when c's values almost determine c'.
        correlations = {}
        for c in fields:
            marked = set()
            nunique_c = sample[c].nunique(dropna=False)
            if nunique_c == 0 or nunique_c > 0.5 * len(sample):
                correlations[c] = marked
                continue
            grouped = sample.groupby(c, dropna=False)
            for c2 in fields:
                if c2 == c:
                    continue
                if (grouped[c2].nunique(dropna=False) <= 1).mean() >= 0.99:
                    marked.add(c2)
            correlations[c] = marked
        return per_field, correlations

    # -- Module 3: prefix layout planner -------------------------------------------------

    def plan_prefix(self, sample: pd.DataFrame, fields: List[str]):
        per_field, correlations = self.profile(sample, fields)
        assigned = set()
        prefix: List[str] = []

        # "Initially there is one live group containing all sampled rows"
        live = {(): sample.index.to_numpy()}

        while True:
            best_field, best_score = None, 0
            for f in fields:
                if f in assigned:
                    continue
                counts, lengths = per_field[f]
                score = 0
                for rows in live.values():
                    sub = sample[f].loc[rows]
                    for v, n in Counter(sub.tolist()).items():
                        if n > 1:
                            score += (n - 1) * lengths.get(v, self._value_length(v))
                if score > best_score:
                    best_field, best_score = f, score
            if best_field is None:
                break

            prefix.append(best_field)
            assigned.add(best_field)

            # split every live group by the values of the selected field
            new_live = {}
            for group_key, rows in live.items():
                sub = sample[best_field].loc[rows]
                for v, sub_rows in sub.groupby(sub, dropna=False):
                    new_live[group_key + (v,)] = sub_rows.index.to_numpy()
            new_live = {g: r for g, r in new_live.items() if len(r) >= TAIL_MIN_ROWS}
            live = new_live
            # "If the number of live groups exceeds G_max, splitting stops."
            if len(live) > MAX_LIVE_GROUPS or not live:
                break

        # "All remaining fields are appended after the chosen prefix fields in their original
        # schema order."
        order = prefix + [f for f in fields if f not in assigned]
        return order, prefix, correlations

    # -- Module 4: materializer and request streamer --------------------------------------

    def materialize(self, df: pd.DataFrame, order: List[str], prefix: List[str]) -> pd.DataFrame:
        reordered = df[order].reset_index(drop=True)

        if prefix:
            tmp = reordered.copy()
            key_cols = []
            ascending = []
            temp_cols = []
            for j, f in enumerate(prefix, start=1):
                # C_j = group by the first j ordered fields, count rows
                key = tmp[prefix[:j]].astype(str).agg("\x00".join, axis=1)
                value_name, count_name = f"__v_{j}", f"__c_{j}"
                # the serialized prefix value is compared as text, like the harness does
                tmp[value_name] = tmp[f].astype(str)
                tmp[count_name] = key.map(key.value_counts())
                key_cols.extend([count_name, value_name])
                ascending.extend([False, True])
                temp_cols.extend([value_name, count_name])

            tmp = tmp.sort_values(by=key_cols, ascending=ascending, kind="mergesort")
            reordered = tmp.drop(columns=temp_cols).reset_index(drop=True)
        return reordered

    # -- interface entry point ------------------------------------------------------------

    def reorder(
        self,
        df: pd.DataFrame,
        early_stop: int = 0,
        row_stop: int = None,
        col_stop: int = None,
        col_merge: List[List[str]] = [],
        one_way_dep: List[Tuple[str, str]] = [],
        distinct_value_threshold: float = 0.8,
        parallel: bool = True,
    ) -> Tuple[pd.DataFrame, List[List[str]]]:
        work = df.copy()

        # The harness hands the merged-column groups to every candidate; merge them the same way
        # so the profiler works on the relation the candidate is scored on.
        if col_merge:
            for col_to_merge in col_merge:
                group = [c for c in work.columns if c in col_to_merge]
                if group and all(c in work.columns for c in group):
                    work = self.merging_columns(work, group, prepended=False)

        fields = work.columns.tolist()
        if not fields or len(work) == 0:
            return work, []

        # Module 2: profiler over a bounded random sample of the relation.
        if len(work) > PROFILE_SAMPLE_ROWS:
            sample = work.sample(n=PROFILE_SAMPLE_ROWS, random_state=PROFILE_SAMPLE_SEED)
        else:
            sample = work

        # Module 3: prefix layout planning.
        order, prefix, _correlations = self.plan_prefix(sample, fields)

        # Module 4: materialize the full relation in the planned layout and stream order.
        final_df = self.materialize(work, order, prefix)
        return final_df, []
