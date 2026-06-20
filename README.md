<p align="center">
  <b>Branch Writer</b><br>
  <i>Co-writing editor for local LLMs</i><br>
  Steer AI text generation in real time — interrupt, redirect, and continue from any cursor position.
</p>

<p align="center">
  <a href="https://github.com/Unjuno/branch-writer/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://github.com/Unjuno/branch-writer/actions/workflows/ci.yml"><img src="https://github.com/Unjuno/branch-writer/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+"></a>
  <a href="https://nodejs.org/"><img src="https://img.shields.io/badge/node-20%2B-green" alt="Node 20+"></a>
  <a href="https://ollama.com/"><img src="https://img.shields.io/badge/ollama-✓-orange" alt="Ollama"></a>
  <a href="https://streamlit.io/"><img src="https://img.shields.io/badge/built%20with-Streamlit-ff4b4b" alt="Streamlit"></a>
</p>

---

## Demo

<video src="https://github.com/Unjuno/branch-writer/raw/main/demo.mp4" controls width="100%"></video>

*2x speed — 4-minute original: [demo.mp4](demo.mp4)*

---

## What is Branch Writer?

Branch Writer is **not** a ChatGPT wrapper. It replaces the traditional "submit prompt → wait → read response" loop with a **synchronous co-writing model**: you can interrupt an ongoing LLM stream at any cursor position, truncate the suffix, and redirect the generation — all in real time.

The goal is not to offload writing entirely to AI, but to **pilot the generation process** like a co-pilot: the AI writes ahead, and you steer.

---

## Key Features

- **Cursor-level intervention** — Place the cursor anywhere in the latest assistant message, type a redirect, press Enter. The suffix is discarded and the AI regenerates from that point.
- **Real-time streaming** — Tokens appear as they are generated. Textarea focus pauses display updates but accumulation continues.
- **Interrupt mid-stream** — Even during active generation, pressing Enter aborts the current stream and immediately starts a new one.
- **Snapshot anchoring** — On intervention, the full text is snapshotted. Editing does not change the anchor until Enter is pressed.
- **Undo** — Revert the last intervention from the sidebar.
- **Escape to reset** — Pressing Escape restores the textarea to the latest streamed content without stopping the stream.
- **IME guard** — Triple-check prevents accidental regeneration during Japanese/Chinese IME composition.
- **Stale stream guards** — Unique stream keys on every generation; events from stale streams are silently ignored.
- **Local-first** — No database, no cloud, no telemetry. Everything runs on your machine.

---

## Quick Start

### Prerequisites

- **Python 3.11+**
- **Ollama** ([install](https://ollama.com/download)) or any OpenAI-compatible endpoint (LM Studio, llama.cpp server, vLLM, SGLang)
- A model pulled locally (e.g. `ollama pull llama3.2:1b`)

### Install & Run

```bash
git clone https://github.com/Unjuno/branch-writer.git
cd branch-writer
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

That's it. The app opens in your browser at `http://localhost:8501`.

> **Note for frontend development**: The React component (`components/latest_message_editor/frontend/`) requires Node 20+ and `npm run build` if you modify it. See [development docs](docs/development.md).

### One-Click Setup

| Platform | Command |
|----------|---------|
| Linux / macOS | `bash <(curl -fsSL https://raw.githubusercontent.com/Unjuno/branch-writer/main/scripts/setup.sh)` |
| Windows | `powershell -ExecutionPolicy Bypass -File setup.ps1` |

Both scripts handle cloning, venv creation, dependency installation, Ollama setup, model pull, and app launch.

---

## How It Works

```
  ┌──────────────────────────────────────────────┐
  │         Streamlit App (:8501)                │
  │  ┌─────────────┐    ┌─────────────────────┐  │
  │  │ Sidebar      │    │ React Component     │  │
  │  │  - Model sel │    │  - Textarea editor  │  │
  │  │  - Settings  │    │  - SSE streaming    │  │
  │  │  - Undo btn  │    │  - Cursor tracking  │  │
  │  └─────────────┘    └──────────┬──────────┘  │
  │                                 │             │
  └─────────────────────────────────│─────────────┘
                                    │ HTTP / SSE
  ┌─────────────────────────────────│─────────────┐
  │          FastAPI Server (:8765) │             │
  │  ┌──────────────────────────────▼──────────┐  │
  │  │  /api/stream   /api/abort   /health     │  │
  │  │                                         │  │
  │  │  normal mode → full conversation        │  │
  │  │  intervention → frozen msgs + prefix    │  │
  │  │  long mode → auto-continuation loop     │  │
  │  └─────────────────────┬───────────────────┘  │
  └────────────────────────│──────────────────────┘
                           │ OpenAI-compatible API
  ┌────────────────────────│──────────────────────┐
  │           Ollama / LM Studio / vLLM ...       │
  │               http://localhost:11434/v1        │
  └────────────────────────────────────────────────┘
```

### Core Workflow

1. The AI generates a response via streaming SSE tokens
2. During or after generation, move the cursor to any position in the latest assistant message
3. Type an intervention prompt (or leave empty to regenerate from that point) and press **Enter**
4. The AI discards everything after the cursor position and generates a new continuation
5. Press **Escape** at any time to revert the textarea to the latest streamed content

---

## Configuration

### LLM Backend

The app auto-detects models from Ollama's API. You can also connect to any OpenAI-compatible endpoint by setting:

- **API URL** — defaults to `http://localhost:11434/v1` (Ollama)
- **API Key** — optional, for endpoints that require one

### Model Settings

Settings are adjustable from the sidebar:

| Setting | Default | Description |
|---------|---------|-------------|
| Temperature | 0.7 | Response randomness |
| Max tokens | 4096 | Max tokens per generation |
| Context window | 8192 | Context length (auto-detected) |
| Timeout | 180s | Request timeout |
| Long mode | Off | Auto-continue until complete |

---

## Project Structure

```
branch-writer/
├── app.py                              # Streamlit entry point
├── branch_writer/
│   ├── config.py                       # LLM settings, model capabilities
│   ├── intervention.py                 # Suffix discard, overlap stripping
│   ├── llm.py                          # OpenAI-compatible HTTP client
│   ├── messages.py                     # Chat message models
│   ├── state.py                        # Session state management
│   ├── streaming_server.py             # FastAPI SSE server (port 8765)
│   └── model_discovery/                # MCP-based model discovery
├── components/
│   └── latest_message_editor/
│       ├── __init__.py                 # Streamlit component wrapper
│       └── frontend/src/
│           ├── LatestMessageEditor.tsx  # React editor (SSE, cursor, intervention)
│           └── main.tsx
├── tests/                              # pytest test suite
│   ├── test_intervention.py            # Core intervention logic
│   ├── test_streaming_server.py        # SSE server endpoints
│   ├── test_llm.py, test_config.py, test_messages.py, ...
│   └── test_e2e_browser.py            # Playwright end-to-end
├── scripts/
│   ├── setup.sh                        # Linux/macOS quick setup
│   └── setup.ps1                       # Windows quick setup
└── docs/
    ├── concept.md                      # Product philosophy
    ├── architecture.md                 # Implementation structure
    ├── usage.md                        # User guide
    ├── intervention-ux.md              # UX spec (developers)
    ├── development.md                  # Build & dev procedures
    ├── known-limitations.md            # Known limits & non-goals
    └── roadmap.md                      # Future priorities
```

---

## Testing

```bash
# All tests (except browser e2e)
python -m pytest --ignore=tests/test_e2e_browser.py -v

# Specific test files
python -m pytest tests/test_intervention.py -v
python -m pytest tests/test_streaming_server.py -v
python -m pytest tests/test_state.py -v
```

CI runs automatically on push/PR to `main` — Python tests (3.11) and frontend build (Node 20) in parallel.

---

## Documentation

| Doc | Contents |
|-----|----------|
| [Concept](docs/concept.md) | Product philosophy and design decisions |
| [Usage](docs/usage.md) | User operation guide |
| [Architecture](docs/architecture.md) | Implementation structure |
| [Development](docs/development.md) | Build, test, and dev process |
| [Known Limitations](docs/known-limitations.md) | What this project is **not** |
| [Roadmap](docs/roadmap.md) | Future priorities |

---

## Contributing

PRs are welcome. If you're planning a larger change, please open an issue first to discuss.

See [CONTRIBUTING.md](CONTRIBUTING.md) (if present) or the [development docs](docs/development.md) to get started.

---

## License

[MIT](LICENSE) © 2026 Unjuno
