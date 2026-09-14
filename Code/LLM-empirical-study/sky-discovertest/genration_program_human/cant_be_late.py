# EVOLVE-BLOCK START
"""
Uniform Progress (human / paper solution for Can't-Be-Late).

"The policy switches among idle, spot, and on-demand using the following rules:
 (1) Thrifty Rule: once cp(t)=C0, terminate all instances and remain idle.
 (2) Safety Net Rule: if the job is idle and R(t) < C(t) + 2d, switch to on-demand and stay on
     it until completion.
 (3) Exploitation Rule: once on a spot instance, stay on it until it is preempted.
 (4) Uniform Progress: when idle and cp(t) < ep(t) = t*C0/R0, switch to on-demand and stay on it
     to catch up.
 (5) Taking Risks: whenever a spot instance is available, start or resume spot use even if
     cp(t) < ep(t), subject to the next rule.
 (6) Hysteresis: while on on-demand, remain on on-demand until cp(t) >= ep(t+2d); only then may
     an available spot instance be taken."

with C0 = total computation (task_duration), R0 = time to deadline (deadline), d = the mean
changeover delay (restart_overhead), cp(t) = C0 - C(t) the progress made so far and
ep(t) = t*C0/R0 the progress required by a uniform spread over the horizon.

Interface: identical to initial_greedy.py -- one Strategy subclass with NAME, _from_args and
_step(last_cluster_type, has_spot).

Interface notes: the Next Spot Lifetime Oracle o(t) variant needs a future spot-lifetime
predictor that this simulator does not expose, so rules (5)/(6) are used as written for the
no-oracle case; the gang-scheduled multi-instance Polarization Rule has no counterpart in the
single-instance interface (the multi-instance variant is a separate benchmark task).
"""

import math
from sky_spot.strategies.strategy import Strategy
from sky_spot.utils import ClusterType


class UniformProgressStrategy(Strategy):
    NAME = "uniform_progress_human"

    def __init__(self, args):
        super().__init__(args)

    def reset(self, env, task):
        super().reset(env, task)

    def progress(self):
        """cp(t) = C0 - C(t): computation completed so far."""
        return sum(self.task_done_time)

    def uniform_progress_required(self, t):
        """ep(t) = t * C0 / R0: the progress a uniform spread over the horizon asks for."""
        return t * self.task_duration / self.deadline

    def _step(self, last_cluster_type: ClusterType, has_spot: bool) -> ClusterType:
        env = self.env
        c0 = self.task_duration
        d = self.restart_overhead
        t = env.elapsed_seconds
        gap = env.gap_seconds

        cp = self.progress()
        remaining_work = c0 - cp

        # (1) Thrifty Rule: once cp(t) = C0, terminate all instances and remain idle.
        if remaining_work <= 1e-3:
            return ClusterType.NONE

        # (2) Safety Net Rule: R(t) < C(t) + 2d -> switch to on-demand and stay to the end.
        #    (tick-aligned, because equality on a tick boundary is unsafe)
        remaining_time = self.deadline - t
        left_ticks = math.floor(remaining_time / gap)
        need_ticks = math.ceil((remaining_work + 2 * d) / gap)
        if need_ticks >= left_ticks:
            return ClusterType.ON_DEMAND

        # (6) Hysteresis: while on on-demand, remain there until cp(t) >= ep(t + 2d).
        if env.cluster_type == ClusterType.ON_DEMAND:
            if self.uniform_progress_required(t + 2 * d) - cp > 0:
                return ClusterType.ON_DEMAND

        # (5) Taking Risks: whenever spot is available, start or resume spot use -- (3) the
        #     Exploitation Rule keeps it until it is preempted.
        if has_spot:
            return ClusterType.SPOT

        # (4) Uniform Progress: idle and cp(t) < ep(t) -> on-demand to catch up;
        #     otherwise stay idle and wait for spot rather than paying for on-demand.
        if self.uniform_progress_required(t) - cp > 0:
            return ClusterType.ON_DEMAND
        return ClusterType.NONE

    @classmethod
    def _from_args(cls, parser):
        args, _ = parser.parse_known_args()
        return cls(args)

# EVOLVE-BLOCK END
