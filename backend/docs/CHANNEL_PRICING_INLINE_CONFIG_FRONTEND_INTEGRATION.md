# 渠道保存缺价当前页配置弹窗前端接入文档

本文只描述一个场景：**保存渠道时，如果渠道里的模型在目标令牌分组还没有定价，前端应在当前页面直接弹出配置弹窗，用户填写后继续完成保存，而不是跳转到定价管理页。**

---

## 1. 背景与目标

### 1.1 现状问题

渠道保存时，后端会检查 `supported_models × token_group_ids` 的定价覆盖情况。若某个模型在某个分组没有定价，接口返回 `422`，此前只有一条提示文案：

```text
模型“claude-fable-5”在令牌分组“3”没有默认定价，请先配置价格
```

用户只能离开渠道表单，去定价管理页手工配置，再回到渠道页重新保存，流程割裂且容易丢失表单内容。

### 1.2 本次目标

```text
点击保存渠道
  ├─ 定价完整 → 正常保存成功
  └─ 存在缺价 → 422 返回结构化缺价明细
       ↓
     当前页面弹出「配置模型价格」弹窗（渠道表单保持不关闭）
       ↓
     用户确认价格 → 前端创建缺失的定价规则
       ↓
     自动重试保存渠道 → 正常保存成功
```

取消弹窗时保留渠道表单内容，不做任何保存。

---

## 2. 涉及接口

| 用途 | 方法 | 路径 | 成功状态码 |
| --- | --- | --- | --- |
| 新建渠道 | POST | `/api/admin/channels/create` | `201` |
| 更新渠道 | POST | `/api/admin/channels/update` | `200` |
| 创建缺失的定价规则 | POST | `/api/admin/pricing-rules/create` | `201` |
| 查询单个模型预设价格（可选） | GET | `/api/admin/pricing-rules/preset` | `200` |

鉴权：管理员 Bearer Token。
请求参数位置：渠道保存与规则创建使用 JSON Body；预设价格查询使用 Query。

---

## 3. 保存渠道

### 3.1 请求字段

`POST /api/admin/channels/create`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `name` | string | 是 | 渠道名称 |
| `base_url` | string | 是 | 上游地址 |
| `api_key` | string | 是 | 上游密钥 |
| `config` | object | 否 | 渠道扩展配置 |
| `supported_models` | string[] | 否 | 渠道支持的公开模型名 |
| `token_group_ids` | integer[] | 否 | 渠道绑定的令牌分组 |
| `model_mapping` | object | 否 | 公开模型名 → 上游模型名 |
| `param_override` | object | 否 | 上游参数覆写 |
| `header_override` | object | 否 | 上游请求头覆写 |
| `priority` | integer | 否 | 路由优先级，默认 `0` |
| `weight` | integer | 否 | 路由权重，默认 `1` |
| `active` | boolean | 否 | 是否启用，默认 `true` |
| `healthy` | boolean | 否 | 是否健康，默认 `true` |

`POST /api/admin/channels/update` 额外要求：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `channel_id` | string(UUID) | 是 | 渠道 ID |
| `api_key` | string \| null | 否 | 留空或 `null` 表示不修改密钥 |

### 3.2 成功响应

```json
{
  "code": 201,
  "message": "OK",
  "data": { "id": "255e0749-87d7-4edc-b0df-e6774c597ca1" },
  "request_id": "..."
}
```

`/channels/update` 的响应结构相同，`code` 为 `200`。

---

## 4. 缺价错误的结构

### 4.1 响应示例

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

### 4.2 `data.unpriced` 字段

每个缺价模型一项；同一模型的多个缺失分组合并在 `token_group_ids` 中。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `model_id` | string | 模型 ID |
| `model_name` | string | 模型名 |
| `token_group_ids` | integer[] | 该模型缺少定价的分组 ID |
| `preset` | object | 该模型的预设价格信息，结构同 `GET /api/admin/pricing-rules/preset` |

### 4.3 `preset` 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `model_id` | string | 模型 ID |
| `model_name` | string | 模型名 |
| `matched` | boolean | 是否命中目录预设价格 |
| `match_type` | string | 名称匹配方式，例如 `exact` |
| `template_id` | string \| null | 模型当前模板，用于拉取价格骨架 |
| `model_type` | string | 模型类型 |
| `currency` | string \| null | 预设币种 |
| `pricing_rules` | array | 预设规则；`matched = false` 时为空 |
| `pricing_modifiers` | array | 预设长上下文加价修正项 |
| `pricing_fields` | string[] | 可用于定价的字段白名单 |
| `requires_pricing_input` | boolean | 是否仍需人工填写单价 |
| `source_url` | string \| null | 预设价格来源 |
| `price_updated_at` | string \| null | 预设价格更新时间 |
| `note` | string \| null | 预设价格备注 |

### 4.4 触发条件

| 情况 | 结果 |
| --- | --- |
| 该模型在该分组已有定价规则 | 保存成功，不进入弹窗 |
| 该分组缺定价，模型命中目录预设 | 后端自动播种预设价格，保存成功，不进入弹窗 |
| 该分组缺定价，模型无目录预设 | 返回 `422`，进入弹窗 |
| 该分组缺定价，目录预设缺少单价 | 返回 `422`，进入弹窗 |

说明：

- 其他 `422` 错误的 `data` 仍为 `null`；只有缺价错误会带 `data.unpriced`。
- 发生缺价错误时整次保存回滚：渠道字段、路由、已补齐的其他模型价格都不会写入。
- 已停用模型、已停用或已删除的令牌分组不参与检查。

---

## 5. 当前页弹窗流程

### 5.1 触发

保存渠道的请求返回 `422`，且 `data.unpriced` 非空时：

- 不关闭渠道表单；
- 不跳转路由；
- 直接打开「配置模型价格」弹窗。

### 5.2 弹窗内容

按 `data.unpriced` 逐项渲染：

```text
模型：claude-fable-5
分组：3
价格：命中预设时预填；未命中时展示模板骨架并要求填写
```

### 5.3 预填规则

| `preset.matched` | 预填方式 |
| --- | --- |
| `true` | 使用 `preset.pricing_rules` 的 `name`、`conditions`、`currency`、`items[].unit_amount` 预填 |
| `false` | 使用 `preset.template_id` 调用 `GET /api/admin/provider-templates/detail?template_id=...`，取其 `default_pricing_rules` 作为骨架，单价留空 |

补充：

- 预设包含多条规则（尺寸档位、分档计费）时，可让用户选择要应用的规则，或逐条展示并全部创建。
- `preset.pricing_fields` 可用于条件字段候选。
- `preset.pricing_modifiers` 是长上下文加价修正项；如需保留预设加价行为，可在规则创建后调用 `POST /api/admin/pricing-modifiers/create`。

---

## 6. 创建缺失定价规则

### 6.1 接口

`POST /api/admin/pricing-rules/create`，成功状态码 `201`。

### 6.2 请求字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `model_id` | string(UUID) | 是 | 模型 ID |
| `token_group_id` | integer | 是 | 令牌分组 ID |
| `name` | string | 是 | 规则名称 |
| `conditions` | array | 否 | 规则条件，默认空数组 |
| `items` | array | 是 | 计费项，至少一项 |
| `items[].label` | string | 是 | 计费项名称 |
| `items[].position` | integer | 是 | 排序位置，从 0 开始 |
| `items[].kind` | string | 是 | 计费项类型，例如 `input_text_tokens` |
| `items[].source_fields` | string[] | 否 | 计量来源字段 |
| `items[].estimate_config` | object | 否 | 估算参数 |
| `items[].free_quantity` | integer | 否 | 免费额度 |
| `items[].unit_amount` | string \| null | 条件必填 | 单价；不可计价的输入视频时长项可为 `null` |
| `items[].active` | boolean | 否 | 默认 `true` |
| `currency` | string | 否 | 币种，默认 `CNY` |
| `active` | boolean | 否 | 默认 `true` |

说明：

- 优先级由服务端按「模型 + 分组」自动分配，请求不需要传 `priority`。
- 预设包含多条规则时，逐条调用本接口创建。
- 每个缺失的「模型 + 分组」组合都要创建，直到 `data.unpriced` 中所有组合都有规则。

### 6.3 请求示例

```json
{
  "model_id": "6c8273a8-f33f-47fc-8f47-ccf7c87fa20c",
  "token_group_id": 3,
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
  ],
  "active": true
}
```

### 6.4 响应示例

```json
{
  "code": 201,
  "message": "OK",
  "data": { "id": "..." },
  "request_id": "..."
}
```

---

## 7. 自动重试保存

所有缺失规则创建成功后：

1. 使用**原来的渠道表单数据**重新调用 `/channels/create` 或 `/channels/update`；
2. 后端检测到这些分组已有定价，保存成功；
3. 关闭弹窗与渠道表单，刷新列表。

如果重试后仍返回 `422` 且 `data.unpriced` 非空，说明还有未处理的模型/分组（例如用户只填了部分），应使用新的 `data.unpriced` 更新弹窗内容，而不是关闭弹窗。

保存同一渠道是幂等的：已补齐的分组不会重复生成规则。

---

## 8. 前端伪代码

```text
async function saveChannel(form) {
  const result = await post(channelPath, form);

  if (result.code === 422 && result.data?.unpriced?.length) {
    const filled = await openPricingDialog(result.data.unpriced);
    if (!filled) return;              // 用户取消，保留表单

    for (const group of filled) {
      for (const rule of group.rules) {
        await post("/api/admin/pricing-rules/create", {
          model_id: group.model_id,
          token_group_id: group.token_group_id,
          ...rule,
        });
      }
    }

    return saveChannel(form);         // 自动重试
  }

  if (result.code !== 200 && result.code !== 201) {
    throw new Error(result.message);
  }
}
```

弹窗内部：

```text
for each item of unpriced:
  if item.preset.matched:
    rules = item.preset.pricing_rules        // 直接预填单价
  else:
    template = get("/api/admin/provider-templates/detail", { template_id: item.preset.template_id })
    rules = template.default_pricing_rules   // 单价留空，要求用户填写
  render(item.model_name, item.token_group_ids, rules)
```

---

## 9. 边界与注意事项

- **不会复制其他分组的价格**：缺失分组只使用目录预设价或用户本次填写的价格。
- **预设按模型名匹配**：自定义改名的模型可能没有预设，此时弹窗必须要求用户填写。
- **预设缺少单价**：同样进入弹窗，不允许静默写入不完整价格。
- **移除分组不删价格**：从渠道移除某个分组不会删除该分组已有定价规则。
- **整次保存回滚**：弹窗出现时渠道尚未保存，不存在半保存状态。
- **批量创建复用模型**：`POST /api/admin/models/batch-create` 复用已存在模型但无法补种价格时，也会返回同结构的 `data.unpriced`。
- **单模型创建不受影响**：`POST /api/admin/models/create` 同名仍返回「模型名称已存在」。

---

## 10. 相关文档

- `CHANNEL_PRICING_SEED_FRONTEND_INTEGRATION.md`：渠道保存与批量创建的定价播种完整说明
- `ADMIN_CONSOLE_FRONTEND_INTEGRATION.md`：管理台接口总览，B7/B8 节
