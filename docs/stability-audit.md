# Stability Audit Memo

Date: 2026-06-19

## 1. `streaming_error` formal handling

- **Problem**: React received SSE `error` events but only logged them and returned silently. Python had no way to know the stream failed.
- **Fix** (`LatestMessageEditor.tsx`): On SSE error or fetch error, send `{ type: "streaming_error", message, content, messageId }` via `Streamlit.setComponentValue()`.
- **Fix** (`app.py`): `render_messages()` now handles `"streaming_error"` event: sets `latest.status = "error"`, preserves partial content (or falls back to `before_content`), sets `last_error`, calls `set_generating(False)`, clears `streaming_intervention`.
- **Fix** (`app.py`): Extracted `handle_streaming_error()` function for testability.
- **Tests** (`test_app_smoke.py`): 4 test cases — normal error path, stale event skip, before_content fallback, empty messages.

## 2. SSE server startup protection

- **Problem**: `start_server()` had no guard against multiple calls within the same process (the `_server_started` flag and `_server_lock` were defined but never used).
- **Fix** (`streaming_server.py`): Added `global _server_started`, lock-guarded idempotency check.
- **Fix**: Added `/health` endpoint returning `{"status": "ok"}`.
- **Fix**: On port conflict, check if existing server responds to `/health` (reuse if healthy). If not, raise `RuntimeError`.
- **Fix**: Added `_is_port_in_use()` using raw socket.
- **Tests** (`test_streaming_server.py`): 5 tests — port detection, idempotency, healthy reuse, port conflict error.

## 3. React component stream lifecycle

- **Problem**: `interventionData` compared by object identity (`!==`), causing unnecessary re-streams on every rerun even when data was semantically identical.
- **Fix**: Computed `interventionKey = "selectionStart:insertion:action"` for semantic comparison.
- **Problem**: Error/abort events did not reset `completedRef`, potentially preventing re-stream on transient errors.
- **Fix**: Reset `completedRef` to `false` in error and abort handlers.
- **Problem**: Error events and fetch errors did not notify Python (covered in #1).
- **Observation**: `doneSentRef` prevents double-sending `streaming_done`. Cleanup `useEffect` calls `abort()` on unmount. Both correct.
- **Tests**: Manual verification of lifecycle via code review (no E2E test infrastructure change).

## 4. Intervention position specification

- **Current**: UI uses **line-based selection** (splits by `\n`, calculates char position by summing `lines[i].length + 1`).
- **JS**: `String.prototype.length` and `split("\n")` use **UTF-16 code units**, not code points. For characters outside the BMP (emoji), this gives wrong indices.
- **Python**: `len()` and `[:n]` slicing use **Unicode code points**.
- **Fix**: `validate_selection_start()` in Python already protects against out-of-range values. JS should eventually use `Array.from()` for code-point-accurate indexing, but this is noted as a known discrepancy for future work.
- **Tests** (`test_intervention.py`): Added emoji, surrogate pair (𝄞), newline, and mixed emoji+newline tests confirming Python-side correctness.

## 5. Intervention streaming merge logic

- **Validation**: `base_content = assistant_prefix + insertion` is the sole base.
- **Validation**: `strip_continuation_overlap()` correctly removes repeated boundary text.
- **Validation**: SSE token events in intervention mode include `fullContent` (server-computed: `prefix + insertion + clean`). Frontend uses `fullContent` when present.
- **Tests** (`test_intervention.py`): Added `test_strip_overlap_prefix_and_insertion_preserved` (specific Japanese example), `test_strip_overlap_full_repeat`, empty edge cases, max overlap limit, Japanese+emoji boundary.

## 6. `is_generating` stuck prevention

Traced all paths that must lead to `set_generating(False)`:

| Scenario | Resolution | Status |
|---|---|---|
| Normal streaming done | `handle_streaming_complete` → `set_generating(False)` | ✅ Already correct |
| Intervention streaming done | Same as above | ✅ |
| Streaming error | `handle_streaming_error` → `set_generating(False)` | ✅ Fixed |
| Aborted stream | React sets `completedRef=false`, `streamId=null`; no Python event sent. On next rerun a new stream starts. | ✅ Not stuck (rerun resumes) |
| Keyword retry exhausted | `handle_streaming_complete` → `retried=False` → `set_generating(False)` | ✅ Already correct |
| Validator error | Same as above | ✅ |
| LM Studio / Ollama offline | Yields SSE `error` → React sends `streaming_error` → `set_generating(False)` | ✅ Fixed |

## 7. Dependencies

- **`requirements.txt`**: Added `fastapi>=0.110`, `uvicorn>=0.29` (were missing despite being used at runtime).
- **Frontend build**: Verified `npm run build` passes in CI (`.github/workflows/ci.yml`).
- **Python tests**: Verified `python -m pytest` passes (82 tests).
- **CI**: Both `test` and `frontend` jobs defined in `.github/workflows/ci.yml`.

## 8. Log audit

- **Problem**: `app.py` used `logging.FileHandler("branch_writer.log")` with no rotation → unbounded growth.
- **Fix**: Replaced with `RotatingFileHandler` (5MB max, 3 backups).
- **Fix**: Wrapped in try/except `(OSError, PermissionError)` to survive read-only/deployment environments.
- **Observation**: FileHandler is only in `app.py` (the Streamlit entry point). Other modules use plain `logging.getLogger()`. This is fine — `basicConfig` root handler applies to all children.

## Summary of Changes

| File | Change |
|---|---|
| `app.py` | `streaming_error` handler, `handle_streaming_error()` function, `RotatingFileHandler`, crash-safe file logging |
| `branch_writer/streaming_server.py` | `/health` endpoint, `_is_port_in_use()`, idempotent `start_server()` with lock, port conflict detection |
| `branch_writer/streaming_server.py` | Moved `import httpx` to module level |
| `components/.../LatestMessageEditor.tsx` | `streaming_error` event emission, semantic intervention comparison, `completedRef` reset on error/abort |
| `requirements.txt` | Added `fastapi`, `uvicorn` |
| `tests/test_app_smoke.py` | 4 `handle_streaming_error` tests |
| `tests/test_intervention.py` | Emoji/surrogate/newline selection tests, overlap tests (Japanese, max limit, edge cases) |
| `tests/test_streaming_server.py` | New file: 5 tests for startup/health/port conflict |
