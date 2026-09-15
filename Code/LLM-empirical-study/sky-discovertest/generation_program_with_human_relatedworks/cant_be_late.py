"""
Can't-Be-Late solution generated from the *human* related-work section
(merged_human_re/b93fea400aedf898), adapted to the ADRS strategy interface
(`_step(last_cluster_type, has_spot) -> ClusterType` with `NAME` and `_from_args`).

Solution text this file implements, verbatim where quoted:

  "for a job with total work W, an on-demand capacity R, a failover latency L, and current durable
   progress C(t), any spot failure at time t can be repaired without missing the deadline if
   C(t) + R(D - t - L) >= W. This inequality defines a failover horizon
   T = D - L - (W - C(t))/R."

  "The controller performs the following steps at every polling interval. First, it detects spot
   preemptions; if a preempted job was relying on spot, the controller immediately starts an
   on-demand tail of capacity R_j and restores C_j from durable checkpoint. Because the preemption
   time is less than the current T_j, the tail is guaranteed to finish. Second, for each job still
   in spot mode, it recomputes T_j from the latest C_j. If now is within one polling interval of
   T_j, it starts the on-demand tail proactively, since no useful spot checkpoint can be guaranteed
   after that point. Third, it instructs each spot worker to checkpoint by min(now +
   delta_checkpoint, T_j - K) ... If a checkpoint at time t_checkpoint is acknowledged and advances
   C_j, T_j moves later by delta_C / R_j ... If a checkpoint is not acknowledged before T_j is
   reached, the job is moved to on-demand tail mode."

  "A job is accepted only if W_j <= R_j * (D_j - admission_time - L); if this fails, even a perfect
   on-demand execution started immediately cannot meet the deadline, so the job is rejected or R_j
   is increased."

  "To choose which spot offers to use, the controller gathers available spot instances from all
   zones with their current prices and, optionally, the output of a black-box availability
   predictor ... offers whose effective cost per durable work unit is not lower than the on-demand
   price are discarded ... A job receives no more spot capacity than its remaining work W_j - C_j,
   and no new spot work is assigned unless the spot workers can reach their next checkpoint
   before T_j."

Interface mapping (this simulator exposes one region and one instance type per run):

* W_j = `task_duration`, D_j = `deadline`, C_j = `sum(task_done_time)` (durable progress), and
  R_j = 1 work unit per second, because one on-demand tick of `gap_seconds` completes exactly
  `gap_seconds` of work. L = `restart_overhead`, the failover latency (cloud API launch + boot +
  restore from checkpoint) that the simulator charges on every cluster-type change.
* The polling interval is the simulator tick `env.gap_seconds`.
* Checkpoints: the simulator has no checkpoint mechanism. Progress is durable as soon as a tick is
  accounted, so the worst-case time to make a checkpoint durable is K = 0 and C_j is always the
  latest acknowledged value; `delta_checkpoint` (the application's checkpoint period) is therefore
  one tick. Clause 3 reduces to "C_j never needs to be aged", and the tail is entered only through
  clauses 1 and 2.
* Spot-offer ranking (prices per zone, effective cost per durable work unit, sorting by
  cost-effectiveness, allocation in increasing T_j order) has nothing to rank here: one region,
  one instance type, and `has_spot` is a boolean with no price attached. What survives is the
  admission rule that comes with it - "no new spot work is assigned unless the spot workers can
  reach their next checkpoint before T_j" - which is enforced below as `elapsed + gap <= T`.
* The admission test of the last paragraph cannot reject a job: the interface must return a
  ClusterType for a job it has already been given. A job that fails the test is run entirely on
  the guaranteed resource instead, which is the same "guaranteed to finish" outcome the acceptance
  rule exists to protect.
* Tail mode: "the tail mode uses exactly enough on-demand capacity to finish the remaining work;
  if spot is still alive and appears cheaper, spot workers may continue concurrently". Running the
  tail and a spot worker concurrently is not expressible when `_step` returns one ClusterType per
  tick; what is implemented is the tail itself (on-demand from the moment it is started until the
  job completes), which is the part that carries the deadline guarantee.
"""

import math

from sky_spot.strategies.strategy import Strategy
from sky_spot.utils import ClusterType


class FailoverHorizonStrategy(Strategy):
    """
    Two-mode automaton per job: spot mode and guaranteed on-demand tail mode, switched on the
    failover horizon T_j = D_j - L - (W_j - C_j) / R_j.
    """

    NAME = "failover_horizon_tail"

    def __init__(self, args):
        super().__init__(args)

    def reset(self, env, task):
        super().reset(env, task)
        self._in_tail_mode = False
        # Admission: W_j <= R_j * (D_j - admission_time - L), with admission_time = 0 (the job is
        # submitted to the controller at simulation start) and R_j = 1.
        self._admitted = self.task_duration <= 1.0 * (self.deadline - self.restart_overhead)

    def _step(self, last_cluster_type: ClusterType, has_spot: bool) -> ClusterType:
        env = self.env
        gap = env.gap_seconds
        now = env.elapsed_seconds

        # Durable progress C_j and remaining work W_j - C_j.
        work_left = self.task_duration - sum(self.task_done_time)
        if work_left <= 1e-9:
            return ClusterType.NONE

        # A job that cannot be admitted is run entirely on the guaranteed resource, since the
        # controller cannot reject it.
        if not self._admitted:
            return ClusterType.ON_DEMAND

        # Failover horizon T_j = D_j - L - (W_j - C_j) / R_j.
        horizon = self.deadline - self.restart_overhead - work_left / 1.0

        # Clause 1 - spot preemption while relying on spot: the on-demand tail starts immediately
        # and runs to completion. It is guaranteed to finish because the preemption happened
        # before T_j.
        if self._in_tail_mode:
            return ClusterType.ON_DEMAND
        if last_cluster_type == ClusterType.SPOT and not has_spot:
            self._in_tail_mode = True
            return ClusterType.ON_DEMAND

        # Clause 2 - still in spot mode and now within one polling interval of T_j: start the tail
        # proactively, since no useful spot checkpoint can be guaranteed after that point.
        if now + gap >= horizon:
            self._in_tail_mode = True
            return ClusterType.ON_DEMAND

        # Clause 3 + the spot-offer admission rule - spot work is assigned only while the next
        # checkpoint (one polling interval away, K = 0) is still reachable before T_j.
        if has_spot and now + gap <= horizon:
            return ClusterType.SPOT

        # Before the horizon, spot is the only resource used; while it is unavailable the job
        # waits rather than buying on-demand outside the tail.
        return ClusterType.NONE

    @classmethod
    def _from_args(cls, parser):
        args, _ = parser.parse_known_args()
        return cls(args)
