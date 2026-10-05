# Planning evidence provenance

This ledger prevents reported, source-verified, and future experiment claims from being conflated.

## Vocabulary

- **VERIFIED-SOURCE** — independently read from the exact named source revision.
- **REPORTED** — supplied by prior workflow/report/consumer evidence but not rerun as part of this planning branch.
- **UNVERIFIED-IMAGE** — an image/digest is named, but its bytes and full source correspondence are not established by this planning work.
- **FUTURE-EXPERIMENT** — only candidate execution can establish the claim.

| Claim | Provenance | Notes |
|---|---|---|
| Loom `149406d` pins runner source `002aba…` and safety image `8d7c…` | VERIFIED-SOURCE | Read from Loom source at the named revision. |
| `149406d` directly follows `f2f56c55…` | VERIFIED-SOURCE | Git parent relation. |
| OpenCode v2.0.23 tag resolves to `0fd7e2829449b052abf0078666669302923d77af` | VERIFIED-SOURCE | Git tag ref. |
| OpenCode v2.0.18 tag resolves to `cd9a14a6b688d4021bee381dfd39d2cef9c0f862` | VERIFIED-SOURCE | Git tag ref. |
| v2.0.23 still evaluates configured plugin modules in the OpenCode process | VERIFIED-SOURCE | `packages/core/src/plugin/module.ts` is unchanged from v2.0.18 and invokes `plugin.effect(...)` in-process. |
| v2.0.23 `tool.execute.after` still precedes later result normalization/return | VERIFIED-SOURCE | `packages/core/src/tool.ts` is unchanged from v2.0.18. |
| v2.0.23 durable Session events expose canonical native tool called/success/failed records | VERIFIED-SOURCE | `packages/schema/src/session-event.ts`. |
| v2.0.23 Code Mode public metadata records inner tool name/status/input but not per-inner returned value/error | VERIFIED-SOURCE | `packages/core/src/codemode/tool.ts`. |
| v2.0.23 PluginHost adds parent Session creation, remove, compact, and metadata update since v2.0.18 | VERIFIED-SOURCE | Exact upstream commits inspected. |
| OpenCode v2.0.23 provides plugin isolation from arbitrary in-process plugins | VERIFIED-SOURCE: false | No such boundary was found; module/hook execution model remains in-process. |
| Safety image `8d7c…` passed the reported Loom provider-free composition at `149406d` | REPORTED | Do not promote to independently rerun evidence in this branch. |
| Normal-observation image `df50…` demonstrated patched-runtime semantics | REPORTED | Research/reference only; patched OpenCode is out of scope. |
| Safety image `8d7c…` bytes exactly correspond to current planning sources | UNVERIFIED-IMAGE | Must be re-established if ever used for a future authorized baseline. |
| A stock-v2.0.23 runner bridge can satisfy TRUST-001 | FUTURE-EXPERIMENT | Not established by source inspection. |
| A stock-v2.0.23 runner bridge can satisfy Code Mode final caller evidence | FUTURE-EXPERIMENT / currently UNPROVEN | No sufficient stock public final-inner-result surface has yet been demonstrated. |
| Proposed OS/channel controls prevent shell subprocess authority from forging evidence | FUTURE-EXPERIMENT | Must be verified against the constructed candidate. |

## Source anchors

Planning source inspection used:

- `bateau84/loom@149406dfa0a01f94491d17054e50a1bc84bb97be`
- `bateau84/opencode-eval-runner@002aba96441da8c69c5ce19ac77de298cfeb28d2`
- `anomalyco/opencode@v2.0.23`
- `anomalyco/opencode@v2.0.18`

No model inference or candidate execution was performed to produce this ledger.
