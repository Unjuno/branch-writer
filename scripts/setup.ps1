# Branch Writer セットアップスクリプト (Windows PowerShell)
# 使い方: powershell -ExecutionPolicy Bypass -File setup.ps1

$RepoUrl = "https://github.com/Unjuno/branch-writer.git"
$AppDir = Join-Path $env:USERPROFILE "branch-writer"
$Model = "llama3.2:1b"

Write-Host "========================================"
Write-Host " Branch Writer セットアップ"
Write-Host "========================================"

# ---- Python 確認 ----
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "❌ Python が見つかりません。https://www.python.org/downloads/ からインストールしてください。"
    exit 1
}
Write-Host "✓ Python: $(& python --version)"

# ---- Git clone / pull ----
if (Test-Path $AppDir) {
    Write-Host "✓ 既存のリポジトリを更新します..."
    Set-Location $AppDir
    git pull
}
else {
    Write-Host "✓ リポジトリをクローンします..."
    git clone $RepoUrl $AppDir
    Set-Location $AppDir
}

# ---- Python 仮想環境 & 依存関係 ----
if (-not (Test-Path ".venv")) {
    Write-Host "✓ 仮想環境を作成します..."
    python -m venv .venv
}
.\.venv\Scripts\Activate.ps1
Write-Host "✓ 依存関係をインストールします..."
pip install -q -r requirements.txt

# ---- Ollama 確認 ----
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    Write-Host ""
    Write-Host "⚠️  Ollama がインストールされていません。"
    Write-Host "    https://ollama.com/download/windows からダウンロードしてインストールしてください。"
    Write-Host "    インストール後、もう一度このスクリプトを実行してください。"
    exit 1
}
Write-Host "✓ Ollama: $(& ollama --version)"

# ---- モデルダウンロード ----
Write-Host "✓ モデル ($Model) をダウンロードします（初回のみ）..."
ollama pull $Model

# ---- 起動 ----
Write-Host ""
Write-Host "========================================"
Write-Host " セットアップ完了！"
Write-Host " Streamlit を起動します..."
Write-Host "========================================"
Write-Host ""
streamlit run app.py
