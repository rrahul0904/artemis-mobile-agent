# Artemis Mobile Agent

An independently structured, Apache-2.0 Android automation/testing runtime reconstructed from public ARTEMIS product contracts. It is designed around **trace-first execution**: every task records observations, actions, post-state, and verification evidence instead of equating a successful click with a successful test.

## Included

- ADB device discovery with strict device binding
- screenshot + UIAutomator hierarchy capture and indexed UI elements
- tap, long press, text, swipe, key, launch app, install APK, open URL, wait
- Flash reactive `observe → decide → act → re-observe → verify` loop
- Pro profile with target prechecks, checkpoint evidence, independent final verification, and recovery behavior
- pause/resume/cancel lifecycle and per-device serialization
- persisted steps/events/evidence, HTML replay, and optional MP4 replay export
- REST API, WebSocket telemetry, browser workspace, optional bearer-token protection
- Python SDK, CLI and MCP-compatible tools (`mobile_run_task`, `mobile_manage_task`, `mobile_get_device_state`, `mobile_inspect_trace`, `mobile_diagnose`)
- optional native MCP transport (`pip install '.[mcp]'`)
- provider-neutral remote planner + verifier bridges with screenshot payloads for arbitrary model/VLM reasoning
- logcat diagnostics, Dockerfile, Compose, fake Android backend, GitHub Actions

## Certified local acceptance flow

```bash
python -m pip install -e '.[dev]'
ARTEMIS_FAKE_DEVICE=1 artemis-mobile run "Open Settings, go to Battery and verify battery percentage"
pytest
```

The fake device follows the same orchestration path and verifies visible `87%` battery evidence.

## Browser/API

```bash
ARTEMIS_FAKE_DEVICE=1 artemis-mobile serve --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`. Useful endpoints: `/health`, `/api/devices`, `/api/runs`, `/api/diagnostics`.

## Real Android device

Install Android Platform Tools and enable USB debugging:

```bash
adb devices -l
artemis-mobile diagnose
artemis-mobile serve
```

An explicitly requested serial is never silently replaced with another device.

## Model planner

The built-in deterministic planner handles evidence-backed visible-text navigation and makes the repository runnable without secrets. For arbitrary model-directed workflows, configure `ARTEMIS_PLANNER_URL` and optional `ARTEMIS_PLANNER_TOKEN`; see `docs/DEPLOYMENT.md`.

## Deployment

The Docker image includes `adb`, `ffmpeg`, and a health check. A hosted demo can use `ARTEMIS_FAKE_DEVICE=1`. Real-device production instances must run on infrastructure that can reach the Android device/emulator.

See [Deployment](docs/DEPLOYMENT.md) and [Parity status](docs/PARITY.md).


## Security and SDK

Set `ARTEMIS_API_TOKEN` to require bearer authentication on API routes and WebSocket connections. Python callers can use `artemis_mobile_agent.sdk.ArtemisClient` for devices, run submission, status, lifecycle control, trace retrieval, and wait/poll workflows.
