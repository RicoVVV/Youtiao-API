# 邀请返利（Affiliate）前端接入文档

本文档描述一期邀请返利能力：邀请链接 / 邀请码绑定、被邀请人注册赠送额度、充值或会员订单产生返利、返利转入余额，以及管理员只读查询接口。

- 所有金额单位为 USD，响应中为固定 6 位小数的字符串，例如 `"12.500000"`。
- 返利比例字段为百分比字符串，例如 `"5.00"` 表示 5%。
- 业务接口统一返回 `{ code, message, data, request_id }`，本文只描述 `data`。

## 一、鉴权

用户接口：

```
Authorization: Bearer {access_token}
```

管理员接口同上，且账号必须具备管理员角色。

## 二、注册与登录绑定

### 2.1 邀请链接

邀请链接由后端在 `GET /api/affiliate/detail` 中返回：

```
{server_url}/register?aff={aff_code}
```

前端进入注册页时读取 `aff` 或 `aff_code` Query 参数，保存并在注册时作为 `aff_code` 提交。邀请码输入框也提交同一字段。

### 2.2 邮箱/密码注册

`POST /api/auth/register`

新增可选 Body 字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `aff_code` | string | 否 | 邀请返利码，最大 32 字符，大小写不敏感 |

示例：

```json
{
  "username": "alice",
  "password": "secret-123",
  "email": "alice@example.com",
  "verification_code": "123456",
  "aff_code": "ABCD2345WXYZ"
}
```

规则：

- 邀请返利总开关关闭时，`aff_code` 被静默忽略，不影响注册。
- 总开关开启且 `aff_code` 非空时，邀请码无效、格式错误、邀请自己或重复绑定都会返回 `422`，且**不会创建账号**。
- 邀请码会在邮箱验证码被消费前预校验；邀请码无效时邮箱验证码仍然有效，可直接修正后重试。
- 邀请关系建立成功且管理员配置了注册赠送额度时，系统会在注册事务内给**新注册用户**的钱包入账一笔赠送余额，余额明细类型为 `signup_bonus`；赠送额度为 0 时不会入账。赠送额度只在注册时发放一次，重复绑定或后续登录不会重复发放。

### 2.3 Google 首次登录

`POST /api/auth/google/login`

新增可选 Body 字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `aff_code` | string | 否 | 仅在本次登录首次创建本地账号时生效 |

已有 Google 账号再次登录时忽略该字段。首次创建账号并成功绑定邀请关系时，与邮箱注册一致发放注册赠送额度。

## 三、公开系统设置

`GET /api/system-settings/detail`

新增字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `affiliate_enabled` | boolean | 是否展示邀请返利入口和注册邀请码输入框 |
| `affiliate_signup_bonus` | string | 邀请码注册赠送余额（USD），固定 6 位小数；为 `"0.000000"` 时表示不赠送，注册页可据此展示赠送文案 |

## 四、用户接口

### 4.1 查询邀请详情

`GET /api/affiliate/detail`

无 Query 参数。首次访问会懒创建当前用户的邀请档案。

响应 `data`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `enabled` | boolean | 邀请返利总开关 |
| `aff_code` | string | 当前用户邀请码 |
| `invite_url` | string | 邀请链接；站点未配置公开地址时为相对路径 |
| `effective_rebate_rate_percent` | string | 当前用户作为邀请人的有效比例 |
| `aff_count` | integer | 已绑定被邀请人数量 |
| `available_quota` | string | 可转入余额的返利额度 |
| `frozen_quota` | string | 冻结中的返利额度 |
| `history_quota` | string | 累计返利总额 |
| `signup_bonus` | string | 当前配置的邀请注册赠送余额（USD）；用于邀请页展示被邀请人可获得的赠送额度 |
| `invitees` | array | 最近 20 个被邀请人摘要 |

`invitees[]`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `user_id` | string(uuid) | 被邀请人 ID |
| `username` | string | 脱敏后的用户名 |
| `created_at` | datetime | 绑定时间 |
| `total_rebate` | string | 该被邀请人累计贡献的返利 |

### 4.2 被邀请人列表

`GET /api/affiliate/invitees/list`

Query：

| 参数 | 类型 | 说明 |
|---|---|---|
| `page` | integer | 从 1 开始，默认 1 |
| `page_size` | integer | 默认 20，最大 100 |

响应：

```json
{
  "items": [
    {
      "user_id": "uuid",
      "username": "a***",
      "created_at": "2026-10-26T10:00:00+08:00",
      "total_rebate": "2.000000"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### 4.3 返利流水

`GET /api/affiliate/records/list`

Query 同 4.2。

`items[]`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string(uuid) | 流水 ID |
| `action` | string | `accrue` 返利产生，`transfer` 转入余额 |
| `amount` | string | 金额 |
| `source_username` | string \| null | 脱敏后的被邀请人用户名；`transfer` 为空 |
| `order_no` | string \| null | 来源充值/会员订单号；`transfer` 为空 |
| `created_at` | datetime | 流水时间 |

### 4.4 转入余额

`POST /api/affiliate/quota/transfer`

无 Body。

成功响应：

```json
{
  "transferred_quota": "10.000000",
  "balance": "30.000000"
}
```

规则：

- 每次转入全部可用返利额度；冻结中的额度不会转入。
- 转入前会先解冻已到期返利。
- 可用额度为 0 时返回 `422`。
- 转入会在余额明细中生成一条 `affiliate_rebate` 类型记录。

## 五、管理员接口

所有接口需要管理员权限，均为只读。

### 5.1 返利产生流水

`GET /api/admin/affiliates/records/accrue/list`

Query：`page`、`page_size`。

`items[]`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string(uuid) | 流水 ID |
| `inviter_id` | string(uuid) | 邀请人 |
| `inviter_username` | string | 邀请人用户名 |
| `invitee_id` | string(uuid) \| null | 被邀请人；账号删除后为空 |
| `invitee_username` | string \| null | 被邀请人用户名 |
| `order_no` | string \| null | 来源订单号 |
| `order_amount` | string \| null | 订单金额 |
| `rebate_amount` | string | 返利金额 |
| `created_at` | datetime | 产生时间 |

### 5.2 返利转出流水

`GET /api/admin/affiliates/records/transfer/list`

Query：`page`、`page_size`。

`items[]`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string(uuid) | 流水 ID |
| `user_id` | string(uuid) | 转出用户 |
| `username` | string | 用户名 |
| `amount` | string | 转出金额 |
| `balance_after` | string \| null | 转账后钱包余额 |
| `available_quota_after` | string \| null | 转账后可用返利额度 |
| `frozen_quota_after` | string \| null | 转账后冻结额度 |
| `history_quota_after` | string \| null | 转账后累计返利 |
| `created_at` | datetime | 转出时间 |

### 5.3 邀请用户列表

`GET /api/admin/affiliates/users/list`

Query：

| 参数 | 类型 | 说明 |
|---|---|---|
| `page` | integer | 默认 1 |
| `page_size` | integer | 默认 20，最大 100 |
| `search` | string | 按用户名或邮箱模糊搜索，最大 128 字符 |

`items[]`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `user_id` | string(uuid) | 用户 ID |
| `username` | string | 用户名 |
| `aff_code` | string | 邀请码 |
| `inviter_id` | string(uuid) \| null | 上级 |
| `inviter_username` | string \| null | 上级用户名 |
| `aff_count` | integer | 绑定人数 |
| `available_quota` / `frozen_quota` / `history_quota` | string | 三池额度 |
| `created_at` | datetime | 档案创建时间 |

### 5.4 单用户概览

`GET /api/admin/affiliates/users/detail?user_id={uuid}`

`data`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `user_id` | string(uuid) | 用户 ID |
| `username` | string | 用户名 |
| `aff_code` | string | 邀请码 |
| `inviter_id` | string(uuid) \| null | 上级 |
| `inviter_username` | string \| null | 上级用户名 |
| `rebate_rate_percent` | string | 有效返利比例 |
| `rebate_rate_custom` | boolean | 是否使用专属比例 |
| `invited_count` | integer | 绑定人数 |
| `rebated_invitee_count` | integer | 实际产生过返利的被邀请人数 |
| `available_quota` / `frozen_quota` / `history_quota` | string | 三池额度 |
| `created_at` | datetime | 档案创建时间 |

## 六、管理端系统设置

`POST /api/admin/system-settings/update`

新增可选项：

| 字段 | 类型 | 约束 | 默认 | 说明 |
|---|---|---|---|---|
| `affiliate_enabled` | boolean | — | `false` | 邀请返利总开关，默认关闭，由管理员显式开启 |
| `affiliate_rebate_rate_percent` | number | 0–100 | `5.00` | 全局返利比例（百分比） |
| `affiliate_rebate_freeze_hours` | integer | 0–720 | `5` | 返利冻结小时数，0 表示不冻结 |
| `affiliate_rebate_duration_days` | integer | 0–3650 | `0` | 被邀请人注册后产生返利的有效天数，0 表示永久 |
| `affiliate_rebate_per_invitee_cap` | number | ≥ 0 | `0` | 单个被邀请人的返利上限（USD），0 表示无上限 |
| `affiliate_signup_bonus` | number | 0–1000000 | `0` | 通过邀请码或邀请链接注册的新用户赠送余额（USD），0 表示不赠送 |

一期暂未提供“管理员充值参与返利”开关，管理员充值不会产生返利；如后台页面需要该开关，需二期新增字段与对应行为。

`GET /api/admin/system-settings/detail` 会返回上述字段。其中 `affiliate_rebate_rate_percent`、`affiliate_rebate_per_invitee_cap` 与 `affiliate_signup_bonus` 按统一金额格式以字符串返回，例如 `"5.00"`、`"0"`；更新时既可传数字也可传数字字符串。

## 七、错误码

| HTTP | 场景 | 说明 |
|---|---|---|
| 401 | 未登录或令牌失效 | 统一鉴权错误 |
| 403 | 非管理员访问管理端；`affiliate` 侧边栏模块被关闭 | 功能不可用 |
| 404 | 邀请档案不存在（管理端按用户查询） | 用户从未建立邀请档案 |
| 422 | 邀请码格式错误 / 无效 / 重复绑定 / 无可用返利额度 | 返回统一校验错误 |

常见业务码：

| code | 说明 |
|---|---|
| `affiliate.code_invalid` | 邀请码无效或格式错误 |
| `affiliate.already_bound` | 已绑定邀请人，不能重复绑定 |
| `affiliate.quota_empty` | 暂无可转入的邀请返利 |

## 八、行为说明

1. 邀请关系只在注册或 Google 首次登录时建立，建立后不可更换。
2. 一期返利只由两类订单触发：钱包充值订单、会员购买订单。兑换码核销、管理员加余额不产生返利。
3. 返利基数取订单的入账金额 `amount`，会员赠送余额不计入。
4. 同一订单只会产生一笔返利，重复支付回调不会重复入账。
5. 返利先进入独立额度池，不会自动增加可消费余额；用户需调用 4.4 转入余额。
6. 冻结期大于 0 时，返利先进入冻结池；查询详情或转入余额时会把已到期部分惰性解冻。
7. 邀请人被注销后，其邀请码不再可用，也不会继续产生返利；邀请人恢复后恢复可用。被邀请人被注销时，其邀请人的邀请人数会回退，恢复时补回。
8. 邀请返利入口对应侧边栏模块 key `affiliate`，管理员可在侧边栏配置中隐藏。
9. 注册赠送额度只发放给通过邀请码注册的新用户，直接入账钱包余额，可在钱包余额明细中看到 `signup_bonus` 类型记录；该赠送不进入返利额度池，也不触发邀请人返利。
10. 注册赠送额度仅当邀请返利总开关开启且邀请关系绑定成功时发放；修改后台配置只影响之后注册的新用户，不会追溯补发。
