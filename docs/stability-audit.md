# Branch Writer v0 Stability Audit

## 1. Scope

This audit covers runtime stability risks observed during local testing:

- Streamlit rerun loops
- custom component repeated events
- app crashes from unexpected exceptions
- heavy rerenders from long chat histories
- local LLM request hangs
- React component resizing overhead

---

## 2. Findings

## 2.1 Duplicate intervention event processing

### Risk

Streamlit custom components keep returning their last value across reruns. If the app processes the same intervention event after every rerun, the latest assistant message can be repeatedly regenerated or reverted.

### Mitigation

The app now computes an intervention request identifier and stores the last handled identifier in session state.

Duplicate events are ignored and do not trigger another `st.rerun()`.

Relevant files:

- `app.py`
- `branch_writer/state.py`

---

## 2.2 Unexpected exceptions can crash the app

### Risk

Only expected `LlmError`, `TypeError`, and `ValueError` were handled in generation and intervention flows. Other exceptions could bubble into Streamlit and show a hard crash.

### Mitigation

Defensive exception guards were added around normal generation and intervention generation. Unexpected errors are converted into visible app errors instead of crashing the app process.

Relevant file:

- `app.py`

---

## 2.3 UI remains interactive during generation

### Risk

A user can trigger UI controls while generation is already running. In Streamlit this is usually serialized, but stale inputs and reruns can still create confusing state transitions.

### Mitigation

Core sidebar inputs, manual intervention buttons, and chat input are disabled while generation is active.

Relevant file:

- `app.py`

---

## 2.4 Long chat history causes heavy rerenders

### Risk

Every rerun re-renders the whole chat history. Long creative sessions can make the app sluggish.

### Mitigation

The app now renders only the most recent N messages. The default is 80. The limit can be changed in the sidebar.

This affects rendering only. It does not currently trim LLM context.

Relevant file:

- `app.py`

---

## 2.5 No quick recovery from bad state

### Risk

If session state becomes unstable during development, the user has to restart Streamlit or clear browser/session state manually.

### Mitigation

A `Clear chat` button was added. It clears chat messages, undo history, error state, generation state, and the last handled intervention request ID while preserving LLM settings.

Relevant file:

- `app.py`

---

## 2.6 Local LLM requests can hang too long

### Risk

A fixed 600-second request timeout can make the app appear frozen when a local model stalls.

### Mitigation

Request timeout is now configurable from the sidebar. The default is 180 seconds, with an allowed range from 5 to 900 seconds.

Relevant files:

- `branch_writer/config.py`
- `branch_writer/llm.py`
- `app.py`

---

## 2.7 React component height updates on every render

### Risk

Calling `Streamlit.setFrameHeight()` on every React render can increase frontend churn and contribute to jitter.

### Mitigation

The component now calls `Streamlit.setFrameHeight()` only when message content or insertion text changes.

Selection state updates are also guarded so repeated identical selection values do not trigger extra React state updates.

Relevant file:

- `components/latest_message_editor/frontend/src/LatestMessageEditor.tsx`

---

## 3. Remaining Risks

## 3.1 Synchronous LLM generation

Generation still runs synchronously in the Streamlit request cycle. This is acceptable for v0 but can still feel heavy with slow models.

Possible future improvement:

- streaming output
- background worker
- cancel generation button

## 3.2 LLM context can grow indefinitely

Rendering is now capped, but LLM context still uses the full message history. Long sessions can eventually exceed model context or slow requests.

Possible future improvement:

- configurable LLM context message limit
- manual context trimming
- story summary memory

## 3.3 Component event IDs are still Python-guarded

The app-side duplicate guard is the primary protection. A future improvement is to emit explicit unique `requestId` values from the React component for every button click.

---

## 4. Current Stability Posture

The v0 app now has basic guards against:

- repeated intervention rerun loops
- hard crashes from unexpected generation exceptions
- expensive full-history rerenders
- local LLM request hangs
- stale development state

The next recommended validation step is local testing with:

1. manual fallback intervention UI
2. built React component intervention UI
3. repeated regenerate / undo cycles
4. long conversation history
5. intentionally stopped LM Studio server
