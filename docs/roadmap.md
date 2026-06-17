# Branch Writer v0 ロードマップ / TODO

## 1. 目的

この文書は、Branch Writer v0 の実装中に使用するロードマップ兼TODOリストである。

作業はこの順番に従う。  
仕様が膨らみそうになった場合は、`docs/spec-v0.md`、`docs/design-v0.md`、`docs/implementation-plan.md` に戻って判断する。

v0の最優先目標は次である。

> 普通のチャットUI。ただし、AIの最新出力だけは途中から曲げられる。

---

## 2. 進捗ステータス定義

各タスクは以下の形式で管理する。

```text
- [ ] 未着手
- [x] 完了
```

必要に応じて、作業中のメモはタスク直下に追記する。

---

## 3. Milestone 0: リポジトリ基盤

### 目的

実装を始められる最低限のプロジェクト基盤を作る。

### TODO

- [x] `README.md` を作成する
- [x] `.gitignore` を作成する
- [x] `LICENSE` を作成する
- [x] `requirements.txt` を作成する
- [x] Pythonパッケージ用ディレクトリ `branch_writer/` を作成する
- [x] テスト用ディレクトリ `tests/` を作成する
- [x] GitHub Actions用ディレクトリ `.github/workflows/` を作成する

### 完了条件

- [x] リポジトリ直下の基本ファイルが揃っている
- [x] `.env` 系の秘密情報がgit管理対象外になっている
- [x] `pip install -r requirements.txt` の準備ができている

---

## 4. Milestone 1: コアモデルと純粋ロジック

### 目的

UIに依存しないコアロジックを先に作る。

### TODO

- [x] `branch_writer/__init__.py` を作成する
- [x] `branch_writer/messages.py` を作成する
- [x] `branch_writer/intervention.py` を作成する
- [x] `branch_writer/config.py` を作成する
- [x] `branch_writer/state.py` を作成する

### `messages.py`

- [x] `ChatMessage` を定義する
- [x] `MessageRole` を定義する
- [x] `MessageStatus` を定義する
- [x] `is_intervenable()` を実装する
- [x] `append_user_message()` を実装する
- [x] `append_assistant_message()` を実装する

### `intervention.py`

- [x] `regenerate_from_here()` を実装する
- [x] `insert_and_continue()` を実装する
- [x] `validate_selection_start()` を実装する
- [x] `prefix` / `discarded` の計算を分離する

### `config.py`

- [x] `LlmSettings` を定義する
- [x] デフォルト設定を定義する
- [x] `validate_llm_settings()` を実装する

### `state.py`

- [x] session state 初期化関数を実装する
- [x] Undo stack 初期化を実装する
- [x] 生成中フラグ初期化を実装する

### 完了条件

- [ ] Streamlitなしでコアロジックをimportできる
- [x] 最新Assistantだけ介入可能と判定できる
- [x] selectionStartから正しくprefix/discardedを作れる

---

## 5. Milestone 2: テスト基盤

### 目的

コアロジックをpytestで検証できるようにする。

### TODO

- [x] `tests/test_messages.py` を作成する
- [x] `tests/test_intervention.py` を作成する
- [x] `tests/test_config.py` を作成する
- [x] `pytest` を `requirements.txt` に追加する

### `test_messages.py`

- [x] 最新Assistantは介入可能
- [x] 過去Assistantは介入不可
- [x] Userメッセージは介入不可
- [x] 空履歴は介入不可
- [x] error状態のAssistantは介入不可

### `test_intervention.py`

- [x] `regenerate_from_here()` の正常系
- [x] `insert_and_continue()` の正常系
- [x] `selectionStart == 0`
- [x] `selectionStart == len(content)`
- [x] `selectionStart < 0` はエラー
- [x] `selectionStart > len(content)` はエラー

### `test_config.py`

- [x] デフォルト設定を検証する
- [x] base_url空文字を検証する
- [x] model空文字を検証する
- [x] temperature範囲を検証する
- [x] max_tokens範囲を検証する

### 完了条件

- [ ] `pytest` がローカルで通る
- [x] UIなしで介入ロジックの安全性を確認できる

---

## 6. Milestone 3: Streamlit基本チャット

### 目的

通常のチャットUIをStreamlitで実装する。

### TODO

- [x] `app.py` を作成する
- [x] `st.set_page_config()` を設定する
- [x] session state 初期化を呼び出す
- [x] `st.chat_message` で履歴表示する
- [x] `st.chat_input` で通常送信を受け取る
- [x] Userメッセージを履歴に追加する
- [x] Assistant応答を履歴に追加する
- [x] 最新Assistantだけ特殊表示できるように表示経路を分離する

### 完了条件

- [ ] `streamlit run app.py` で起動できる
- [ ] 通常チャット入力ができる
- [x] 入力内容が履歴に残る
- [x] Assistant応答が表示される

---

## 7. Milestone 4: LLM接続

### 目的

OpenAI互換ローカルLLM APIと接続する。

### TODO

- [x] `branch_writer/llm.py` を作成する
- [x] OpenAI互換APIへリクエストする関数を実装する
- [x] サイドバーにLLM設定UIを追加する
- [x] API Base URLを設定できるようにする
- [x] API Keyを設定できるようにする
- [x] Modelを設定できるようにする
- [x] Temperatureを設定できるようにする
- [x] Max Tokensを設定できるようにする
- [x] 通常チャット生成をダミー応答からLLM応答へ置き換える
- [x] 接続失敗時のエラー表示を実装する

### 完了条件

- [ ] ローカルLLMへ通常チャットを送信できる
- [ ] ローカルLLMから応答を受け取れる
- [x] 接続失敗時にUI上でエラーが表示される
- [x] APIキーがgitに保存されない

---

## 8. Milestone 5: 最新Assistant特殊表示

### 目的

最新Assistantメッセージだけをcustom componentへ差し替える準備をする。

### TODO

- [x] `render_frozen_message()` を作る
- [x] `render_latest_assistant_message()` を作る
- [x] 最新Assistantかどうかの判定を表示層で使う
- [x] 過去メッセージはStreamlit標準表示にする
- [x] 最新Assistantだけ別関数で表示する

### 完了条件

- [x] 最新Assistantだけ表示経路が分離されている
- [x] custom component導入前でも通常表示できる

---

## 9. Milestone 6: custom component 基盤

### 目的

React/TypeScriptのStreamlit custom componentを導入する。

### TODO

- [x] `components/latest_message_editor/` を作成する
- [x] Python wrapper `components/latest_message_editor/__init__.py` を作成する
- [x] frontend `package.json` を作成する
- [x] frontend `tsconfig.json` を作成する
- [x] `LatestMessageEditor.tsx` を作成する
- [x] `index.tsx` を作成する
- [x] Pythonから `messageId` と `content` を渡せるようにする
- [x] React側で本文を表示する
- [x] React側からPythonへダミーイベントを返す

### 完了条件

- [ ] Streamlitからcustom componentを呼べる
- [x] 最新Assistant本文がReact側に表示される
- [x] Python側でcomponent返却値を受け取れる

---

## 10. Milestone 7: 選択位置取得

### 目的

最新Assistantメッセージ内のカーソル位置・選択範囲を取得する。

### TODO

- [x] React側の本文表示を `textarea` ベースにする
- [x] `selectionStart` を取得する
- [x] `selectionEnd` を取得する
- [x] カーソル移動時に選択値を保持する
- [x] 範囲選択時に選択値を保持する
- [x] Python側へ `selectionStart` / `selectionEnd` を返す

### 完了条件

- [ ] カーソル位置をPython側で確認できる
- [ ] 範囲選択の開始・終了をPython側で確認できる
- [x] selectionStartを介入処理に渡せる

---

## 11. Milestone 8: ここから再生成

### 目的

最新Assistantメッセージの任意地点から先を破棄し、続きを再生成する。

### TODO

- [x] componentに「ここから再生成」ボタンを追加する
- [x] `regenerate_from_here` イベントを返す
- [x] Python側で対象メッセージが介入可能か確認する
- [x] `prefix = content[:selectionStart]` を作る
- [x] discarded suffixをLLM文脈から除外する
- [x] LLMへ介入生成を投げる
- [x] 最新Assistant内容を `prefix + continuation` に置き換える
- [x] Undo snapshotを保存する

### 完了条件

- [ ] 最新Assistantの途中から再生成できる
- [x] 破棄したsuffixが生成文脈に含まれない
- [x] 介入後も最新Assistantとして扱われる
- [x] Undo可能な状態になる

---

## 12. Milestone 9: 入力して続ける

### 目的

最新Assistantメッセージの任意地点にユーザー文を挿入し、その後を生成する。

### TODO

- [x] componentに「入力して続ける」ボタンを追加する
- [x] 挿入文入力欄を表示する
- [x] `insert_and_continue` イベントを返す
- [x] Python側で対象メッセージが介入可能か確認する
- [x] `prefix = content[:selectionStart]` を作る
- [x] `prefix + insertion` を生成文脈にする
- [x] discarded suffixをLLM文脈から除外する
- [x] LLMへ介入生成を投げる
- [x] 最新Assistant内容を `prefix + insertion + continuation` に置き換える
- [x] Undo snapshotを保存する

### 完了条件

- [ ] 任意地点にユーザー文を挿入できる
- [ ] 挿入文の後をLLMが生成できる
- [x] 破棄したsuffixが生成文脈に含まれない
- [x] Undo可能な状態になる

---

## 13. Milestone 10: Undo

### 目的

直前の介入を取り消せるようにする。

### TODO

- [x] UndoボタンをUIに追加する
- [x] Undo stackから直前snapshotを取り出す
- [x] 対象メッセージが最新Assistantか確認する
- [x] 最新Assistantのcontentをbefore_contentへ戻す
- [x] Undo失敗時のエラー表示を実装する

### 完了条件

- [ ] 直前の「ここから再生成」を取り消せる
- [ ] 直前の「入力して続ける」を取り消せる
- [x] 最新Assistantが変わっている場合はUndoしない

---

## 14. Milestone 11: CI

### 目的

GitHub Actionsで最低限の品質確認を自動化する。

### TODO

- [x] `.github/workflows/ci.yml` を作成する
- [x] Pythonをセットアップする
- [x] 依存関係をインストールする
- [x] `pytest` を実行する
- [x] frontendのビルドチェックを追加する

### 完了条件

- [ ] push時にCIが走る
- [ ] pytestがCI上で通る
- [ ] frontend buildがCI上で通る
- [ ] 失敗時に原因が追える

---

## 15. Milestone 12: README整備

### 目的

ユーザーがローカルでcloneして試せる状態にする。

### TODO

- [x] プロダクト概要を書く
- [x] v0の機能を書く
- [x] セットアップ手順を書く
- [x] ローカルLLM起動例を書く
- [x] Streamlit起動手順を書く
- [x] LLM設定項目を書く
- [x] APIキーをコミットしない注意を書く
- [x] 既知の制限を書く

### 完了条件

- [x] READMEだけでローカル起動手順が分かる
- [x] ローカルLLMのBase URL / Model設定が分かる
- [x] v0でできること・できないことが分かる

---

## 16. ローカル実機テスト前チェックリスト

ユーザーがローカルでcloneして実機テストする前に、以下を満たす。

- [x] `git clone` できる
- [x] `pip install -r requirements.txt` できる
- [ ] `streamlit run app.py` で起動できる
- [x] サイドバーでLLM設定を入力できる
- [x] 通常チャット送信ができる
- [ ] ローカルLLMから応答を受け取れる
- [x] 最新Assistantメッセージだけ介入UIが出る
- [ ] 任意地点から「ここから再生成」できる
- [ ] 任意地点から「入力して続ける」できる
- [ ] 直前の介入をUndoできる
- [ ] `pytest` が通る
- [ ] GitHub Actions CIが通る
- [x] READMEに起動手順がある

---

## 17. 実装開始条件

実装開始前に、以下の文書が存在していること。

- [x] `docs/spec-v0.md`
- [x] `docs/tech-stack.md`
- [x] `docs/design-v0.md`
- [x] `docs/implementation-plan.md`
- [x] `docs/roadmap.md`

上記が揃ったら、実装を開始する。

---

## 18. v0完了条件

Branch Writer v0 は、以下を満たした時点で完了とする。

- [ ] 通常チャットUIが動作する
- [ ] OpenAI互換ローカルLLM APIに接続できる
- [ ] 最新Assistantメッセージだけ介入可能である
- [ ] ここから再生成が動作する
- [ ] 入力して続けるが動作する
- [ ] Undoが動作する
- [ ] 過去メッセージは編集不可である
- [ ] pytestが通る
- [ ] CIが通る
- [x] READMEに実行手順がある

---

## 19. v0以降に回すもの

以下はv0では扱わない。

- [ ] 分岐ツリーUI
- [ ] 候補A/B/C比較
- [ ] 過去メッセージからの分岐
- [ ] 自動矛盾検出
- [ ] 自然終了ガード
- [ ] キャラクターDB
- [ ] 世界観DB
- [ ] タイムライン管理
- [ ] 永続保存
- [ ] プロジェクト管理
- [ ] デスクトップアプリ化
