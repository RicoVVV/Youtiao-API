# 使用记录列表：时间筛选与汇总 前端接入文档

本文档仅描述本次改动：使用记录列表接口新增时间范围筛选，并在响应中返回汇总数据（消耗额度、总 Token、RPM、TPM）。

- 金额单位为 CNY（人民币），十进制字符串。
- 未传时间参数时，默认查询**当天**（Asia/Shanghai 自然日）的记录。

## 鉴权

```
Authorization: Bearer {access_token}
```

## 接口

| 范围 | 方法 | 路径 |
|---|---|---|
| 用户 | GET | `/api/usage/records/list` |
| 管理员 | GET | `/api/admin/usage/records/list` |

## 请求参数（Query）

所有参数均放在 Query 中，均为可选。

| 参数 | 类型 | 说明 |
|---|---|---|
| `page` | integer | 页码，从 1 开始，默认 `1`。 |
| `page_size` | integer | 每页条数，默认 `20`，最大 `100`。 |
| `range` | string | 预设时间范围：`today`、`last_7_days`、`last_30_days`。与 `start_at` / `end_at` 同时传入时，以 `start_at` / `end_at` 为准。 |
| `start_at` | datetime | 自定义范围开始，ISO 8601 且必须带时区，例如 `2026-09-01T00:00:00+08:00`。必须与 `end_at` 成对出现。 |
| `end_at` | datetime | 自定义范围结束，ISO 8601 且必须带时区。必须与 `start_at` 成对出现。 |
| `request_type` | string | 按请求类型筛选，长度 1-64。 |
| `model_name` | string | 按模型名称筛选，长度 1-64。 |
| `token_display_name` | string | 按 API 令牌名称筛选，长度 1-128。 |
| `status` | string | 按记录状态筛选，长度 1-32。取值：`reserved`、`succeeded`、`failed`、`refunded`。 |
| `request_id` | string | 按使用记录详情中的请求 ID 精确筛选，长度 1-128。适用于全部请求类型（`text`、`image`、`video`、`channel_test`）。 |
| `usage_record_id` | uuid | 按使用记录 ID（列表 `items[].id`）精确筛选。 |

仅管理员接口额外支持以下 Query 参数：

| 参数 | 类型 | 说明 |
|---|---|---|
| `user_id` | uuid | 按用户筛选。 |
| `channel_id` | uuid | 按渠道筛选。 |
| `provider_name` | string | 按供应商筛选，长度 1-64。 |
| `username` | string | 按用户名模糊筛选，长度 1-128。 |

### 时间范围规则

- **不传任何时间参数**：默认当天，即 Asia/Shanghai 当天 00:00 至次日 00:00。
- **`range`**：
  - `today`：当天。
  - `last_7_days`：今天及之前共 7 个自然日。
  - `last_30_days`：今天及之前共 30 个自然日。
- **`start_at` / `end_at`**：
  - 按 Asia/Shanghai **自然日**过滤，不是精确到秒的时间戳过滤。`start_at` 所在日为起始日（含），`end_at` 所在日为结束日（**不含**）。
  - 例如 `start_at=2026-09-01T00:00:00+08:00&end_at=2026-09-02T00:00:00+08:00` 表示查询 9 月 1 日当天。
  - `end_at` 所在日必须晚于 `start_at` 所在日，否则返回 `422`。例如同一天内的 `00:00` 到 `23:59` 会被拒绝，应改用 `range=today` 或将 `end_at` 设为次日 00:00。
  - 跨度不能超过 366 天。

## 响应

统一响应包装为 `{ code, message, data, request_id }`，下表字段位于 `data` 中。

| 字段 | 类型 | 说明 |
|---|---|---|
| `items` | array | 当前页使用记录列表，按创建时间倒序。 |
| `total` | integer | 满足筛选条件的记录总数（包含所有状态，如 `failed`、`reserved`）。用于分页。 |
| `page` | integer | 当前页码。 |
| `page_size` | integer | 每页条数。 |
| `summary` | object | 满足筛选条件的汇总数据，不受分页影响。 |

### `items[]` 字段（用户接口）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string(uuid) | 使用记录 ID。 |
| `request_type` | string | 请求类型。 |
| `token_display_name` | string \| null | API 令牌名称。 |
| `model_name` | string | 模型名称。 |
| `status` | string | 状态：`reserved` / `succeeded` / `failed` / `refunded`。 |
| `amount` | string | 本次消耗金额（CNY，十进制字符串）。 |
| `created_at` | datetime | 创建时间。 |
| `started_at` | datetime \| null | 开始时间。 |
| `completed_at` | datetime \| null | 完成时间。 |
| `duration_ms` | integer \| null | 耗时（毫秒）。 |
| `first_token_duration_ms` | integer \| null | 首 Token 耗时（毫秒）。 |
| `prompt_tokens` | integer \| null | 输入 Token 数。 |
| `completion_tokens` | integer \| null | 输出 Token 数。 |
| `cached_tokens` | integer \| null | 缓存读取 Token 数。 |
| `cache_write_tokens` | integer \| null | 缓存写入 Token 数。 |

管理员接口的 `items[]` 在上述字段基础上额外包含：`username`、`channel_name`、`provider_name`。

### `summary` 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `total_count` | integer | 调用次数，等于 `succeeded` + `refunded` 的记录数。 |
| `settled_amount` | string | 消耗额度（CNY），仅统计 `succeeded` 记录的 `amount` 之和。 |
| `total_tokens` | integer | 总 Token，仅统计 `succeeded` 记录的 `prompt_tokens + completion_tokens` 之和。 |
| `average_rpm` | string | 平均每分钟请求数，十进制字符串，最多 6 位小数。 |
| `average_tpm` | string | 平均每分钟 Token 数，十进制字符串，最多 6 位小数。 |

### RPM / TPM 计算口径

```
minutes      = 所选范围的自然日天数 * 24 * 60
average_rpm  = total_count / minutes
average_tpm  = total_tokens / minutes
```

- 当天（`today` 或默认）：分母为 1440。
- `last_7_days`：分母为 10080。
- `last_30_days`：分母为 43200。
- 分母包含无请求的空闲分钟，是按自然时间的平均值。
- 前端展示可格式化，例如 `Number(average_rpm).toFixed(2)`。

### 注意事项

- `summary` 的筛选条件与 `items` 完全一致，但只统计 `succeeded` / `refunded` 的调用次数，因此 `summary.total_count` 可能小于 `total`（`total` 还包含 `failed`、`reserved` 记录）。
- 未成功的请求不计入 `settled_amount` 与 `total_tokens`。
- 当列表数据为空时，`summary` 各数值为 `0`，`average_rpm` 与 `average_tpm` 为 `"0"`。

## 示例

### 用户：默认查询当天

```
GET /api/usage/records/list?page=1&page_size=20
Authorization: Bearer {access_token}
```

```json
{
  "code": 200,
  "message": "OK",
  "request_id": "5d8e2a1c-3b4f-4e6a-9f0d-1a2b3c4d5e6f",
  "data": {
    "items": [
      {
        "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
        "request_type": "chat_completion",
        "token_display_name": "default-key",
        "model_name": "qwen-plus",
        "status": "succeeded",
        "amount": "0.012500",
        "created_at": "2026-10-09T10:21:33+08:00",
        "started_at": "2026-10-09T10:21:33+08:00",
        "completed_at": "2026-10-09T10:21:35+08:00",
        "duration_ms": 1830,
        "first_token_duration_ms": 420,
        "prompt_tokens": 1200,
        "completion_tokens": 350,
        "cached_tokens": 0,
        "cache_write_tokens": 0
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "summary": {
      "total_count": 1,
      "settled_amount": "0.012500",
      "total_tokens": 1550,
      "average_rpm": "0.000694",
      "average_tpm": "1.076389"
    }
  }
}
```

### 用户：近 7 天并按状态筛选

```
GET /api/usage/records/list?range=last_7_days&status=succeeded&page=1&page_size=20
Authorization: Bearer {access_token}
```

`data.summary` 的 `average_rpm` 分母为 10080 分钟。

### 管理员：自定义日期范围（9 月 1 日当天）

```
GET /api/admin/usage/records/list?start_at=2026-09-01T00:00:00%2B08:00&end_at=2026-09-02T00:00:00%2B08:00&page=1&page_size=20
Authorization: Bearer {admin_access_token}
```

`%2B` 为 URL 编码后的 `+`。

## 错误

错误使用统一错误包装返回，并带有对应 HTTP 状态码。

| 状态码 | 场景 |
|---|---|
| `401` | 缺少或无效的访问令牌。 |
| `403` | 非管理员访问管理员接口。 |
| `422` | `range` 取值不合法；`page` / `page_size` 超出范围（`page_size` 最大 100）；`usage_record_id` 不是合法 UUID；`start_at` 与 `end_at` 未成对提供；时间缺少时区；`end_at` 所在日不晚于 `start_at` 所在日；时间跨度超过 366 天。 |
