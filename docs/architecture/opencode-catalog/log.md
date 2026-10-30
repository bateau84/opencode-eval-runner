---
type: Log
title: OpenCode catalog architecture change log
description: Changes to the OpenCode catalog architecture bundle.
tags: [log, architecture, opencode, catalog]
timestamp: 2026-10-30T00:00:00Z
---

## 2026-10-30

- Runtime upgrade: moved the pinned OpenCode image from 2.0.23 to 2.2.2. Updated native catalog validation/fixture for required 2.2.2 fields; provider-free native and Code Mode probes pass. Full runtime-evidence acceptance later passed all 11 scenarios with rootless Podman after isolating engine storage from runner/OpenCode XDG state. See [ADR-001](decisions/adr-001-pin-catalog-through-supported-file-interface.md).
- Final review closeout: `/tmp/opencode/catalog-review-20261030/followup/nullable-assembled-probe.log` confirms assembled exact-version 2.0.23 nullable-effort catalog/variant consumption PASS with snapshot cleanup. `/tmp/opencode/catalog-review-20261030/followup/final-validator.log` confirms missing effort values fail before OCI and current catalog validation passes. Snapshot reuse across lanes/retries is PASS with injected invocation results; no inference/provider availability is claimed. Supersedes the preceding nullable-edge proof limitation; details and boundaries are in [ADR-001](decisions/adr-001-pin-catalog-through-supported-file-interface.md).
- Implementation follow-up: accepts native discriminated reasoning option objects and sends the endpoint-compatible User-Agent. Verified real current-catalog acquisition without inference and a provider-free orchestration probe showing one snapshot across 17 calls, including retry. Independent assembled OCI catalog-consumption evidence is recorded in [ADR-001](decisions/adr-001-pin-catalog-through-supported-file-interface.md); provider inference remains unclaimed.
- Validator correction: native `effort.values` requires an array and permits string/null entries; null is preserved in the snapshot. The assembled probe was not repeated with this edge fixture.
- Runtime acceptance closeout: all 11 provider-free scenarios pass on immutable OpenCode 2.2.2 image ID `bc34c7eaa69a98d2da07a89e3fd6b396c4ee20cae797a34d17e65f4472fc3f57` (`/tmp/opencode/runtime-acceptance-20261030-final5/summary.json`); exact-version offline probe confirms nullable custom nested model/variant consumption and `opencode.models.dev` activation. The dated failure statement is superseded by the verified evidence recorded above; no paid or external provider inference was used.

See [ADR-001](decisions/adr-001-pin-catalog-through-supported-file-interface.md) for the implementation decision and full verification boundaries.
