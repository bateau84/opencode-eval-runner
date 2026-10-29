---
name: python-testing
description: "Production-ready Python tests with pytest — fixtures, parametrize, pytest-asyncio for async tests, monkeypatch, tmp_path, conftest.py scoping, markers, coverage, targeted mutation testing, and testing FastAPI/httpx code. Use when writing or reviewing pytest tests, setting up fixtures, testing async code, parametrizing cases, mocking dependencies, or configuring pytest in pyproject.toml. Also use when the user mentions pytest, unittest, fixtures, mocking, or test coverage in Python."
license: MIT
metadata:
  author: Bateau
  version: "1.2.0"
---

> Pair with `python-common-practice` for shared verification guidance.

**Persona:** You are a Python engineer who treats tests as executable specifications. You write tests to constrain behavior, not to chase a coverage number.

# Python Testing with pytest

Tests pin behavior. A good test fails for exactly one reason and names that reason. Prefer plain `assert` (pytest rewrites it for rich diffs) over `unittest`'s `assertEqual` zoo.

## Structure and naming

- Files `test_*.py`, functions `test_*`, one behavior per test. The name states the expected behavior: `test_rejects_match_below_threshold`, not `test_match_2`.
- **Arrange / Act / Assert** with blank lines between phases. If a test needs comments to explain phases, it is doing too much.
- Put shared fixtures in `conftest.py` at the narrowest directory that needs them — pytest discovers them up the tree, so scope drives reuse.

## Fixtures over setUp

Fixtures are dependency injection for tests: request what you need, get teardown for free via `yield`.

```python
import pytest

@pytest.fixture
def settings(tmp_path):
    # tmp_path is a per-test directory — no manual cleanup, no shared state
    return Settings(database_file=str(tmp_path / "test.db"))

@pytest.fixture
def repo(settings):
    conn = open_connection(settings.database_file)
    run_migrations(conn)
    yield Repository(conn)   # everything after yield is teardown
    conn.close()
```

Scope deliberately: default `function` (fresh per test, safest). Use `module`/`session` only for expensive, read-only setup — shared mutable fixtures leak state and create order-dependent flakiness.

## Parametrize instead of loops

A loop inside one test stops at the first failure and reports one case. `parametrize` runs each case independently and names it.

```python
@pytest.mark.parametrize(
    ("title_a", "title_b", "expected"),
    [
        ("Song (Live)", "Song", True),
        ("Song", "Totally Other", False),
    ],
    ids=["live-suffix-matches", "different-titles-reject"],
)
def test_fuzzy_match(title_a, title_b, expected):
    assert is_match(title_a, title_b) is expected
```

## Async tests (pytest-asyncio)

When `pyproject.toml` sets `asyncio_mode = "auto"`, every `async def test_*` runs on the event loop with no decorator. Without it, mark each one `@pytest.mark.asyncio`. Know which mode the repo uses before adding tests.

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

```python
async def test_fetches_playlist(httpx_mock):
    httpx_mock.add_response(json={"items": []})
    result = await client.get_playlist("abc")
    assert result == []
```

Async fixtures use the same `async def` + `yield` shape. Do not call `asyncio.run()` inside a test — you are already on the loop; nesting raises `RuntimeError`.

## Mocking — at the boundary, not the internals

Mock I/O and external services (YouTube/Spotify APIs, the network), not your own pure functions. Prefer real objects (the `tmp_path` SQLite DB) over mocks when they are cheap — sortarr's web tests run against a real in-process SQLite DB for exactly this reason.

```python
def test_skips_on_api_error(monkeypatch):
    def boom(*_): raise TimeoutError
    monkeypatch.setattr(client, "get_playlist", boom)
    # monkeypatch auto-reverts after the test — no manual cleanup
```

- `monkeypatch` for attributes/env/dicts (auto-reverted).
- `unittest.mock.AsyncMock` for awaitables; a plain `Mock` returns a coroutine-less value and the `await` fails.
- For httpx, prefer `pytest-httpx`'s `httpx_mock` or `respx` over patching internals — patch the transport, not the call site.

## Coverage and CI

```bash
pytest                       # all tests
pytest -k "match and not slow"   # filter by name expression
pytest -x --ff               # stop at first failure, failed-first ordering
pytest -q tests/test_match.py::test_fuzzy_match   # one test
pytest --cov=src --cov-report=term-missing        # coverage with missing lines
```

Coverage is a floor, not a goal: 100% coverage with no assertions tests nothing. Chase uncovered *branches* that carry risk, not the percentage.

## Targeted mutation testing

After the relevant suite is green, consider a few mutations for changed or high-risk comparisons, guards, exception paths, and state updates. Mutation testing changes production code to challenge the tests; coverage only shows execution. Neither a whole-repository run nor a fixed mutation score is required.

**Manual fallback:** preserve current edits and use an isolated test copy containing the candidate. Run the selected pytest cases and confirm they actually collected and passed rather than only skipping/xfailing. Change one production behavior with tests fixed, rerun, and inspect the failing assertion. Verify imports resolve to the mutated source, not another installed package or a monkeypatched replacement. An import/setup/type-check failure or unexplained timeout is not an assertion-based kill. For a real survivor, add a contract-derived test and prove it rejects the mutant. Restore only the probe change, inspect the diff, and rerun the relevant suite without discarding unrelated work.

**Automation:** [mutmut](https://mutmut.readthedocs.io/en/latest/) is an option for a compatible pytest project. Prefer the repository's pinned environment. Check the installed version's help and documentation before choosing source paths, test selection, timeout/concurrency settings, or configuration keys; these can differ between versions. Bound the scope before using `mutmut run`, then inspect outcomes with `mutmut browse`. Verify copied fixtures/configuration and imported source. Do not treat cached/incremental results as a fresh run when dependencies, configuration, fixtures, or the candidate changed without the tool accounting for them.

`mutmut apply` writes a mutant into source. Use it only in an isolated, recoverable copy and verify restoration even after interruption. Do not install tools or publish reports merely because the command appears here; a safe manual sample or a stated limitation is preferable to unsupported setup.

Record candidate, tool/Python versions, source/test scope, budget, baseline, actual outcomes, and final restoration in existing verification notes. Triage survivors into real gaps, missing execution, justified equivalence/out-of-scope behavior, or unresolved cases. Keep invalid/timeout/error/untested outcomes visible and report any score with its definition and denominator. Never weaken expected values, skip a hard test, or add an unjustified exclusion to raise that score. `test-driven-development` contains the shared method and deeper triage guidance.

## Common mistakes

| Mistake | Fix |
| --- | --- |
| `async def` test with no `asyncio_mode`/marker | Test is silently skipped or errors. Set `asyncio_mode = "auto"` or mark it. |
| `Mock()` where an `await` happens | Use `AsyncMock`; a sync Mock isn't awaitable. |
| `session`-scoped mutable fixture | Tests leak state and depend on order. Default to `function` scope. |
| Loop over cases in one test | Use `parametrize` so each case runs and reports independently. |
| Mocking your own pure logic | Mock only I/O boundaries; test real logic directly. |
| Shared session/file DB across tests | Give each test its own DB via `tmp_path` (function scope); a shared file leaks state and throws `database is locked` under parallel workers. |
| `assertEqual`/`TestCase` boilerplate | Use plain `assert`; pytest rewrites it with rich diffs. |

## References

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [pytest-httpx](https://github.com/Colin-b/pytest_httpx)
