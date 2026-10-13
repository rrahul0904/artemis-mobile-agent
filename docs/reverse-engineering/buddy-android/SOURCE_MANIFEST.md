# Buddy Android — Source Manifest and Evidence Ledger

Control issue: #1  
Canonical destination: `rrahul0904/artemis-mobile-agent`  
Status: `RESEARCHING`

## Frozen source

- Source discussion: https://www.reddit.com/r/SideProject/comments/1x4iqin/i_built_an_android_app_where_claude_code_codex_or/
- Donor repository: https://github.com/ghorbelhamdi/buddy-android
- Donor commit: `8db149d645ca8e4a6a0da4baddc6a1e45963d329`
- Donor commit title: `Buddy 2.1.3`
- License: Apache-2.0 for Buddy code. The donor also bundles components under GPL-2.0, LGPL-3.0, BSD-3-Clause, and SIL OFL; notices/source obligations must remain isolated and honored if any code or binary is reused.
- Artemis base commit: `2a81d6b39d9bf95b56010a7c70b8103dc6b959d3`

This reconstruction is evidence-led and clean-room by default. We copy product contracts and behavior only unless a separately reviewed component is explicitly adopted under compatible license terms.

## Primary evidence inspected

| Evidence | What it establishes | Confidence |
|---|---|---:|
| Reddit SideProject source | User problem, product claim, examples, request for approval-design feedback | High |
| Donor `README.md` | UX, setup, tool surface, architecture, distribution, security claims | High |
| `McpServer.java` | Loopback `127.0.0.1:8765`, bearer auth, Streamable HTTP MCP subset, `/event` side channel | High |
| `Guard.java` | UI-target safety heuristics, protected Buddy UI, risky-label matching, per-app mode selection | High |
| Repository tree | Android app, proot/native libs, embedded Linux scripts, terminal/session/bubble implementation, CI | High |
| Google Play Accessibility policy | Generalized autonomous agent use of Accessibility API is prohibited for ordinary Play distribution | High |
| Artemis `devices.py` | Current backend seam (`DeviceBackend`), ADB implementation and fake backend | High |
| Artemis README/PARITY | Existing trace-first orchestration, verifier, replay, API, MCP, lifecycle and deployment capabilities | High |

## Donor reconstruction

### User-facing contract

A user installs an Android app, enables Accessibility, installs/signs into an agent runtime, opens a floating bubble, gives a natural-language task, and observes the agent operate arbitrary apps by reading the screen and performing gestures. The user can intervene, add instructions, stop execution, and approve outward-facing/irreversible actions.

### Runtime topology

```text
Android UI / bubble
      |
      v
Embedded Alpine/proot runtime -> Claude Code / Codex / OpenCode
      |                                  |
      | streamed events                  | MCP tool calls
      v                                  v
Android service <-------------- loopback MCP :8765
      |
      v
Accessibility observations + gestures + intents
```

### Observed tool surface

`read_screen`, `tap`, `long_press`, `type_text`, `scroll`, `swipe`, `press`, `open_app`, `list_apps`, `open_url`, `screenshot`, `wait`, `install_apk`, `wait_for_install`, `confirm`, `ask`, `notify`, `update_buddy`.

### Safety contract in donor

- MCP is loopback-only and bearer-token protected.
- Buddy's own protected UI is off-limits to agent taps.
- Messaging/social/money/shopping categories default to stricter treatment.
- Risky UI labels/resources (send/pay/delete/etc.) trigger approval logic.
- Approval is short-lived and consumed by the next risky action.
- An optional separate reviewer model can assess actions.
- Developer mode is explicitly riskier because untrusted on-screen text can influence shell-capable agents.

## External market / adjacent evidence

### DroidBridge

`zephyr7030/DroidBridge` independently validates the on-device MCP pattern and extends it with Accessibility, optional Shizuku/root identities, explicit MCP safety annotations, signed update metadata, Android Keystore handling, filesystem/command/network/automation tools, and a capability-centric settings model.

Implication for Artemis: the differentiated product should not be merely “MCP on Android.” Artemis should compete on **trace-first verified autonomy, policy evidence, replay, recovery, and multi-transport parity**.

## Policy boundary

Google Play's current AccessibilityService policy prohibits ordinary apps from using the Accessibility API to autonomously initiate, plan, and execute actions or decisions, except qualifying accessibility tools whose core purpose assists people with disabilities. Therefore the generalized agent edition must assume direct/sideload distribution unless the product scope changes materially.

## Open evidence gaps

- Physical-device behavior has not yet been independently replayed against the frozen donor SHA.
- OEM-specific background execution behavior is not yet certified.
- Donor approval/reviewer behavior has not yet been fuzzed for race, concurrency, stale-target, or prompt-injection edge cases.
- Embedded agent login/update flows have not yet been independently reproduced.
- No claim is made that donor UI/UX is production-grade across devices.

## Next evidence gates

1. Commit clean-room reconstruction model and Shipping Contract.
2. Implement the smallest device-native companion slice behind Artemis's `DeviceBackend` interface.
3. Prove tool-contract parity on fake backend before physical-device work.
4. Produce physical-device traces for read/tap/type/scroll/open-app/stop/approval flows.
5. Only then advance roadmap status to `RUNTIME_VERIFIED` / `UAT_VERIFIED`.