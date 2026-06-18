"""コード検証パネル — PythonコードでAIの出力を検証・編集する."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from branch_writer.llm import generate_text as _generate_text

TEMPLATES: dict[str, str] = {
    "空テンプレート": """\
# 利用可能な変数:
#   messages: list[ChatMessage]  会話履歴全体
#   last_content: str            最後のAssistantメッセージ
#   settings: LlmSettings        LLM設定
#   generate_text(prompt, settings) -> str  LLM呼び出し

result = {}
""",
    "不適切表現チェック": """\
result = {}

bad_words = ["間違い", "誤り", "違う", "失敗"]
found = [w for w in bad_words if w in last_content]
if found:
    pos = last_content.find(found[0])
    result = {
        "analysis": f"不適切な表現を検出: {', '.join(found)}",
        "suggestions": [
            {"action": "regenerate_from_here", "position": pos}
        ],
    }
""",
    "品質チェック": """\
result = {}
issues = []

if len(last_content) < 50:
    issues.append("出力が短すぎる（50字未満）")

sentences = last_content.count('。')
if sentences < 2:
    issues.append(f"文章が短い（{sentences}文）")

if '？' in last_content and '？' == last_content[-1]:
    issues.append("疑問文で終わっている")

if issues:
    result = {
        "analysis": " | ".join(issues),
        "suggestions": [
            {"action": "regenerate_from_here", "position": 0}
        ],
    }
""",
    "重複チェック": """\
result = {}
if len(messages) >= 2:
    prev = messages[-2].content if len(messages) >= 2 else ""
    if prev and prev[-60:] in last_content:
        result = {
            "analysis": "前回メッセージと内容が重複しています",
            "suggestions": [
                {"action": "regenerate_from_here", "position": 0}
            ],
        }
""",
    "LLMで文体チェック": '''\
result = {}

prompt = (
    "以下の創作文章を分析し、以下の3点を評価してください:\\n"
    "1. 文章の流れや自然さ（問題があれば指摘）\\n"
    "2. 改善すべき表現\\n"
    "3. 続きとして提案する方向性\\n\\n"
    "--- 分析対象 ---\\n"
    + last_content
)

analysis = generate_text(prompt, settings)
if "問題" in analysis or "改善" in analysis:
    result = {
        "analysis": analysis,
        "suggestions": [
            {"action": "regenerate_from_here", "position": 0}
        ],
    }
''',
    "キーワード抽出＋挿入": """\
result = {}
import re

# 特定のキーワードが見つかったら、その直後に補足を挿入
keywords = {"しかし": "ただし、", "例えば": "具体例:"}
for kw, prefix in keywords.items():
    if kw in last_content:
        pos = last_content.find(kw) + len(kw)
        result = {
            "analysis": f"「{kw}」を検出、補足挿入を提案",
            "suggestions": [
                {
                    "action": "insert_and_continue",
                    "position": pos,
                    "text": "\n\n（" + prefix + "補足説明をここに追加）",
                }
            ],
        }
        break
""",
}

VALIDATOR_HELP = """\
### 📖 コード検証パネルの使い方

右側のエディタでPythonコードを書き、左側のAI出力を検証できます。

**利用可能な変数:**
- `messages` — `list[ChatMessage]` 会話履歴全体
- `last_content` — `str` 最後のAssistantメッセージ
- `settings` — `LlmSettings` 現在のLLM設定

**コードが設定すべき変数:**
```python
result = {
    "analysis": "分析結果の説明",          # str
    "suggestions": [                       # list[dict]
        {
            "action": "regenerate_from_here",  # 以下から再生成
            "position": 123,                   # 文字位置
        },
        {
            "action": "insert_and_continue",   # 挿入して続ける
            "position": 123,
            "text": "挿入するテキスト",
        },
    ],
}
```

**基本フロー:**
1. テンプレートを選択して土台にする
2. 必要ならコードを編集・調整
3. 「コードを生成」でLLMに自動生成させる
4. 「実行」で検証 → 結果が下に表示
5. 提案があれば「提案を適用」で即座に反映

---

**💡 検証コードからLLMを呼び出す:**
``generate_text`` 関数で、LLM自身に出力を評価させられます:
```python
result = {}
analysis = generate_text(
    f"以下の創作文章の問題点を3つ挙げてください:\\n{last_content}",
    settings,
)
if "問題" in analysis:
    result = {{
        "analysis": analysis,
        "suggestions": [
            {{"action": "regenerate_from_here", "position": 0}}
        ],
    }}
```
"""

VALIDATOR_EXTRA_DOCS = """
### 🔄 LLM再帰検証の使い方

``generate_text(prompt, settings)`` でLLM自身に評価させられます。

**ユースケース例:**
- **文体チェック**: 「この文章を採点し、改善点を挙げてください」
- **事実確認**: 「この文章に矛盾点や誤りはありますか？」
- **トーン調整**: 「この文章のトーンを分析し、より読みやすくする提案をしてください」
- **続きの方向性**: 「この文章の続きとして、どのような展開が考えられますか？」

**注意点:**
- ``generate_text`` は会話履歴に影響しません（一時的な呼び出しです）
- 応答が遅くなる場合があります（LLMの応答時間に依存）
"""


def execute_validator_code(code: str, env: dict[str, Any]) -> dict[str, Any]:
    """Execute validator code in a sandboxed namespace.

    The code has access to ``messages``, ``last_content``, ``settings``,
    and ``generate_text`` from *env*, and must set a ``result`` variable
    (a dict with ``analysis`` and optionally ``suggestions``).
    """
    exec_env: dict[str, Any] = {
        "messages": env.get("messages", []),
        "last_content": env.get("last_content", ""),
        "settings": env.get("settings"),
        "generate_text": env.get("generate_text"),
        "result": {},
    }
    try:
        exec(code, exec_env)
        result = exec_env.get("result", {})
        if not isinstance(result, dict):
            return {
                "analysis": f"エラー: result は dict である必要があります (got {type(result).__name__})",
            }
        return result
    except Exception as exc:
        return {"analysis": f"コード実行エラー: {type(exc).__name__}: {exc}"}


def code_generation_prompt(
    last_user_message: str,
    last_assistant_content: str,
) -> str:
    """Build a prompt for the LLM to generate validation code."""
    return f"""\
あなたは創作支援ツール「Branch Writer」のコード生成アシスタントです。
現在の会話に基づいて、AIの出力を検証するPythonコードを生成してください。

## 直近のユーザー入力
{last_user_message or "(なし)"}

## AIの出力（検証対象）
{last_assistant_content}

## 要件
- コードのみを出力してください。説明文は不要です。
- 生成するコードは以下の変数にアクセスできます:
  - `last_content` (str): AIの出力内容
  - `messages` (list): 全メッセージ
  - `settings`: LLM設定
- コードは `result` 変数に dict を代入してください:
  ```python
  result = {{
      "analysis": "分析結果の説明",
      "suggestions": [
          {{
              "action": "regenerate_from_here",  # または "insert_and_continue"
              "position": 123,
              "text": "挿入テキスト",  # insert_and_continue の場合のみ必須
          }}
      ]
  }}
  ```
- suggestions は空リストでも構いません（問題がない場合）。
- エラーハンドリングは不要です（実行環境が補完します）。
"""
