# Development

## 環境構築

```bash
git clone https://github.com/Unjuno/branch-writer.git
cd branch-writer

# Python
python -m venv .venv
source .venv/bin/activate      # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# フロントエンド
cd components/latest_message_editor/frontend
npm install
```

## 起動

```bash
streamlit run app.py
```

Ollama または LM Studio が別途必要です。

## テスト

```bash
# すべてのテスト（e2e除く）
python -m pytest tests/ --ignore=tests/test_e2e_browser.py -v

# 特定のテストのみ
python -m pytest tests/test_intervention.py -v
python -m pytest tests/test_app_smoke.py -v
python -m pytest tests/test_streaming_server.py -v

# e2eテスト（サーバー起動が必要）
python -m pytest tests/test_e2e_browser.py -v
```

## フロントエンドビルド

React コンポーネントを変更した場合、Streamlitに反映する前にビルドが必要です。

```bash
cd components/latest_message_editor/frontend
npm run build
```

開発中は以下のコマンドでホットリロードが有効な dev server を起動できます（Streamlitの component dev URL と併用）。

```bash
cd components/latest_message_editor/frontend
npm run dev
```

## 注意事項

### formatter 全面適用禁止

リポジトリ全体に formatter を一括適用しないでください。既存のコードスタイルはそのまま維持します。

### unrelated refactor 禁止

機能追加やバグ修正と無関係なリファクタリングは行わないでください。レビューが困難になります。

### commit 粒度

1 commit = 1 論理変更を原則とします。複数の問題を同時に修正する場合は、可能な限り分割してください。

## プロジェクト構成

```
branch_writer/
  __init__.py
  config.py           # LLM設定とモデル能力DB
  intervention.py     # 介入ロジック（suffix破棄、overlap stripping）
  llm.py              # OpenAI互換APIクライアント
  messages.py         # チャットメッセージモデル
  model_discovery/    # MCPベースのモデル探索
  state.py            # セッション状態管理
  streaming_server.py # SSEストリーミングサーバー

components/
  latest_message_editor/
    __init__.py       # Streamlitコンポーネントラッパー
    frontend/
      src/LatestMessageEditor.tsx  # メインコンポーネント
      src/main.tsx    # エントリポイント

tests/                # pytestテスト
scripts/              # セットアップスクリプト
```
