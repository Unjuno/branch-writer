# Architecture

## 全体構造

```
app.py                          # Streamlit アプリケーションエントリポイント
branch_writer/
  config.py                     # LLM設定とモデル能力データベース
  intervention.py               # 再生成・挿入ロジック（suffix破棄, overlap stripping）
  llm.py                        # OpenAI 互換 API クライアント
  messages.py                   # チャットメッセージモデル
  model_discovery/              # MCP ベースのモデル探索
  state.py                      # セッション状態管理
  streaming_server.py           # SSE ストリーミングサーバー (FastAPI on port 8765)

components/
  latest_message_editor/        # React カスタムコンポーネント
    __init__.py                 # Streamlit コンポーネントラッパー
    frontend/
      src/LatestMessageEditor.tsx  # メインエディタコンポーネント

tests/                          # pytest テスト
scripts/                        # セットアップスクリプト
```

## React Component 内部状態

```
LatestMessageEditor.tsx
  draftContent: string          # textarea の表示内容
  streamId: string | null       # 現在のストリームID
  accumulatedRef: string        # 全stream tokenの蓄積（同期的読み取り用）
  isEditingRef: boolean         # ユーザー編集中フラグ（stream更新ブロック用）
  selectionRef: {start,end}     # カーソル位置保存（re-render後復元用）
  abortControllerRef            # 現在のstream fetch の AbortController
  doneSentRef                   # streaming_done 重複送信防止
  completedRef                  # 同一streamKeyの再開防止
  failedStreamKeyRef            # 失敗したstreamのkey記録
```

## Streaming サーバー（streaming_server.py）

- FastAPI on port 8765（固定）
- `POST /api/stream` - SSE ストリーム開始
- `POST /api/abort` - ストリーム中断
- `GET /health` - ヘルスチェック
- 通常生成: `_stream_normal()` - 全メッセージをLLMに送信
- 介入生成: `_stream_intervention()` - frozen_messages + assistant_prefix で生成

### SSE Event Types

| event | タイミング | data フィールド |
|---|---|---|
| token | 各chunk到着時 | fullContent, streamId |
| done | 生成完了 | fullContent, streamId |
| error | エラー発生 | message, streamId |
| aborted | 中断要求検出 | streamId |

## 介入データフロー

```
[User types in textarea]
  -> onChange: isEditingRef=true, stream表示更新停止
  -> Enter: sendInlineEvent()
    -> fetch /api/abort (生成中の場合)
    -> abortController.abort() (生成中の場合)
    -> Streamlit.setComponentValue({ type, currentContent, selectionStart })
      -> Python: _handle_inline()
        -> snapshot currentContent
        -> clamp selectionStart
        -> create _intervention_event
      -> Streamlit re-render
        -> React useEffect detects isStreaming + interventionData
        -> startStreaming("intervention", { baseContent, assistantPrefix, ... })
          -> POST /api/stream (mode=intervention)
          -> SSE events -> accumulatedRef -> setDraftContent
```

## 主要な設計判断

### なぜ React が streaming の主導権を持つか

Python（Streamlit）は状態管理とイベントルーティングに専念し、実際のHTTP streaming接続は React が管理します。これにより以下が可能になります。

- abort の即時性（Pythonのrerunを待たずに中断）
- `accumulatedRef` による同期的な内容参照
- `isEditingRef` による表示更新の細粒度制御

### なぜ textarea か

contenteditable はcursor位置の取得精度とstreaming更新との整合性に問題があります。textarea は `selectionStart` / `selectionEnd` が常に文字単位で正確で、React の controlled component として扱えます。
