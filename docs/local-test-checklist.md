# Branch Writer v0 ローカル実機テスト手順

## 1. 目的

この文書は、ユーザーがローカル環境で Branch Writer v0 を確認するための最小チェックリストである。

---

## 2. セットアップ

```bash
git clone https://github.com/Unjuno/branch-writer.git
cd branch-writer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
git clone https://github.com/Unjuno/branch-writer.git
cd branch-writer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 3. Pythonテスト

```bash
python -m pytest
```

期待結果:

```text
passed
```

---

## 4. React component build

```bash
cd components/latest_message_editor/frontend
npm install
npm run build
cd ../../..
```

期待結果:

```text
build completed successfully
```

---

## 5. アプリ起動

```bash
streamlit run app.py
```

期待結果:

- ブラウザでBranch Writerが開く
- サイドバーにLLM設定が出る
- チャット入力欄が出る

---

## 6. LLM設定

サイドバーで以下を設定する。

| 項目 | 例 |
|---|---|
| API Base URL | `http://localhost:11434/v1` |
| API Key | 空文字または任意のローカル用文字列 |
| Model | ローカルLLM側で起動しているモデル名 |
| Temperature | `0.7` |
| Max Tokens | `512` |

---

## 7. 通常チャット確認

1. チャット入力欄に短い文章を入力する。
2. Assistant応答が返ることを確認する。
3. 応答が最新Assistantメッセージとして表示されることを確認する。

期待結果:

- Userメッセージが履歴に追加される
- Assistantメッセージが履歴に追加される
- 最新Assistantだけ介入UIになる

---

## 8. ここから再生成確認

React componentをbuildしていない場合は、手動 `selectionStart` fallback UI で確認する。

1. 最新Assistantメッセージの途中位置を選ぶ、または `selectionStart` を手入力する。
2. 「ここから再生成」を押す。
3. 選択地点より後ろが破棄され、新しい続きを生成することを確認する。

期待結果:

- prefixは残る
- discarded suffixは消える
- 新しい continuation が付く
- Undoボタンが有効になる

---

## 9. 入力して続ける確認

1. 最新Assistantメッセージの途中位置を選ぶ、または `selectionStart` を手入力する。
2. 挿入文を入力する。
3. 「入力して続ける」を押す。
4. prefix + insertion + continuation になることを確認する。

期待結果:

- prefixは残る
- insertionが入る
- discarded suffixは消える
- insertionの後ろをLLMが続ける
- Undoボタンが有効になる

---

## 10. Undo確認

1. 「ここから再生成」または「入力して続ける」を実行する。
2. サイドバーの「Undo last intervention」を押す。
3. 最新Assistantメッセージが介入前の内容に戻ることを確認する。

期待結果:

- 直前の介入だけ取り消せる
- 最新Assistantが変わっている場合はUndoしない

---

## 11. v0で確認しないもの

以下はv0対象外。

- 過去メッセージ編集
- 分岐ツリーUI
- 候補比較UI
- 自動矛盾検出
- 自然終了ガード
- 永続保存
