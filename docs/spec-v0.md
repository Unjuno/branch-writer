# Branch Writer v0 仕様書

## 1. プロダクト概要

Branch Writer は、ローカルLLMを前提とした創作向けチャットUIである。

基本の見た目と操作は、一般的なチャットUIと同じにする。  
ただし、最新のAI応答だけは、途中の任意地点から介入・再生成できる。

中心となる体験は次である。

> 普通のチャットUI。ただし、AIの最新出力だけは途中から曲げられる。

---

## 2. コア体験

ユーザーは通常のチャット入力で指示を出す。

AIは小説・シーン・会話・描写などを生成する。

生成された最新のAI応答に対して、ユーザーが「ここから違う」と感じた場合、その地点から先を捨てて再生成できる。

また、ユーザーはその地点に自分の文を挿入してから、その続きをAIに生成させることもできる。

過去のメッセージは編集不可とする。

---

## 3. 基本原則

v0では、編集・介入できるのは **最新のAssistantメッセージのみ** とする。

過去のUserメッセージ、過去のAssistantメッセージは編集不可とする。

理由は、過去メッセージを後から編集すると、それ以降の会話履歴との整合性が壊れるためである。

ユーザーが新しいメッセージを送信した時点で、直前のAssistantメッセージは凍結される。

---

## 4. v0でユーザーができる操作

v0でユーザーができる基本操作は3つである。

### 4.1 通常チャット送信

ユーザーは、通常のChatGPT風UIと同じようにメッセージを入力して送信できる。

この操作により、ローカルLLMが通常のAssistant応答を生成する。

### 4.2 ここから再生成

ユーザーは、最新Assistantメッセージ内の任意地点を選択できる。

システムは、その地点より前のテキストを残し、その地点以降を破棄する。

その後、残したprefixを前提として、ローカルLLMに続きを生成させる。

### 4.3 入力して続ける

ユーザーは、最新Assistantメッセージ内の任意地点を選択し、そこに自分の文を入力できる。

システムは、その地点より前のテキストを残し、ユーザー文を挿入し、その後をローカルLLMに生成させる。

---

## 5. v0で実装する範囲

### 5.1 通常チャットUI

通常のチャットUIを提供する。

ユーザーはプロンプトを入力し、AIは応答を返す。

### 5.2 最新メッセージ限定の介入

介入できるのは最新のAssistantメッセージのみとする。

ユーザーが次のメッセージを送信した時点で、直前のAssistantメッセージは凍結される。

### 5.3 ここから再生成

ユーザーが最新Assistantメッセージ内の任意地点を選ぶ。

システムは、その地点より前のテキストを残し、その地点以降を破棄する。

その後、ローカルLLMに続きを生成させる。

### 5.4 入力して続ける

ユーザーが最新Assistantメッセージ内の任意地点を選び、自分の文を入力する。

システムは、その地点より前のテキストを残し、ユーザー文を挿入し、その後をローカルLLMに生成させる。

### 5.5 ローカルLLM

v0はローカルLLMを前提とする。

未公開原稿や創作中の本文をクラウドAPIへ送らず、ユーザーの手元で処理できることを重視する。

### 5.6 ローカルLLM接続設定

ユーザー環境ごとにローカルLLMサーバーのURL、APIキー、モデル名が異なるため、アプリ内で接続設定を変更できるようにする。

最低限、以下の設定項目を持つ。

| 項目 | 内容 | 例 |
|---|---|---|
| API Base URL | ローカルLLMサーバーのURL | `http://localhost:11434/v1` |
| API Key | APIキー。不要なローカル環境では空でもよい | `ollama` / `lm-studio` / 空文字 |
| Model | 使用するモデル名 | `qwen2.5:7b` / `llama3.1:8b` |
| Temperature | 生成のランダム性 | `0.7` |
| Max Tokens | 最大生成トークン数 | `512` |

v0では OpenAI互換のChat Completions API、またはそれに近いローカルLLM APIを想定する。

想定例:

- Ollama OpenAI-compatible endpoint
- LM Studio local server
- llama.cpp server
- OpenAI-compatible local proxy

APIキーはリポジトリに保存しない。

`.env` や `.env.local` を使う場合、それらは `.gitignore` に含める。

### 5.7 Undo

直前の介入は取り消せるようにする。

---

## 6. v0で実装しない範囲

以下はv0では実装しない。

- 過去メッセージの編集
- 選択範囲だけの部分リライト
- 候補A/B/Cの比較表示
- 分岐ツリーUI
- 自動矛盾検出
- 自然終了ガード
- 不自然な終端の自動修正
- 括弧・文末・助詞などの自動補正
- キャラクターDB
- 世界観・設定DB
- タイムライン管理
- 複数ドキュメント管理
- 出版・投稿機能
- マルチユーザー共同編集
- クラウド同期
- fine-tuning
- 独自モデル学習
- 高度な小説IDE機能

---

## 7. メッセージ編集ルール

あるメッセージが介入可能である条件は、次のすべてを満たす場合だけである。

1. チャット履歴の最新メッセージである。
2. role が `assistant` である。
3. status が `complete` または `streaming` である。

それ以外のメッセージは凍結状態とする。

---

## 8. 介入の意味論

最新Assistantメッセージの本文を `content` とする。

介入地点を `selectionStart` とする。

このとき、内部的には次のように扱う。

```text
prefix = content.slice(0, selectionStart)
discarded = content.slice(selectionStart)
```

### 8.1 ここから再生成

```text
nextContent = prefix + continuation
```

### 8.2 入力して続ける

```text
nextContent = prefix + insertion + continuation
```

`discarded` は新しい生成文脈には含めない。

ただし、Undo用には内部的に保持してよい。

---

## 9. 生成時の文脈構築

介入時、LLMに渡す文脈は次の要素から構成する。

1. 凍結済みの過去チャット履歴
2. 最新Assistantメッセージの `prefix`
3. ユーザー挿入文がある場合は `insertion`

破棄されたsuffix、つまり `discarded` は文脈に含めない。

---

## 10. データモデル案

v0時点で想定する最小データモデルは次の通りである。

```ts
type MessageRole = "user" | "assistant";

type MessageStatus = "streaming" | "complete" | "error";

type ChatMessage = {
  id: string;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  createdAt: string;
};

type InterventionMode = "regenerate_from_here" | "insert_and_continue";

type InterventionRequest = {
  messageId: string;
  selectionStart: number;
  insertion?: string;
  mode: InterventionMode;
};

type LlmSettings = {
  baseUrl: string;
  apiKey: string;
  model: string;
  temperature: number;
  maxTokens: number;
};
```

---

## 11. v0の成功条件

ユーザーが30秒以内に次の価値を理解できること。

> 普通のチャットUIなのに、AIの最新出力だけは「ここから違う」と思った地点からやり直せる。

---

## 12. v0の非目標

Branch Writer v0 は、完全な小説制作IDEを目指さない。

キャラクター、伏線、時系列、分岐、矛盾、終端補正をすべて管理するツールではない。

v0の目的は、ただ1つの操作体験を検証することである。

> 最新AI出力への途中介入。

---

## 13. 仕様固定時点の判断

v0では、以下の判断を固定する。

| 項目 | 判断 |
|---|---|
| UI | 普通のチャットUI |
| 介入対象 | 最新Assistantメッセージのみ |
| 操作 | 通常送信 / ここから再生成 / 入力して続ける |
| LLM | ローカルLLM前提 |
| LLM設定 | UIからBase URL / API Key / Model等を変更可能 |
| 過去履歴 | 編集不可 |
| 候補表示 | v0では実装しない |
| 分岐ツリー | v0では実装しない |
| 自動補正 | v0では実装しない |
