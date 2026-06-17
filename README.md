# Branch Writer

Branch Writer is a local-first AI writing chat UI that lets you interrupt the latest assistant response from any point, insert your own text, and regenerate the continuation.

チャットして、AIの返答の途中に割り込んで、書き換えて、続きを紡ぐ。

## Features

- Normal chat with non-blocking streaming
- **Regenerate from here** — discard content after any cursor position and regenerate
- **Insert and continue** — insert your own text at any point, then have the AI continue
- **Per-message token counts** — estimated token/character count for each message
- **Context usage display** — real-time input/output/limit with color-coded warnings
- **Auto model discovery** — detects available models from Ollama / LM Studio
- **Auto base URL detection** — works out of the box with Ollama and LM Studio defaults
- **Model-aware defaults** — context window and max tokens auto-set per model
- **Insertion log** — reuse previously inserted text
- **Undo last intervention** — revert the most recent intervention
- **OpenAI-compatible local LLM support** — Ollama, LM Studio, llama.cpp, etc.

## Requirements

- Python 3.12+
- A local LLM server (Ollama, LM Studio, etc.)

## Installation

```powershell
git clone https://github.com/Unjuno/branch-writer.git
cd branch-writer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## Usage

1. Start your local LLM server (Ollama, LM Studio, etc.)
2. Run `streamlit run app.py`
3. Click **🔄 モデル一覧を再取得** in the sidebar to auto-detect your LLM
4. Select a model and start chatting

The API Base URL is optional — if left empty, Branch Writer automatically probes Ollama (`localhost:11434`) and LM Studio (`localhost:1234`).

## Settings

| Setting | Default | Description |
|---|---|---|
| API Base URL | Auto (Ollama / LM Studio) | LLM endpoint; auto-detected if empty |
| API Key | `""` | Authentication key |
| Model | auto-discovered | Model selection |
| Temperature | `0.7` | Generation temperature |
| Max Tokens (output) | per-model default | Max output tokens |
| Context Window | per-model default | Model's total context window |

## Testing

```bash
python -m pytest
```

## Architecture

```text
Streamlit app (Python)
  |
  +-- branch_writer/
        - config.py        — LLM settings & model capabilities DB
        - llm.py           — OpenAI-compatible API client
        - intervention.py  — regenerate / insert logic
        - messages.py      — chat message model
        - state.py         — session state management
        - model_discovery/ — MCP-based model discovery (Ollama / LM Studio)
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
- No persistence

## License

MIT License.
