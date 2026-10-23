# 渠道批量拉取模型与创建改造说明（前端）

本文是给前端同事的**改造任务说明**，用于把「渠道拉取上游模型 → 创建本地模型」从单模型流程升级为批量流程。

接口的完整说明见 [ADMIN_CONSOLE_FRONTEND_INTEGRATION.md](./ADMIN_CONSOLE_FRONTEND_INTEGRATION.md) 的 Part B。
本文只描述本次需要前端改造的内容。

## 1. 本次改动概览

| 问题 | 改造结果 |
| --- | --- |
| 填入模型时要求配置令牌分组 | 渠道流程不强制分组；批量创建接口可选传 `token_group_ids` 指定定价播种分组，不传时使用系统默认分组 |
| 模型只能单个选择、单个创建 | 新增**批量预览**与**批量创建**接口，支持多选后统一配置 |
| Provider 概念不直观 | API 字段仍为 `provider_id`，但界面统一显示为 **端点（Endpoint）** |
| 批量配置后价格展示不明确 | 批量预览逐模型返回预设价格摘要、是否需填写、失败原因，前端按行展示 |

统一响应信封：

```json
{ "code": 200, "message": "OK", "data": {}, "request_id": "..." }
```

所有接口均为管理员接口，需要管理员 Bearer Token。业务校验失败返回 HTTP 422。

## 2. 端点选择

| 用途 | 方法 | 路径 |
| --- | --- | --- |
| 查询可选端点 | GET | `/api/admin/models/providers/list` |

> 接口路径与字段名保留 `providers` / `provider_id` 是为了与现有模型管理接口一致，但**界面文案必须显示为“端点”**，例如“选择端点”“端点不支持该模型类型”。

响应示例：

```json
{
  "items": [
    {
      "provider_id": "openai",
      "provider_name": "OpenAI",
      "provider_logo_url": "https://...",
      "model_types": ["image", "text", "video"]
    }
  ]
}
```

前端使用 `provider_id` 作为选项值，用 `provider_name` 和 `model_types` 渲染名称与可选模型类型。

## 3. 批量预览

多选模型后调用，用于生成批量配置表格。

| 用途 | 方法 | 路径 |
| --- | --- | --- |
| 批量预览模板与价格 | POST | `/api/admin/models/batch-match-preview` |

### 请求

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `model_names` | string[] | 是 | 所选上游模型名，1–200 个；重复名称只保留首次出现，空名称会被忽略 |
| `provider_id` | string | 否 | 批量选择的端点，应用到所有模型 |
| `model_type` | string | 否 | 统一指定 `text` / `image` / `video`；不传则按模型名逐个推断 |

```json
{
  "model_names": ["gpt-4o", "my-relay-model"],
  "provider_id": "openai"
}
```

### 响应

`items` 与请求顺序一致，每项字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `model_name` | string | 模型名 |
| `matched` | boolean | 是否命中该端点的预设定价 |
| `requires_pricing_input` | boolean | 是否需要人工填写价格 |
| `match_type` | string | `exact`（命中预设）/ `provider_fallback`（使用端点模板兜底）/ `none` |
| `template_id` | string \| null | 将使用的模型模板 |
| `model_type` | string \| null | 解析出的模型类型 |
| `provider_id` | string \| null | 端点标识 |
| `provider_name` | string \| null | 端点展示名 |
| `provider_logo_url` | string \| null | 端点图标 |
| `pricing_summary` | array | 价格摘要；**仅命中预设时非空** |
| `pricing_rules` | array | 完整定价规则骨架；未命中时作为价格编辑器初始值 |
| `pricing_modifiers` | array | 预设的长上下文加价规则 |
| `pricing_fields` | string[] | 定价可引用字段白名单 |
| `input_schema` | object \| null | 模型请求契约 |
| `error` | string \| null | 该模型无法用当前端点创建时的原因 |

`pricing_summary` 单项：

```json
{ "kind": "input_text_tokens", "label": "输入 token", "unit_amount": "2.500000", "currency": "USD" }
```

`summary`：

```json
{ "total": 2, "preset_matched": 1, "requires_pricing_input": 1, "failed": 0 }
```

说明：

- `pricing_summary` 只在 `matched = true` 时返回，避免把模板兜底价误展示成真实价格。
- `requires_pricing_input = true` 时，前端应展示价格编辑入口，初始值取 `pricing_rules`。
- `error != null` 表示该行无法创建（例如端点没有对应的模型类型模板），应禁用该行并展示错误。

## 4. 批量创建

| 用途 | 方法 | 路径 |
| --- | --- | --- |
| 批量创建模型 | POST | `/api/admin/models/batch-create` |

### 请求

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `provider_id` | string | 否 | 批量公共端点；每个 item 可覆盖 |
| `token_group_ids` | integer[] | 否 | 整批模型默认定价规则的播种分组，可多选；留空或空数组表示系统默认分组 |
| `items` | object[] | 是 | 1–200 个模型，名称不能重复 |
| `items[].name` | string | 是 | 模型名 |
| `items[].provider_id` | string | 否 | 单模型端点覆盖 |
| `items[].template_id` | string | 否 | 单模型模板覆盖 |
| `items[].model_type` | string | 否 | 单模型类型覆盖 |
| `items[].pricing_rules` | array | 条件必填 | 未命中预设时必须提供，形状与预览返回的 `pricing_rules` 一致 |
| `items[].description` | string | 否 | 模型介绍 |
| `items[].default_concurrency_limit` | integer | 否 | 默认并发上限 |
| `items[].active` | boolean | 否 | 默认 `true` |

```json
{
  "provider_id": "openai",
  "token_group_ids": [1, 3],
  "items": [
    { "name": "gpt-4o" },
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

`token_group_ids` 为可选项：传入时整批模型的默认定价规则会按分组顺序各播种一套；不传或传空数组时使用系统默认分组。分组不存在或已停用时整批创建失败。

### 响应

HTTP 201：

```json
{
  "code": 201,
  "message": "OK",
  "data": {
    "items": [
      { "id": "...", "name": "gpt-4o", "pricing_configured": true },
      { "id": "...", "name": "my-relay-model", "pricing_configured": true }
    ]
  },
  "request_id": "..."
}
```

### 原子性

批量创建是**整体事务**：

- 任一模型校验失败，整批回滚，不会创建任何模型；
- 422 文案会带上失败的模型名，例如：
  `模型“my-relay-model”创建失败：该模型未匹配到所选 Provider 的预设价格，请手动填写定价规则`。

前端应保留用户已填写的表格内容，允许修正后重新提交。

## 5. 价格如何展示

推荐表格列：

| 列 | 内容 |
| --- | --- |
| 选择 | 复选框；`error != null` 的行禁用 |
| 模型名 | `model_name` |
| 端点 | `provider_name`（表头文案用“端点”） |
| 类型 | `model_type` |
| 价格 | 命中预设时展示 `pricing_summary`；未命中显示“需填写” |
| 状态 | 已匹配预设 / 需填写价格 / 无法创建 |

价格单元格示例：

- 命中预设：`输入 token $2.50 / 1M`、`输出 token $10.00 / 1M`；
- 需要填写：显示“需填写”，点击展开编辑器，字段来自 `pricing_rules`；
- 无法创建：显示 `error`，并禁用创建。

表格上方展示汇总：`已匹配 X / 需填写 Y / 失败 Z`。

`unit_amount` 的语义随计费项类型变化：

- 文本 token 项：每 100 万 token；
- 图片 token 项：每 token；
- 按次 / 时长项：每单位；
- 展示时始终带上接口返回的 `currency`。

**未命中预设的行必须填写完整价格后才能提交**；后端会在任一行缺少价格时拒绝整批。

## 6. 推荐交互流程

1. 填写渠道 URL 与 API Key，点击“拉取模型”。
2. 模型列表支持多选。
3. 选择“端点”（接口字段 `provider_id`），必要时选择模型类型。
4. 确定默认定价规则的播种分组（接口字段 `token_group_ids`，可多选）：
   - 渠道表单的分组选择器已有分组时，批量配置自动填入同一组分组；
   - 渠道尚未选择分组时，默认选中系统默认分组；
   - 在批量配置中修改分组时，同步回渠道表单的分组选择器，保证两边一致。
5. 点击“批量配置/预览”，调用批量预览接口。
6. 表格展示每个模型的价格与状态；对“需填写”的行展开价格编辑器。
7. 点击“批量创建”，提交公共 `provider_id`、`token_group_ids` + 每个模型的 `pricing_rules`（如有）。
8. 创建成功后，把所有新模型名加入渠道的 `supported_models`，再保存渠道（新建渠道时直接包含这些名称），并提交与批量配置一致的 `token_group_ids`。

## 7. 验收清单

- [ ] 模型拉取流程支持选择默认定价规则的播种分组，默认选中系统默认分组。
- [ ] 渠道表单已选择分组时，批量配置自动继承同一组分组。
- [ ] 在批量配置中修改分组会同步回渠道表单，保存渠道后两边分组一致。
- [ ] 选择多个分组时，每个分组各生成一套默认定价规则。
- [ ] 模型列表支持多选，并按批量流程统一配置端点。
- [ ] 界面文案使用“端点”，不展示 “Provider” 字样。
- [ ] 批量预览表格能区分“已匹配预设 / 需填写价格 / 无法创建”。
- [ ] 命中预设的行展示价格摘要（含币种）。
- [ ] 未命中预设的行展示“需填写”，并能基于 `pricing_rules` 编辑价格。
- [ ] 存在未填写价格时无法提交，或提交后展示后端 422 文案。
- [ ] 批量创建失败时没有任何模型被创建，修正后可重新提交。
- [ ] 创建成功后模型名可加入渠道 `supported_models` 并保存成功。
