# Branch Writer

Branch Writer は、ローカルLLMを使ったチャットUIです。
AIの返答の途中に割り込んで、書き換えて、続きを紡ぐことができます。

チャットして、AIの返答の途中に割り込んで、書き換えて、続きを紡ぐ。

## 機能

- ノンブロッキングストリーミングでの通常チャット
- **途中から再生成** — AIの返答の任意の位置から後ろを破棄して、続きを再生成
- **入力して続ける** — 任意の位置に自分の文章を挿入して、続きをAIに生成させる
- **トークン数表示** — 各メッセージの推定トークン数・文字数を表示
- **コンテキスト使用状況** — 入力・出力枠・上限をリアルタイム表示（色付き警告）
- **モデル自動検出** — Ollama / LM Studio から利用可能なモデルを自動取得
- **API URL 自動検出** — 空欄なら Ollama / LM Studio を自動で探す
- **モデル別デフォルト値** — モデル選択時にコンテキストウィンドウと出力上限を自動設定
- **挿入履歴** — 以前挿入した文章を再利用
- **介入の取り消し** — 直前の介入を元に戻せる
- **OpenAI 互換ローカルLLM対応** — Ollama, LM Studio, llama.cpp など

## 必要環境

- Python 3.12+
- Ollama または LM Studio などのローカルLLMサーバー

## クイックスタート（Ollama + 最小モデル）

以下のスクリプトで、Ollama のインストールからモデルダウンロード、アプリ起動までを一括で行えます。

**macOS / Linux:**
```bash
# 1. Ollama をインストール
curl -fsSL https://ollama.com/install.sh | sh

# 2. Branch Writer をセットアップして起動
bash <(curl -fsSL https://raw.githubusercontent.com/Unjuno/branch-writer/main/scripts/setup.sh)
```

**Windows (PowerShell):**
```powershell
# 1. https://ollama.com/download/windows から Ollama をインストール

# 2. Branch Writer をセットアップして起動
powershell -ExecutionPolicy Bypass -c "iex (iwr https://raw.githubusercontent.com/Unjuno/branch-writer/main/scripts/setup.ps1)"
```

## 手動セットアップ

```powershell
git clone https://github.com/Unjuno/branch-writer.git
cd branch-writer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## 使い方

1. Ollama などのローカルLLMサーバーを起動する
2. `streamlit run app.py` を実行する
3. サイドバーの「🔄 モデル一覧を再取得」をクリックしてモデルを検出する
4. モデルを選択してチャットを開始する

API ベースURL は空欄で構いません。自動的に Ollama (localhost:11434) と LM Studio (localhost:1234) を探索します。

## 設定項目

| 項目 | デフォルト | 説明 |
|---|---|---|
| API ベースURL | 自動 (Ollama / LM Studio) | LLMエンドポイント。空欄で自動検出 |
| API キー | 空文字 | 認証キー |
| モデル | 自動検出 | モデル選択 |
| 温度 (Temperature) | 0.7 | 生成のランダム性 |
| 出力トークン上限 | コンテキストの約50% | コンテキストウィンドウから自動計算 |
| コンテキストウィンドウ | モデル別 | モデルのコンテキスト上限 |

## テスト

```bash
python -m pytest
```

## アーキテクチャ

```text
Streamlit アプリ (Python)
  |
  +-- branch_writer/
        - config.py        — LLM設定 & モデル能力データベース
        - llm.py           — OpenAI互換APIクライアント
        - intervention.py  — 再生成 / 挿入ロジック
        - messages.py      — チャットメッセージモデル
        - state.py         — セッション状態管理
        - model_discovery/ — MCPベースのモデル探索 (Ollama / LM Studio)
```

## セキュリティ注意

APIキーをリポジトリにコミットしないでください。以下のファイルはローカルに保持してください：

```text
.env
.env.local
.streamlit/secrets.toml
```

## v0 の既知の制限

- 介入できるのは最新のAssistantメッセージのみ
- 過去のメッセージは編集不可（凍結）
- 分岐ツリーUIなし
- 自動矛盾検出なし
- 永続化なし

## ライセンス

MIT License.
