/**
 * 分组监控与告警：类型定义与展示辅助
 * 字段约定与《分组监控与告警前端接入文档》一致：
 * - success_rate 为 0~1 的 number；耗时为整数毫秒；无数据为 null（不要当 0 渲染）
 * - 时间统一为 ISO 8601 UTC 字符串，前端按本地时区渲染
 */

export type RequestType = "text" | "image" | "video";
export type MetricKey =
  | "success_rate"
  | "average_duration_ms"
  | "average_first_token_ms";
/** 服务器资源告警指标（actual_value / threshold_value 为 0~100 的百分比数值） */
export type ServerMetricKey =
  | "cpu_usage"
  | "memory_usage"
  | "swap_usage"
  | "disk_usage";
export type AnyMetricKey = MetricKey | ServerMetricKey;
export type PeriodKey = "latest" | "last_24h";

/* ---------------- 分组指标 ---------------- */

export type GroupMetricItem = {
  group_id: number;
  group_name: string;
  request_type: RequestType;
  period: PeriodKey;
  window_start: string | null;
  sample_count: number;
  success_rate: number | null;
  average_duration_ms: number | null;
  average_first_token_ms: number | null;
  /** 用户侧：是否有已触发告警 */
  has_open_alert?: boolean;
  /** 管理侧：已触发告警数 */
  open_alert_count?: number;
};

export type GroupListResponse = {
  window_minutes: number;
  latest_window_start: string | null;
  range_start: string;
  items: GroupMetricItem[];
};

export type TrendSeries = {
  key: string;
  request_type: RequestType;
  metric: MetricKey;
  name: string;
  unit: "ratio" | "ms";
  values: (number | null)[];
};

export type TrendResponse = {
  group_id: number;
  group_name: string;
  window_minutes: number;
  x_axis: string[];
  series: TrendSeries[];
};

/* ---------------- 渠道指标（管理侧） ---------------- */

export type ChannelMetricItem = {
  group_id: number;
  group_name: string;
  channel_id: string;
  channel_name: string;
  request_type: RequestType;
  period: PeriodKey;
  window_start: string | null;
  sample_count: number;
  success_rate: number | null;
  average_duration_ms: number | null;
  average_first_token_ms: number | null;
};

export type ChannelListResponse = {
  window_start: string | null;
  window_minutes: number;
  items: ChannelMetricItem[];
};

/* ---------------- 告警记录（管理侧） ---------------- */

export type AlertStatus =
  | "pending"
  | "open"
  | "resolved"
  | "acknowledged"
  | "ignored";

export type NotifyStatus = "pending" | "sent" | "failed" | "skipped";

export type AlertItem = {
  id: string;
  /** 服务器资源告警时 group / channel 均为 null */
  group_id: number | null;
  group_name: string | null;
  /** null 表示分组级告警 */
  channel_id: string | null;
  channel_name: string | null;
  metric: AnyMetricKey;
  status: AlertStatus;
  first_window_start: string;
  last_window_start: string;
  triggered_at: string | null;
  resolved_at: string | null;
  acknowledged_at: string | null;
  sample_count: number;
  actual_value: number | null;
  threshold_value: number | null;
  consecutive_hits: number;
  notified_at: string | null;
  notification_status: NotifyStatus;
  notification_error: string | null;
};

export type Paged<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

/* ---------------- 阈值规则（管理侧） ---------------- */

export type AlertRule = {
  id: string;
  /** null 表示全局默认规则 */
  group_id: number | null;
  group_name: string | null;
  enabled: boolean;
  success_rate_min: number | null;
  avg_duration_ms_max: number | null;
  avg_first_token_ms_max: number | null;
  min_sample_count: number;
  consecutive_hits: number;
  /** 告警推送要 @ 的手机号，英文逗号分隔；分组行为空字符串表示沿用全局默认 */
  at_mobiles: string;
  /** 是否 @ 所有人；分组行或全局默认行任一为 true 即生效 */
  at_all: boolean;
};

/* ---------------- 钉钉推送配置（管理侧） ---------------- */

export type NotificationConfig = {
  /** 分组业务告警推送开关 */
  notify_group_alerts: boolean;
  /** 服务器资源告警推送开关 */
  notify_resource_alerts: boolean;
  webhook_url: string;
  keyword: string;
  timeout_seconds: number;
  silence_minutes: number;
  notify_on_resolved: boolean;
  sign_secret_configured: boolean;
};

/** 测试通知通道：group=分组业务告警，server=服务器资源告警 */
export type NotificationTestScope = "group" | "server";

export type NotificationTestResult = {
  status: "sent" | "failed" | "skipped";
  error: string | null;
  sent_at: string | null;
};

/* ---------------- 服务器资源监控（管理侧，1 分钟粒度） ---------------- */

/** 容量块：宿主未启用交换分区时三个字段全为 null */
export type ServerCapacity = {
  total_bytes: number | null;
  used_bytes: number | null;
  usage_percent: number | null;
};

export type ServerNic = {
  name: string;
  rx_bytes: number | null;
  tx_bytes: number | null;
  rx_errors: number;
  tx_errors: number;
  rx_dropped: number;
  tx_dropped: number;
  /** 字节/秒；首次采集或网卡重新计数时为 null */
  rx_rate_bps: number | null;
  tx_rate_bps: number | null;
};

export type ServerDisk = {
  mount: string;
  used_bytes: number | null;
  total_bytes: number | null;
  usage_percent: number | null;
};

export type ServerLatest = {
  /** false 表示尚未有任何采样，其余数值字段为 null，前端渲染空状态（接口不返回 404） */
  has_data: boolean;
  window_minutes: number;
  window_start: string | null;
  sample_interval_seconds: number | null;
  cpu: {
    usage_percent: number | null;
    core_count: number;
    /** 首次采集或核数变化时为 null */
    per_core_percent: (number | null)[] | null;
  };
  /** 本机模式（Windows）下三个字段恒为 null */
  load: { load1: number | null; load5: number | null; load15: number | null };
  memory: ServerCapacity;
  swap: ServerCapacity;
  /** 含回环 lo；「对外流量」口径需自行过滤 */
  network_interfaces: ServerNic[];
  disks: ServerDisk[];
  max_disk_mount: string | null;
  max_disk_usage_percent: number | null;
};

export type ServerTrendUnit = "percent" | "count" | "bytes_per_second";
export type ServerTrendGroup = "cpu" | "memory" | "load" | "disk" | "network";

export type ServerTrendSeries = {
  /** 稳定 key，用于序列开关与配色 */
  key: string;
  name: string;
  unit: ServerTrendUnit;
  group: ServerTrendGroup;
  /** 与 x_axis 严格等长；null 表示未采集 / 窗口跳过 / 无法计算，图表断开 */
  values: (number | null)[];
};

export type ServerTrendResponse = {
  window_minutes: number;
  x_axis: string[];
  series: ServerTrendSeries[];
};

/** 服务器资源告警阈值；阈值字段为 null 表示不评估该指标 */
export type ResourceRule = {
  /** 配置行尚未创建（采集任务未跑过）时为 null */
  id: string | null;
  enabled: boolean;
  cpu_usage_max: number | null;
  memory_usage_max: number | null;
  swap_usage_max: number | null;
  disk_usage_max: number | null;
  consecutive_hits: number;
};

/* ---------------- 展示辅助 ---------------- */

/** 图表中三种请求类型的配色 */
export const TYPE_COLORS: Record<RequestType, string> = {
  text: "#4c6fff",
  image: "#7c5cff",
  video: "#10b981",
};

export const REQUEST_TYPES: RequestType[] = ["text", "image", "video"];

const pad = (n: number) => String(n).padStart(2, "0");

/** ISO UTC → 本地「MM-dd HH:mm」，空值/非法值返回占位符 */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** ISO UTC → 本地「HH:mm」（24 小时内的趋势 X 轴用） */
export function fmtClock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** 成功率：0~1 → 百分比字符串；null → 占位符（无数据与 0% 必须区分） */
export function fmtRate(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(2)}%`;
}

/** 耗时毫秒 → 紧凑展示：小于 1 秒显示毫秒，其余统一显示秒（420ms / 4.1s） */
export function fmtMs(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  if (v < 1000) return `${v}ms`;
  return `${(v / 1000).toFixed(1)}s`;
}

/** 按指标类型格式化告警里的当前值/阈值 */
export function fmtMetricValue(
  metric: AnyMetricKey,
  v: number | null | undefined
): string {
  if (metric === "success_rate") return fmtRate(v);
  // 服务器资源指标是 0~100 的百分比数值，与 success_rate 的 0~1 口径不同
  if (metric === "cpu_usage" || metric === "memory_usage" || metric === "swap_usage" || metric === "disk_usage")
    return fmtPercent(v);
  return fmtMs(v);
}

/** 0~100 的使用率 → 百分比字符串；null → 占位符 */
export function fmtPercent(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${v.toFixed(1)}%`;
}

/** 字节数 → 紧凑展示：512 B / 1.5 GB */
export function fmtBytes(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let n = v;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  const text = n >= 100 ? n.toFixed(0) : n >= 10 ? n.toFixed(1) : n.toFixed(2);
  return `${text} ${units[i]}`;
}

/** 字节/秒速率 → 紧凑展示；null → 占位符（首次采集速率不可比） */
export function fmtBps(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${fmtBytes(v)}/s`;
}
