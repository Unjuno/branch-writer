# Branch Writer 最適化戦略

> Enter→first token の体感を、予想なし・予想ありで削る。

---

## 1. 基本認識

### 1.1 何を最適化するか

Branch Writer のコア UX は「文中の任意位置から続きだけ再生成」である。
普通の chat UI と違い、**cursor 位置を変えて何度も再生成する**という操作が頻発する。

したがって、重要な指標は単一发行のスループットではなく、以下になる。

| 指標 | 意味 | 目標 |
|---|---|---|
| TTFT P50 | Enter→初回token反映 中央値 | < 300ms |
| TTFT P95 | Enter→初回token反映 95パーセンタイル | < 800ms |
| abort-to-restart P95 | 割り込んで再生成までの間隔 95パーセンタイル | < 500ms |

### 1.2 何を予想するか

**予想するのは本文ではなく、計算状態である。**

```
悪い:
  ユーザーが次にどんな文章を欲しがるかを予測する

良い:
  ユーザーがEnterした瞬間に必要になるprefix計算を先に済ませる
```

### 1.3 前提確認（現状の正しさ）

Branch Writer の介入再生成は、discard suffix を backend へ送っていない。
`frozen_messages_before_latest()` は latest assistant 以外を返し、介入時も
`draft_content[:selection_start]` を prefix にしており、意味論的に正しい。

この構造を変える必要はない。変えるべきは**タイミング**と**cache 活用**。

---

## 2. 優先順位

| 優先 | 施策 | 難度 | 効き方 |
|---:|---|---|---|
| P0 | TTFT 分解計測 | 低 | 何が遅いか確定させる |
| P0 | UI render 最適化 | 低 | first token 即時反映、後続は coalesce |
| P1 | backend prefix cache (vLLM APC / SGLang RadixAttention / llama.cpp cache_prompt) | 中 | first token 前の無音を削る |
| P1 | cursor idle warmup (prefill only) | 中〜高 | Enter 後の prefill を前倒し |
| P2 | hidden regeneration | 高 | 当たればほぼ即表示 |
| P2 | speculative decoding | 中 | 流れ出した後を速くする |

### 2.1 やってはいけない順番

- hidden regeneration を最初にやるな。無駄撃ち・abort・slot 占有・stale stream 問題が増える。
- 予想系（warmup, hidden）は、非予想系（計測, cache, UI）が効かないと確定してから。

---

## 3. P0: 計測基盤（Step 1）

### 3.1 TTFT 分解

```
Enter (t0)
  → fetch開始 (t1)
    → FastAPI受信 (t2)
      → backend POST (t3)
        → upstream first chunk (t4)
      → SSE token emit (t5)
    → textarea 反映 (t6)
```

各 gap を取る：

| 区間 | 意味 | 支配的なら |
|---|---|---|
| t1-t0 | JS 処理遅延 | React 最適化 |
| t2-t1 | ネットワーク | localhost なら無視 |
| t3-t2 | FastAPI 内処理 | 軽微 |
| t4-t3 | prefill + queue | **backend cache が効く** |
| t5-t4 | SSE 直列化 | 無視 |
| t6-t5 | DOM 反映 | first token 即時、後続 coalesce |

### 3.2 記録項目

各タイムスタンプを `performance.now()` + SSE debug event で取得。
`backend_timings` は llama.cpp / Ollama / vLLM の response metrics から抽出。

---

## 4. P0: UI 最適化（Step 2）

### 4.1 方針

予想なしで効く。やるべき。

- first token だけは即時 `setDraftContent` する（絶対遅延させない）
- 後続 token は requestAnimationFrame または 20-33ms で coalesce する
- `Streamlit.setFrameHeight()` は高さが実際に変わったときだけ呼ぶ

### 4.2 効果

体感を変えずに React commit 数と layout 再計算を 50% 以上減らせる。
TTFT 自体の改善は小さいが、streaming 中の jank 削減になる。

---

## 5. P1: Backend Prefix Cache

### 5.1 原理

Branch Writer の再生成 prompt は、実質的にこうなる：

```
system prompt
user / assistant history
latest assistant prefix       ← これだけが変わる
```

`system + history` は cursor 位置が変わっても大きく変わらない。
したがって、backend 側で共通 prefix の KV cache を再利用する方式が効く。

### 5.2 候補 backend

| Backend | 仕組み | OpenAI-compat | 導入難度 |
|---|---|---|---|
| llama.cpp | `cache_prompt + id_slot` | あり | 低（既存 payload に field 追加） |
| vLLM | APC (`enable_prefix_caching`) | あり | 低（server 起動 option） |
| SGLang | RadixAttention | あり | 低（server 起動 option） |
| Ollama | cache 明示制御なし、`keep_alive` のみ | あり | — |
| LM Studio | KV cache 制御は docs 上未確認 | あり | — |

### 5.3 実験計画

同じ会話履歴で再生成を 2 回実行し、backend cache metrics を比較する。

- `cache_n / (cache_n + prompt_n) >= 0.8` かつ
- TTFT p50 が 30% 以上低下すれば合格

---

## 6. P1: Cursor Idle Warmup

### 6.1 仕組み

```text
cursor 移動 or 編集
  → 200ms 止まる
    → 現在の cursor 位置で prefix を作る
      → n_predict=0 相当で prefill だけ実行
        → Enter されたら同じ prefix で本生成
```

### 6.2 予想の範囲

予想しているのは「ユーザーは今の cursor 位置で Enter するかもしれない」だけ。
本文内容は一切予想しない。文章内容予測よりはるかに簡単。

### 6.3 条件

- backend cache が効くことを確認してから実装する
- 無駄撃ちしても 1 回の prefill コストだけ（生成はしない）
- 外れた場合も cache は次の再生成に使える

---

## 7. P2: Hidden Regeneration

### 7.1 仕組み

```text
cursor が止まる
  → 裏で実際に生成を開始
    → Enter されたらその stream を visible へ昇格
```

当たれば最高。体感はかなりヌルヌルになる。

### 7.2 リスク

外したときの無駄が大きい。

```
cursor が動いた
本文が変わった
model 設定が変わった
history が変わった
temperature が変わった
```

この場合、裏生成は全部破棄。local backend だと無駄撃ちが逆に体感を悪化させる。

### 7.3 実施条件（厳しく）

```text
- textarea が focus 中
- 直近 300ms 入力なし
- cursor 位置が安定
- 既存 stream なし
- backend が warm
- prompt token 数が一定以上
- 1 hidden stream まで
```

---

## 8. P2: Speculative Decoding

- 主に decode 高速化。TTFT 改善は限定的または悪化もありうる。
- llama.cpp `--spec-type ngram-mod` または draft model で試す。
- 創作文章では n-gram の効きがばらつく可能性あり。
- P0 計測で prefill が支配的と確定した場合は優先度を下げる。

---

## 9. 判断フロー

```text
P0: TTFT 分解計測
├─ T_prefill* 支配的 → P1 backend cache
│   └─ cache 効いた → P1 idle warmup
│       └─ さらに改善必要 → P2 hidden regeneration
│
├─ T_decode 支配的 → P2 speculative decoding
│
└─ T_ui 支配的 → P0 UI 最適化
    └─ それでも遅い → 計測再検討
```

---

## 10. 目標値

| 指標 | 現状（推定） | 目標 |
|---|---|---|
| TTFT P50 | 未計測 | < 300ms |
| TTFT P95 | 未計測 | < 800ms |
| abort-to-restart P95 | 未計測 | < 500ms |
| decode speed | 未計測 | 20+ token/s |

この水準を切れないなら「面白いデモ」のまま。
切れれば「実用的な cursor-native generation editor」になる。

---

## 11. 論文リサーチ結果

### 11.1 frozen prefix 特化 cache

| 論文 | 年 | 関係性 |
|---|---|---|
| **Prompt Cache** (MLSys 2024) | 2024 | **最も直接的**。prompt を module 単位に分割定義し、module 単位で attention state を再利用。GPU 8x, CPU 60x TTFT 改善。Branch Writer の frozen_messages + assistant_prefix 構造に自然にマッピング可能 |
| **Sparse Prefix Caching** (arXiv:2605.05219) | 2026 | dense な per-token cache ではなく sparse checkpoint のみ保存、残りは再計算。介入での微小な prefix 変更には再計算コストが低いという示唆 |
| **Not All Tokens Are Worth Caching** (2026) | 2026 | system prompt 92.3% reuse, CoT 2.2% reuse の差に着目。Branch Writer では frozen_messages を高優先、assistant_prefix の動的部分を低優先で evict する設計に使える |

### 11.2 abort-to-restart / speculative KV

| 論文 | 年 | 関係性 |
|---|---|---|
| **SpeCache** (arXiv:2503.16163) | 2025 | **ニッチかつ最重要**。次 token が attend する KV pair を予測して先読み。介入再生成で「同じ frozen prefix + 少し違う suffix」の先読みに直接応用可能 |
| **Transactional KV Caching for Speculative Decoding** (TechRxiv 2026) | 2026 | **abort に特化**。KV cache 書き込みを「未コミット」状態に保ち、accept 確定時のみ commit。abort 時に KV をロールバック可能 → 介入 abort 問題への新しいアプローチ |

### 11.3 マルチテナント / scheduling

| 論文 | 年 | 関係性 |
|---|---|---|
| **KVShare** (arXiv:2503.16525) | 2025 | 異なる request 間で KV cache 共有。DHD algorithm で selective recomputation。TTFT 9.39x 改善 |
| **k-LPM Scheduling** (arXiv:2502.04677) | 2025 | RadixAttention 下での query scheduling 理論。NP-hard 証明と k-LPM アルゴリズム。複数 session を扱う場合に応用可能 |

### 11.4 その他

| 論文 | 年 | 関係性 |
|---|---|---|
| **Self-Speculative Decoding with KV Cache Compression** (NTU 2026) | 2026 | draft-side KV cache 圧縮、acceptance rate を online control signal に利用 |
| **Predicting LLM Inference Latency: Roofline-Driven ML Method** (NeurIPS 2024) | 2024 | TTFT を roofline model で予測。計測基盤設計の参考 |

### 11.5 論文知見の判断フローへの反映

```text
P0: TTFT 分解計測
├─ T_prefill* 支配的 → P1 backend cache
│   ├─ 既存 backend (vLLM APC / SGLang RadixAttention / llama.cpp cache_prompt)
│   │   └─ まずはこれで十分。論文レベルの新規実装は不要
│   └─ さらに削りたい → Prompt Cache 方式の module-based attention reuse
│       └─ frozen_messages を module 化し、assistant_prefix だけ別 module にする
│           → Prefix Cache より granular な reuse。要 backend 改修 or proxy 層での実装
│
├─ T_decode 支配的 → P2 speculative decoding
│   └─ SpeCache の speculative KV prefetch が idle warmup の理論的裏付けになる
│
└─ abort が遅い → Transactional KV Caching
    └─ abort 時に KV をロールバックできる形で保持 → 再生成時の prefill 節約
```

### 11.6 実装判断

| 判断 | 根拠 |
|---|---|
| **論文レベルの新規実装は P0/P1 より優先しない** | 既存 backend (SGLang RadixAttention, vLLM APC) で Prefix Cache は利用可能。まずは backend 選択と設定でどこまで行けるかを確認する |
| **Prompt Cache 方式は P1 後に検討** | backend prefix cache が効かない or 不十分な場合の次の選択肢。実装コストが高いため P1 の結果を見て判断 |
| **Transactional KV Caching は影響が大きい** | `branch_writer/streaming_server.py` の abort 機構と密接に関わる。backend 側の対応が必要で、現時点では概念設計のみ |
| **既存 backend の cache_prompt / prefix caching / RadixAttention の設定確認と実験を最優先** | 導入コストが最も低く、最も確実な改善経路 |
