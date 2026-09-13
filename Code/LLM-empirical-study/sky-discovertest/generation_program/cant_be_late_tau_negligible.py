"""SENSITIVITY VARIANT of cant_be_late.py (not the primary deliverable).

Identical to cant_be_late.py except that rule 2 drops the R*tau term, i.e. it takes the
solution at its own parameter guidance ("tau is the control loop interval, chosen small
enough that R_i * tau is negligible relative to delta"). In this simulator the control
period is the trace gap (600 s) while delta = restart_overhead (72 s), so the two
thresholds of the controller cross and the literal rule oscillates on-demand/spot;
this variant shows the result when the sampling allowance is negligible.
"""
# EVOLVE-BLOCK START
"""
Protected-progress scheduler (LLM solution for the Can't-Be-Late paper).

Implementation of the "protected progress vs. fallback line" control invariant:

  P(t)  durable, committed progress of the running application
        (in the simulator: sum(self.task_done_time); uncommitted work does not exist)
  W     required work of the window            (self.task_duration)
  D     deadline of the window                 (self.deadline)
  R     W / D, the on-demand rate that would just meet the deadline if used alone
  delta worst-case time to launch an on-demand anchor and restore the checkpoint
        (self.restart_overhead)
  tau   control sampling period                (env.gap_seconds)

On-demand is the *guarantee* mechanism, spot is the *acceleration* mechanism.
A fresh on-demand anchor started at t can still finish the window iff

    P(t) >= F(t) = W - R * (D - t - delta)        (the fallback line)

so the scheduler drives the distance to that line, slack(t) = P(t) - F(t):

  rule 1: anchor active and slack >= 2 * R * delta  -> cancel the anchor, spot alone
  rule 2: no anchor and slack <= R * delta + R * tau -> provision the on-demand anchor
  rule 3: a spot revocation is observed             -> launch the anchor immediately
  rule 4: otherwise                                 -> ride SPOT when available, else wait

No price forecast, bid model or per-zone availability model is used: spot is exploited
only once it has already been converted into durable time lead.
"""

import math

from sky_spot.strategies.strategy import Strategy
from sky_spot.utils import ClusterType


class ProtectedProgressStrategy(Strategy):
    NAME = "protected_progress_seed"

    def __init__(self, args):
        super().__init__(args)

    def reset(self, env, task):
        super().reset(env, task)

    def _step(self, last_cluster_type: ClusterType, has_spot: bool) -> ClusterType:
        env = self.env
        gap = env.gap_seconds

        # ---- durable / committed progress P(t) (uncommitted work is treated as lost) ----
        progress = sum(self.task_done_time)
        work_left = self.task_duration - progress
        if work_left <= 1e-9:
            # window finished; the boundary checkpoint is taken and the window ends
            return ClusterType.NONE

        # ---- window parameters ----
        w = self.task_duration
        d = self.deadline
        t = env.elapsed_seconds
        r = w / d                       # on-demand rate that just meets the deadline
        delta = self.restart_overhead   # worst-case anchor launch / checkpoint restore
        tau = gap                       # control sampling period

        # ---- fallback line F(t) and the distance to it ----
        fallback_line = w - r * (d - t - delta)
        slack = progress - fallback_line

        anchor_active = (last_cluster_type == ClusterType.ON_DEMAND)
        spot_revoked = (last_cluster_type == ClusterType.SPOT and not has_spot)

        # rule 3: a revocation must start the anchor right away
        if spot_revoked:
            return ClusterType.ON_DEMAND

        if anchor_active:
            # rule 1: spot has already banked enough durable lead -> cancel the anchor
            if slack >= 2.0 * r * delta:
                return ClusterType.SPOT if has_spot else ClusterType.NONE
            return ClusterType.ON_DEMAND

        # rule 2: the lead is about to be consumed -> provision the anchor now,
        # one delta is needed for its launch, hence the R * tau sampling allowance
        if slack <= r * delta:
            return ClusterType.ON_DEMAND

        # rule 4: opportunistic execution -- spot when it is available, otherwise wait
        if has_spot:
            return ClusterType.SPOT
        return ClusterType.NONE

    @classmethod
    def _from_args(cls, parser):
        args, _ = parser.parse_known_args()
        return cls(args)

# EVOLVE-BLOCK END
