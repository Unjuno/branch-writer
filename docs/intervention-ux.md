# Intervention UX Specification

この文書は Branch Writer の介入機能に関するUX仕様を定義します。将来の実装判断の基準となるため、コードより先にこの仕様を参照してください。

## 対象

- 介入操作は最新Assistantメッセージのみを対象とする
- 過去のAssistantメッセージは凍結され、介入不可
- ストリーミング中のAssistantメッセージも介入可能（status == "streaming"）

## Anchor (snapshot)

- 介入開始時に、その時点のテキスト全体をsnapshotとして保存する
- `isEditingRef` が `true` の間は anchor を更新しない（編集内容を保持するため）
- Enter が押された時点の `textarea.value` + `selectionStart` を `currentContent` としてPython側に送信する

## Streaming 中の表示制御

- textareaにフォーカスしていてユーザーが何も入力していない場合、stream token は表示更新される
- ユーザーが文字を入力した場合（`onChange`）、`isEditingRef = true` となりstream tokenの表示更新を停止する
- stream tokenはバックグラウンドで `accumulatedRef` に蓄積され続ける
- カーソル位置は `selectionRef` に保存され、stream更新後のre-renderで復元される

## Enter の動作

### 非生成中（isStreaming == false）

| 条件 | 動作 |
|---|---|
| Enter | inline_continue イベントを送信 |
| Shift+Enter | 改行（再生成トリガーしない） |
| IME変換中Enter | 無視 |

### 生成中（isStreaming == true）

| 条件 | 動作 |
|---|---|
| Enter | abort + inline_continue_interrupt イベントを送信 |
| Shift+Enter | 改行（再生成トリガーしない） |
| IME変換中Enter | 無視 |

### 送信内容

```
{
  type: "inline_continue" | "inline_continue_interrupt",
  messageId: string,
  currentContent: string,    // textarea.value 全体
  selectionStart: number,    // textarea.selectionStart
  insertion: "",             // 常に空文字
  requestId: string
}
```

## Python 側の処理

### _handle_inline

1. `currentContent` を `message.content` にsnapshot
2. `selectionStart` を `[0, len(currentContent)]` にclamp
3. `message.status = "streaming"`
4. `_intervention_event` を作成（action=regenerate_from_here, insertion=""）

### handle_intervention_event

1. `before_content = latest.content`（snapshot）
2. `prefix = before_content[:selection_start]`（cursor位置でtruncate）
3. `base_content = prefix + effective_insertion`（insertionは空なので prefix と同じ）
4. `latest.content = base_content`
5. Streaming intervention を開始（frozen_messages, assistant_prefix）

## Suffix 破棄

- 選択位置 `selectionStart` より後ろのテキストは常に破棄される
- これは仕様であり、バグではない
- 破棄されたテキストは undo 操作で復元可能

## Escape の動作

- `isEditingRef = false`
- `draftContent = accumulatedRef.current`（最新のstream内容に戻す）
- stream 自体は止めない

## Stale Guard

- 各streamには `streamKey` が割り当てられる
- 完了・エラーイベントの `streamKey` が現在のstreamと一致しない場合は無視する
- `failedStreamKeyRef` で失敗したstreamを記憶し、同一streamKeyの再開を防止する

## Undo

- 直前の介入操作のみ取り消せる
- 取り消し前のsnapshotを undo stack に保存
- 取り消し後は介入前の内容に復元する

## 生成中の割り込み（Interrupt）

1. React が `/api/abort` に現在の `streamId` を送信
2. ローカルの `abortController` をabort
3. `inline_continue_interrupt` イベントをPythonに送信
4. Python は即座に介入処理を実行（旧streamの完了を待たない）
5. 旧streamのgeneratorは abort event を検出して終了
6. 新streamが即座に開始される

## IME ガード

- `isComposingRef` + `nativeEvent.isComposing` + `keyCode === 229` の三重チェック
- 日本語・中国語などの入力途中のEnterで再生成がトリガーされないことを保証
