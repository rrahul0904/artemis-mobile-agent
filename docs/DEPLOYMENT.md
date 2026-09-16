# Deployment

## Hosted demo / API-only deployment
Set `ARTEMIS_FAKE_DEVICE=1`. The service is fully usable for API/UI/trace verification without attached hardware.

## Real Android execution
The runtime must execute on a host that has Android Platform Tools and network/USB access to the target device or emulator. Set `ARTEMIS_FAKE_DEVICE=0` (default), confirm `adb devices -l`, and expose port 8000 only to trusted networks.

## Planner integration
The built-in deterministic planner drives evidence-backed visible-text navigation and certifies the Settings/Battery acceptance flow. For arbitrary model-directed workflows configure:

- `ARTEMIS_PLANNER_URL`: provider-neutral HTTPS endpoint.
- `ARTEMIS_PLANNER_TOKEN`: optional bearer token.

The endpoint receives `{goal, profile, observation, history}` and returns `{thought, action}` where `action` follows the API action schema. This keeps model-provider credentials outside the mobile runtime.

## Docker
```bash
docker build -t artemis-mobile-agent .
docker run --rm -p 8000:8000 -e ARTEMIS_FAKE_DEVICE=1 artemis-mobile-agent
```

## Production hardening
Use a reverse proxy/TLS and authentication before exposing a real-device instance on the public Internet. Persist `/data`; keep planner tokens in the platform secret store. Real-device runners are best deployed near the hardware/emulator fleet rather than to a serverless runtime.
