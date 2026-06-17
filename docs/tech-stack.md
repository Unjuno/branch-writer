# Branch Writer 技術スタック

## 1. 結論

Branch Writer v0 の技術スタックは、以下で固定する。

```text
Streamlit
+ Streamlit custom component
+ React / TypeScript
+ Python backend
+ OpenAI互換ローカルLLM API
```

基本UIは Streamlit で実装する。  
ただし、最新Assistantメッセージ内の選択位置取得と介入UIだけは、Streamlit custom component として React / TypeScript で実装する。

---

## 2. 採用技術

| 領域 | 採用技術 | 用途 |
|---|---|---|
| アプリ本体 | Streamlit | 通常チャットUI、設定UI、画面構成 |
| カスタムUI | Streamlit custom component | 最新Assistantメッセージの選択位置取得・介入操作 |
| フロントエンド | React / TypeScript | custom component の実装 |
| バックエンド | Python | 状態管理、LLM呼び出し、介入処理 |
| LLM接続 | OpenAI互換API | Ollama / LM Studio / llama.cpp server 等への接続 |
| 状態管理 | `st.session_state` | チャット履歴、設定、Undo履歴 |
| テスト | pytest | Pythonロジックの単体テスト |
| CI | GitHub Actions | lint / test の自動実行 |

---

## 3. 採用理由

### 3.1 Streamlit を採用する理由

v0のUIは、通常のチャットUIを基本とする。

Streamlit は、PythonだけでチャットUI、サイドバー設定、状態管理を素早く構築できる。

v0では高度なWebアプリ全体を作ることよりも、次の体験を早く検証することを重視する。

> 普通のチャットUI。ただし、AIの最新出力だけは途中から曲げられる。

そのため、アプリ全体は Streamlit で十分である。

### 3.2 custom component を採用する理由

Branch Writer v0 の中核は、最新Assistantメッセージ内の任意地点を選び、その地点から再生成することである。

このため、ブラウザ側で次の値を取得する必要がある。

```ts
selectionStart
selectionEnd
content
action
insertion
```

Streamlit標準ウィジェットだけでは、ブラウザ上の選択開始位置・終了位置を自然に扱いにくい。

そのため、最新Assistantメッセージの表示部分だけを Streamlit custom component として実装する。

React / TypeScript 側で選択位置を取得し、`Streamlit.setComponentValue()` 相当の仕組みで Python 側へ値を返す。

### 3.3 React / TypeScript を採用する理由

最新Assistantメッセージの介入UIでは、以下が必要になる。

- メッセージ本文の表示
- テキスト選択位置の取得
- 選択時の操作メニュー表示
- 「ここから再生成」アクション
- 「入力して続ける」アクション
- ユーザー挿入文の入力
- Python側へのイベント返却

これらはブラウザUIの責務であり、React / TypeScript で実装するのが自然である。

### 3.4 OpenAI互換APIを採用する理由

v0はローカルLLM前提とする。

ただし、ユーザー環境によってLLM実行基盤は異なる。

想定する接続先は以下である。

- Ollama OpenAI-compatible endpoint
- LM Studio local server
- llama.cpp server
- OpenAI-compatible local proxy

この差異を吸収するため、v0では OpenAI互換の Chat Completions API に寄せる。

ユーザーはアプリ内の設定UIから、以下を変更できる。

| 設定項目 | 例 |
|---|---|
| API Base URL | `http://localhost:11434/v1` |
| API Key | `ollama` / `lm-studio` / 空文字 |
| Model | `qwen2.5:7b` / `llama3.1:8b` |
| Temperature | `0.7` |
| Max Tokens | `512` |

---

## 4. アーキテクチャ概要

```text
+-------------------------------+
| Streamlit app                 |
|                               |
|  - chat messages              |
|  - chat input                 |
|  - LLM settings sidebar       |
|  - session state              |
|                               |
|  +-------------------------+  |
|  | LatestMessageComponent  |  |
|  | React / TypeScript      |  |
|  |                         |  |
|  | - display latest msg    |  |
|  | - get selectionStart    |  |
|  | - get selectionEnd      |  |
|  | - emit intervention     |  |
|  +-------------------------+  |
|                               |
+---------------+---------------+
                |
                v
+-------------------------------+
| Python intervention logic      |
|                               |
| - normal chat send             |
| - regenerate from here         |
| - insert and continue          |
| - undo                         |
+---------------+---------------+
                |
                v
+-------------------------------+
| Local LLM API                  |
| OpenAI-compatible endpoint     |
+-------------------------------+
```

---

## 5. ディレクトリ構成案

```text
branch-writer/
  app.py
  branch_writer/
    __init__.py
    config.py
    llm.py
    state.py
    intervention.py
    messages.py
  components/
    latest_message_editor/
      __init__.py
      frontend/
        package.json
        tsconfig.json
        src/
          LatestMessageEditor.tsx
          index.tsx
  docs/
    spec-v0.md
    tech-stack.md
  tests/
    test_intervention.py
    test_messages.py
  .github/
    workflows/
      ci.yml
  .gitignore
  README.md
  requirements.txt
```

---

## 6. 主要モジュールの責務

### 6.1 `app.py`

Streamlitアプリのエントリポイント。

責務:

- ページ設定
- チャット履歴表示
- 通常チャット入力
- LLM設定UI
- 最新Assistantメッセージ用custom componentの呼び出し
- 介入イベントの受け取り

### 6.2 `branch_writer/llm.py`

ローカルLLM APIとの通信を扱う。

責務:

- OpenAI互換APIへのリクエスト
- 通常チャット生成
- 介入後の続きを生成
- エラーハンドリング

### 6.3 `branch_writer/intervention.py`

介入処理の純粋ロジックを扱う。

責務:

- `regenerate_from_here`
- `insert_and_continue`
- `prefix` / `discarded` の計算
- Undo用スナップショット生成

### 6.4 `branch_writer/state.py`

Streamlit session state の初期化と更新を扱う。

責務:

- チャット履歴
- LLM設定
- Undo履歴
- 現在の生成状態

### 6.5 `components/latest_message_editor`

最新Assistantメッセージ専用のカスタムコンポーネント。

責務:

- 最新Assistantメッセージの表示
- 選択位置の取得
- 選択時の操作メニュー表示
- 介入イベントの生成
- Python側への値返却

---

## 7. v0で実装しない技術要素

v0では以下を採用しない。

- Next.js
- FastAPI
- Electron
- Tauri
- データベース
- 認証
- クラウド同期
- 複数ユーザー対応
- 分岐グラフ用ライブラリ
- 高度なリッチテキストエディタ

理由は、v0の検証対象が「最新Assistantメッセージへの途中介入」であり、上記は初期検証には重いためである。

---

## 8. 実装フェーズ

### Phase 1: Streamlit基本チャット

- Streamlitアプリ起動
- LLM設定UI
- 通常チャット送信
- OpenAI互換ローカルLLM API接続
- チャット履歴表示

### Phase 2: 最新Assistantメッセージ介入

- React / TypeScript custom component 作成
- 最新Assistantメッセージ表示
- `selectionStart` / `selectionEnd` 取得
- 「ここから再生成」実装
- 「入力して続ける」実装
- Undo実装

### Phase 3: 品質・開発基盤

- pytest追加
- GitHub Actions CI追加
- README作成
- `.gitignore` 作成
- ローカル実行手順整備

---

## 9. 固定判断

v0の技術スタックとして、以下を固定する。

| 項目 | 固定内容 |
|---|---|
| アプリ基盤 | Streamlit |
| 介入UI | Streamlit custom component |
| 介入UI実装 | React / TypeScript |
| バックエンド | Python |
| LLM接続 | OpenAI互換ローカルLLM API |
| 状態管理 | `st.session_state` |
| テスト | pytest |
| CI | GitHub Actions |

この構成により、Streamlitの実装速度を維持しながら、v0仕様に必要なリッチな選択介入UIを実現する。
