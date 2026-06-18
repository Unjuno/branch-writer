# Branch Writer

Branch Writer は、ローカル LLM を使ったチャット UI です。
AI の返答途中に割り込み、書き換え、そこから続きを生成できます。

## 主な機能

- ストリーミング対応の通常チャット
- **途中から再生成**: AI の返答の任意位置より後ろを破棄して再生成
- **入力して続ける**: 任意位置に自分の文章を挿入し、続きの生成を AI に任せる
- **トークン数表示**: 各メッセージの推定トークン数と文字数を表示
- **コンテキスト使用状況**: 入力・出力・上限をリアルタイム表示し、色で警告
- **モデル自動検出**: Ollama / LM Studio から利用可能なモデルを自動取得
- **API URL 自動検出**: 空欄なら Ollama / LM Studio を自動探索
- **モデル別デフォルト値**: モデル選択時にコンテキストウィンドウと出力上限を自動設定
- **挿入履歴**: 以前挿入した文章を再利用
- **介入の取り消し**: 直前の介入を元に戻す
- **OpenAI 互換のローカル LLM 対応**: Ollama, LM Studio, llama.cpp など

## 必要環境

- Python 3.12 以上
- Ollama または LM Studio などのローカル LLM サーバー

## クイックスタート

以下のスクリプトで、Ollama のインストールからモデルのダウンロード、アプリ起動までをまとめて実行できます。

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

1. Ollama などのローカル LLM サーバーを起動する
2. `streamlit run app.py` を実行する
3. サイドバーの「🔄 モデル一覧を再取得」をクリックしてモデルを検出する
4. モデルを選択してチャットを開始する

API ベース URL は空欄で問題ありません。Ollama (`localhost:11434`) と LM Studio (`localhost:1234`) を自動で探索します。

## 設定項目

| 項目 | デフォルト | 説明 |
|---|---|---|
| API ベース URL | 自動 (Ollama / LM Studio) | LLM エンドポイント。空欄で自動検出 |
| API キー | 空文字 | 認証キー |
| モデル | 自動検出 | モデルの選択 |
| 温度 (Temperature) | 0.7 | 生成のランダム性 |
| 出力トークン上限 | コンテキストの約 50% | コンテキストウィンドウから自動計算 |
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
        - config.py        - LLM 設定とモデル能力データベース
        - llm.py           - OpenAI 互換 API クライアント
        - intervention.py  - 再生成 / 挿入ロジック
        - messages.py      - チャットメッセージモデル
        - state.py         - セッション状態管理
        - model_discovery/ - MCP ベースのモデル探索 (Ollama / LM Studio)
```

## セキュリティ上の注意

API キーをリポジトリにコミットしないでください。次のファイルはローカルにのみ保持してください。

```text
.env
.env.local
.streamlit/secrets.toml
```

## v0 の既知の制限

- 介入できるのは最新の Assistant メッセージのみ
- 過去のメッセージは編集不可（凍結）
- 分岐ツリー UI はない
- 自動矛盾検出はない
- 永続化はない

## ライセンス

MIT License
