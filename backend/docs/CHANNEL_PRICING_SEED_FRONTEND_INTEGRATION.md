# 渠道分组定价自动播种前端接入文档

本文说明本次改动后，管理台在「保存渠道」与「批量创建模型」两个流程中的定价播种行为，供前端同事对接。

本次改动只涉及后端，接口路径与既有字段不变，变化集中在：

1. 保存渠道时，自动为模型补齐渠道所绑定令牌分组的预设定价规则；
2. 批量创建遇到同名模型时复用已有模型，不再报「模型名称已存在」，也不再要求先删模型；
3. 复用已存在模型且本次无法补种价格时，接口返回 `422`，前端需提示用户先填写价格。

---

## 1. 鉴权与统一响应

- 鉴权：管理员 Bearer Token，与其他 `/api/admin/**` 接口一致。
- 成功响应统一信封：

```json
{
  "code": 200,
  "message": "OK",
  "data": {},
  "request_id": "..."
}
```

- 失败响应统一信封（本文只新增 `422` 场景）：

```json
{
  "code": 422,
  "message": "模型“claude-fable-5”在令牌分组“3”没有默认定价，请先配置价格",
  "data": null,
  "request_id": "..."
}
```

> `message` 已按请求语言返回。缺价错误会在 `data.unpriced` 中返回结构化明细，见 2.5；其他 `422` 的 `data` 仍为 `null`。前端按 HTTP 状态码 `422` 判断即可，不需要解析 `message`。

---

## 2. 保存渠道

### 2.1 接口

| 用途 | 方法 | 路径 | 成功状态码 |
| --- | --- | --- | --- |
| 新建渠道 | POST | `/api/admin/channels/create` | `201` |
| 更新渠道 | POST | `/api/admin/channels/update` | `200` |

请求参数位置：JSON Body。

### 2.2 请求字段（与现有接口一致）

`POST /api/admin/channels/create`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `name` | string | 是 | 渠道名称，1–128 字符 |
| `base_url` | string | 是 | 上游地址 |
| `api_key` | string | 是 | 上游密钥 |
| `config` | object | 否 | 渠道扩展配置 |
| `supported_models` | string[] | 否 | 渠道支持的公开模型名 |
| `token_group_ids` | integer[] | 否 | 渠道绑定的令牌分组；本次改动的定价播种目标 |
| `model_mapping` | object | 否 | 公开模型名 → 上游模型名 |
| `param_override` | object | 否 | 上游请求参数覆写 |
| `header_override` | object | 否 | 上游请求头覆写 |
| `priority` | integer | 否 | 路由优先级，默认 `0` |
| `weight` | integer | 否 | 路由权重，默认 `1`，最小 `1` |
| `active` | boolean | 否 | 是否启用，默认 `true` |
| `healthy` | boolean | 否 | 是否健康，默认 `true` |

`POST /api/admin/channels/update` 额外要求：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `channel_id` | string(UUID) | 是 | 渠道 ID |
| `api_key` | string \| null | 否 | 留空或 `null` 表示不修改密钥 |

### 2.3 新增的定价播种行为

保存渠道时，后端会对 `supported_models` × `token_group_ids` 的每一组绑定做检查：

| 情况 | 后端行为 |
| --- | --- |
| 该模型在该分组已有定价规则 | 不处理 |
| 该分组没有定价规则，模型名命中目录预设价格 | 按目录预设价格生成一套定价规则 |
| 该分组没有定价规则，模型名没有目录预设 | 不写库，返回 `422` 提示先填写价格 |
| 该分组没有定价规则，预设价格缺少单价 | 不写库，返回 `422` 提示先填写价格 |

说明：

- **不会复制其他分组的价格**。同一模型不同分组各自使用目录预设价，避免把人工调整过的价格隐式带到其他分组。
- 已有分组的定价规则不会被修改或删除。
- 从渠道移除某个分组，不会删除该分组已有的定价规则（价格可能被其他渠道共用）。
- 只有启用状态的模型参与检查；已停用模型不会阻断保存。
- 重复保存同一渠道是幂等的：已补齐的分组不会重复生成规则。

### 2.4 响应示例

`POST /api/admin/channels/create`（`201`）：

```json
{
  "code": 201,
  "message": "OK",
  "data": { "id": "255e0749-87d7-4edc-b0df-e6774c597ca1" },
  "request_id": "..."
}
```

`POST /api/admin/channels/update`（`200`）：

```json
{
  "code": 200,
  "message": "OK",
  "data": { "id": "255e0749-87d7-4edc-b0df-e6774c597ca1" },
  "request_id": "..."
}
```

### 2.5 缺少预设价格时的错误

```json
{
  "code": 422,
  "message": "模型“claude-fable-5”在令牌分组“3”没有默认定价，请先配置价格",
  "data": {
    "unpriced": [
      {
        "model_id": "6c8273a8-f33f-47fc-8f47-ccf7c87fa20c",
        "model_name": "claude-fable-5",
        "token_group_ids": [3],
        "preset": {
          "model_id": "6c8273a8-f33f-47fc-8f47-ccf7c87fa20c",
          "model_name": "claude-fable-5",
          "matched": false,
          "match_type": "none",
          "template_id": "anthropic_messages",
          "model_type": "text",
          "currency": null,
          "pricing_rules": [],
          "pricing_modifiers": [],
          "pricing_fields": ["input_tokens", "output_tokens"],
          "requires_pricing_input": true,
          "source_url": null,
          "price_updated_at": null,
          "note": null
        }
      }
    ]
  },
  "request_id": "..."
}
```

- `data.unpriced` 每个模型一项，`token_group_ids` 为该模型缺少定价的分组。
- `preset` 与 `GET /api/admin/pricing-rules/preset` 返回结构一致：
  - `preset.matched = true` 时，可直接用 `preset.pricing_rules` 预填价格；
  - `preset.matched = false` 时，用 `preset.template_id` 调 `GET /api/admin/provider-templates/detail` 取模板骨架，单价留空由用户填写。
- `message` 仍会把所有模型与分组合并成一条，便于直接提示。
- 发生该错误时，本次渠道保存整体回滚：渠道字段、路由、已补齐的其他模型价格都不会写入。
- 用户配置好价格后重新保存渠道即可。

### 2.6 请求示例

```json
{
  "name": "zzshu",
  "base_url": "https://example.com/v1",
  "api_key": "sk-xxx",
  "supported_models": ["claude-fable-5", "claude-opus-4-8"],
  "token_group_ids": [3],
  "model_mapping": { "claude-fable-5": "claude-fable-5-upstream" },
  "priority": 0,
  "weight": 1,
  "active": true,
  "healthy": true
}
```

---

## 3. 批量创建模型

### 3.1 接口

| 用途 | 方法 | 路径 | 成功状态码 |
| --- | --- | --- | --- |
| 批量创建模型 | POST | `/api/admin/models/batch-create` | `201` |

请求参数位置：JSON Body。

### 3.2 行为变化：同名模型复用

此前 `items[].name` 与已存在模型同名时，整批返回 `422`（`模型“xxx”创建失败：模型名称已存在`），渠道流程只能先删除模型再重建，导致该模型在所有分组下的价格规则被一并归档。

现在改为：

| 情况 | 后端行为 |
| --- | --- |
| 模型名不存在 | 新建模型，并按 `token_group_ids` 播种预设价格 |
| 模型名已存在 | 复用该模型；只为本次 `token_group_ids` 中缺少定价规则的分组补种价格 |
| 复用模型 + 该行提交了 `pricing_rules` | 缺失分组使用提交的价格 |
| 复用模型 + 未提交 `pricing_rules` + 命中目录预设 | 缺失分组使用目录预设价格 |
| 复用模型 + 无目录预设或预设缺少单价 | 返回 `422`，提示先填写价格 |

说明：

- 复用模型时**不会重建模型**，不会修改模型名称、模板、类型等字段。
- 已有分组的定价不受影响。
- **不会复制其他分组的价格**。
- 同一批内 `items[].name` 仍然不能重复。
- 整批仍是原子操作：任一模型校验失败，整批回滚。
- 新建模型（名称不存在）的校验规则不变：指定 Provider 但未命中预设且未提交 `pricing_rules` 时，仍返回原有缺价文案。

### 3.3 请求字段（与现有接口一致）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `provider_id` | string | 否 | 批量公共端点，单条可覆盖 |
| `token_group_ids` | integer[] | 否 | 默认定价规则的播种分组；留空或空数组表示系统默认分组 |
| `items` | object[] | 是 | 1–200 个模型 |
| `items[].name` | string | 是 | 模型名 |
| `items[].description` | string | 否 | 模型介绍 |
| `items[].provider_id` | string | 否 | 单模型端点覆盖 |
| `items[].template_id` | string | 否 | 单模型模板覆盖 |
| `items[].model_type` | string | 否 | 单模型类型覆盖 |
| `items[].pricing_rules` | array | 条件必填 | 无预设价格时必填 |
| `items[].default_concurrency_limit` | integer | 否 | 默认并发上限 |
| `items[].active` | boolean | 否 | 默认 `true` |

### 3.4 响应示例

```json
{
  "code": 201,
  "message": "OK",
  "data": {
    "items": [
      { "id": "...", "name": "claude-fable-5", "pricing_configured": true },
      { "id": "...", "name": "my-relay-model", "pricing_configured": true }
    ]
  },
  "request_id": "..."
}
```

- 复用已存在模型时，`id` 为该模型原有 ID。
- `pricing_configured` 表示该模型当前是否已有带齐单价的定价方案。

### 3.5 请求示例

```json
{
  "provider_id": "openai",
  "token_group_ids": [3],
  "items": [
    { "name": "claude-fable-5" },
    {
      "name": "my-relay-model",
      "pricing_rules": [
        {
          "name": "按 token 计费",
          "conditions": [],
          "currency": "USD",
          "items": [
            {
              "label": "输入 token",
              "position": 0,
              "kind": "input_text_tokens",
              "source_fields": [],
              "free_quantity": 0,
              "unit_amount": "2.500000"
            },
            {
              "label": "输出 token",
              "position": 1,
              "kind": "output_text_tokens",
              "source_fields": [],
              "free_quantity": 0,
              "unit_amount": "10.000000"
            }
          ]
        }
      ]
    }
  ]
}
```

### 3.6 缺少预设价格时的错误

```json
{
  "code": 422,
  "message": "模型“my-relay-model”在令牌分组“3”没有默认定价，请先配置价格",
  "data": {
    "unpriced": [
      {
        "model_id": "...",
        "model_name": "my-relay-model",
        "token_group_ids": [3],
        "preset": { "...": "结构同 2.5 / GET /pricing-rules/preset" }
      }
    ]
  },
  "request_id": "..."
}
```

复用已存在模型但无法补种价格时，`data.unpriced` 的结构与渠道保存一致，前端可在批量配置弹窗内直接展开价格编辑器补填。

---

## 4. 查询模型预设价格（手动创建计费规则）

### 4.1 接口

| 用途 | 方法 | 路径 |
| --- | --- | --- |
| 查询模型预设价格 | GET | `/api/admin/pricing-rules/preset` |

- 鉴权：管理员 Bearer Token。
- 参数位置：Query。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `model_id` | string(UUID) | 是 | 模型 ID |

### 4.2 行为说明

- 按模型名匹配目录预设价格，并按模型当前模板的计费项口径覆盖单价。
- 命中预设时 `matched = true`，`pricing_rules` 为可直接套用的完整规则，包含 `name`、`conditions`、`currency` 与各计费项的 `unit_amount`。
- 未命中预设时 `matched = false`、`pricing_rules = []`、`requires_pricing_input = true`，前端应保留模板骨架并要求管理员填写单价。
- 该接口只读，不会创建或修改任何定价规则。

### 4.3 响应字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `model_id` | string | 模型 ID |
| `model_name` | string | 模型名 |
| `matched` | boolean | 是否命中目录预设价格 |
| `match_type` | string | 名称匹配方式，例如 `exact` |
| `template_id` | string \| null | 模型当前模板 |
| `model_type` | string | 模型类型 |
| `currency` | string \| null | 预设币种；未命中时为 `null` |
| `pricing_rules` | array | 预设定价规则；形状与创建计费规则的 `rule` 一致 |
| `pricing_modifiers` | array | 预设长上下文加价修正项；如需使用，可再调用 `POST /api/admin/pricing-modifiers/create` |
| `pricing_fields` | string[] | 该模型可用于定价的字段白名单 |
| `requires_pricing_input` | boolean | 是否仍需要人工填写单价 |
| `source_url` | string \| null | 预设价格来源 |
| `price_updated_at` | string \| null | 预设价格更新时间 |
| `note` | string \| null | 预设价格备注 |

### 4.4 响应示例

命中预设：

```json
{
  "code": 200,
  "message": "OK",
  "data": {
    "model_id": "6c8273a8-f33f-47fc-8f47-ccf7c87fa20c",
    "model_name": "claude-fable-5",
    "matched": true,
    "match_type": "exact",
    "template_id": "anthropic_messages",
    "model_type": "text",
    "currency": "USD",
    "pricing_rules": [
      {
        "name": "按 token 计费",
        "conditions": [],
        "currency": "USD",
        "items": [
          {
            "label": "输入 token",
            "position": 0,
            "kind": "input_text_tokens",
            "source_fields": [],
            "free_quantity": 0,
            "unit_amount": "2.500000"
          },
          {
            "label": "输出 token",
            "position": 1,
            "kind": "output_text_tokens",
            "source_fields": [],
            "free_quantity": 0,
            "unit_amount": "10.000000"
          }
        ]
      }
    ],
    "pricing_modifiers": [],
    "pricing_fields": ["input_tokens", "output_tokens"],
    "requires_pricing_input": false,
    "source_url": "https://example.com/pricing",
    "price_updated_at": "2026-10-20T00:00:00Z",
    "note": null
  },
  "request_id": "..."
}
```

未命中预设：

```json
{
  "code": 200,
  "message": "OK",
  "data": {
    "model_id": "...",
    "model_name": "my-relay-model",
    "matched": false,
    "match_type": "none",
    "template_id": "openai_text",
    "model_type": "text",
    "currency": null,
    "pricing_rules": [],
    "pricing_modifiers": [],
    "pricing_fields": ["input_tokens", "output_tokens"],
    "requires_pricing_input": true,
    "source_url": null,
    "price_updated_at": null,
    "note": null
  },
  "request_id": "..."
}
```

### 4.5 前端使用建议

1. 在新建计费规则弹窗中，模型切换后调用该接口。
2. `matched = true` 时，用返回的第一条 `pricing_rules` 预填表单的 `name`、`conditions`、`currency` 与 `items[].unit_amount`，管理员可再调整后保存。
3. 返回多条规则（尺寸档位、分档计费）时，可让管理员选择要应用的规则，或沿用当前交互只预填第一条。
4. `matched = false` 时，保持现有模板骨架，单价留空并要求管理员填写。
5. 保存仍走现有 `POST /api/admin/pricing-rules/create`，本次不改变该接口的请求结构。

## 5. 前端交互建议

### 5.1 保存渠道

推荐在当前页面直接完成配置，不跳转到定价管理页：

1. 保存失败且状态码为 `422`、`data.unpriced` 非空时，保持渠道表单不关闭，直接打开「配置模型价格」弹窗。
2. 弹窗按 `data.unpriced` 逐项展示 `model_name` 与缺失的 `token_group_ids`：
   - `preset.matched = true`：用 `preset.pricing_rules` 预填名称、条件、币种与单价；
   - `preset.matched = false`：用 `preset.template_id` 拉取模板骨架，单价留空，要求用户填写。
3. 用户确认后，对每个模型/分组调用 `POST /api/admin/pricing-rules/create` 创建缺失规则；预设包含多条规则时逐条创建。需要长上下文修正项时再调用 `POST /api/admin/pricing-modifiers/create`。
4. 全部创建成功后，自动重新调用当前渠道保存接口；此时后端会认为这些分组已有定价，正常保存成功。
5. 用户取消弹窗时，保留渠道表单内容，不做任何保存。

> 也可以直接复用 `GET /api/admin/pricing-rules/preset` 获取单个模型的预设价格，但缺价错误的 `data.unpriced` 已包含同样的 `preset`，可直接使用，减少一次请求。
>
> 该“当前页弹窗配置并重试保存”流程的完整独立说明见 `CHANNEL_PRICING_INLINE_CONFIG_FRONTEND_INTEGRATION.md`。

### 5.2 批量创建

1. 批量预览中 `requires_pricing_input = true` 的行，仍需在提交前填写完整价格。
2. 若提交后收到 `422` 缺价提示，说明该模型没有目录预设价格且本次未提交完整 `pricing_rules`，应引导用户展开价格编辑器补填。
3. 同名模型现在会复用，不再需要「先删除模型再创建」；前端不应再以「模型名称已存在」作为引导删除模型的依据。

### 5.3 手动创建计费规则

1. 在定价规则新建弹窗中，模型切换后调用 `GET /api/admin/pricing-rules/preset`。
2. `matched = true` 时自动套用返回的预设价格；`matched = false` 时保留模板骨架并要求填写单价。

### 5.4 展示建议

- 渠道详情中可继续按 `token_group_ids` 展示分组；本次改动不会新增字段。
- 模型定价仍以 `(模型, 令牌分组)` 为维度，不从渠道维度覆盖价格。

---

## 6. 兼容性说明

- 渠道与批量创建接口的路径、请求字段、成功响应字段均未变化。
- 新增只读接口 `GET /api/admin/pricing-rules/preset`。
- 保存渠道新增了一次定价检查，可能返回此前不会出现的 `422` 缺价错误。
- 单模型创建 `POST /api/admin/models/create` 行为不变：同名仍返回「模型名称已存在」。
- 已停用模型、已停用或已被删除的令牌分组不参与渠道保存时的定价播种。
