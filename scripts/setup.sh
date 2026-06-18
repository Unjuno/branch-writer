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

# ---- Python の確認 ----
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
  echo "❌ Python が見つかりません。https://www.python.org/downloads/ からインストールしてください。"
  exit 1
fi
PYTHON=$(command -v python3 || command -v python)
echo "✓ Python: $($PYTHON --version)"

# ---- Git の clone / pull ----
if [ -d "$APP_DIR" ]; then
  echo "✓ 既存のリポジトリを更新します..."
  cd "$APP_DIR" && git pull
else
  echo "✓ リポジトリをクローンします..."
  git clone "$REPO_URL" "$APP_DIR"
  cd "$APP_DIR"
fi

# ---- Python 仮想環境と依存関係 ----
if [ ! -d ".venv" ]; then
  echo "✓ 仮想環境を作成します..."
  $PYTHON -m venv .venv
fi
source .venv/bin/activate
echo "✓ 依存関係をインストールします..."
pip install -q -r requirements.txt

# ---- Ollama の確認 / 自動インストール ----
if ! command -v ollama &>/dev/null; then
  echo "⚠️  Ollama がインストールされていません。自動インストールします..."
  echo "   curl -fsSL https://ollama.com/install.sh | sh"
  curl -fsSL https://ollama.com/install.sh | sh
  if ! command -v ollama &>/dev/null; then
    echo "❌ Ollama のインストールに失敗しました。手動でインストールしてください:"
    echo "   curl -fsSL https://ollama.com/install.sh | sh"
    exit 1
  fi
fi
echo "✓ Ollama: $(ollama --version)"

# ---- モデルのダウンロード ----
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
