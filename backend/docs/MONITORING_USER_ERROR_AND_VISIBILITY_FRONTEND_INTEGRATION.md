# Monitoring Frontend Integration Guide — Type-Based Modes & Visibility Order

This document covers only two frontend changes:

1. Monitoring visibility is configured in the order **request types first, then groups** — the group picker only shows groups that support the selected types.
2. The real/probe mode switch lives **inside the type area**, and only `text` has a switch. `image` and `video` have **no switch** and always use real traffic.

All endpoints require an admin Bearer token:

```
Authorization: Bearer {access_token}
```

All `/api/**` responses use the unified envelope `{ code, message, data, request_id }`.

---

## 1. Visibility: Select Types First, Then Groups

### 1.1 Query visibility config (admin)

```
GET /api/admin/monitoring/user-visibility/detail
```

Response example:

```json
{
  "code": 200,
  "message": "OK",
  "request_id": "...",
  "data": {
    "enabled": true,
    "group_ids": [1, 2],
    "request_types": ["text", "video"],
    "groups": [
      { "id": 1, "name": "default", "is_active": true, "request_types": ["text", "image", "video"] },
      { "id": 2, "name": "ces", "is_active": true, "request_types": ["text"] },
      { "id": 3, "name": "video-only", "is_active": true, "request_types": ["video"] }
    ],
    "updated_at": "2026-10-23T02:00:00+00:00"
  }
}
```

| Field | Type | Description |
|---|---|---|
| `enabled` | boolean | Whether the visibility restriction is active |
| `group_ids` | integer[] | Whitelisted token group IDs; empty when `enabled=false` |
| `request_types` | string[] | Whitelisted request types; all three when `enabled=false` |
| `groups` | object[] | All token groups with their supported request types |
| `groups[].request_types` | string[] | Types supported by that group's enabled models/routes/channels; empty if none |
| `updated_at` | string \| null | Last update time, ISO 8601 UTC |

### 1.2 Required UI order

1. Render the request type checkboxes (`text`, `image`, `video`) first.
2. Filter the group picker using `groups[].request_types`:
   - Keep a group only when its `request_types` intersects the currently selected visible types.
   - Example: when only `text` is selected, a group whose `request_types` is only `["image"]` or `["video"]` must not appear.
   - When multiple types are selected, a group that supports any one of them remains selectable.
3. If the admin unchecks a type, automatically deselect groups that no longer support any selected type.
4. After types and groups are chosen, save the visibility whitelist with the endpoint below.

### 1.3 Update visibility config (admin)

```
POST /api/admin/monitoring/user-visibility/update
Content-Type: application/json
```

Request body:

```json
{
  "enabled": true,
  "group_ids": [1, 2],
  "request_types": ["text", "video"]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `enabled` | boolean | yes | `false` clears the whitelist and restores unrestricted visibility |
| `group_ids` | integer[] | when enabled | Allowed token group IDs |
| `request_types` | string[] | when enabled | Allowed request types: `text`, `image`, `video` |

Response: same structure as `user-visibility/detail`.

Errors:

| Status | When |
|---|---|
| `422` | `enabled=true` with an empty group list |
| `422` | `enabled=true` with an empty request type list |
| `422` | `request_types` contains an unsupported value |
| `422` | `group_ids` contains a non-existent group |
| `401` / `403` | Not authenticated / not an admin |

---

## 2. Mode Switch Inside the Type Area

### 2.1 Mode rules

| Request type | Allowed modes | Default | Admin UI |
|---|---|---|---|
| `text` | `real`, `probe` | `probe` | Render a real/probe switch |
| `image` | `real` only | `real` | **No switch**; show a fixed "Real Traffic" label |
| `video` | `real` only | `real` | **No switch**; show a fixed "Real Traffic" label |

- The switch belongs to each type row, not to a global toolbar.
- Only `text` renders both options. `image` / `video` render the row without any switch or disabled toggle.
- Modes affect both admin and user-side monitoring pages.

### 2.2 Query modes (admin)

```
GET /api/admin/monitoring/mode/detail
```

Response:

```json
{
  "code": 200,
  "message": "OK",
  "request_id": "...",
  "data": {
    "modes": { "text": "probe", "image": "real", "video": "real" },
    "probe_interval_seconds": 60,
    "updated_at": "2026-10-23T02:00:00+00:00"
  }
}
```

`modes` always contains all three keys so the UI can render labels, but only `modes.text` is switchable.

### 2.3 Switch text mode (admin)

```
POST /api/admin/monitoring/mode/update
Content-Type: application/json
```

Request body when toggling text:

```json
{
  "modes": { "text": "probe" },
  "probe_interval_seconds": 60
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `modes.text` | string | no | `real` or `probe`; omit to keep the current value |
| `probe_interval_seconds` | integer | no | Probe interval in seconds, range `30`–`3600`, default `60`; omit to keep the current value |

Notes:

- `modes` and each field inside it are optional; omitted values keep their current state.
- Do not render switches for `image` / `video`, and do not send them from the UI.
- If `probe` is sent for `image` or `video`, the API returns `422` (`Only the text request type supports probe mode`).

Response: same structure as `mode/detail`.

Errors:

| Status | When |
|---|---|
| `422` | `modes` contains an unsupported request type or mode |
| `422` | `modes.image` / `modes.video` is `probe` |
| `422` | `probe_interval_seconds` is outside `30`–`3600` |
| `401` / `403` | Not authenticated / not an admin |

---

## 3. Fields Used by the UI from Monitoring Lists

Both `GET /api/monitoring/groups/list` and `GET /api/monitoring/groups/trend` (and their admin counterparts) now return:

| Field | Type | Description |
|---|---|---|
| `modes` | object | `{ "text": "real" \| "probe", "image": "real", "video": "real" }` |
| `request_types` | string[] | Request types available to the caller |

- Use `request_types` to build the type selector; do not hard-code `["text", "image", "video"]`.
- Use `modes.text` to render the text switch.
- For `image` / `video`, always render the fixed "Real Traffic" label regardless of `modes`.

Example:

```json
{
  "code": 200,
  "message": "OK",
  "request_id": "...",
  "data": {
    "window_minutes": 5,
    "latest_window_start": "2026-10-23T02:05:00+00:00",
    "range_start": "2026-10-22T02:10:00+00:00",
    "modes": { "text": "probe", "image": "real", "video": "real" },
    "request_types": ["text", "video"],
    "items": []
  }
}
```

---

## 4. Frontend Checklist

1. **Types** (`components/console/monitoring/types.ts`)
   - Add `type MonitorMode = "real" | "probe"`.
   - Add `type MonitorModes = Record<"text" | "image" | "video", MonitorMode>`.
   - Replace `mode: MonitorMode` with `modes: MonitorModes` on the list/trend/channel response types.
   - Keep `request_types: RequestType[]`.
2. **Visibility editor**
   - Move the type checkboxes to the first step.
   - Filter groups by `groups[].request_types` against the selected types.
   - Drop group selections that become invalid after a type is unchecked.
3. **Mode control**
   - Remove any global mode switch.
   - Render the switch inside the `text` type row only.
   - Render `image` and `video` rows without a switch, showing "Real Traffic" as static text.
   - On change, call `POST /api/admin/monitoring/mode/update` with `{ "modes": { "text": next } }`, then reload the list/trends.
4. **i18n keys** (suggested)

| Key | zh-CN | en-US |
|---|---|---|
| `monitoring.modeLabel` | `数据模式` | `Data Mode` |
| `monitoring.mode.real` | `真实请求` | `Real Traffic` |
| `monitoring.mode.probe` | `嗅探测试` | `Probe Tests` |
| `monitoring.modeUpdateFailed` | `切换数据模式失败` | `Failed to switch data mode` |
