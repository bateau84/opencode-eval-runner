---
name: python-error-handling
description: "Idiomatic exception handling in Python — catching narrowly, custom exception hierarchies, exception chaining with `raise ... from`, try/except/else/finally, context managers for cleanup, re-raising vs wrapping, EAFP vs LBYL, and mapping domain errors to HTTP responses. Use when designing error flow, defining custom exceptions, handling failures from I/O or external APIs, deciding what to catch, or cleaning up resources reliably. Also use when the user mentions exceptions, try/except, raise, error handling, or custom errors in Python."
license: MIT
metadata:
  author: Bateau
  version: "1.2.0"
---

> Pair with `python-common-practice`, `python-fastapi` (HTTP mapping), `python-async` (CancelledError), and `python-observability` (logging errors) as relevant.

**Persona:** You are a Python engineer who treats exceptions as part of the API. You catch what you can handle and let the rest propagate to someone who can.

# Error Handling

Python prefers **EAFP** ("easier to ask forgiveness than permission") — try the operation and handle the exception rather than pre-checking. Pre-checks race with reality; the exception is the truth.

```python
# ✓ EAFP — one atomic attempt
try:
    return cache[key]
except KeyError:
    return load(key)

# ✗ LBYL — racy for I/O; fine when a simple guard avoids broad catching
if key in cache:
    return cache[key]
```

**EAFP is a convention, not a universal rule.** Broad catches can hide failures from both humans and agents. Prefer EAFP where the exception type is known and the catch is narrow; inspect the framework's actual error behavior rather than guessing at its hierarchy. Use explicit checks where they express the contract more clearly, while accounting for race conditions between checking and acting.

## Catch narrowly

Catch the **specific** exception you can handle. A bare `except:` or `except Exception:` swallows bugs, `KeyboardInterrupt`, and (in async) cancellation — turning a crash you'd fix into silent wrong behavior.

```python
# ✗ Bad — hides programming errors and makes debugging impossible
try:
    sync_playlist(p)
except Exception:
    pass

# ✓ Good — handle the failures you expect; let the rest surface
try:
    sync_playlist(p)
except (httpx.HTTPError, TimeoutError) as e:
    log.warning("sync failed for %s: %s", p.id, e)
    metrics.errors_total.inc()
```

If you must catch broadly (a top-level worker loop that must not die), log with `log.exception(...)` to capture the traceback, then continue or re-raise — never `pass`.

## Agent navigability — narrow exception surfaces

Prefer narrow exception surfaces: agents catching from broad hierarchies must guess error object shapes — a predictable interface failure, not a model failure.

**Framework guidance — catch the specific exception, not the family:**

| Framework | Broad (avoid) | Narrow (prefer) |
| --- | --- | --- |
| `requests` / `httpx` | `requests.exceptions.RequestException` | `httpx.TimeoutException`, `httpx.HTTPStatusError` |
| `django` ORM | `django.core.exceptions.ObjectDoesNotExist` | `MyModel.DoesNotExist` |
| SQLAlchemy | `sqlalchemy.exc.SQLAlchemyError` | `sqlalchemy.exc.IntegrityError`, `sqlalchemy.exc.OperationalError` |

Wrap framework exceptions at the boundary into domain exceptions. This collapses the broad hierarchy into a predictable, narrow surface for all downstream code.

## Custom exceptions — a hierarchy with a common base

Give your package one base exception; specific errors subclass it. Callers can then catch the whole family or a specific case. This is what lets a FastAPI handler map *all* your domain errors in one place.

```python
class SortarrError(Exception):
    """Base for all sortarr domain errors."""

class AuthRequiredError(SortarrError): ...
class QuotaExceededError(SortarrError): ...
```

Subclass the most specific stdlib type when it fits (`ValueError`, `LookupError`); invent a new hierarchy only for domain concepts the stdlib doesn't model.

## Chain exceptions — preserve the cause

When you wrap a low-level error in a domain one, use `raise ... from` so the original traceback survives. Bare `raise NewError(...)` inside an `except` hides the root cause.

```python
try:
    resp = await client.get(url)
    resp.raise_for_status()
except httpx.HTTPStatusError as e:
    raise QuotaExceededError("YouTube quota hit") from e   # ✓ keeps the cause
```

To deliberately suppress the context, use `from None` — and only when the cause is genuinely noise.

This is also how you keep storage details out of the API: the **repository** catches the driver error and raises a domain error, so the route never imports `sqlite3` or sees a driver exception.

```python
import sqlite3

def save_rule(self, rule: Rule) -> None:
    try:
        self._con.execute("INSERT INTO rules (id, pattern) VALUES (?, ?)", (rule.id, rule.pattern))
    except sqlite3.IntegrityError as e:
        raise DuplicateRuleError(rule.id) from e   # domain error — a handler maps it to 409
```

## else and finally

`else` runs only when `try` didn't raise — put success logic there. `finally` always runs; prefer a **context manager** over manual try/finally.

```python
with open_connection(db_path) as conn:   # closed on any exit path
    conn.execute(...)
```

Write your own with `contextlib.contextmanager` or `__enter__/__exit__`; use `async with` for async resources.

## Re-raise, don't return error sentinels

Returning `None`/`-1`/`False` to signal failure forces every caller to remember to check, and the type checker can't help. Raise instead — the failure can't be silently ignored. (Return `X | None` only when "not found" is a *normal, expected* outcome, not an error.)

In async code, **never swallow `asyncio.CancelledError`** — re-raise it so shutdown and timeouts work (→ See `python-async`).

## Mapping to HTTP

In FastAPI, register one exception handler per domain base class rather than try/except in every route (→ See `python-fastapi`):

```python
@app.exception_handler(AuthRequiredError)
async def _auth(_: Request, exc: AuthRequiredError):
    return JSONResponse(status_code=401, content={"detail": str(exc)})
```

Never leak a stack trace or internal message to a client — log the detail server-side, return a clean message.

## Common mistakes

| Mistake | Fix |
| --- | --- |
| `except Exception: pass` | Catch the specific type; if broad, `log.exception` then re-raise. |
| Bare `raise FooError()` inside `except` | `raise FooError() from err` to preserve the cause. |
| `except:` (bare) | Catches `KeyboardInterrupt`/`SystemExit`/cancellation too — name the type. |
| Manual try/finally for cleanup | Use a context manager (`with`). |
| Returning `None`/`-1` for errors | Raise an exception; reserve `None` for expected absence. |
| Swallowing `CancelledError` in async | Re-raise it. |
| Leaking tracebacks to API clients | Log server-side; return a sanitized message. |
| EAFP with broad `except` on a framework hierarchy | Prefer LBYL guard or narrow catch; wrap at the boundary into a domain exception. |

**Diagnose:** 1- `ruff check` (bugbear `B`) — flags overly broad `except` and `raise` without `from` 2- read the full traceback (don't truncate) — the chained `from` cause usually names the real failure.

## References

- [Errors and Exceptions — tutorial](https://docs.python.org/3/tutorial/errors.html)
- [Built-in Exceptions](https://docs.python.org/3/library/exceptions.html)
- [Glossary — EAFP / LBYL](https://docs.python.org/3/glossary.html)
- [Alexis King — Parse, don't validate](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/)
