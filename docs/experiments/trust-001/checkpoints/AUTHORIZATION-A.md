# Authorization A — TRUST-001 stock OpenCode candidate

**Decision:** GRANTED  
**Scope:** prototype construction + explicitly named provider-free local preflights only  
**Planning checkpoint:** `fdbc3c9b1c5314f588ffb3cfd34bf0a19502c2aa`  
**Candidate branch:** `experiment/trust-001-stock-opencode`  
**OpenCode:** stock v2.0.23 only  
**Model/provider inference:** NOT AUTHORIZED  
**Authorization B:** NOT GRANTED

This decision authorizes Wave-2 construction under the Gate-1 PASS recorded in PR #43. It does not establish TRUST-001 feasibility.

## 1. Immutable external constraints

- OpenCode v2.0.23 remains stock and unmodified.
- No OpenCode source patch, fork, custom binary, or upstream PR is permitted.
- Loom production semantics remain unchanged.
- Loom source used by the candidate must be the pinned generation `149406dfa0a01f94491d17054e50a1bc84bb97be`.
- PR #41 patched-runtime work is research/reference only.
- Any runner-owned evidence-safety code reused from PR #41 must be copied/reviewed as runner code and must not carry a patched OpenCode dependency.

## 2. Candidate construction boundary

The authorized candidate is:

> stock OpenCode v2.0.23 with a runner-owned trusted bridge plugin; isolated Loom execution in a separate OCI domain; host-side trusted collector/scope/safety/evidence writer; distinct evidence and capability channels.

No broader generic remote-PluginHost platform is authorized.

## 3. Allowed repository mutations

Construction may change only:

- `Containerfile`;
- `runner/cli.py`;
- new `runner/trust001/**`;
- `container/invoke.py`;
- new `container/trust001/**`;
- new `trust001/**` bridge / isolated-host sources;
- new `tests/trust001/**`;
- new `tests/test_trust001_*.py`;
- a dedicated provider-free workflow under `.github/workflows/trust001-*.yml`;
- new checkpoint/results documents under `docs/experiments/trust-001/checkpoints/**`;
- this Authorization-A record.

Existing Gate-1 planning documents are frozen. A change to the reviewed TCB, capability authority, channel model, scope/closure rule, or first-sink policy requires returning to the affected earlier gate.

No Loom repository mutation is authorized.

## 4. Stock OpenCode build requirement

The candidate runtime must package the official upstream stock OpenCode v2.0.23 artifact only.

The build must:

- pin `@opencode/cli@2.0.23`;
- verify `opencode --version`;
- record the resulting candidate image digest and image-config digest;
- record the stock OpenCode package/source identity used;
- contain no `runtime-patches/` or equivalent replacement binary.

The exact built image digest becomes part of the Gate-2 candidate checkpoint.

## 5. Reviewed trusted boundary

The candidate may trust only:

- host runner launcher/orchestrator;
- host collector/scope accountant/safety projector/final writer;
- stock OpenCode v2.0.23 core;
- runner-owned bridge plugin;
- reviewed bridge/correlation/channel implementation;
- selected host kernel + OCI engine enforcement assumptions.

The following remain untrusted for evidence authority:

- Loom module/dependencies;
- Loom callbacks/handlers/product state;
- model/product outputs;
- writable workspace;
- Loom subprocesses;
- stock OpenCode shell subprocesses;
- arbitrary external plugins.

## 6. Capability surface

The remote Loom broker is limited to the Gate-1 reviewed pinned-Loom surface:

- immutable location facts;
- legacy plugin storage `get/set/scan`, generation-lifetime and product-only;
- `rpc.register`;
- `agent.transform`;
- `agent.list`;
- `tool.transform`;
- `tool.list`;
- `permission.hook("evaluate")`;
- Session hooks used by pinned Loom;
- `session.get`;
- `session.context`;
- `session.synthetic`;
- `tool.hook("execute.before")`;
- `tool.hook("execute.after")`;
- remote Loom tool execution handlers.

No generic "call arbitrary PluginHost method" operation is allowed.

Any newly required capability creates a new candidate checkpoint and requires affected authority review before use.

## 7. Plugin-source closure

Before stock OpenCode activation, candidate construction must derive a plugin-source closure manifest covering:

- effective plugin add/remove operations;
- explicit config documents;
- config roots;
- auto-discovered `plugin/` / `plugins/` paths;
- configured package/local targets;
- resolved symlink targets;
- watched inputs capable of changing the operation set.

For the tested generation:

- only the runner bridge may be admitted as evaluated external in-process plugin code;
- every input that can change the operation set must be runner-owned/read-only or otherwise outside evaluated write authority;
- the Loom module must never be imported/evaluated in the OpenCode process;
- a post-activation source-set change is a checkpoint failure, not a hot reload.

## 8. Mount/process policy

Authorized prototype defaults:

- read-only OCI root filesystems;
- non-root execution;
- dropped capabilities;
- no-new-privileges;
- no host PID namespace;
- no container-engine socket inside candidate domains;
- no evidence volume inside evaluated domains;
- bridge/runner source read-only;
- Loom source/dependencies read-only;
- workspace mounted only at the requested normal product mode;
- plugin-source/config closure protected independently of general workspace writability;
- OpenCode and Loom HOME/XDG/state isolated from each other and from host ambient state;
- core dumps disabled or made unavailable/non-persistent.

Changes that weaken these controls require renewed authority review.

## 9. Channel model

Two distinct channels are authorized.

### Evidence channel

- direction: trusted OpenCode bridge → host collector;
- only evidence-authoritative candidate observation ingress;
- endpoint outside workspace;
- endpoint inaccessible to Loom;
- no reusable secret in process environment;
- admitted peer bound to the expected bridge/OpenCode generation;
- listener closes/unlinks after admission;
- established descriptor must be close-on-exec;
- no reconnect.

### Capability channel

- direction: bridge ↔ isolated Loom;
- product callbacks/results only;
- distinct endpoint/descriptors/material from evidence channel;
- no collector-readable evidence framing or direct evidence-write authority;
- admitted isolated Loom generation bound before product execution;
- listener closes/unlinks after admission;
- no reconnect;
- identity/integrity loss makes affected work unresolved and affected evidence ineligible.

A shell/Loom child gaining evidence-channel read/write/duplication authority rejects the checkpoint.

## 10. Request and seal protocol

Construction must implement only the reviewed lifecycle:

- trusted request IDs;
- one accepted response per outstanding request;
- reject unknown, unsolicited, duplicate, replayed, stale-generation, post-cancellation, and late responses;
- channel loss never retries product work;
- restart creates a new generation.

Completeness requires the reviewed two-phase generation close:

1. stop admitting new case-required work;
2. settle/classify all already-admitted work;
3. assign monotonic evidence sequence;
4. drain accepted observations;
5. emit `seal(generation, finalSequence)`;
6. collector requires a contiguous sequence through `finalSequence`;
7. any accepted post-seal request/event is a completeness failure.

Construction may implement the mechanism; proof that the chosen stock lifecycle provides a sufficient close/drain boundary remains a provider-free preflight obligation.

## 11. First-sink policy

Candidate-controlled raw runtime observation may exist transiently only in bounded trusted memory/IPC.

Before any candidate-controlled:

- file write;
- stdout/stderr diagnostic;
- OCI log payload;
- temporary persistence;
- clipping/truncation;
- exported artifact;

credential protection must already have occurred.

Diagnostics use fixed/bounded reason codes and non-sensitive identities only.

Normal stock OpenCode/Loom product stores are not automatically runner evidence stores. If candidate code copies/promotes them, the copy boundary becomes a reviewed evidence sink.

## 12. Named provider-free preflights authorized

Only the following candidate executions are authorized before Authorization B:

### PF-01 — Stock runtime provenance

Build/start the candidate stock-OpenCode image and verify:

- v2.0.23;
- no patched runtime;
- exact source/image/config/component provenance;
- no external inference.

### PF-02 — Plugin-source closure

Using synthetic project/config fixtures:

- enumerate effective plugin-source operations;
- prove evaluated-writable workspace mutations cannot add/replace/reload in-process plugin code;
- test symlink/config/watch/restart/cold-start escape attempts.

### PF-03 — Evidence-channel authority

Using synthetic bridge observations and a hostile local child:

- listener admission/closure;
- descriptor close-on-exec;
- no inheritance;
- no reconnect;
- `/proc/<pid>/fd`, `pidfd_getfd`, ptrace/process-memory attempts where the host permits the test;
- failure/suppression yields incomplete evidence, never false completion.

### PF-04 — Capability-peer authority

Using a synthetic isolated plugin peer:

- expected peer admission;
- unadmitted peer rejection;
- duplicate/replay/stale-generation/late response rejection;
- malformed/oversized/code-bearing message rejection;
- identity/integrity loss makes affected work unresolved/ineligible;
- no evidence-channel authority from capability traffic.

### PF-05 — Registration/transform fidelity

Provider-free synthetic plugin fixtures for:

- tool namespace/definition registration;
- opaque execute-handler identity;
- `tool.list` self-identity parity;
- initial `agent.transform` declarative replay;
- registration order.

Dynamic agent-registry reload parity remains outside the initial claim unless separately reviewed.

### PF-06 — Hook/callback fidelity

Provider-free synthetic fixtures for:

- `execute.before` mutation/failure;
- handler return/throw;
- `execute.after` mutation;
- permission mutation;
- Session context/retry mutation;
- cancellation + late response;
- channel loss before/after product completion.

No claim of remote-side-effect rollback is allowed.

### PF-07 — Legacy storage bounds

Synthetic generation-lifetime `get/set/scan` tests proving:

- only the admitted Loom plugin namespace is reachable;
- structural/size limits;
- no arbitrary KV namespace escape;
- no evidence authority.

### PF-08 — Event ordering / root admission / sealing

Provider-free stock OpenCode + synthetic tool/plugin fixture proving or falsifying:

- trusted root Session admission;
- public-event observation path;
- same/different-parent overlapping calls;
- monotonic collector sequence;
- drain and `seal(generation, finalSequence)`;
- sequence gap and post-seal rejection.

### PF-09 — First-sink confidentiality

Synthetic credentials at every actual candidate-controlled first sink:

- literal;
- short;
- JSON escaped;
- nested/deep-key;
- representation-changing echo;
- sensitive-key value;
- boundary-spanning value;
- timeout/error/transport-loss path.

Plaintext at any candidate-controlled first sink is FAIL.

### PF-10 — Pinned Loom provider-free activation

Only after PF-01 through PF-07 pass for the exact candidate checkpoint:

- execute pinned Loom `149406d` in the isolated Loom domain;
- activate the runner bridge in stock OpenCode;
- no model/provider call;
- verify required registrations/capability use can initialize without importing Loom into OpenCode;
- verify plugin-source closure remains unchanged.

This preflight does not authorize SCN-01 through SCN-07 or any model-backed `eval:live`.

## 13. Explicitly not authorized

Authorization A does not permit:

- model/provider inference;
- paid/credentialed inference;
- semantic scenarios SCN-01 through SCN-07;
- general adversarial Wave-4 execution beyond the named provider-free preflights;
- runner→Loom model-backed composition;
- OpenCode modification;
- Loom modification;
- merge to main;
- release/default image pin changes;
- production adoption.

## 14. Review boundary

Before Authorization B:

- Gate 2 independent source/authority review must PASS;
- Gate 2C provider-free preflight must PASS;
- exact source/image/component checkpoint must be recorded.

Review roles:

- **Gate 2:** independent cold source/authority Reviewer;
- **Gate 2C:** independent cold preflight/adversarial Reviewer.

The implementation author must not self-promote an `UNPROVEN` or `NOT RUN` item to PASS.

## 15. Rejection/recovery

The Gate-1 checkpoint discipline remains authoritative.

Any demonstrated rejection condition stops the exact candidate checkpoint. Corrections create a new source/image/component checkpoint and return to earlier gates whenever authority, TCB, capability surface, channel model, scope/seal rule, or first-sink boundary changes.
