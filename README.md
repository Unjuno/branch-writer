# Branch Writer

Branch Writer は、生成中のAI本文に人間が途中介入し、その時点のsnapshotから続きを再生成できる writing editor です。

通常のチャットUIとは異なり、最新Assistant本文の任意位置にカーソルを置き、介入文を入力してEnterを押すだけで、現在のstreamを中断し、選択位置以降を破棄して再生成できます。

目的は、AIに文章を丸投げすることではなく、人間が生成過程を操縦しながら長文を書くことです。

## Quick Start

```bash
git clone https://github.com/Unjuno/branch-writer.git
cd branch-writer
python -m venv .venv
source .venv/bin/activate      # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Ollama または LM Studio が起動している必要があります。

## Core Workflow

1. AI が返答をストリーミング生成する
2. 生成中または完了後、textarea 内の任意位置にカーソルを移動する
3. 介入文をタイプするか、空のままEnterでその位置からの再生成を指示する
4. AI が選択位置以降を破棄し、新しい続きを生成する
5. Escape で編集中止（stream内容に復帰）

## Documents

| 文書 | 内容 |
|---|---|
| [docs/concept.md](docs/concept.md) | プロダクトの思想と設計判断 |
| [docs/usage.md](docs/usage.md) | ユーザー操作ガイド |
| [docs/intervention-ux.md](docs/intervention-ux.md) | UX仕様（開発者向け） |
| [docs/architecture.md](docs/architecture.md) | 実装構造 |
| [docs/development.md](docs/development.md) | 開発環境・ビルド手順 |
| [docs/known-limitations.md](docs/known-limitations.md) | 既知制限と非目標 |
| [docs/roadmap.md](docs/roadmap.md) | 今後の優先順位 |

## License

MIT License
