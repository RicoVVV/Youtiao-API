ma# 余额预警设置改造说明（前端）

本文是给前端同事的**改造任务说明**，用于把余额预警从“管理员统一设置阈值”改为：

- **管理员**：只打开/关闭余额预警总开关，并保证邮箱注册与 SMTP 配置完整；
- **用户**：自行设置预警阈值，并可填写自己的收件邮箱；不填则使用注册邮箱；
- **非邮箱注册账号**：没有注册邮箱，开启预警时必须填写收件邮箱。

接口契约的完整说明见 [ADMIN_CONSOLE_FRONTEND_INTEGRATION.md](./ADMIN_CONSOLE_FRONTEND_INTEGRATION.md) 的 Part A。
本文只描述本次前端需要改动的内容。

## 1. 与旧版实现的差异

| 位置 | 旧版 | 本次改动后 |
| --- | --- | --- |
| 管理员系统设置 | 有 `balance_alert_enabled` + `balance_alert_threshold` | **移除 `balance_alert_threshold`**，只保留 `balance_alert_enabled` |
| 用户资料 | 无余额预警字段 | 新增 `balance_alert_threshold`、`balance_alert_email` |
| 用户接口 | 无 | 新增 `POST /api/user/balance-alert/update` |
| 收件人 | 固定为注册邮箱 | 优先使用用户自设邮箱，未设置时回退注册邮箱 |

> 如果前端已经在管理员设置页加了“预警阈值”输入框，需要删除该输入框及对应请求字段。后端已不再接受该字段（多传会被忽略，但响应中不会返回）。

## 2. 接口契约

统一响应信封：

```json
{ "code": 200, "message": "OK", "data": {}, "request_id": "..." }
```

业务校验失败返回 HTTP 422，`message` 为可直接展示的原因。管理员接口使用管理员 Bearer Token，用户接口使用当前用户 Bearer Token。

### 2.1 管理员：读取 / 更新开关

| 用途 | 方法 | 路径 |
| --- | --- | --- |
| 读取系统设置 | GET | `/api/admin/system-settings/detail` |
| 更新系统设置 | POST | `/api/admin/system-settings/update` |

相关字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `email_verification_enabled` | boolean | 邮箱注册开关，必须为 `true` 才能开启余额预警 |
| `balance_alert_enabled` | boolean | 余额预警总开关 |

更新示例：

```json
{
  "balance_alert_enabled": true
}
```

422 场景：

- `balance_alert_enabled = true` 但 `email_verification_enabled = false`；
- 在 `balance_alert_enabled = true` 时关闭 `email_verification_enabled`。

**前端交互**：邮箱注册关闭时，余额预警开关应置灰或强制关闭，并提示先完成邮箱注册与 SMTP 配置。

### 2.2 用户：读取设置

| 用途 | 方法 | 路径 |
| --- | --- | --- |
| 读取当前用户信息 | GET | `/api/user/info` |

`data` 中新增/相关字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `email` | string \| null | 注册邮箱（邮箱注册或 Google 登录才有） |
| `balance_alert_email` | string \| null | 用户自设的预警收件邮箱；`null` 表示使用注册邮箱 |
| `balance_alert_threshold` | string \| null | 用户阈值，6 位小数；`null` 表示未开启 |

示例：

```json
{
  "id": "...",
  "username": "alice",
  "balance": "12.34",
  "usage": "5.00",
  "email": "alice@example.com",
  "balance_alert_threshold": "5.000000",
  "balance_alert_email": null
}
```

**有效收件人 = `balance_alert_email ?? email`**，前端展示时可按此计算。

### 2.3 用户：更新阈值与收件邮箱

| 用途 | 方法 | 路径 |
| --- | --- | --- |
| 更新余额预警设置 | POST | `/api/user/balance-alert/update` |

请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `threshold` | number / 数字字符串 / `null` | 是 | 大于 0、最多 6 位小数、单位 USD；`null` 表示关闭该用户的余额预警 |
| `email` | string / `null` | 否 | 自定义收件邮箱；省略、`null`、空字符串表示清除自定义邮箱并回退注册邮箱 |

设置阈值并使用注册邮箱：

```json
{
  "threshold": "5.000000",
  "email": null
}
```

设置阈值并使用自定义邮箱：

```json
{
  "threshold": "5.000000",
  "email": "alerts@example.com"
}
```

关闭余额预警：

```json
{
  "threshold": null,
  "email": null
}
```

响应 `data`：

```json
{
  "balance_alert_threshold": "5.000000",
  "balance_alert_email": "alerts@example.com"
}
```

422 场景：

| 场景 | 提示 |
| --- | --- |
| `threshold <= 0` | 请求校验失败（`threshold` 必须大于 0） |
| 邮箱格式不合法 | `邮箱格式不合法` |
| 开启预警，但既没有自定义邮箱也没有注册邮箱 | `当前账号未绑定邮箱，请填写接收余额预警的邮箱` |

邮箱会去除首尾空白并统一为小写。

## 3. UI 改造建议

### 3.1 管理员系统设置页

1. 删除“余额预警阈值”输入项。
2. 保留“余额预警”开关。
3. 当 `email_verification_enabled = false` 时禁用开关，并展示“需先开启邮箱注册验证并完成 SMTP 配置”。
4. 后端返回的 422 文案直接展示。

### 3.2 用户控制台（个人资料 / 账户设置）

新增“余额预警”区块：

| 控件 | 行为 |
| --- | --- |
| 预警阈值输入框 | 数字输入，> 0，最多 6 位小数，单位 USD |
| 收件邮箱输入框 | 可留空；占位文案展示注册邮箱，例如 `留空则发送至 alice@example.com` |
| 开启 / 关闭 | 关闭时提交 `threshold: null` |
| 保存 | 同时提交 `threshold` 与 `email` |

交互规则：

- 账号有注册邮箱：收件邮箱可留空，提示“留空时使用注册邮箱”。
- 账号无注册邮箱：收件邮箱为必填，未填写时不允许开启，并展示后端 422 文案。
- 保存成功后使用响应中的 `balance_alert_threshold`、`balance_alert_email` 刷新表单。
- 用户修改阈值或邮箱后，后端会重置该用户的低余额提醒周期，无需前端额外处理。

## 4. 运行行为（供文案说明）

- 预警在用户产生扣费后懒校验，不轮询。
- 扣费后余额小于等于用户阈值时发送一封提醒邮件；同一低余额周期只发一次。
- 余额充值回升到阈值以上后再次跌破，会重新发送。
- 收件人优先 `balance_alert_email`，否则注册邮箱。
- 管理员开关、邮箱注册开关、用户阈值、可用收件邮箱任一不满足时不会发信。

## 5. 验收清单

- [ ] 管理员设置页不再出现阈值输入框，只有余额预警开关。
- [ ] 邮箱注册未开启时，管理员无法开启余额预警（前端禁用 + 后端 422）。
- [ ] 邮箱注册用户可以只填阈值，保存后按注册邮箱收信。
- [ ] 用户可以填写自定义邮箱，保存后按自定义邮箱收信。
- [ ] 用户清空自定义邮箱后，回退使用注册邮箱。
- [ ] 无注册邮箱的账号不填邮箱时开启失败，并展示 422 文案；填写后可正常开启。
- [ ] 用户可以关闭预警（`threshold: null`），关闭后不再收信。
- [ ] `/api/user/info` 回显 `email`、`balance_alert_email`、`balance_alert_threshold` 三个字段。
