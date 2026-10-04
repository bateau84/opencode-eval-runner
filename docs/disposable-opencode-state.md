# Disposable OpenCode state profile

## Purpose

`--opencode-state-profile disposable` is an opt-in lifecycle for provider-free
composition tests that need the **real `opencode-eval-runner invoke` path** but
must not read the caller's installed OpenCode auth or database state.

It does not replace normal invoke behavior and does not change the default image
or the default state-selection rules.

## Exact invocation

For the RSP composition profile:

```bash
opencode-eval-runner invoke \
  --engine podman \
  --image '<reviewed-safety-image@sha256:...>' \
  --transport opencode \
  --opencode-state-profile disposable \
  --require-evidence-safety \
  --evidence-policy-file /private/disposable/inventory.json \
  --workspace /path/to/disposable/workspace \
  --workspace-mode rw \
  --config /path/to/synthetic-provider-config.json \
  --model fixture/mock \
  --prompt-file /path/to/prompt.txt \
  --output /path/to/result.json
```

Loom should add the state-profile option underneath its existing:

```text
bun run eval:live -> scripts/run-evals.py -> opencode-eval-runner invoke
```

No alternate `observe` entrypoint is involved.

## Selection contract

The profile is deliberately explicit:

- `--database` is rejected.
- Ambient `OPENCODE_EVAL_RUNNER_AUTH`, `..._DB`, `..._CONFIG`,
  `..._CONFIG_ROOT`, or `..._MODELS` overrides are rejected before container
  execution.
- Installed default `auth.json`, model catalog, and database paths are not
  selected.
- Default provider credential environment variables are not forwarded merely
  because they exist on the host. Only names explicitly requested with `--env`
  are forwarded.
- `--auth`, `--config`, `--models-catalog`, and `--config-root` remain available
  as explicit synthetic inputs. The RSP policy source states must describe those
  explicit selections exactly.
- No `/seed/opencode.db` mount is present.

The ordinary `default` profile retains the historical fallback behavior.

## Database lifecycle

Inside the disposable container, OpenCode receives a fresh XDG tree under
`/tmp/runtime`. Before any model invocation, the runner executes a provider-free
OpenCode session-list startup against that same environment.

The database must be absent before this startup. OpenCode then owns bootstrap:

1. the pinned OpenCode database layer sees an empty database;
2. it creates the current schema using its generated schema bootstrap;
3. it creates the normal `migration` journal;
4. it records the pinned migration IDs itself.

The runner does **not** create tables or fake migration-journal rows.

For the pinned OpenCode source used by the eval image, the runner then opens the
new database read-only and attests:

- `session_v2`, `credential`, and `migration` tables exist;
- the migration journal contains exactly 48 migrations;
- first migration is `20260127222353_familiar_lady_ursula`;
- last migration is `20260923013825_project_time_active`;
- there are zero Session rows before inference;
- there are zero credential rows before inference.

A mismatch fails before the model/provider request.

If `--expected-plugin` is used, its activation barrier creates a temporary
Session. Under the disposable profile that preflight runs against a **separate
temporary OpenCode HOME/data/cache/state tree** while reusing only the reviewed
config/plugin root. Its temporary state is deleted afterward. The production
disposable database is re-attested after plugin preflight and before the actual
model/provider request, so its reported zero Session/credential counts remain
true at the inference boundary.

This avoids the unsupported hand-built-schema path where a pre-created
`session` table with no matching migration journal makes OpenCode replay the
first migration and fail with `table session already exists`.

## Result acknowledgement

Successful disposable execution adds:

```json
{
  "runtime_state": {
    "schema": "opencode-eval-runner/runtime-state/v1",
    "profile": "disposable",
    "database_source": "runtime-bootstrap",
    "database_created": true,
    "database_seed_present": false,
    "auth_source": "none",
    "session_rows_before_inference": 0,
    "credential_rows_before_inference": 0,
    "migration_count": 48,
    "first_migration": "20260127222353_familiar_lady_ursula",
    "last_migration": "20260923013825_project_time_active"
  }
}
```

`auth_source` may be `explicit` only when an explicit synthetic `--auth` seed
was selected.

In RSP mode `runtime_state` is a reviewed protocol field and receives an
`exact` disposition. The host safety adapter rejects disposable replies that do
not carry the matching attestation.

## Inventory agreement

For `source-path-roles/v1`, the disposable profile requires policy source states
to match actual runner selection:

- `credential_seed`: `not_selected`;
- `auth`: `not_selected` unless explicit `--auth`, then `complete`;
- `config`: `not_selected` unless explicit `--config`, then `complete`;
- `models`: `not_selected` unless explicit `--models-catalog`, then `complete`;
- `config_root`: `not_selected` unless explicit `--config-root`, then `complete`.

An incomplete policy or a contradictory source declaration is rejected before
container/model execution. The runner does not upgrade incomplete inventory by
inference.

## Scope

This profile proves disposable OpenCode host-state bootstrap for composition
tests. It does not establish protected-capture acceptance, same-process plugin
isolation, signing, or safety for arbitrary tool-created files.
