#!/usr/bin/env bash
set -euo pipefail

# Branch Writer セットアップスクリプト (macOS / Linux)
# 使い方: curl -fsSL https://ollama.com/install.sh | sh で Ollama を入れてから、
#         このスクリプトを実行するか、まとめて:
#   bash <(curl -fsSL https://raw.githubusercontent.com/Unjuno/branch-writer/main/scripts/setup.sh)

REPO_URL="https://github.com/Unjuno/branch-writer.git"
APP_DIR="$HOME/branch-writer"
MODEL="llama3.2:1b"

echo "========================================"
echo " Branch Writer セットアップ"
echo "========================================"

# ---- Python 確認 ----
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
  echo "❌ Python が見つかりません。https://www.python.org/downloads/ からインストールしてください。"
  exit 1
fi
PYTHON=$(command -v python3 || command -v python)
echo "✓ Python: $($PYTHON --version)"

# ---- Git clone / pull ----
if [ -d "$APP_DIR" ]; then
  echo "✓ 既存のリポジトリを更新します..."
  cd "$APP_DIR" && git pull
else
  echo "✓ リポジトリをクローンします..."
  git clone "$REPO_URL" "$APP_DIR"
  cd "$APP_DIR"
fi

# ---- Python 仮想環境 & 依存関係 ----
if [ ! -d ".venv" ]; then
  echo "✓ 仮想環境を作成します..."
  $PYTHON -m venv .venv
fi
source .venv/bin/activate
echo "✓ 依存関係をインストールします..."
pip install -q -r requirements.txt

# ---- Ollama 確認 ----
if ! command -v ollama &>/dev/null; then
  echo ""
  echo "⚠️  Ollama がインストールされていません。"
  echo "   以下のコマンドでインストールしてください:"
  echo ""
  echo "   curl -fsSL https://ollama.com/install.sh | sh"
  echo ""
  echo "   インストール後、もう一度このスクリプトを実行してください。"
  exit 1
fi
echo "✓ Ollama: $(ollama --version)"

# ---- モデルダウンロード ----
echo "✓ モデル ($MODEL) をダウンロードします（初回のみ）..."
ollama pull "$MODEL"

# ---- 起動 ----
echo ""
echo "========================================"
echo " セットアップ完了！"
echo " Streamlit を起動します..."
echo "========================================"
echo ""
streamlit run app.py
