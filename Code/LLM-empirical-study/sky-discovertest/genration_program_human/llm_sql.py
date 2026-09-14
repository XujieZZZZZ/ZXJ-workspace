import pandas as pd
from solver import Algorithm
from typing import Tuple, List
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from collections import Counter
import networkx as nx
import numpy as np


class Evolved(Algorithm):
    """
    GGR: the greedy approximation of OPHR (the paper's algorithm; the benchmark's
    initial_program.py is the paper's own implementation of the same algorithm).

    Selection rule, from the paper's implementation section: "For each candidate value v in
    field c, the subroutine HITCOUNT(v,c,T,FD) computes R_v = rows where T[i,c]=v and looks up
    functional dependencies from c to infer columns that must repeat for those rows. It
    estimates a hit-count score for placing c and its inferred columns first as: (len(v)^2 +
    the average length over R_v of values in the inferred columns) * (|R_v|-1). The list of
    fields placed first is [c] plus the inferred fields. At each recursion level, GGR scans all
    columns and all distinct values, chooses the (v,c) with the largest HITCOUNT [...]
    Functional dependencies reduce the candidate fields at each recursion step, because once a
    value in field c is placed, a field c' with c -> c' can be placed immediately after c and
    does not need to be separately reordered. [...] table statistics [...] can stop recursion
    early at a configured row/column recursion depth [...] if recursion stops, a fixed field
    ordering is chosen using per-field expected HITCOUNT estimates of avg_len(c)^2."

    The functional dependencies are read off the table (a dependency c -> c' holds when every
    value of c is paired with exactly one value of c'), the table statistics are the column
    statistics of `Algorithm.calculate_col_stats`, and the recursion-depth stop and the
    avg_len(c)^2 fallback ordering are the row_stop / col_stop / fixed_reorder of this file.
    """

    def __init__(self, df: pd.DataFrame = None):
        self.df = df

        self.dep_graph = None  # functional dependencies c -> c'

        self.num_rows = 0
        self.num_cols = 0
        self.column_stats = None
        self.val_len = None
        self.row_stop = None
        self.col_stop = None
        self.base = 2000

    # ------------------------------------------------------------------ table statistics

    def build_fd_graph(self, df: pd.DataFrame) -> nx.DiGraph:
        """Functional dependencies of the table: c -> c' when c determines c'.

        c -> c' holds exactly when c and (c, c') have the same number of distinct value
        combinations; the columns are addressed by position because a column_merge group can
        leave a duplicated column name behind.
        """
        graph = nx.DiGraph()
        cols = list(df.columns)
        graph.add_nodes_from(cols)
        positions = [p for p, c in enumerate(cols) if c != "original_index"]
        if not positions:
            return graph
        codes = {}
        for p in positions:
            codes[p] = pd.factorize(df.iloc[:, p], use_na_sentinel=False)
        base = max(len(codes[p][1]) for p in positions) + 1
        num_rows = len(df)
        for p in positions:
            code_p, uniq_p = codes[p]
            num_groups = len(uniq_p)
            if num_groups >= num_rows:
                continue  # a fully distinct key determines nothing but itself
            combined = code_p * base
            for q in positions:
                if q == p:
                    continue
                code_q, uniq_q = codes[q]
                if len(uniq_q) < num_groups:
                    continue
                if np.unique(combined + code_q).size == num_groups:
                    graph.add_edge(cols[p], cols[q])
        return graph

    def _length_sq(self, value) -> float:
        cached = self.val_len.get(value) if self.val_len is not None else None
        return cached if cached is not None else self.calculate_length(value)

    def hitcount(self, value, count: int, inferred_value_lens: List[float]) -> float:
        """HITCOUNT(v,c,T,FD): (len(v)^2 + avg length over R_v of the inferred fields) *
        (|R_v|-1). Because c -> c' holds, every row of R_v carries the same value in c', so the
        average over R_v is that one value's squared length."""
        if count <= 1:
            return 0.0
        score = self._length_sq(value) + sum(inferred_value_lens)
        return score * (count - 1)

    def find_max_group(self, df: pd.DataFrame, early_stop: int = 0) -> Tuple:
        """Scan all columns and all distinct values; return the (value, column) with the
        largest HITCOUNT.

        Columns are addressed by position: a column_merge group can produce a name that
        already exists in the table (e.g. PDMX has both a `path_metadata` column and a
        `path`+`metadata` merge), and a duplicated name is not addressable by label.
        """
        if df.empty or len(df.columns) == 0:
            return None
        cols = list(df.columns)
        best = None
        best_score = -1.0
        for pos, col in enumerate(cols):
            if col == "original_index":
                continue
            inferred_pos = [p for p, c in enumerate(cols) if p != pos and c in self.get_cached_dependent_columns(col)]
            codes, uniques = pd.factorize(df.iloc[:, pos], use_na_sentinel=False)
            if len(uniques) == 0:
                continue
            counts = np.bincount(codes, minlength=len(uniques))
            _, first_pos = np.unique(codes, return_index=True)
            for code, value in enumerate(uniques):
                count = int(counts[code])
                if count <= 1:
                    continue
                inferred_lens = []
                if inferred_pos:
                    first_row = df.iloc[first_pos[code]]
                    inferred_lens = [self._length_sq(first_row.iloc[p]) for p in inferred_pos]
                score = self.hitcount(value, count, inferred_lens)
                if score > best_score:
                    best_score = score
                    best = (value, col)
        if best is None or best_score < early_stop:
            return None
        return best

    def get_dependent_columns(self, col: str) -> List[str]:
        """FDs reduce the candidate fields at each recursion step: once a value in field c is
        placed, a field c' with c -> c' is placed immediately after c."""
        if self.dep_graph is None or not self.dep_graph.has_node(col):
            return []
        return list(nx.descendants(self.dep_graph, col))

    @lru_cache(maxsize=None)
    def get_cached_dependent_columns(self, col: str) -> List[str]:
        return self.get_dependent_columns(col)

    # ------------------------------------------------------------------ column ordering

    def reorder_columns_for_value(self, row, value, column_names, grouped_rows_len: int = 1):
        """Fields placed first: every field of the row that holds `value`, each followed by the
        fields its functional dependencies force to repeat, then the remaining fields.

        Positions, not names: a column_merge group can leave the table with a duplicated
        column name, and every position must still land in exactly one output slot.
        """
        fields = list(row)
        holds_value = [field == value for field in fields]
        cols_with_value = [col for col, flag in zip(column_names, holds_value) if flag]

        placed = [False] * len(fields)
        order = []
        for pos, (col, flag) in enumerate(zip(column_names, holds_value)):
            if not flag:
                continue
            order.append(pos)
            placed[pos] = True
            if self.dep_graph is not None and grouped_rows_len > 1:
                # a field c' with c -> c' is placed immediately after the field c
                dependents = self.get_cached_dependent_columns(col)
                for p2, c2 in enumerate(column_names):
                    if not placed[p2] and c2 in dependents:
                        order.append(p2)
                        placed[p2] = True
        order += [pos for pos, done in enumerate(placed) if not done]

        assert len(order) == len(fields), f"Reordered cols len: {len(order)}  Original cols len: {len(fields)}"
        return [fields[pos] for pos in order], cols_with_value

    def fixed_reorder(self, df: pd.DataFrame, row_sort: bool = True) -> Tuple[pd.DataFrame, List[List[str]]]:
        """Fixed field ordering from per-field expected HITCOUNT estimates of avg_len(c)^2."""
        num_rows, column_stats = self.calculate_col_stats(df, enable_index=True)
        reordered_columns = [col for col, _, _, _ in column_stats]
        reordered_df = df[reordered_columns]

        assert reordered_df.shape == df.shape
        column_orderings = [reordered_columns] * num_rows

        if row_sort:
            reordered_df = reordered_df.sort_values(by=reordered_columns, axis=0)

        return reordered_df, column_orderings

    def column_recursion(self, result_df, max_value, grouped_rows, row_stop, col_stop, early_stop):
        cols_settled = []
        with ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(self.reorder_columns_for_value, row, max_value, grouped_rows.columns.tolist(), len(grouped_rows))
                for row in grouped_rows.itertuples(index=False)
            ]
            for i, future in enumerate(as_completed(futures)):
                reordered_row, cols_settled = future.result()
                result_df.loc[i] = reordered_row

        grouped_value_counts = Counter()

        if not result_df.empty:
            # Group by the first column
            grouped_result_df = result_df.groupby(result_df.columns[0])
            grouped_value_counts = Counter(grouped_rows.stack())  # this is still faster than updating from cached value counts

            for _, group in grouped_result_df:
                if group[group.columns[0]].iloc[0] != max_value:
                    continue

                dependent_cols = self.get_cached_dependent_columns(group.columns[0])
                length_of_settle_cols = len(cols_settled)

                if dependent_cols:
                    assert length_of_settle_cols >= 1, f"Dependent columns should be no less than 1, but got {length_of_settle_cols}"

                # drop all the settled columns and reorder the rest
                group_remainder = group.iloc[:, max(1, length_of_settle_cols):] if dependent_cols else group.iloc[:, 1:]

                grouped_remainder_value_counts = Counter(group_remainder.stack())

                reordered_group_remainder, _ = self.recursive_reorder(
                    group_remainder, grouped_remainder_value_counts, early_stop=early_stop, row_stop=row_stop, col_stop=col_stop + 1
                )
                # Update the group with the reordered columns
                group.iloc[:, max(1, length_of_settle_cols):] = reordered_group_remainder.values

                result_df.update(group)
                break

        return result_df, grouped_value_counts

    def recursive_reorder(
        self,
        df: pd.DataFrame,
        value_counts: Dict,
        early_stop: int = 0,
        original_columns: List[str] = None,
        row_stop: int = 0,
        col_stop: int = 0,
    ) -> Tuple[pd.DataFrame, List[List[str]]]:
        if df.empty or len(df.columns) == 0 or len(df) == 0:
            return df, []

        if self.row_stop is not None and row_stop >= self.row_stop:
            return self.fixed_reorder(df)

        if self.col_stop is not None and col_stop >= self.col_stop:
            return self.fixed_reorder(df)

        if original_columns is None:
            original_columns = df.columns.tolist()

        # Find the value whose grouping has the largest HITCOUNT
        maximal = self.find_max_group(df, early_stop=early_stop)
        if maximal is None:
            # If there is no max value, then fall back to fixed reorder
            return self.fixed_reorder(df)
        max_value = maximal[0]

        grouped_rows = df[df.isin([max_value]).any(axis=1)]
        remaining_rows = df[~df.isin([max_value]).any(axis=1)]

        # If there is no grouped rows, return the original DataFrame
        if grouped_rows.empty:
            return self.fixed_reorder(df)

        result_df = pd.DataFrame(columns=df.columns)

        reordered_remaining_rows = pd.DataFrame(columns=df.columns)  # Initialize empty dataframe first

        # Column Recursion
        result_df, grouped_value_counts = self.column_recursion(result_df, max_value, grouped_rows, row_stop, col_stop, early_stop)

        remaining_value_counts = value_counts - grouped_value_counts  # Approach 1 - update remaining value counts with subtraction

        # Row Recursion
        reordered_remaining_rows, _ = self.recursive_reorder(
            remaining_rows, remaining_value_counts, early_stop=early_stop, row_stop=row_stop + 1, col_stop=col_stop
        )
        old_column_names = result_df.columns.tolist()
        result_cols_reset = result_df.reset_index(drop=True)
        result_rows_reset = reordered_remaining_rows.reset_index(drop=True)
        final_result_df = pd.DataFrame(result_cols_reset.values.tolist() + result_rows_reset.values.tolist())

        if row_stop == 0 and col_stop == 0:
            final_result_df.columns = old_column_names
            final_result_df.columns = final_result_df.columns.tolist()[:-1] + ["original_index"]

        return final_result_df, []

    def recursive_split_and_reorder(self, df: pd.DataFrame, original_columns: List[str] = None, early_stop: int = 0):
        """
        Recursively split the DataFrame into halves until the size is <= 1000, then apply the recursive reorder function.
        """
        if len(df) <= self.base:
            initial_value_counts = Counter(df.stack())
            return self.recursive_reorder(df, initial_value_counts, early_stop, original_columns, row_stop=0, col_stop=0)[0]

        mid_index = len(df) // 2
        df_top_half = df.iloc[:mid_index]
        df_bottom_half = df.iloc[mid_index:]

        with ThreadPoolExecutor() as executor:
            future_top = executor.submit(self.recursive_split_and_reorder, df_top_half, original_columns, early_stop)
            future_bottom = executor.submit(self.recursive_split_and_reorder, df_bottom_half, original_columns, early_stop)

        reordered_top_half = future_top.result()
        reordered_bottom_half = future_bottom.result()

        assert reordered_bottom_half.shape == df_bottom_half.shape
        reordered_df = pd.concat([reordered_top_half, reordered_bottom_half], axis=0, ignore_index=True)

        assert reordered_df.shape == df.shape

        return reordered_df

    @lru_cache(maxsize=None)
    def calculate_length(self, value):
        if isinstance(value, bool):
            return 4**2
        if isinstance(value, (int, float)):
            return len(str(value)) ** 2
        if isinstance(value, str):
            return len(value) ** 2
        return 0

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
        # Prepare
        initial_df = df.copy()
        if col_merge:
            self.num_rows, self.column_stats = self.calculate_col_stats(df, enable_index=True)
            reordered_columns = [col for col, _, _, _ in self.column_stats]
            for col_to_merge in col_merge:
                final_col_order = [col for col in reordered_columns if col in col_to_merge]
                df = self.merging_columns(df, final_col_order, prepended=False)
        self.num_rows, self.column_stats = self.calculate_col_stats(df, enable_index=True)
        self.column_stats = {col: (num_groups, avg_len, score) for col, num_groups, avg_len, score in self.column_stats}

        # Functional dependencies of the table (c -> c'), used to place a dependent field right
        # after the field that determines it.
        self.dep_graph = self.build_fd_graph(df)
        self.get_cached_dependent_columns.cache_clear()

        # One way dependency statistics
        if one_way_dep is not None and len(one_way_dep) > 0:
            for dep in one_way_dep:
                col1 = [col for col in df.columns if dep[0] in col]
                col2 = [col for col in df.columns if dep[1] in col]
                assert len(col1) == 1, f"Expected one column to match {dep[0]}, but got {len(col1)}"
                assert len(col2) == 1, f"Expected one column to match {dep[1]}, but got {len(col2)}"
                self.dep_graph.add_edge(col1[0], col2[0])

        # Discard too distinct columns by threshold [optional]
        nunique_threshold = len(df) * distinct_value_threshold
        columns_to_discard = [col for col in df.columns if df[col].nunique() > nunique_threshold]
        columns_to_discard = sorted(columns_to_discard, key=lambda x: self.column_stats[x][2], reverse=True)
        columns_to_recurse = [col for col in df.columns if col not in columns_to_discard]
        df["original_index"] = range(len(df))
        discarded_columns_df = df[columns_to_discard + ["original_index"]]
        df_to_recurse = df[columns_to_recurse + ["original_index"]]
        recurse_df = df_to_recurse

        self.column_stats = {col: stats for col, stats in self.column_stats.items() if col not in columns_to_discard}
        initial_value_counts = Counter(recurse_df.stack())
        self.val_len = {val: self.calculate_length(val) for val in initial_value_counts.keys()}

        self.row_stop = row_stop if row_stop else len(recurse_df)
        self.col_stop = col_stop if col_stop else len(recurse_df.columns.tolist())
        print("*" * 80)
        print(f"DF columns = {df.columns}")
        print("*" * 80)

        # Early stop and fall back
        recurse_df, _ = self.fixed_reorder(recurse_df)

        # Recursive reordering
        self.num_cols = len(recurse_df.columns)
        if parallel:
            reordered_df = self.recursive_split_and_reorder(recurse_df, original_columns=columns_to_recurse, early_stop=early_stop)
        else:
            reordered_df, _ = self.recursive_reorder(
                recurse_df,
                initial_value_counts,
                early_stop=early_stop,
            )

        assert (
            reordered_df.shape == recurse_df.shape
        ), f"Reordered DataFrame shape {reordered_df.shape} does not match original DataFrame shape {recurse_df.shape}"
        assert recurse_df["original_index"].is_unique, "Passed in recurse index contains duplicates!"
        assert reordered_df["original_index"].is_unique, "Reordered index contains duplicates!"

        if len(columns_to_discard) > 0:
            final_df = pd.merge(reordered_df, discarded_columns_df, on="original_index", how="left")
        else:
            final_df = reordered_df

        final_df = final_df.drop(columns=["original_index"])

        if not col_merge:
            assert (
                final_df.shape == initial_df.shape
            ), f"Final DataFrame shape {final_df.shape} does not match original DataFrame shape {initial_df.shape}"
        else:
            assert (
                final_df.shape[0] == initial_df.shape[0]
            ), f"Final DataFrame shape {final_df.shape[0]} does not match original DataFrame shape {initial_df.shape[0]}"
            assert (
                final_df.shape[1] == recurse_df.shape[1] + len(columns_to_discard) - 1
            ), f"Final DataFrame shape {final_df.shape} does not match original DataFrame shape {recurse_df.shape}"

        # sort by the first column to get the final order
        final_df = final_df.sort_values(by=final_df.columns.to_list(), axis=0)
        return final_df, []
