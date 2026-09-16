# Parity status

Implemented in this rebuild:

- device discovery and strict serial binding
- screenshots and UIAutomator hierarchy capture
- indexed elements and normalized-coordinate support
- click, long-press, text, swipe, key, app launch, APK install, URL open, wait
- Flash reactive execution
- Pro pre-action target checks and failure recovery loop
- task lifecycle: queue/run/pause/resume/cancel
- per-device mutual exclusion
- trace store with step/evidence/event replay
- REST, WebSocket, browser console, CLI
- MCP-compatible tool facade plus optional native FastMCP transport
- logcat and runtime diagnostics
- provider-neutral remote model-planner bridge
- Docker deployment and hermetic fake-device CI

Not claimed as independently certified here:

- Google ARTEMIS benchmark parity or AndroidWorld >99%
- a bundled proprietary multimodal/VLM provider
- physical-device execution in GitHub Actions
- video encoding/replay and the upstream console's full visual design
- upstream internal prompt/checker implementation details

Those are external-evidence or upstream-specific boundaries, not blockers to deploying this rebuild.
