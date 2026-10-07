"""监控指标值对象，承载单个统计目标在一个窗口内的原始计数与派生指标。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetricBucket:
    """一个统计目标在单个窗口内的原始计数。

    成功率与平均值均由计数派生；样本数为零时派生指标返回 ``None``，
    避免把「没有流量」表达成 0，前端图表据此断开而不是画成低点。
    """

    succeeded_count: int = 0
    failed_count: int = 0
    refunded_count: int = 0
    total_duration_ms: int = 0
    first_token_sum_ms: int = 0
    first_token_count: int = 0

    @classmethod
    def from_snapshot(cls, snapshot) -> "MetricBucket":
        """由已落库的分组快照行还原指标值对象。"""

        return cls(
            succeeded_count=snapshot.succeeded_count,
            failed_count=snapshot.failed_count,
            refunded_count=snapshot.refunded_count,
            total_duration_ms=snapshot.total_duration_ms,
            first_token_sum_ms=snapshot.first_token_sum_ms,
            first_token_count=snapshot.first_token_count,
        )

    def __add__(self, other: "MetricBucket") -> "MetricBucket":
        """合并两个窗口或两类维度的计数，供区间汇总使用。"""

        return MetricBucket(
            succeeded_count=self.succeeded_count + other.succeeded_count,
            failed_count=self.failed_count + other.failed_count,
            refunded_count=self.refunded_count + other.refunded_count,
            total_duration_ms=self.total_duration_ms + other.total_duration_ms,
            first_token_sum_ms=self.first_token_sum_ms + other.first_token_sum_ms,
            first_token_count=self.first_token_count + other.first_token_count,
        )

    @property
    def sample_count(self) -> int:
        """参与成功率计算的样本数，等于成功、失败与退款请求之和。"""

        return self.succeeded_count + self.failed_count + self.refunded_count

    @property
    def success_rate(self) -> float | None:
        """成功率，四舍五入到四位小数；无样本时返回 ``None``。"""

        if self.sample_count == 0:
            return None
        return round(self.succeeded_count / self.sample_count, 4)

    @property
    def average_duration_ms(self) -> int | None:
        """成功请求的平均耗时；没有成功请求时返回 ``None``。"""

        if self.succeeded_count == 0:
            return None
        return self.total_duration_ms // self.succeeded_count

    @property
    def average_first_token_ms(self) -> int | None:
        """成功请求的平均首 token 耗时；没有记录到首 token 时返回 ``None``。"""

        if self.first_token_count == 0:
            return None
        return self.first_token_sum_ms // self.first_token_count
