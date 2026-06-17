# Branch Writer

Branch Writer is a local-first AI writing chat UI that lets you interrupt the latest assistant response from any point, insert your own text, and regenerate the continuation.

チャットして、AIの返答の途中に割り込んで、書き換えて、続きを紡ぐ。

## Features

- Normal chat with streaming output
- **Non-blocking streaming** — generation runs in the background; you can intervene mid-generation
- **Regenerate from here** — discard content after any cursor position and regenerate
- **Insert and continue** — insert your own text at any point, then have the AI continue
- **Context usage display** — real-time sidebar showing input tokens, output headroom, and model context limit with color-coded warnings
- **Per-message token counts** — each message shows estimated token/character count
- **Auto model discovery** — detects available models from Ollama / LM Studio
- **Insertion log** — reuse previously inserted text
- **Undo last intervention** — revert the most recent intervention
- **OpenAI-compatible local LLM support** — works with Ollama, LM Studio, llama.cpp

## Local LLM Assumption

v0 targets local LLMs exclusively.

Supported endpoints:

- Ollama (OpenAI-compatible endpoint)
- LM Studio local server
- llama.cpp server
- Any OpenAI-compatible local proxy

### Settings

| Setting | Default | Description |
|---|---|---|
| API Base URL | `http://localhost:11434/v1` | LLM endpoint |
| API Key | `""` | Authentication key |
| Model | auto-discovered | Model selection |
| Temperature | `0.7` | Generation temperature |
| Max Tokens (output) | `4096` | Max output tokens |
| Context Window | `8192` | Model's total context window |

## Installation

```bash
git clone https://github.com/Unjuno/branch-writer.git
cd branch-writer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## Testing

```bash
python -m pytest
```

## Optional: Build the React Intervention Component

Without building the React component, the app falls back to a manual `selectionStart` UI. The fallback is fully functional.

To use the richer React/TypeScript editor:

```bash
cd components/latest_message_editor/frontend
npm install
npm run build
cd ../../..
streamlit run app.py
```

For frontend development, start the component dev server:

```bash
cd components/latest_message_editor/frontend
npm install
npm run dev
```

Then, in another shell:

```bash
BRANCH_WRITER_COMPONENT_URL=http://localhost:5173 streamlit run app.py
```

On Windows PowerShell:

```powershell
$env:BRANCH_WRITER_COMPONENT_URL="http://localhost:5173"
streamlit run app.py
```

## Architecture

```text
Streamlit app (Python)
  |
  +-- LatestMessageEditor (React/TypeScript custom component)
  |     - Displays latest assistant message
  |     - Captures cursor position
  |     - Emits intervention events
  |
  +-- branch_writer/
        - config.py        — LLM settings model
        - llm.py           — OpenAI-compatible API client
        - intervention.py  — regenerate / insert logic
        - messages.py      — chat message model
        - state.py         — session state management
```

## Security Notes

Do not commit API keys. The following files should remain local:

```text
.env
.env.local
.streamlit/secrets.toml
```

## Known v0 Limitations

- Only the latest assistant message can be intervened on
- Past messages are frozen (no editing)
- No branch tree UI
- No automatic contradiction detection
- No natural-ending guard
- No persistence
- Intervention continuation still uses synchronous streaming

## License

MIT License.
