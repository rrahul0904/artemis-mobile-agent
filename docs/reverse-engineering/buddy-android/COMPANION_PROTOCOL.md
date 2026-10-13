# Artemis Android Companion Protocol v1

The device-native companion is an execution transport. It does not own planning, task success, or verification.

## Authentication

All `/v1/*` requests require:

```http
Authorization: Bearer <per-install-random-token>
```

The baseline server listens only on `127.0.0.1:8765`.

## `GET /v1/device`

Returns one local device and its transport capabilities.

```json
{
  "device": {
    "serial": "android-local",
    "state": "device",
    "model": "Pixel 9",
    "transport": "companion"
  },
  "capabilities": ["observe_ui", "gesture", "text", "key", "launch_app"]
}
```

## `POST /v1/observe`

Request:

```json
{"serial":"android-local","step":1}
```

Response:

```json
{
  "hierarchy_xml":"<hierarchy>...</hierarchy>",
  "width":1080,
  "height":2400,
  "activity":"com.android.settings",
  "sequence":7,
  "digest":"sha256:..."
}
```

`screenshot_base64` is optional. The first Accessibility-only implementation may omit it.

## `POST /v1/action`

Request:

```json
{
  "serial":"android-local",
  "action":{"type":"click","target_index":4},
  "observation":{"sequence":7,"digest":"sha256:..."}
}
```

The companion MUST re-observe before a write. If the current UI digest differs from the supplied digest, it rejects the request as stale instead of guessing.

Response:

```json
{"ok":true,"message":"action accepted","stdout":"","stderr":""}
```

Transport acceptance is not task success. Artemis re-observes and verifies the semantic postcondition.

## `GET /v1/logcat`

Diagnostics endpoint. The companion may return only its own diagnostic stream when Android permissions prevent general logcat access.

## Errors

- `401`: invalid/missing bearer token
- `404`: unknown route
- `409`: stale observation / lease conflict
- `422`: invalid action contract
- `423`: companion stopped or human takeover active
- `500`: executor failure

## v1 write capabilities

First slice: `click`, `long_press`, `input_text`, `swipe`, `press_key`, `launch_app`, `open_link`, `wait`, `finish`.

APK installation, shell/filesystem, developer mode and provider-specific runtime operations are deliberately out of v1 transport scope.
