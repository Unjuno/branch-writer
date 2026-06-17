# Branch Writer v0 実装計画書

## 1. 目的

この文書は、Branch Writer v0 を実装するための作業順序、成果物、テスト方針、CI方針、完了条件を固定するための計画書である。

仕様書と設計書で固定した通り、v0の目的は次の体験を実装・検証することである。

> 普通のチャットUI。ただし、AIの最新出力だけは途中から曲げられる。

---

## 2. 前提ドキュメント

実装は以下の文書に従う。

| 文書 | 役割 |
|---|---|
| `docs/spec-v0.md` | v0仕様 |
| `docs/tech-stack.md` | 技術スタック固定 |
| `docs/design-v0.md` | v0設計 |
| `docs/implementation-plan.md` | 実装計画 |

この文書は、実装開始前の最後の計画文書である。

---

## 3. 実装方針

### 3.1 基本方針

小さく作り、各段階で動作確認可能な状態にする。

実装は次の順序で進める。

1. プロジェクト基盤
2. Python純粋ロジック
3. Streamlit基本チャット
4. OpenAI互換ローカルLLM接続
5. 最新Assistantメッセージの特殊表示
6. React/TypeScript custom component
7. 介入処理
8. Undo
9. テスト
10. CI
11. README整備

### 3.2 実装で守る制約

v0では以下を実装しない。

- 過去メッセージ編集
- 選択範囲だけの部分リライト
- 候補A/B/C比較
- 分岐ツリーUI
- 自動矛盾検出
- 自然終了ガード
- データベース永続化
- 認証
- 複数ユーザー対応
- クラウド同期
- 高度なリッチテキストエディタ

---

## 4. 作業単位

## 4.1 Phase 0: ドキュメント・リポジトリ基盤

### 目的

実装前の最低限のリポジトリ基盤を整える。

### 作業

- `README.md` 作成
- `.gitignore` 作成
- `LICENSE` 作成
- `requirements.txt` 作成
- `docs/` 以下の文書確認

### 成果物

```text
README.md
.gitignore
LICENSE
requirements.txt
```

### 完了条件

- リポジトリを見た人がプロダクト概要を理解できる
- ローカル実行に必要な依存が把握できる
- 秘密情報をコミットしない設定になっている

---

## 4.2 Phase 1: Pythonパッケージ基盤

### 目的

Streamlit UIに依存しない純粋ロジックを先に作る。

### 作業

- `branch_writer/` パッケージ作成
- `branch_writer/messages.py` 作成
- `branch_writer/intervention.py` 作成
- `branch_writer/config.py` 作成
- `branch_writer/state.py` 作成

### 成果物

```text
branch_writer/
  __init__.py
  config.py
  messages.py
  intervention.py
  state.py
```

### 実装内容

#### `messages.py`

- `ChatMessage`
- `is_intervenable`
- `append_user_message`
- `append_assistant_message`

#### `intervention.py`

- `regenerate_from_here`
- `insert_and_continue`
- `validate_selection_start`

#### `config.py`

- `LlmSettings`
- デフォルト設定
- 設定バリデーション

#### `state.py`

- session state 初期化用関数
- Undo stack 初期化

### 完了条件

- Streamlitなしで主要ロジックをテストできる
- 最新Assistantだけ介入可能と判定できる
- selectionStartからprefix/discardedを正しく作れる

---

## 4.3 Phase 2: テスト基盤

### 目的

実装初期からCIで落とせるようにする。

### 作業

- `tests/` 作成
- `pytest` 導入
- `test_messages.py` 作成
- `test_intervention.py` 作成
- `test_config.py` 作成

### 成果物

```text
tests/
  test_messages.py
  test_intervention.py
  test_config.py
```

### テスト対象

#### `test_messages.py`

- 最新Assistantは介入可能
- 過去Assistantは介入不可
- Userメッセージは介入不可
- 空履歴では介入不可

#### `test_intervention.py`

- `regenerate_from_here`
- `insert_and_continue`
- `selectionStart == 0`
- `selectionStart == len(content)`
- 不正なselectionStart

#### `test_config.py`

- デフォルト設定
- model未設定
- base_url未設定
- temperature範囲
- max_tokens範囲

### 完了条件

- `pytest` が通る
- コアロジックがUIなしで検証できる

---

## 4.4 Phase 3: Streamlit基本チャット

### 目的

通常のチャットUIをStreamlitで実装する。

### 作業

- `app.py` 作成
- Streamlitページ設定
- `st.chat_message` による履歴表示
- `st.chat_input` による通常送信
- `st.session_state` によるメッセージ保持
- ダミーAssistant応答で動作確認

### 成果物

```text
app.py
```

### 完了条件

- `streamlit run app.py` で起動できる
- ユーザー入力が履歴に追加される
- ダミーAssistant応答が履歴に追加される
- 最新Assistantだけを判定できる

---

## 4.5 Phase 4: LLM接続

### 目的

OpenAI互換ローカルLLM APIへ接続する。

### 作業

- `branch_writer/llm.py` 作成
- API Base URL / API Key / Model を使った生成
- サイドバー設定UI
- 通常チャット生成をLLM接続に置き換える
- 接続失敗時のエラー表示

### 成果物

```text
branch_writer/llm.py
```

### 設定項目

| 項目 | 初期値候補 |
|---|---|
| API Base URL | `http://localhost:11434/v1` |
| API Key | 空文字 |
| Model | 空文字 |
| Temperature | `0.7` |
| Max Tokens | `512` |

### 完了条件

- ローカルLLM APIへ通常チャットを送れる
- 接続失敗時にUI上でエラーが見える
- APIキーをリポジトリへ保存しない

---

## 4.6 Phase 5: 最新Assistant特殊表示

### 目的

最新Assistantメッセージだけを、将来custom componentに置き換えられるように分離する。

### 作業

- 過去メッセージはStreamlit標準表示
- 最新Assistantメッセージ表示関数を分離
- まずはStreamlit標準表示で仮実装

### 完了条件

- 最新Assistantだけ表示経路が分離されている
- custom component導入時に影響範囲が小さい

---

## 4.7 Phase 6: Streamlit custom component 基盤

### 目的

React/TypeScript custom component の最小基盤を作る。

### 作業

- `components/latest_message_editor/` 作成
- Python wrapper 作成
- React/TypeScript frontend 作成
- 最新Assistant本文をcomponentに渡す
- componentからダミーイベントを返す

### 成果物

```text
components/
  latest_message_editor/
    __init__.py
    frontend/
      package.json
      tsconfig.json
      src/
        LatestMessageEditor.tsx
        index.tsx
```

### 完了条件

- Streamlitからcustom componentを呼び出せる
- React側に最新Assistant本文を表示できる
- Python側へイベントを返せる

---

## 4.8 Phase 7: 選択位置取得

### 目的

最新Assistantメッセージ内の `selectionStart` / `selectionEnd` を取得する。

### 作業

- React側で本文表示を `textarea` ベースにする
- 選択開始位置を取得する
- 選択終了位置を取得する
- Python側に返す

### 返却イベント例

```ts
{
  action: "selection_changed",
  messageId: "...",
  selectionStart: 42,
  selectionEnd: 57
}
```

### 完了条件

- カーソル位置を取得できる
- 範囲選択の開始・終了を取得できる
- Python側で値を受け取れる

---

## 4.9 Phase 8: ここから再生成

### 目的

最新Assistantメッセージの任意位置から先を破棄し、続きを再生成する。

### 作業

- componentに「ここから再生成」ボタンを追加
- `regenerate_from_here` イベントを返す
- Python側で介入可能判定
- prefix作成
- LLMへ介入生成リクエスト
- 最新Assistant内容を置換
- Undo snapshot保存

### 完了条件

- 最新Assistantの任意地点から再生成できる
- discarded suffix は生成文脈に含まれない
- 介入後もメッセージは最新Assistantとして保持される
- Undo用のbefore/afterが保存される

---

## 4.10 Phase 9: 入力して続ける

### 目的

最新Assistantメッセージの任意地点にユーザー文を挿入し、その後を生成する。

### 作業

- componentに「入力して続ける」ボタンを追加
- 挿入文入力欄を表示
- `insert_and_continue` イベントを返す
- Python側でprefix + insertionを作成
- LLMへ介入生成リクエスト
- 最新Assistant内容を置換
- Undo snapshot保存

### 完了条件

- 任意地点にユーザー文を挿入できる
- 挿入文の後をLLMが生成する
- discarded suffix は生成文脈に含まれない
- Undo用のbefore/afterが保存される

---

## 4.11 Phase 10: Undo

### 目的

直前の介入を取り消せるようにする。

### 作業

- Undoボタン追加
- Undo snapshot を復元
- 対象メッセージが最新Assistantか確認
- 復元後のUI更新

### 完了条件

- 直前の再生成を取り消せる
- 直前の入力して続ける操作を取り消せる
- 最新Assistantが変わっている場合はUndoしない

---

## 4.12 Phase 11: CI

### 目的

GitHub Actionsで最低限の品質確認を自動化する。

### 作業

- `.github/workflows/ci.yml` 作成
- Pythonセットアップ
- 依存インストール
- `pytest` 実行
- 必要ならフロントエンドの型チェックを追加

### 成果物

```text
.github/
  workflows/
    ci.yml
```

### 完了条件

- push時にCIが走る
- pytestが通る
- CI失敗時に原因を追える

---

## 4.13 Phase 12: README整備

### 目的

ユーザーがローカルで試せる状態にする。

### 作業

- プロダクト概要
- v0の機能
- インストール手順
- ローカルLLM起動例
- Streamlit起動手順
- 設定項目説明
- 注意事項

### 完了条件

- ユーザーがREADMEだけで起動できる
- ローカルLLMのBase URL / Model設定が分かる
- APIキーをコミットしない注意がある

---

## 5. コミット単位案

実装は以下の単位でコミットする。

| 順番 | コミット内容 |
|---:|---|
| 1 | `chore: add project metadata` |
| 2 | `feat: add core message and intervention models` |
| 3 | `test: add core logic tests` |
| 4 | `feat: add basic streamlit chat app` |
| 5 | `feat: add local llm client` |
| 6 | `feat: isolate latest assistant rendering` |
| 7 | `feat: add latest message custom component scaffold` |
| 8 | `feat: capture selection in latest message editor` |
| 9 | `feat: regenerate latest assistant from selection` |
| 10 | `feat: insert text and continue from selection` |
| 11 | `feat: add undo for latest intervention` |
| 12 | `ci: add github actions` |
| 13 | `docs: add readme usage guide` |

---

## 6. ローカル実機テスト前の完了条件

ユーザーがローカルでcloneして実機テストする前に、以下を満たす。

- `streamlit run app.py` で起動する
- サイドバーでLLM設定を入力できる
- 通常チャット送信ができる
- ローカルLLMから応答を受け取れる
- 最新Assistantメッセージだけ介入UIが出る
- 任意地点から「ここから再生成」できる
- 任意地点から「入力して続ける」できる
- 直前の介入をUndoできる
- `pytest` が通る
- GitHub Actions CIが通る
- READMEに起動手順がある

---

## 7. 実装開始前の確認事項

実装開始前に、以下を確認する。

1. `docs/spec-v0.md` が確定している
2. `docs/tech-stack.md` が確定している
3. `docs/design-v0.md` が確定している
4. `docs/implementation-plan.md` が確定している
5. ロードマップ/TODOを作成済みである

この計画書の次に作成する文書は、`docs/roadmap.md` とする。

---

## 8. 実装開始判断

実装開始は、ロードマップ/TODOを作成した後に行う。

理由は、実装作業中に仕様が膨らむことを避けるためである。

v0の実装では、常に次を優先する。

```text
通常チャットUI
+ 最新Assistantメッセージへの途中介入
```

それ以外の機能は、v0では追加しない。
