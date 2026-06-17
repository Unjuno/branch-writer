# Branch Writer

Branch Writer is a local-first AI writing chat UI that lets you intervene in the latest assistant response from any point and regenerate the continuation.

Branch Writer は、ローカルLLMを前提とした創作向けチャットUIです。

普通のチャットUIとして使えます。ただし、最新のAI応答だけは、途中の任意地点から「ここから再生成」または「入力して続ける」ができます。

## v0 Concept

```text
普通のチャットUI
+
最新Assistantメッセージだけ途中介入可能
```

## v0 Features

- 通常チャット送信
- 最新Assistantメッセージのみ介入可能
- 任意地点から「ここから再生成」
- 任意地点にユーザー文を入れて「入力して続ける」
- ローカルLLM接続設定
- OpenAI互換ローカルLLM API対応
- 直前介入のUndo

## Local LLM Assumption

v0はローカルLLMを前提にします。

想定接続先:

- Ollama OpenAI-compatible endpoint
- LM Studio local server
- llama.cpp server
- OpenAI-compatible local proxy

アプリ内で以下を設定できるようにします。

| Setting | Example |
|---|---|
| API Base URL | `http://localhost:11434/v1` |
| API Key | empty / `ollama` / `lm-studio` |
| Model | `qwen2.5:7b` / `llama3.1:8b` |
| Temperature | `0.7` |
| Max Tokens | `512` |

## Planned Tech Stack

| Area | Technology |
|---|---|
| App UI | Streamlit |
| Intervention UI | Streamlit custom component |
| Custom component | React / TypeScript |
| Backend | Python |
| LLM API | OpenAI-compatible local endpoint |
| State | `st.session_state` |
| Tests | pytest |
| CI | GitHub Actions |

## Project Documents

| Document | Purpose |
|---|---|
| [`docs/spec-v0.md`](docs/spec-v0.md) | v0 specification |
| [`docs/tech-stack.md`](docs/tech-stack.md) | fixed tech stack |
| [`docs/design-v0.md`](docs/design-v0.md) | v0 design |
| [`docs/implementation-plan.md`](docs/implementation-plan.md) | implementation plan |
| [`docs/roadmap.md`](docs/roadmap.md) | roadmap / TODO checklist |

## Development Status

v0 is currently under implementation.

The first implementation target is:

```text
Streamlit basic chat
+ local LLM settings
+ latest assistant intervention UI
```

## Installation

This section will be completed during implementation.

Expected flow:

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

## Security Notes

Do not commit API keys or local environment files.

The following files should remain local only:

```text
.env
.env.local
.streamlit/secrets.toml
```

## License

MIT License.
