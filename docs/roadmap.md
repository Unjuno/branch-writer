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

- [ ] `README.md` を作成する
- [ ] `.gitignore` を作成する
- [ ] `LICENSE` を作成する
- [ ] `requirements.txt` を作成する
- [ ] Pythonパッケージ用ディレクトリ `branch_writer/` を作成する
- [ ] テスト用ディレクトリ `tests/` を作成する
- [ ] GitHub Actions用ディレクトリ `.github/workflows/` を作成する

### 完了条件

- [ ] リポジトリ直下の基本ファイルが揃っている
- [ ] `.env` 系の秘密情報がgit管理対象外になっている
- [ ] `pip install -r requirements.txt` の準備ができている

---

## 4. Milestone 1: コアモデルと純粋ロジック

### 目的

UIに依存しないコアロジックを先に作る。

### TODO

- [ ] `branch_writer/__init__.py` を作成する
- [ ] `branch_writer/messages.py` を作成する
- [ ] `branch_writer/intervention.py` を作成する
- [ ] `branch_writer/config.py` を作成する
- [ ] `branch_writer/state.py` を作成する

### `messages.py`

- [ ] `ChatMessage` を定義する
- [ ] `MessageRole` を定義する
- [ ] `MessageStatus` を定義する
- [ ] `is_intervenable()` を実装する
- [ ] `append_user_message()` を実装する
- [ ] `append_assistant_message()` を実装する

### `intervention.py`

- [ ] `regenerate_from_here()` を実装する
- [ ] `insert_and_continue()` を実装する
- [ ] `validate_selection_start()` を実装する
- [ ] `prefix` / `discarded` の計算を分離する

### `config.py`

- [ ] `LlmSettings` を定義する
- [ ] デフォルト設定を定義する
- [ ] `validate_llm_settings()` を実装する

### `state.py`

- [ ] session state 初期化関数を実装する
- [ ] Undo stack 初期化を実装する
- [ ] 生成中フラグ初期化を実装する

### 完了条件

- [ ] Streamlitなしでコアロジックをimportできる
- [ ] 最新Assistantだけ介入可能と判定できる
- [ ] selectionStartから正しくprefix/discardedを作れる

---

## 5. Milestone 2: テスト基盤

### 目的

コアロジックをpytestで検証できるようにする。

### TODO

- [ ] `tests/test_messages.py` を作成する
- [ ] `tests/test_intervention.py` を作成する
- [ ] `tests/test_config.py` を作成する
- [ ] `pytest` を `requirements.txt` に追加する

### `test_messages.py`

- [ ] 最新Assistantは介入可能
- [ ] 過去Assistantは介入不可
- [ ] Userメッセージは介入不可
- [ ] 空履歴は介入不可
- [ ] error状態のAssistantは介入不可

### `test_intervention.py`

- [ ] `regenerate_from_here()` の正常系
- [ ] `insert_and_continue()` の正常系
- [ ] `selectionStart == 0`
- [ ] `selectionStart == len(content)`
- [ ] `selectionStart < 0` はエラー
- [ ] `selectionStart > len(content)` はエラー

### `test_config.py`

- [ ] デフォルト設定を検証する
- [ ] base_url空文字を検証する
- [ ] model空文字を検証する
- [ ] temperature範囲を検証する
- [ ] max_tokens範囲を検証する

### 完了条件

- [ ] `pytest` がローカルで通る
- [ ] UIなしで介入ロジックの安全性を確認できる

---

## 6. Milestone 3: Streamlit基本チャット

### 目的

通常のチャットUIをStreamlitで実装する。

### TODO

- [ ] `app.py` を作成する
- [ ] `st.set_page_config()` を設定する
- [ ] session state 初期化を呼び出す
- [ ] `st.chat_message` で履歴表示する
- [ ] `st.chat_input` で通常送信を受け取る
- [ ] Userメッセージを履歴に追加する
- [ ] ダミーAssistant応答を履歴に追加する
- [ ] 最新Assistantだけ特殊表示できるように表示経路を分離する

### 完了条件

- [ ] `streamlit run app.py` で起動できる
- [ ] 通常チャット入力ができる
- [ ] 入力内容が履歴に残る
- [ ] ダミーAssistant応答が表示される

---

## 7. Milestone 4: LLM接続

### 目的

OpenAI互換ローカルLLM APIと接続する。

### TODO

- [ ] `branch_writer/llm.py` を作成する
- [ ] OpenAI互換APIへリクエストする関数を実装する
- [ ] サイドバーにLLM設定UIを追加する
- [ ] API Base URLを設定できるようにする
- [ ] API Keyを設定できるようにする
- [ ] Modelを設定できるようにする
- [ ] Temperatureを設定できるようにする
- [ ] Max Tokensを設定できるようにする
- [ ] 通常チャット生成をダミー応答からLLM応答へ置き換える
- [ ] 接続失敗時のエラー表示を実装する

### 完了条件

- [ ] ローカルLLMへ通常チャットを送信できる
- [ ] ローカルLLMから応答を受け取れる
- [ ] 接続失敗時にUI上でエラーが表示される
- [ ] APIキーがgitに保存されない

---

## 8. Milestone 5: 最新Assistant特殊表示

### 目的

最新Assistantメッセージだけをcustom componentへ差し替える準備をする。

### TODO

- [ ] `render_frozen_message()` を作る
- [ ] `render_latest_assistant_message()` を作る
- [ ] 最新Assistantかどうかの判定を表示層で使う
- [ ] 過去メッセージはStreamlit標準表示にする
- [ ] 最新Assistantだけ別関数で表示する

### 完了条件

- [ ] 最新Assistantだけ表示経路が分離されている
- [ ] custom component導入前でも通常表示できる

---

## 9. Milestone 6: custom component 基盤

### 目的

React/TypeScriptのStreamlit custom componentを導入する。

### TODO

- [ ] `components/latest_message_editor/` を作成する
- [ ] Python wrapper `components/latest_message_editor/__init__.py` を作成する
- [ ] frontend `package.json` を作成する
- [ ] frontend `tsconfig.json` を作成する
- [ ] `LatestMessageEditor.tsx` を作成する
- [ ] `index.tsx` を作成する
- [ ] Pythonから `messageId` と `content` を渡せるようにする
- [ ] React側で本文を表示する
- [ ] React側からPythonへダミーイベントを返す

### 完了条件

- [ ] Streamlitからcustom componentを呼べる
- [ ] 最新Assistant本文がReact側に表示される
- [ ] Python側でcomponent返却値を受け取れる

---

## 10. Milestone 7: 選択位置取得

### 目的

最新Assistantメッセージ内のカーソル位置・選択範囲を取得する。

### TODO

- [ ] React側の本文表示を `textarea` ベースにする
- [ ] `selectionStart` を取得する
- [ ] `selectionEnd` を取得する
- [ ] カーソル移動時に選択値を保持する
- [ ] 範囲選択時に選択値を保持する
- [ ] Python側へ `selectionStart` / `selectionEnd` を返す

### 完了条件

- [ ] カーソル位置をPython側で確認できる
- [ ] 範囲選択の開始・終了をPython側で確認できる
- [ ] selectionStartを介入処理に渡せる

---

## 11. Milestone 8: ここから再生成

### 目的

最新Assistantメッセージの任意地点から先を破棄し、続きを再生成する。

### TODO

- [ ] componentに「ここから再生成」ボタンを追加する
- [ ] `regenerate_from_here` イベントを返す
- [ ] Python側で対象メッセージが介入可能か確認する
- [ ] `prefix = content[:selectionStart]` を作る
- [ ] discarded suffixをLLM文脈から除外する
- [ ] LLMへ介入生成を投げる
- [ ] 最新Assistant内容を `prefix + continuation` に置き換える
- [ ] Undo snapshotを保存する

### 完了条件

- [ ] 最新Assistantの途中から再生成できる
- [ ] 破棄したsuffixが生成文脈に含まれない
- [ ] 介入後も最新Assistantとして扱われる
- [ ] Undo可能な状態になる

---

## 12. Milestone 9: 入力して続ける

### 目的

最新Assistantメッセージの任意地点にユーザー文を挿入し、その後を生成する。

### TODO

- [ ] componentに「入力して続ける」ボタンを追加する
- [ ] 挿入文入力欄を表示する
- [ ] `insert_and_continue` イベントを返す
- [ ] Python側で対象メッセージが介入可能か確認する
- [ ] `prefix = content[:selectionStart]` を作る
- [ ] `prefix + insertion` を生成文脈にする
- [ ] discarded suffixをLLM文脈から除外する
- [ ] LLMへ介入生成を投げる
- [ ] 最新Assistant内容を `prefix + insertion + continuation` に置き換える
- [ ] Undo snapshotを保存する

### 完了条件

- [ ] 任意地点にユーザー文を挿入できる
- [ ] 挿入文の後をLLMが生成できる
- [ ] 破棄したsuffixが生成文脈に含まれない
- [ ] Undo可能な状態になる

---

## 13. Milestone 10: Undo

### 目的

直前の介入を取り消せるようにする。

### TODO

- [ ] UndoボタンをUIに追加する
- [ ] Undo stackから直前snapshotを取り出す
- [ ] 対象メッセージが最新Assistantか確認する
- [ ] 最新Assistantのcontentをbefore_contentへ戻す
- [ ] Undo失敗時のエラー表示を実装する

### 完了条件

- [ ] 直前の「ここから再生成」を取り消せる
- [ ] 直前の「入力して続ける」を取り消せる
- [ ] 最新Assistantが変わっている場合はUndoしない

---

## 14. Milestone 11: CI

### 目的

GitHub Actionsで最低限の品質確認を自動化する。

### TODO

- [ ] `.github/workflows/ci.yml` を作成する
- [ ] Pythonをセットアップする
- [ ] 依存関係をインストールする
- [ ] `pytest` を実行する
- [ ] 必要に応じてfrontendの型チェックを追加する

### 完了条件

- [ ] push時にCIが走る
- [ ] pytestがCI上で通る
- [ ] 失敗時に原因が追える

---

## 15. Milestone 12: README整備

### 目的

ユーザーがローカルでcloneして試せる状態にする。

### TODO

- [ ] プロダクト概要を書く
- [ ] v0の機能を書く
- [ ] セットアップ手順を書く
- [ ] ローカルLLM起動例を書く
- [ ] Streamlit起動手順を書く
- [ ] LLM設定項目を書く
- [ ] APIキーをコミットしない注意を書く
- [ ] 既知の制限を書く

### 完了条件

- [ ] READMEだけでローカル起動手順が分かる
- [ ] ローカルLLMのBase URL / Model設定が分かる
- [ ] v0でできること・できないことが分かる

---

## 16. ローカル実機テスト前チェックリスト

ユーザーがローカルでcloneして実機テストする前に、以下を満たす。

- [ ] `git clone` できる
- [ ] `pip install -r requirements.txt` できる
- [ ] `streamlit run app.py` で起動できる
- [ ] サイドバーでLLM設定を入力できる
- [ ] 通常チャット送信ができる
- [ ] ローカルLLMから応答を受け取れる
- [ ] 最新Assistantメッセージだけ介入UIが出る
- [ ] 任意地点から「ここから再生成」できる
- [ ] 任意地点から「入力して続ける」できる
- [ ] 直前の介入をUndoできる
- [ ] `pytest` が通る
- [ ] GitHub Actions CIが通る
- [ ] READMEに起動手順がある

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
- [ ] READMEに実行手順がある

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
