<#
================================================================================
  JARVIS — one-command Windows setup / handover installer
================================================================================
  Run this on the NEW Windows PC and it does the whole job:
    1. Installs every piece of software JARVIS needs (Python, Git, Node.js,
       and optionally Ollama / Tesseract / FFmpeg) via winget.
    2. Clones the repo (default branch = claude/ponytail-full-command-wuy33g).
    3. Creates the Python virtual environment and installs all requirements.
    4. Writes your .env, prompting you ONCE for your Anthropic API key
       (entered hidden — no key ever sits in this script or in your clipboard
       history longer than needed).
    5. Optionally pulls the local Ollama models (free offline brain).
    6. Optionally sets up connected-apps (MCP) config.
    7. Optionally imports your old notes/tasks/memory database.
    8. Makes a Desktop shortcut and runs the self-test.

  Fastest way to run it (paste into PowerShell on the new PC):

    powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/hughdwill-byte/JARVIS/claude/windows-setup-handover-ahmutr/setup/windows_bootstrap.ps1 | iex"

  Safe to re-run: it skips anything already installed.
================================================================================
#>

$ErrorActionPreference = 'Stop'
$RepoUrl    = 'https://github.com/hughdwill-byte/JARVIS.git'
$Branch     = 'claude/ponytail-full-command-wuy33g'   # the version you asked for
$InstallDir = Join-Path $HOME 'JARVIS'

function Section($t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }
function Ok($t)      { Write-Host "  [ok] $t"   -ForegroundColor Green }
function Info($t)    { Write-Host "  $t"        -ForegroundColor Gray }
function Warn($t)    { Write-Host "  [!] $t"    -ForegroundColor Yellow }
function Ask($q, $default='y') {
    $hint = if ($default -eq 'y') { '[Y/n]' } else { '[y/N]' }
    $a = Read-Host "  $q $hint"
    if ([string]::IsNullOrWhiteSpace($a)) { return ($default -eq 'y') }
    return ($a.Trim().ToLower().StartsWith('y'))
}

function Refresh-Path {
    $m = [Environment]::GetEnvironmentVariable('Path','Machine')
    $u = [Environment]::GetEnvironmentVariable('Path','User')
    $env:Path = ($m, $u | Where-Object { $_ }) -join ';'
}

function Have($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

function Winget-Install($id, $friendly) {
    Info "Installing $friendly ..."
    winget install --id $id -e --source winget `
        --accept-package-agreements --accept-source-agreements `
        --silent --disable-interactivity | Out-Null
    Refresh-Path
}

# ------------------------------------------------------------------ banner ---
Write-Host @'

    ###########################################################
    #                 JARVIS  ->  new Windows PC              #
    #        one command: software + code + keys + data       #
    ###########################################################
'@ -ForegroundColor Cyan

# ------------------------------------------------------------- 0. winget ---
Section '0/8  Checking winget (Windows Package Manager)'
if (-not (Have 'winget')) {
    Warn 'winget was not found.'
    Info 'Install "App Installer" from the Microsoft Store, then re-run this script.'
    Info 'Store link: https://apps.microsoft.com/detail/9nblggh4nns1'
    return
}
Ok 'winget is available'

# ---------------------------------------------------- 1. core software ---
Section '1/8  Core software (required)'
if (Have 'python') { Ok "Python present ($(python --version 2>&1))" }
else               { Winget-Install 'Python.Python.3.12' 'Python 3.12' }

if (Have 'git') { Ok "Git present ($((git --version) 2>&1))" }
else            { Winget-Install 'Git.Git' 'Git' }

if (Have 'node') { Ok "Node.js present ($(node --version 2>&1)) — needed for connected apps (MCP)" }
else             { Winget-Install 'OpenJS.NodeJS.LTS' 'Node.js LTS' }

if (-not (Have 'python')) {
    Warn 'Python still not on PATH. Close this window, open a NEW PowerShell, and re-run.'
    return
}

# ------------------------------------------------ 2. optional software ---
Section '2/8  Optional software'
Info 'Ollama    = free offline brain + local search over your notes (recommended)'
Info 'Tesseract = free local OCR for /ocr reading text from the camera'
Info 'FFmpeg    = helps audio/whisper on some machines'
$wantOllama = Ask 'Install Ollama (free local AI brain)?' 'y'
if ($wantOllama) {
    if (Have 'ollama') { Ok 'Ollama already installed' }
    else               { Winget-Install 'Ollama.Ollama' 'Ollama' }
}
if (Ask 'Install Tesseract OCR?' 'y') {
    if (Have 'tesseract') { Ok 'Tesseract already installed' }
    else                  { Winget-Install 'UB-Mannheim.TesseractOCR' 'Tesseract OCR' }
}
if (Ask 'Install FFmpeg?' 'n') {
    if (Have 'ffmpeg') { Ok 'FFmpeg already installed' }
    else               { Winget-Install 'Gyan.FFmpeg' 'FFmpeg' }
}

# --------------------------------------------------------- 3. get code ---
Section "3/8  Getting the code  ($Branch)"
if (Test-Path (Join-Path $InstallDir '.git')) {
    Ok "Repo already at $InstallDir — updating"
    Push-Location $InstallDir
    git fetch origin | Out-Null
    git checkout $Branch | Out-Null
    git pull origin $Branch | Out-Null
    Pop-Location
} else {
    git clone --branch $Branch $RepoUrl $InstallDir
    Ok "Cloned to $InstallDir"
}
Set-Location $InstallDir

# --------------------------------------------- 4. venv + requirements ---
Section '4/8  Python environment + dependencies'
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    python -m venv .venv
    Ok 'Created .venv'
}
$py = Resolve-Path '.venv\Scripts\python.exe'
& $py -m pip install --upgrade pip | Out-Null
Info 'Installing requirements (this is the slow part — a few minutes) ...'
& $py -m pip install -r requirements.txt
Ok 'All Python packages installed'

# -------------------------------------------------- 5. keys / .env ---
Section '5/8  API key & configuration (.env)'
if (Test-Path '.env') {
    Ok '.env already exists — leaving it untouched'
} else {
    Copy-Item '.env.example' '.env'
    Info 'Your Anthropic API key powers chat, vision and agent tasks.'
    Info 'It is NOT stored anywhere I could copy from your Mac — get/rotate it at'
    Info '  https://console.anthropic.com  (Settings -> API Keys).'
    Info 'Paste it now (hidden) or press Enter to skip and add it later in the app.'
    $secure = Read-Host '  ANTHROPIC_API_KEY' -AsSecureString
    $bstr   = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $key    = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    if (-not [string]::IsNullOrWhiteSpace($key)) {
        (Get-Content '.env') -replace '^ANTHROPIC_API_KEY=.*', "ANTHROPIC_API_KEY=$($key.Trim())" |
            Set-Content '.env'
        Ok 'API key saved to .env'
    } else {
        Warn 'No key entered — add it later in the app: Settings -> AI Brain -> Save & Apply'
    }
    if ($wantOllama -and (Ask 'Use the FREE local model for everyday chat (local_first mode)?' 'n')) {
        (Get-Content '.env') -replace '^LLM_PROVIDER=.*', 'LLM_PROVIDER=local_first' |
            Set-Content '.env'
        Ok 'LLM_PROVIDER set to local_first'
    }
}

# ------------------------------------------------ 6. Ollama models ---
Section '6/8  Local AI models (Ollama)'
if ($wantOllama -and (Have 'ollama')) {
    if (Ask 'Download the local models now (qwen3:8b + nomic-embed-text, ~5 GB)?' 'y') {
        Info 'Pulling qwen3:8b (chat) ...';           ollama pull qwen3:8b
        Info 'Pulling nomic-embed-text (notes search) ...'; ollama pull nomic-embed-text
        Ok 'Local models ready'
    } else { Info 'Skipped — run "ollama pull qwen3:8b" later if you want offline chat.' }
} else {
    Info 'Ollama not installed — skipping (cloud mode still works with your API key).'
}

# ----------------------------------------- 7. connected apps + data ---
Section '7/8  Connected apps (MCP) & your old data'
if (-not (Test-Path 'mcp_servers.json')) {
    if (Ask 'Set up connected-apps config now (Gmail, Calendar, Notion, ...)?' 'n') {
        Copy-Item 'mcp_servers.example.json' 'mcp_servers.json'
        Ok 'Created mcp_servers.json from the template.'
        Info 'Edit it to keep only the apps you use and paste each app''s token, then'
        Info 'do each app''s one-time login. Full guide: docs\COMPUTER_AND_APPS.md'
        if (Ask 'Open it in Notepad now?' 'n') { notepad 'mcp_servers.json' }
    } else {
        Info 'Skipped. Copy mcp_servers.example.json -> mcp_servers.json anytime to enable apps.'
    }
} else { Ok 'mcp_servers.json already present' }

Info ''
Info 'Your notes / tasks / memories live in a database file (data\jarvis.db) that is'
Info 'NOT in GitHub. To carry your history over, copy that file from your Mac'
Info '(JARVIS/data/jarvis.db) into this folder''s data\ directory.'
if (Ask 'Have you placed an old jarvis.db somewhere and want to import it now?' 'n') {
    $src = Read-Host '  Full path to your old jarvis.db'
    if (Test-Path $src) {
        New-Item -ItemType Directory -Force -Path 'data' | Out-Null
        Copy-Item $src 'data\jarvis.db' -Force
        Ok 'Imported your previous notes/tasks/memory.'
    } else { Warn "Not found: $src — skipping (JARVIS will start fresh)." }
}

# ------------------------------------------- 8. shortcut + self-test ---
Section '8/8  Desktop shortcut & self-test'
try {
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'JARVIS.lnk'))
    $lnk.TargetPath       = Join-Path $InstallDir 'launchers\JARVIS.bat'
    $lnk.WorkingDirectory = $InstallDir
    $lnk.Save()
    Ok 'Desktop shortcut "JARVIS" created'
} catch { Warn "Could not create shortcut: $($_.Exception.Message)" }

Info 'Running self-test ...'
try { & $py run_assistant.py --check } catch { Warn "Self-test reported: $($_.Exception.Message)" }

# ------------------------------------------------------------- done ---
Write-Host "`n===============================================================" -ForegroundColor Green
Write-Host ' JARVIS is installed. Start it any time by:' -ForegroundColor Green
Write-Host "   - double-clicking the JARVIS shortcut on your Desktop, or"
Write-Host "   - opening PowerShell and running:"
Write-Host "       cd `"$InstallDir`"; .venv\Scripts\activate; python run_app.py"
Write-Host ''
Write-Host ' Windows tip: Settings -> Privacy & security -> Microphone AND Camera'
Write-Host '   -> turn ON "Let desktop apps access ...", or the mic records silence.'
Write-Host ' In the app: Settings -> pick mic/speaker/camera by name -> Save & Apply.'
Write-Host "===============================================================" -ForegroundColor Green
