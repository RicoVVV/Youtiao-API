# Console Frontend Integration Guide

This guide covers two console features:

1. **Balance alert** — admin turns the feature on; each user sets their own low-balance threshold.
2. **Channel upstream models** — pull models from an upstream channel, then create local models with provider
   selection and preset or manual pricing.

All endpoints are admin-only, use the unified response envelope, and all amounts are USD. Alert emails are sent in
English by the backend.

## Common Conventions

### Authentication

Send an admin Bearer access token on every request:

```http
Authorization: Bearer {admin_access_token}
```

Missing or invalid token → `401`. A non-admin token → `403`.

### Response envelope

All `/api/**` responses use:

```json
{
  "code": 200,
  "message": "OK",
  "data": {},
  "request_id": "b7f1c0c2-1d2e-4f3a-9c3d-2a1e5f6b7c8d"
}
```

### Error envelope

`code` equals the HTTP status; `message` carries the reason:

```json
{
  "code": 422,
  "message": "余额预警依赖邮箱注册验证，开启余额预警时必须同时开启邮箱注册验证",
  "data": null,
  "request_id": "b7f1c0c2-1d2e-4f3a-9c3d-2a1e5f6b7c8d"
}
```

### Endpoint quick reference

| # | Method | Path | Purpose |
|---|---|---|---|
| 1 | GET | `/api/admin/system-settings/detail` | Read the balance alert switch. |
| 2 | POST | `/api/admin/system-settings/update` | Toggle the balance alert. |
| 3 | GET | `/api/user/info` | Read the current user's alert settings. |
| 4 | POST | `/api/user/balance-alert/update` | Set the current user's threshold and recipient email. |
| 5 | POST | `/api/admin/channels/fetch-upstream-models` | Pull the upstream model list. |
| 6 | GET | `/api/admin/models/providers/list` | List selectable endpoints (displayed as 端点). |
| 7 | GET | `/api/admin/models/match-preview` | Preview endpoint preset pricing. |
| 8 | POST | `/api/admin/models/create` | Create a single local model. |
| 9 | POST | `/api/admin/models/batch-match-preview` | Batch preview endpoint template and pricing. |
| 10 | POST | `/api/admin/models/batch-create` | Batch create models. |

---

# Part A — Balance Alert

The balance alert has two sides:

- **Admin:** only turns the feature on (and must have complete email configuration).
- **User:** sets their own threshold and optionally a custom recipient email. When no custom email is set, the
  registration email is used. Accounts without any email must provide one to enable the alert.

The backend emails a user once per low-balance episode when their wallet balance falls to or below **their own**
threshold after a usage charge.

## A1. Admin Switch

| Method | Path | Parameters |
|---|---|---|
| GET | `/api/admin/system-settings/detail` | None |
| POST | `/api/admin/system-settings/update` | JSON body |

Relevant field in `data`:

| Field | Type | Description |
|---|---|---|
| `email_verification_enabled` | boolean | Email-registration switch. Must be `true` for alerts to work. |
| `balance_alert_enabled` | boolean | Whether balance alert emails are enabled globally. |

Admin update request:

```json
{
  "balance_alert_enabled": true
}
```

The admin side does **not** set a threshold. Enabling the switch requires complete email configuration:
`email_verification_enabled` must be `true`, and enabling email registration already validates the SMTP host, port,
security, username, password and sender email.

## A2. Admin Validation Errors

`422` is returned when:

| Condition | Meaning |
|---|---|
| `balance_alert_enabled` is `true` while `email_verification_enabled` is `false` | Email registration must be enabled first; otherwise the backend cannot obtain user emails. |
| The update would disable `email_verification_enabled` while `balance_alert_enabled` stays `true` | The two switches must stay consistent. |

**UI guidance:** treat `email_verification_enabled` as a prerequisite. While it is `false`, disable the balance alert
switch or force it off before submitting.

## A3. User Alert Settings

### Read

| Method | Path | Parameters |
|---|---|---|
| GET | `/api/user/info` | None |

`data` gains:

| Field | Type | Description |
|---|---|---|
| `email` | string \| null | Registration email (from email registration or Google login). |
| `balance_alert_email` | string \| null | Custom alert recipient set by the user; `null` means the registration email is used. |
| `balance_alert_threshold` | string \| null | User's threshold with 6 decimal places, or `null` when not set. |

Example fragment:

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

Effective recipient = `balance_alert_email ?? email`.

### Update

| Method | Path | Parameters |
|---|---|---|
| POST | `/api/user/balance-alert/update` | JSON body |

| Field | Type | Required | Description |
|---|---|---|---|
| `threshold` | number or numeric string, > 0, max 6 decimal places, or `null` | Yes | Sets the reminder threshold in USD. `null` disables the reminder for this user. |
| `email` | string or `null`, max 320 chars | No | Custom alert recipient. Omit, send `null` or an empty string to clear it and fall back to the registration email. |

Set a threshold with a custom recipient:

```json
{
  "threshold": "5.000000",
  "email": "alerts@example.com"
}
```

Set a threshold using the registration email:

```json
{
  "threshold": "5.000000",
  "email": null
}
```

Disable the reminder:

```json
{
  "threshold": null
}
```

Response:

```json
{
  "code": 200,
  "message": "OK",
  "data": {
    "balance_alert_threshold": "5.000000",
    "balance_alert_email": "alerts@example.com"
  },
  "request_id": "..."
}
```

Errors:

| Status | Condition |
|---|---|
| 401 | Missing or invalid access token. |
| 422 | `threshold` is `0` or negative; `email` is not a valid address; the alert is enabled but neither a custom email nor a registration email exists (accounts not registered by email must fill `email`). |

## A4. Runtime Behaviour

- The check is lazy: it runs only after a usage charge deducts the user's balance. There is no periodic scan.
- The admin switch and email-registration switch must both be `true`; the user must have a positive
  `balance_alert_threshold` and a usable recipient (`balance_alert_email` or the registration email), otherwise
  nothing is sent.
- After the deduction, if the new balance is `<=` the user's threshold, one email is sent.
- Only the charge that moves the balance from above the threshold to at-or-below it starts a new low-balance episode.
  Further usage while already below the threshold does not send more emails.
- After a top-up raises the balance above the threshold, the next drop below it sends a new email.
- Updating the user's threshold also starts a new episode, so the next qualifying charge can notify again.
- If SMTP sending fails, the reminder is retried on the user's next usage.

## A5. Scope

There is no wallet or usage response change. The user threshold is the only per-user control: `null` means the user
does not receive balance alert emails.

For the focused frontend change checklist, see
[BALANCE_ALERT_SETTINGS_CHANGE_REQUEST.md](./BALANCE_ALERT_SETTINGS_CHANGE_REQUEST.md).



---

# Part B — Channel Upstream Models & Model Creation

This flow lets an operator fill in a channel URL and API key, pull the upstream model list, and create local models
from the pulled names.

For the focused frontend change checklist (multi-select, endpoint naming, batch pricing display), see
[CHANNEL_MODEL_BATCH_CREATE_CHANGE_REQUEST.md](./CHANNEL_MODEL_BATCH_CREATE_CHANGE_REQUEST.md).

## B1. Fetch Upstream Models

| Method | Path | Parameters |
|---|---|---|
| POST | `/api/admin/channels/fetch-upstream-models` | JSON body |

### Request body

| Field | Type | Required | Description |
|---|---|---|---|
| `base_url` | string | Conditional | Channel URL, e.g. `https://api.example.com/v1`. Required when `channel_id` is absent. |
| `api_key` | string | Conditional | Channel API key. Required when `channel_id` is absent or the stored channel has no key. |
| `channel_id` | UUID | No | Existing channel. Missing `base_url` / `api_key` / headers are filled from the saved channel — useful on the edit page where the key is not returned to the browser. |
| `header_override` | object | No | Extra request headers for gateways with custom auth. Values are converted to strings; an explicit `Authorization` header takes precedence over the default Bearer token. |

```json
{
  "base_url": "https://api.example.com/v1",
  "api_key": "sk-xxxx"
}
```

### URL resolution

| Input `base_url` | Requested URL |
|---|---|
| `https://api.example.com` | `https://api.example.com/v1/models` |
| `https://api.example.com/v1` | `https://api.example.com/v1/models` |
| `https://api.example.com/v1beta` | `https://api.example.com/v1beta/models` |
| `https://ark.cn-beijing.volces.com/api/v3` | `https://ark.cn-beijing.volces.com/api/v3/models` |
| Anything already ending in `/models` | Used as-is |

The request uses `Authorization: Bearer {api_key}` unless `header_override` already supplies an authorization header,
and times out after 15 seconds.

### Response

```json
{
  "code": 200,
  "message": "OK",
  "data": {
    "models": ["gpt-4o", "gpt-4o-mini", "o3"]
  },
  "request_id": "..."
}
```

Model names are de-duplicated and sorted. Supported upstream shapes: OpenAI/Anthropic `data[].id`, `models[].id` /
`models[].name` (the Gemini `models/` prefix is removed), and plain string arrays.

### Errors

| Status | Condition |
|---|---|
| 404 | `channel_id` does not exist. |
| 422 | Missing URL or API key, non-HTTP(S) URL, upstream `401/403`, other upstream HTTP error, invalid JSON, or no models returned. |
| 503 | Upstream is unreachable or timed out. |

## B2. List Selectable Endpoints

| Method | Path | Parameters |
|---|---|---|
| GET | `/api/admin/models/providers/list` | None |

> **Naming:** the API field is `provider_id`, but in this flow it represents the upstream **endpoint / protocol**
> (OpenAI-compatible, Anthropic Messages, Gemini, DashScope, ...). Display the selector as **端点 (Endpoint)**, not
> "Provider".

Example `data`:

```json
{
  "items": [
    {
      "provider_id": "openai",
      "provider_name": "OpenAI",
      "provider_logo_url": "https://...",
      "model_types": ["image", "text", "video"]
    },
    {
      "provider_id": "anthropic",
      "provider_name": "Anthropic",
      "provider_logo_url": "https://...",
      "model_types": ["text"]
    }
  ]
}
```

Use `provider_id` in the provider selector and `model_types` to constrain the model type selector.

## B3. Preview Provider Preset Pricing

| Method | Path | Query parameters |
|---|---|---|
| GET | `/api/admin/models/match-preview` | `name` (required), `provider_id` (optional), `model_type` (optional) |

When `provider_id` is present, pricing is matched **only** within that provider's preset models. `model_type`
(`text` / `image` / `video`) selects the provider template explicitly; when omitted it is inferred from the model
name. A provider without a template for an explicitly requested `model_type` returns `422`.

Response fields relevant to this flow:

| Field | Type | Description |
|---|---|---|
| `matched` | boolean | `true` only when a provider preset price entry matched. |
| `requires_pricing_input` | boolean | `true` when no preset matched (or the preset is incomplete); the form must collect prices. |
| `match_type` | string | `exact` (preset matched), `provider_fallback` (provider template used, no preset price), or `none`. |
| `template_id` | string | Template the model will use. |
| `model_type` | string | Resolved model type. |
| `pricing_rules` | array | Pricing rule skeleton to seed the model. Fill `items[].unit_amount` when `requires_pricing_input` is `true`. |
| `pricing_modifiers` | array | Preset long-context modifiers; empty when no preset matched. |
| `pricing_fields` | array | Pricing whitelist derived from the template contract. |
| `input_schema` | object | Public request contract. |

Example: `GET /api/admin/models/match-preview?name=gpt-4o&provider_id=anthropic` returns `matched: false` and
`requires_pricing_input: true` with the Anthropic text template's pricing skeleton, because the `gpt-4o` preset belongs
to OpenAI.

## B4. Batch Preview

| Method | Path | Parameters |
|---|---|---|
| POST | `/api/admin/models/batch-match-preview` | JSON body |

Use this after multi-selecting model names, so the UI can show one row per model with its matched pricing or a
"needs input" state.

### Request body

| Field | Type | Required | Description |
|---|---|---|---|
| `model_names` | string[] | Yes | Selected upstream model names, 1–200 items. Duplicates are ignored; empty names are skipped. |
| `provider_id` | string | No | Endpoint selected for the batch. Applies to every model. |
| `model_type` | string | No | Forces `text` / `image` / `video` for every model; omit to infer from each name. |

```json
{
  "model_names": ["gpt-4o", "my-relay-model"],
  "provider_id": "openai"
}
```

### Response

```json
{
  "items": [
    {
      "model_name": "gpt-4o",
      "matched": true,
      "requires_pricing_input": false,
      "match_type": "exact",
      "template_id": "openai_text_default",
      "model_type": "text",
      "provider_id": "openai",
      "provider_name": "OpenAI",
      "provider_logo_url": "https://...",
      "pricing_summary": [
        { "kind": "input_text_tokens", "label": "输入 token", "unit_amount": "2.500000", "currency": "USD" },
        { "kind": "output_text_tokens", "label": "输出 token", "unit_amount": "10.000000", "currency": "USD" }
      ],
      "pricing_rules": [{ "name": "按 token 计费", "conditions": [], "items": [] }],
      "pricing_modifiers": [],
      "pricing_fields": ["..."],
      "input_schema": {},
      "error": null
    },
    {
      "model_name": "my-relay-model",
      "matched": false,
      "requires_pricing_input": true,
      "match_type": "provider_fallback",
      "template_id": "openai_text_default",
      "model_type": "text",
      "provider_id": "openai",
      "provider_name": "OpenAI",
      "provider_logo_url": "https://...",
      "pricing_summary": [],
      "pricing_rules": [{ "name": "按 token 计费", "conditions": [], "items": [] }],
      "pricing_modifiers": [],
      "pricing_fields": ["..."],
      "input_schema": {},
      "error": null
    }
  ],
  "summary": { "total": 2, "preset_matched": 1, "requires_pricing_input": 1, "failed": 0 }
}
```

`pricing_summary` is a flattened list of billable items (`kind`, `label`, `unit_amount`, `currency`) and is only
populated for preset-matched rows; unmatched rows return an empty summary and must be filled by the operator.
`pricing_rules` is always returned; for unmatched rows it is the editable skeleton. A row with `error != null` means
the endpoint cannot serve that model (for example the endpoint has no template for the forced `model_type`); exclude
it from the selection.

## B5. Batch Create

| Method | Path | Parameters |
|---|---|---|
| POST | `/api/admin/models/batch-create` | JSON body |

`token_group_ids` is optional. When omitted or empty, preset/manual pricing rules are seeded into the system default
group, exactly like single creation without `token_group_ids`. When provided, every group in the list receives its own
copy of the seeded pricing rules.

### Request body

| Field | Type | Required | Description |
|---|---|---|---|
| `provider_id` | string | No | Common endpoint for the batch; each item may override it. |
| `token_group_ids` | integer[] | No | Target token groups for the seeded pricing rules. Omit or send an empty array to use the system default group. Unknown or inactive groups reject the whole batch. |
| `items` | object[] | Yes | 1–200 models. |
| `items[].name` | string | Yes | Model name. Duplicates in one batch are rejected. |
| `items[].provider_id` | string | No | Per-model endpoint override. |
| `items[].template_id` | string | No | Per-model template override. |
| `items[].model_type` | string | No | Per-model type override. |
| `items[].pricing_rules` | array | Conditional | Required when that model has no preset price. Same shape as B3/B4. |
| `items[].description` | string | No | Model description. |
| `items[].default_concurrency_limit` | integer | No | Concurrency limit. |
| `items[].active` | boolean | No | Defaults to `true`. |

```json
{
  "provider_id": "openai",
  "token_group_ids": [1, 3],
  "items": [
    { "name": "gpt-4o" },
    { "name": "my-relay-model", "pricing_rules": [{ "name": "按 token 计费", "conditions": [], "items": [] }] }
  ]
}
```

### Response

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

### Errors

The batch is atomic: if any model fails validation, nothing is created and `422` returns a message prefixed with the
failing model name, e.g. `模型“my-relay-model”创建失败：该模型未匹配到所选 Provider 的预设价格，请手动填写定价规则`.

## B6. Create a Single Model

| Method | Path | Parameters |
|---|---|---|
| POST | `/api/admin/models/create` | JSON body |

Existing fields are unchanged. `token_group_ids` is optional: omit it and the pricing rules are seeded into the system
default group, or pass one or more group ids to seed a pricing rule copy into each group. Two fields are added:

| Field | Type | Required | Description |
|---|---|---|---|
| `provider_id` | string | No | Endpoint chosen in B2 (the API field is `provider_id`; display it as 端点). Preset pricing is matched within this endpoint only. When set and no preset matches, `pricing_rules` is mandatory. |
| `pricing_rules` | array | Conditional | Manual pricing rules. Shape matches `pricing_rules` from B3: `name`, `conditions`, optional `currency`, and `items` with `label`, `position`, `kind`, `source_fields`, `free_quantity`, `unit_amount`, `estimate_config`. Every billable item must have a `unit_amount` (except `input_video_duration`, which reuses the output item's price). |

### Create with preset pricing

```json
{
  "name": "gpt-4o",
  "provider_id": "openai",
  "token_group_ids": [1],
  "active": true
}
```

### Create with manual pricing

```json
{
  "name": "my-relay-model",
  "provider_id": "openai",
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
```

### Response

```json
{
  "code": 201,
  "message": "OK",
  "data": {
    "id": "0f1c...",
    "name": "my-relay-model",
    "pricing_configured": true
  },
  "request_id": "..."
}
```

### Errors

| Status | Condition |
|---|---|
| 422 | Unknown `provider_id`; `template_id` does not belong to the selected provider; the name matches no provider preset and `pricing_rules` is missing; manual rules are structurally invalid or have missing `unit_amount`; model name already exists. |

## B7. Recommended UI Flow

1. Operator fills the channel URL and API key and clicks **Pull models** → B1.
2. Show the returned model names with multi-select checkboxes.
3. Load endpoint options → B2; display the selector as **端点** and let the operator choose one (plus an optional model
   type when the endpoint supports several).
4. Load token groups from `GET /api/admin/token/groups/list`; let the operator choose the pricing seed groups
   (`token_group_ids`, multi-select, default to the system default group).
5. Call the batch preview with the selected `model_names` + `provider_id` (+ `model_type`) → B4.
6. Render one row per model:
   - **Status column:** `已匹配预设价格` / `需填写价格` / `无法创建`.
   - **Price column:** when `matched` is `true`, render `pricing_summary` as label + amount + currency, e.g.
     `输入 token $2.50 / 1M` and `输出 token $10.00 / 1M`; a "详情" action can show the full `pricing_rules`.
   - When `requires_pricing_input` is `true`, show **需填写** and an inline editor prefilled from `pricing_rules`;
     the operator must complete `unit_amount` for every billable item.
   - When `error != null`, show the error and disable that row's checkbox.
   - Show the summary counts above the table (`preset_matched` / `requires_pricing_input` / `failed`).
7. Click **Batch create** → B5, sending the common `provider_id`, `token_group_ids`, plus each row's name and (when
   needed) `pricing_rules`.
8. After success, add all created model names to the channel's `supported_models` and save the channel via
   `POST /api/admin/channels/update` (or include them in `POST /api/admin/channels/create` for a new channel).

A single model can still be created via B6 when the operator does not need batch selection.

### Pricing display notes

- Preset prices come from the platform catalog; the UI only displays them and does not need to calculate anything.
- `unit_amount` semantics follow the item kind: text token items are per 1M tokens, image token items are per token,
  and count/duration items are per unit. Always show the `currency` returned with the item.
- Unmatched rows must be filled before batch creation; the backend rejects the whole batch if any row is missing
  prices, so no partially priced models are created.
