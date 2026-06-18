# Branch Writer Stability Audit

## Current audit focus

This audit covers the current Streamlit + React component + local SSE server implementation.

The app now includes:

- Streamlit chat UI
- React latest assistant component
- local FastAPI SSE streaming server
- model discovery
- keyword retry filter
- post-generation LLM validator
- intervention history / insertion reuse

## High-risk areas found

### 1. Session state schema drift

Streamlit keeps old session state objects across code reloads. If `LlmSettings` gains new fields, older session objects can miss attributes and crash the sidebar or generation flow.

Mitigation:

- `initialize_state()` now migrates old `llm_settings` objects into the current `LlmSettings` dataclass shape.
- Nested dictionaries such as `kw_filter` and `validator` are also repaired when fields are missing.

### 2. Streaming server dependencies missing

The app imports `fastapi` and `uvicorn` through `branch_writer.streaming_server`, but these packages were not listed in `requirements.txt`.

Mitigation:

- Added `fastapi>=0.110` and `uvicorn>=0.27`.

### 3. SSE server lifecycle

The server was guarded by Streamlit session state. Multiple browser sessions or reloads could attempt to start another uvicorn server on the same port.

Mitigation:

- `start_server()` now uses process-level globals and a lock so the SSE server starts once per Python process.

### 4. Intervention streaming restart loop

React compared `interventionData` by object identity. Streamlit recreates the object on rerun, so the component could treat the same intervention as a new one and restart streaming.

Mitigation:

- The component now computes a stable stream key from the semantic stream inputs instead of relying on object identity.

### 5. Stuck generating state on frontend stream errors

The component previously logged stream errors but did not reliably notify Python. This could leave `is_generating=True` and make the app look stuck.

Mitigation:

- The component now emits a `streaming_error` event and also emits a compatible `streaming_done` fallback to release older Python handlers from generating state.

### 6. Intervention insertion / overlap handling

Intervention streaming must use `assistantPrefix + insertion` as the base. If only `assistantPrefix` is used for overlap stripping or frontend accumulation, insertion text can disappear or repeated boundary text can appear during streaming.

Mitigation:

- The streaming server now uses `base_content = assistant_prefix + insertion` for overlap stripping.
- Token events include `fullContent` so the frontend can display the server-corrected content rather than locally appending raw duplicated chunks.

### 7. Browser offset vs Python offset

JavaScript offsets are UTF-16 code-unit based. Python slicing uses Unicode code points. Emoji and some non-BMP characters can cause offset drift.

Mitigation:

- Line selection now computes offsets with `Array.from(...)`, which approximates Python code point indexing more closely than raw JS string `.length`.

## Remaining risks

### App-level `streaming_error` handling

The frontend emits `streaming_error`, but older Python handlers may ignore it. A compatibility fallback emits `streaming_done`, which prevents stuck generation, but a dedicated Python handler should be added later so the UI can show cleaner error messages.

### Fine-grained caret selection

The current latest assistant component primarily supports line-based selection. This is more stable than free caret selection but less precise. If exact arbitrary-character intervention is restored, JavaScript-to-Python offset conversion must remain explicit.

### Streaming server port ownership

The process-level lock prevents repeated starts inside one Python process. If another external process already owns the same port, uvicorn will still fail. A future improvement should probe the port before starting.

### Validation retry loops

Keyword retry and LLM validation can trigger regeneration. These flows must keep explicit retry ceilings and must clear generation state on terminal failure.

## Recommended manual regression tests

1. Start app after `pip install -r requirements.txt` from a clean virtualenv.
2. Build React component and start Streamlit.
3. Generate a normal response and confirm streaming completes.
4. Select a line and regenerate from that point.
5. Insert text and continue from that point.
6. Force LM Studio / Ollama offline and confirm the UI does not stay stuck in generating state.
7. Use text containing emoji and confirm intervention position is not shifted.
8. Open the app in two browser tabs and confirm the SSE server does not try to start twice.
