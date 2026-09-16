# Parity status

Implemented in this rebuild:

- device discovery and strict serial binding
- screenshots and UIAutomator hierarchy capture
- indexed elements and normalized-coordinate support
- click, long-press, text, swipe, key, app launch, APK install, URL open, wait
- Flash reactive execution
- Pro pre-action target checks, checkpoint evidence, final verifier, and failure recovery loop
- task lifecycle: queue/run/pause/resume/cancel
- per-device mutual exclusion
- trace store with step/evidence/event replay plus optional MP4 export
- REST, WebSocket, browser console, Python SDK, CLI, optional API auth
- MCP-compatible tool facade plus optional native FastMCP transport
- logcat and runtime diagnostics
- provider-neutral remote planner and verifier bridges with screenshot payloads
- Docker deployment and hermetic fake-device CI

Not claimed as independently certified here:

- Google ARTEMIS benchmark parity or AndroidWorld >99%
- a bundled proprietary multimodal/VLM provider
- physical-device execution in GitHub Actions
- the upstream console's full visual design
- upstream internal prompt/checker implementation details

Those are external-evidence or upstream-specific boundaries, not blockers to deploying this rebuild.
