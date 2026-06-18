# Branch Writer セットアップスクリプト (Windows PowerShell)
# 使い方: powershell -ExecutionPolicy Bypass -File setup.ps1

$RepoUrl = "https://github.com/Unjuno/branch-writer.git"
$AppDir = Join-Path $env:USERPROFILE "branch-writer"
$Model = "llama3.2:1b"

Write-Host "========================================"
Write-Host " Branch Writer セットアップ"
Write-Host "========================================"

# ---- Python の確認 ----
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "❌ Python が見つかりません。https://www.python.org/downloads/ からインストールしてください。"
    exit 1
}
Write-Host "✓ Python: $(& python --version)"

# ---- Git の clone / pull ----
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

# ---- Python 仮想環境と依存関係 ----
if (-not (Test-Path ".venv")) {
    Write-Host "✓ 仮想環境を作成します..."
    python -m venv .venv
}
.\.venv\Scripts\Activate.ps1
Write-Host "✓ 依存関係をインストールします..."
pip install -q -r requirements.txt

# ---- Ollama の確認 / 自動インストール ----
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    Write-Host "⚠️  Ollama がインストールされていません。自動インストールを試みます..."
    Write-Host "   Winget で Ollama をインストール中..."
    try {
        winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements 2>$null
    } catch {
        Write-Host "⚠️  Winget でのインストールに失敗しました。手動でインストールしてください:"
        Write-Host "    https://ollama.com/download/windows"
        exit 1
    }
    # winget インストール後、path が通るまでリフレッシュ
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollama) {
        Write-Host "⚠️  Ollama が見つかりません。手動でインストールしてください:"
        Write-Host "    https://ollama.com/download/windows"
        exit 1
    }
}
Write-Host "✓ Ollama: $(& ollama --version)"

# ---- モデルのダウンロード ----
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
