# EVOLVE-BLOCK-START
"""Guaranteed-progress / opportunistic-progress scheduler with an anchor.

Source
------
paper      : Can't-Be-Late.md
pdf_id     : b93fea400aedf898
solution   : LLM-generated from the LLM's own (search-enabled) related work,
             ``data/LLM_data/merged_llm_re_withsearch/b93fea400aedf898.json``
             fields ``solution.idea`` and ``solution.implementation``.

What the LLM proposed
---------------------
Separate *guaranteed* progress from *opportunistic* progress instead of spot
versus on-demand: on-demand is the guarantee mechanism, spot the acceleration
mechanism, and the application's own measurable durable progress decides when
spot is safe.

  * ``W`` required work, ``D`` deadline, ``R = W / D`` the on-demand rate that
    meets the deadline by itself;
  * ``P(t)`` the work completed, committed and made durable -- uncommitted spot
    work does not count;
  * ``δ`` the worst-case launch/restore delay for a fresh on-demand anchor;
  * the *fallback line* ``F(t) = W - R(D - t - δ)``: the progress from which an
    anchor started now still finishes on time;
  * the invariant is "``P(t)`` never falls below ``F(t)``".  While the anchor
    runs, spot is free to run alongside because a spot failure cannot violate the
    invariant.  Once spot work lifts ``P`` a conservative margin above the line
    the anchor is cancelled and spot carries the window alone; if progress stalls
    the anchor restarts before ``P`` reaches the line; a spot revocation launches
    the anchor immediately.  No availability forecasting or bidding is used --
    spot is exploited only once it has already converted into durable time lead.

Fidelity note (adaptation to this benchmark)
--------------------------------------------
The ``_step`` interface is a per-tick decision, so the LLM's *window* machinery
(window-boundary checkpoints, per-partition two-phase commit, lineage
recomputation of uncommitted partitions, the partition queue and the state store)
has no counterpart and is not faked.  The simulator already makes this cheap:
``task_done_time`` only ever grows, so ``P(t) = sum(self.task_done_time)`` is
exactly the LLM's "completed, committed and made durable" progress, and a spot
preemption cannot erase it.  The whole task is therefore treated as a single
window, with the control tick ``τ = env.gap_seconds``.

One parameter is adapted, not the mechanism: the LLM sizes its hysteresis as
"cancel the anchor at ``P >= F + 2Rδ``" while restarting it at
``P < F + Rδ + Rτ``, and states the design assumes "``τ`` ... small enough that
``R·τ`` is negligible relative to ``δ``".  In this benchmark ``τ`` is fixed at
600 s while ``δ`` is 72 s for the 0.02 h changeover delay, so that assumption
does not hold and the literal pair of thresholds would cancel and immediately
restart the anchor every tick.  The reaction delay is therefore taken as the
full ``δ + τ`` the decision actually has to survive and substituted for ``δ``
uniformly across the LLM's own margin:

    cancel  when ``P >= F + 2R(δ + τ)``          (the LLM's ``2Rδ`` when τ <= δ)
    restart when ``P <  F + R(δ + τ)``           (the LLM's ``Rδ + Rτ``)

Everything else -- the invariant, the three rules and their ordering, the
no-forecast stance, and the "spot unavailable -> the anchor is the guarantee"
fallback -- follows the LLM's text.
"""

from __future__ import annotations

from sky_spot.strategies.strategy import Strategy
from sky_spot.utils import ClusterType


class ProgressInvariantStrategy(Strategy):
    """On-demand anchor released only when durable progress has earned the slack."""

    NAME = "progress_invariant_anchor"

    def __init__(self, args):
        super().__init__(args)

    def reset(self, env, task):
        super().reset(env, task)

    def _step(self, last_cluster_type: ClusterType, has_spot: bool) -> ClusterType:
        env = self.env
        gap = env.gap_seconds

        work_left = self.task_duration - sum(self.task_done_time)
        if work_left <= 1e-9:
            return ClusterType.NONE

        # --- the LLM's control quantities -----------------------------------
        R = self.task_duration / self.deadline        # on-demand rate that alone meets D
        delta = self.restart_overhead                 # launch + restore delay
        tau = gap                                     # control sampling period
        P = sum(self.task_done_time)                  # durable, committed progress
        t = env.elapsed_seconds

        # F(t) = W - R(D - t - delta): fallback line.  Progress from here can
        # still finish on time behind a freshly launched anchor.
        F = self.task_duration - R * (self.deadline - t - delta)
        # The LLM's reaction delay delta, widened to the full delay a decision
        # must actually survive at this tick granularity (launch + one control
        # period).  Both thresholds below then keep the LLM's own 2x structure.
        reaction = R * (delta + tau)

        anchor_active = last_cluster_type == ClusterType.ON_DEMAND
        spot_revoked = last_cluster_type == ClusterType.SPOT and not has_spot

        # Rule 3: a spot revocation launches the anchor immediately (if it was
        # already running it simply keeps running).
        if spot_revoked:
            return ClusterType.ON_DEMAND

        # Rule 1: the anchor is active and spot has lifted P a conservative
        # margin above the line -> cancel it, spot carries the window alone.
        # (The LLM's "P >= F + 2Rδ": one reaction delay of slack beyond the
        # restart trigger below, so the two rules cannot oscillate.)
        if anchor_active and P >= F + 2 * reaction:
            return ClusterType.SPOT if has_spot else ClusterType.ON_DEMAND

        # Rule 2: no anchor and P is about to reach the line -> provision the
        # anchor now, because one reaction delay is needed before it produces.
        if not anchor_active and P < F + reaction:
            return ClusterType.ON_DEMAND

        # A running anchor is not released by spot availability -- only Rule 1
        # releases it.  (Spot is what acceleration would be added *alongside* the
        # anchor; this interface runs one cluster type at a time, so the anchor
        # simply keeps running.)
        if anchor_active:
            return ClusterType.ON_DEMAND

        # Opportunistic progress: spot while it is available, otherwise the
        # anchor is the guarantee mechanism.
        if has_spot:
            return ClusterType.SPOT
        return ClusterType.ON_DEMAND

    @classmethod
    def _from_args(cls, parser):
        args, _ = parser.parse_known_args()
        return cls(args)


# EVOLVE-BLOCK END
