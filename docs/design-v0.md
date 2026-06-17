# Branch Writer v0 設計書

## 1. 目的

この文書は、Branch Writer v0 の実装に入る前に、画面構成、状態管理、LLM接続、介入処理、コンポーネント境界を固定するための設計書である。

Branch Writer v0 の目的は、次の一点を検証することである。

> 普通のチャットUI。ただし、AIの最新出力だけは途中から曲げられる。

v0では、完全な小説制作IDE、分岐管理ツール、設定管理ツール、長編執筆環境は目指さない。

---

## 2. 設計方針

### 2.1 基本方針

Branch Writer v0 は、通常のチャットUIを中心に構成する。

ただし、最新Assistantメッセージだけは、通常表示ではなく、介入可能なカスタムコンポーネントとして表示する。

```text
通常Userメッセージ        -> Streamlit標準表示
過去Assistantメッセージ   -> Streamlit標準表示
最新Assistantメッセージ   -> React/TypeScript custom component
通常チャット入力          -> Streamlit st.chat_input
LLM設定                  -> Streamlit sidebar
```

### 2.2 最新Assistantのみ特殊扱いする理由

介入対象は最新Assistantメッセージのみである。

過去メッセージを編集可能にすると、それ以降の会話履歴との整合性が壊れる。

そのため、設計上も最新Assistantだけを特殊表示し、それ以外は凍結済み履歴として扱う。

---

## 3. 画面設計

## 3.1 画面全体

画面は次の構成とする。

```text
+------------------------------------------------+
| Branch Writer                                  |
+------------------------------------------------+
| Sidebar                                        |
| - API Base URL                                 |
| - API Key                                      |
| - Model                                        |
| - Temperature                                  |
| - Max Tokens                                   |
+------------------------------------------------+
| Main                                           |
|                                                |
| User message                                   |
| Assistant message                              |
| User message                                   |
| Latest assistant message editor                |
|                                                |
| [chat input]                                   |
+------------------------------------------------+
```

### 3.2 サイドバー

サイドバーにはLLM接続設定を置く。

| 項目 | 型 | 初期値候補 | 備考 |
|---|---|---|---|
| API Base URL | string | `http://localhost:11434/v1` | OpenAI互換APIのURL |
| API Key | string | 空文字 | 不要な環境では空でよい |
| Model | string | 空文字 | ユーザーが指定 |
| Temperature | float | `0.7` | 0.0 - 2.0程度 |
| Max Tokens | int | `512` | 生成上限 |

APIキーはリポジトリに保存しない。

v0では、設定は `st.session_state` に保持する。

永続化はv0では必須にしない。

### 3.3 メイン領域

メイン領域にはチャット履歴を表示する。

表示ルールは次の通り。

```python
for i, message in enumerate(messages):
    is_latest = i == len(messages) - 1
    is_latest_assistant = is_latest and message.role == "assistant"

    if is_latest_assistant:
        render_latest_message_editor(message)
    else:
        render_frozen_message(message)
```

### 3.4 通常チャット入力

通常送信は Streamlit の `st.chat_input` で実装する。

ユーザーが通常メッセージを送信した場合、直前のAssistantメッセージは凍結済み履歴として扱われる。

---

## 4. メッセージ設計

### 4.1 メッセージ型

```python
from dataclasses import dataclass
from typing import Literal

MessageRole = Literal["user", "assistant"]
MessageStatus = Literal["streaming", "complete", "error"]

@dataclass
class ChatMessage:
    id: str
    role: MessageRole
    content: str
    status: MessageStatus
    created_at: str
```

### 4.2 編集可能判定

編集可能なメッセージは、次の条件をすべて満たすものだけである。

1. チャット履歴の最後のメッセージである。
2. `role == "assistant"` である。
3. `status` が `complete` または `streaming` である。

設計上は、まず `complete` のみを対象にしてよい。  
`streaming` 中の介入はv0実装後半またはv1で扱ってもよい。

```python
def is_intervenable(messages: list[ChatMessage], message_id: str) -> bool:
    if not messages:
        return False

    latest = messages[-1]
    return (
        latest.id == message_id
        and latest.role == "assistant"
        and latest.status in {"complete", "streaming"}
    )
```

### 4.3 凍結済みメッセージ

最新Assistant以外のメッセージは凍結済みとして扱う。

凍結済みメッセージは通常の `st.chat_message` + `st.markdown` で表示する。

---

## 5. 状態管理設計

### 5.1 `st.session_state` に持つ値

v0では、状態は `st.session_state` に保持する。

| Key | 型 | 用途 |
|---|---|---|
| `messages` | list[ChatMessage] | チャット履歴 |
| `llm_settings` | LlmSettings | LLM接続設定 |
| `undo_stack` | list[UndoSnapshot] | 介入取り消し用 |
| `is_generating` | bool | 生成中フラグ |
| `last_error` | str \/ None | 直近エラー |

### 5.2 LLM設定型

```python
from dataclasses import dataclass

@dataclass
class LlmSettings:
    base_url: str
    api_key: str
    model: str
    temperature: float
    max_tokens: int
```

### 5.3 Undoスナップショット型

```python
@dataclass
class UndoSnapshot:
    message_id: str
    before_content: str
    after_content: str
    action: str
    created_at: str
```

v0では、直前の介入だけUndoできればよい。

実装上は stack として持ち、必要なら複数回Undoにも対応できる構造にしておく。

---

## 6. LLM接続設計

### 6.1 接続方式

v0では、OpenAI互換の Chat Completions API を前提とする。

想定接続先:

- Ollama OpenAI-compatible endpoint
- LM Studio local server
- llama.cpp server
- OpenAI-compatible local proxy

### 6.2 LLMクライアント責務

`branch_writer/llm.py` にLLM接続処理を集約する。

責務:

- LLM設定からクライアントを構築する
- 通常チャット生成を実行する
- 介入後の続きを生成する
- エラーを握りつぶさず呼び出し元へ返す

### 6.3 通常チャット生成

通常チャット送信時は、凍結済み履歴を含む全メッセージをLLMに渡す。

```python
def generate_chat_response(
    messages: list[ChatMessage],
    settings: LlmSettings,
) -> str:
    ...
```

### 6.4 介入後の生成

介入時は、破棄された suffix を文脈に含めない。

LLMに渡す文脈は次の通り。

1. 最新Assistant以前の履歴
2. 最新Assistantの `prefix`
3. ユーザー挿入文があれば `insertion`

```python
def generate_intervention_continuation(
    frozen_messages: list[ChatMessage],
    assistant_prefix: str,
    insertion: str,
    settings: LlmSettings,
) -> str:
    ...
```

### 6.5 completion形式とchat形式

v0では実装簡易性を優先し、まずchat形式で実装する。

ただし、最新Assistantメッセージの途中継続は completion形式 の方が自然な場合がある。

そのため、`llm.py` 内部では将来差し替えできるように、呼び出し関数を分離する。

---

## 7. 介入処理設計

### 7.1 介入モード

v0の介入モードは2つ。

```python
InterventionMode = Literal[
    "regenerate_from_here",
    "insert_and_continue",
]
```

### 7.2 介入イベント

React custom component から Python へ返すイベントは次の形を想定する。

```python
@dataclass
class InterventionEvent:
    action: str
    message_id: str
    selection_start: int
    selection_end: int | None
    insertion: str | None
```

`action` は次のいずれか。

```text
regenerate_from_here
insert_and_continue
```

### 7.3 ここから再生成

```python
def apply_regenerate_from_here(
    content: str,
    selection_start: int,
    continuation: str,
) -> tuple[str, str, str]:
    prefix = content[:selection_start]
    discarded = content[selection_start:]
    next_content = prefix + continuation
    return next_content, prefix, discarded
```

### 7.4 入力して続ける

```python
def apply_insert_and_continue(
    content: str,
    selection_start: int,
    insertion: str,
    continuation: str,
) -> tuple[str, str, str]:
    prefix = content[:selection_start]
    discarded = content[selection_start:]
    next_content = prefix + insertion + continuation
    return next_content, prefix, discarded
```

### 7.5 selectionEnd の扱い

v0では、`selectionEnd` は主処理では使わない。

仕様上、選択範囲は「書き換える範囲」ではなく、「切断点」を指定するためのUIである。

常に `selectionStart` から先を破棄する。

`selectionEnd` は将来のUI改善やデバッグのために受け取るだけとする。

---

## 8. custom component 設計

### 8.1 役割

`components/latest_message_editor` は、最新Assistantメッセージ専用のReact/TypeScriptコンポーネントである。

責務:

- 最新Assistantメッセージ本文を表示する
- ユーザーの選択開始位置を取得する
- 選択時に介入操作を表示する
- 「ここから再生成」イベントを返す
- 「入力して続ける」イベントを返す

### 8.2 入力props

Python側からコンポーネントへ渡す値。

```ts
type LatestMessageEditorProps = {
  messageId: string;
  content: string;
  disabled?: boolean;
};
```

### 8.3 返却イベント

コンポーネントからPython側へ返す値。

```ts
type InterventionEvent = {
  action: "regenerate_from_here" | "insert_and_continue";
  messageId: string;
  selectionStart: number;
  selectionEnd: number;
  insertion?: string;
};
```

### 8.4 UI挙動

v0では、リッチテキストエディタは使わない。

最新Assistantメッセージは、選択可能なテキスト領域として表示する。

実装候補:

1. `textarea`
2. `pre` / `div` + `window.getSelection()`
3. `contenteditable`

初期実装では `textarea` を優先する。

理由:

- `selectionStart` / `selectionEnd` を取りやすい
- 実装が単純
- v0では装飾よりも介入体験が重要

### 8.5 操作メニュー

選択またはカーソル位置取得後、次の操作を表示する。

```text
[ここから再生成]
[入力して続ける]
```

`入力して続ける` では、同一コンポーネント内に短い入力欄を出す。

入力欄に文字を入れて確定すると、`insert_and_continue` イベントをPython側へ返す。

---

## 9. 通常送信フロー

### 9.1 処理手順

1. ユーザーが `st.chat_input` に入力する。
2. Userメッセージを `messages` に追加する。
3. LLMへ履歴を送る。
4. Assistant応答を生成する。
5. Assistantメッセージを `messages` に追加する。
6. 追加されたAssistantメッセージは最新なので介入可能になる。

### 9.2 疑似コード

```python
prompt = st.chat_input("メッセージを入力")

if prompt:
    append_user_message(prompt)
    response = generate_chat_response(messages, llm_settings)
    append_assistant_message(response)
```

---

## 10. ここから再生成フロー

### 10.1 処理手順

1. 最新Assistantメッセージ内でユーザーが地点を選ぶ。
2. custom component が `selectionStart` を返す。
3. Python側で対象メッセージが介入可能か確認する。
4. `prefix = content[:selectionStart]` を作る。
5. `discarded = content[selectionStart:]` はLLM文脈に含めない。
6. LLMに `prefix` の続きを生成させる。
7. `nextContent = prefix + continuation` を作る。
8. 最新Assistantメッセージの内容を `nextContent` に置き換える。
9. Undoスナップショットを保存する。

### 10.2 疑似コード

```python
if event.action == "regenerate_from_here":
    latest = messages[-1]
    assert is_intervenable(messages, latest.id)

    before = latest.content
    prefix = before[:event.selection_start]
    continuation = generate_intervention_continuation(
        frozen_messages=messages[:-1],
        assistant_prefix=prefix,
        insertion="",
        settings=llm_settings,
    )
    latest.content = prefix + continuation
    push_undo(latest.id, before, latest.content, event.action)
```

---

## 11. 入力して続けるフロー

### 11.1 処理手順

1. 最新Assistantメッセージ内でユーザーが地点を選ぶ。
2. ユーザーが挿入文を入力する。
3. custom component が `selectionStart` と `insertion` を返す。
4. Python側で対象メッセージが介入可能か確認する。
5. `prefix = content[:selectionStart]` を作る。
6. `discarded = content[selectionStart:]` はLLM文脈に含めない。
7. LLMに `prefix + insertion` の続きを生成させる。
8. `nextContent = prefix + insertion + continuation` を作る。
9. 最新Assistantメッセージの内容を `nextContent` に置き換える。
10. Undoスナップショットを保存する。

### 11.2 疑似コード

```python
if event.action == "insert_and_continue":
    latest = messages[-1]
    assert is_intervenable(messages, latest.id)

    before = latest.content
    prefix = before[:event.selection_start]
    insertion = event.insertion or ""
    continuation = generate_intervention_continuation(
        frozen_messages=messages[:-1],
        assistant_prefix=prefix,
        insertion=insertion,
        settings=llm_settings,
    )
    latest.content = prefix + insertion + continuation
    push_undo(latest.id, before, latest.content, event.action)
```

---

## 12. Undo設計

v0では、直前の介入を取り消せるようにする。

Undo対象は、最新Assistantメッセージへの介入のみである。

通常チャット送信のUndoはv0では扱わない。

### 12.1 処理手順

1. 介入前に `before_content` を保存する。
2. 介入後に `after_content` を保存する。
3. Undo実行時、対象メッセージがまだ最新Assistantであることを確認する。
4. 最新Assistantの内容を `before_content` に戻す。

### 12.2 疑似コード

```python
def undo_last_intervention():
    snapshot = undo_stack.pop()
    latest = messages[-1]

    if latest.id != snapshot.message_id:
        raise ValueError("Undo対象のメッセージが最新ではありません")

    latest.content = snapshot.before_content
```

---

## 13. エラー処理

### 13.1 LLM接続失敗

LLM APIへの接続に失敗した場合、ユーザーに設定確認を促す。

表示例:

```text
ローカルLLMに接続できませんでした。API Base URL、API Key、Modelを確認してください。
```

### 13.2 モデル未設定

Model が空の場合は生成を実行しない。

表示例:

```text
モデル名を設定してください。
```

### 13.3 介入対象不正

最新Assistant以外に対する介入イベントが来た場合は無視する。

表示例:

```text
このメッセージは既に凍結されているため、介入できません。
```

### 13.4 selectionStart 不正

`selectionStart` が `0 <= selectionStart <= len(content)` を満たさない場合は無視する。

---

## 14. テスト設計

v0で最低限テストする対象は、Streamlit画面そのものではなく、純粋関数として切り出せるロジックである。

### 14.1 `intervention.py`

テスト対象:

- `prefix` 計算
- `discarded` 計算
- `regenerate_from_here`
- `insert_and_continue`
- selectionStart境界値

### 14.2 `messages.py`

テスト対象:

- 最新Assistant判定
- Userメッセージは介入不可
- 過去Assistantは介入不可
- 空履歴の場合

### 14.3 `settings.py` または `config.py`

テスト対象:

- デフォルト設定
- Temperature / Max Tokens の範囲
- Base URL 空文字チェック
- Model 空文字チェック

---

## 15. 初期実装順

v0の実装順は次とする。

1. プロジェクト基盤作成
2. Streamlitアプリ起動
3. LLM設定UI
4. 通常チャット送信
5. LLM API呼び出し
6. メッセージ状態管理
7. 最新Assistantのみ特殊表示
8. React custom component 雛形
9. selectionStart / selectionEnd 取得
10. ここから再生成
11. 入力して続ける
12. Undo
13. pytest
14. GitHub Actions CI
15. README整備

---

## 16. v0で実装しないこと

設計上も、以下はv0では扱わない。

- 過去メッセージ編集
- 選択範囲だけのリライト
- 分岐ツリー
- 候補比較UI
- 自動矛盾検出
- 自然終了ガード
- 文末自動補正
- DB永続化
- 認証
- 複数ユーザー
- クラウド同期
- 高度なリッチテキストエディタ

---

## 17. 設計固定判断

v0では、以下の設計を固定する。

| 項目 | 判断 |
|---|---|
| 通常チャットUI | Streamlitで実装 |
| 最新Assistant表示 | custom componentで実装 |
| 選択位置取得 | React/TypeScript側で実装 |
| 介入イベント | custom componentからPythonへ返す |
| 通常生成 | PythonからOpenAI互換APIを呼ぶ |
| 介入生成 | 破棄suffixを除外して生成 |
| 状態管理 | `st.session_state` |
| Undo | 最新Assistant介入のみ対象 |
| 永続化 | v0では不要 |

この設計により、Streamlitの実装速度を保ちながら、Branch Writer v0の中核である「最新AI出力への途中介入」を実現する。
