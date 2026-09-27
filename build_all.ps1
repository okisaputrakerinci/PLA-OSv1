# Build PLA-OSv1 — default layout (PyInstaller standard)
# GUI  : dist\PLAOSV1_GUI\PLAOSV1_GUI.exe
# CLI  : dist\plaosv1.exe
# Setup: dist\installer\PLA-OSv1-Setup-1.0.0-win.exe  (opsional, jika Inno Setup ada)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

# ===== A. KONFIG =====
$APP_NAME    = "PLA-OSv1"
$APP_VERSION = "1.0.0"
$COMPANY     = "OS AI Corp."
$COPYRIGHT   = "(c) 2025 Oki Saputra - OS AI Corp."
$ICON_PNG    = "logo_os_ai_corp.png"
$ICON        = "logo_os_ai_corp.ico"

$GUI_ENTRY   = "leaf_area_gui.py"
$CLI_ENTRY   = "leaf_area_research.py"
$DATA_DIR    = "leaf-area"     # ikut dibundle kalau ada

$ISS_PATH    = ".\installer\plaosv1-installer.iss"
$ISCC        = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $ISCC)) { $ISCC = "C:\Program Files\Inno Setup 6\ISCC.exe" }

# ===== B. VALIDASI & BUAT ICO (multi-size tajam, PowerShell-compatible) =====
foreach ($p in @($GUI_ENTRY, $CLI_ENTRY)) {
  if (-not (Test-Path $p)) { throw "File not found: $p" }
}
if (-not (Test-Path $ICON)) {
  if (Test-Path $ICON_PNG) {
    Write-Host "[ICON] $ICON tidak ada. Membuat dari $ICON_PNG ..."
    & python -m pip install --disable-pip-version-check --quiet pillow
    $pyCode = @'
from PIL import Image
src = "logo_os_ai_corp.png"
im  = Image.open(src).convert("RGBA")
sizes = [(256,256),(128,128),(96,96),(64,64),(48,48),(40,40),(32,32),(24,24),(20,20),(16,16)]
im.save("logo_os_ai_corp.ico", sizes=sizes)
'@
    $pyCode | & python -
    if (-not (Test-Path $ICON)) { throw 'Gagal membuat logo_os_ai_corp.ico' }
  } else {
    throw "Icon file not found: $ICON (atau $ICON_PNG)"
  }
}
if (Test-Path ".\installer") {
  Copy-Item ".\logo_os_ai_corp.ico" ".\installer\logo_os_ai_corp.ico" -Force -ErrorAction SilentlyContinue
}

# ===== C. HELPER: version-file (metadata EXE) =====
function New-VersionFile {
  param(
    [Parameter(Mandatory=$true)][string]$TargetPath,
    [Parameter(Mandatory=$true)][string]$ProductName,
    [Parameter(Mandatory=$true)][string]$FileDescription,
    [Parameter(Mandatory=$true)][string]$InternalName,
    [Parameter(Mandatory=$true)][string]$OriginalFilename,
    [Parameter(Mandatory=$true)][string]$CompanyName,
    [Parameter(Mandatory=$true)][string]$ProductVersion,
    [Parameter(Mandatory=$true)][string]$FileVersion,
    [string]$LegalCopyright = ""
  )
  $toTuple = {
    param($ver)
    $nums = ($ver -split '[^\d]') | Where-Object { $_ -match '^\d+$' }
    while ($nums.Count -lt 4) { $nums += "0" }
    "({0},{1},{2},{3})" -f $nums[0],$nums[1],$nums[2],$nums[3]
  }
  $filevers = & $toTuple $FileVersion
  $prodvers = & $toTuple $ProductVersion
  $langID   = "040904B0"

  $content = @'
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=__FILEVERS__,
    prodvers=__PRODVERS__,
    mask=0x3f,
    flags=0x0,
    OS=0x4,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        "__LANGID__",
        [
          StringStruct("CompanyName",      "__COMPANY__"),
          StringStruct("FileDescription",  "__FILEDESC__"),
          StringStruct("InternalName",     "__INTERNAL__"),
          StringStruct("OriginalFilename", "__ORIGINAL__"),
          StringStruct("ProductName",      "__PRODUCTNAME__"),
          StringStruct("ProductVersion",   "__PRODUCTVER__"),
          StringStruct("FileVersion",      "__FILEVER__"),
          StringStruct("LegalCopyright",   "__COPYRIGHT__")
        ]
      )
    ]),
    VarFileInfo([VarStruct("Translation", [1033, 1200])])
  ]
)
'@
  $content = $content.Replace('__FILEVERS__',   $filevers)
  $content = $content.Replace('__PRODVERS__',   $prodvers)
  $content = $content.Replace('__LANGID__',     $langID)
  $content = $content.Replace('__COMPANY__',    $CompanyName)
  $content = $content.Replace('__FILEDESC__',   $FileDescription)
  $content = $content.Replace('__INTERNAL__',   $InternalName)
  $content = $content.Replace('__ORIGINAL__',   $OriginalFilename)
  $content = $content.Replace('__PRODUCTNAME__',$ProductName)
  $content = $content.Replace('__PRODUCTVER__', $ProductVersion)
  $content = $content.Replace('__FILEVER__',    $FileVersion)
  $content = $content.Replace('__COPYRIGHT__',  $LegalCopyright)

  New-Item -ItemType Directory -Force -Path (Split-Path $TargetPath) | Out-Null
  Set-Content -Path $TargetPath -Value $content -Encoding UTF8
}

# ===== D. PERSIAPAN =====
$EXTRA = @()
if (Test-Path $DATA_DIR) { $EXTRA += "--add-data"; $EXTRA += "$DATA_DIR;$DATA_DIR" }
if (Test-Path $ICON)     { $EXTRA += "--add-data"; $EXTRA += "$ICON;." }
if (Test-Path $ICON_PNG) { $EXTRA += "--add-data"; $EXTRA += "$ICON_PNG;." }

Remove-Item -Recurse -Force .\build, .\dist, .\.venv_gui, .\.venv_cli -ErrorAction SilentlyContinue

$verDir     = ".\build\versioninfo"
$verGUIFile = Join-Path $verDir "ver_gui.txt"
$verCLIFile = Join-Path $verDir "ver_cli.txt"

New-VersionFile -TargetPath $verGUIFile `
  -ProductName $APP_NAME `
  -FileDescription "$APP_NAME GUI" `
  -InternalName "PLAOSV1_GUI" `
  -OriginalFilename "PLAOSV1_GUI.exe" `
  -CompanyName $COMPANY `
  -ProductVersion $APP_VERSION `
  -FileVersion $APP_VERSION `
  -LegalCopyright $COPYRIGHT

New-VersionFile -TargetPath $verCLIFile `
  -ProductName $APP_NAME `
  -FileDescription "$APP_NAME CLI" `
  -InternalName "plaosv1" `
  -OriginalFilename "plaosv1.exe" `
  -CompanyName $COMPANY `
  -ProductVersion $APP_VERSION `
  -FileVersion $APP_VERSION `
  -LegalCopyright $COPYRIGHT

# ===== E. (OPSIONAL) MANIFEST PerMonitorV2 (DPI scaling mulus) =====
$manifestPath = ".\build\manifest\pmv2.manifest"
New-Item -ItemType Directory -Force -Path (Split-Path $manifestPath) | Out-Null
@'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">PerMonitorV2</dpiAwareness>
    </windowsSettings>
  </application>
</assembly>
'@ | Set-Content $manifestPath -Encoding UTF8

# ===== F. BUILD GUI (onedir) =====
Write-Host "`n[GUI] Prepare venv (Python 3.11)..."
& python -m venv .\.venv_gui
.\.venv_gui\Scripts\python -m ensurepip --upgrade
.\.venv_gui\Scripts\python -m pip install --upgrade pip wheel setuptools
.\.venv_gui\Scripts\python -m pip install --no-cache-dir numpy opencv-python PySide6 pyinstaller pyinstaller-hooks-contrib

$pysideDir = (.\.venv_gui\Scripts\python -c "import PySide6,os; print(os.path.dirname(PySide6.__file__))").Trim()
$qtPlugins = Join-Path $pysideDir "plugins"
$qtBin     = Join-Path $pysideDir "Qt\bin"

$EXTRA_GUI = @()
$EXTRA_GUI += $EXTRA
if (Test-Path (Join-Path $qtPlugins "platforms")) {
  $EXTRA_GUI += "--add-binary"; $EXTRA_GUI += "$(Join-Path $qtPlugins 'platforms\*');PySide6\plugins\platforms"
}
foreach ($sub in @("imageformats","styles","iconengines")) {
  $src = Join-Path $qtPlugins $sub
  if (Test-Path $src) {
    $EXTRA_GUI += "--add-binary"; $EXTRA_GUI += "$src\*;PySide6\plugins\$sub"
  }
}
$ogl = Join-Path $qtBin "opengl32sw.dll"
if (Test-Path $ogl) {
  $EXTRA_GUI += "--add-binary"; $EXTRA_GUI += "$ogl;PySide6\Qt\bin"
}

$pyi_gui = ".\.venv_gui\Scripts\pyinstaller"
Write-Host "[GUI] PyInstaller..."
& $pyi_gui --noconfirm --clean --onedir --windowed `
  --name "PLAOSV1_GUI" `
  --icon "$ICON" `
  --version-file "$verGUIFile" `
  --manifest "$manifestPath" `
  --collect-all PySide6 `
  --collect-all shiboken6 `
  --collect-binaries PySide6 `
  --collect-submodules PySide6 `
  --hidden-import PySide6.QtCore `
  --hidden-import PySide6.QtGui `
  --hidden-import PySide6.QtWidgets `
  $EXTRA_GUI `
  ".\$GUI_ENTRY"

if (-not (Test-Path ".\dist\PLAOSV1_GUI\PLAOSV1_GUI.exe")) { throw "GUI build failed (dist\PLAOSV1_GUI\PLAOSV1_GUI.exe not found)." }

# ===== G. BUILD CLI (onefile) =====
Write-Host "`n[CLI] Prepare venv (Python 3.11)..."
& python -m venv .\.venv_cli
.\.venv_cli\Scripts\python -m ensurepip --upgrade
.\.venv_cli\Scripts\python -m pip install --upgrade pip wheel setuptools
.\.venv_cli\Scripts\python -m pip install --no-cache-dir numpy opencv-python pyinstaller

$pyi_cli = ".\.venv_cli\Scripts\pyinstaller"
Write-Host "[CLI] PyInstaller..."
& $pyi_cli --noconfirm --clean --onefile --console `
  --name "plaosv1" `
  --icon "$ICON" `
  --version-file "$verCLIFile" `
  $EXTRA `
  ".\$CLI_ENTRY"

if (-not (Test-Path ".\dist\plaosv1.exe")) { throw "CLI build failed (dist\plaosv1.exe not found)." }

# ===== H. DOKUMEN OPSIONAL =====
New-Item -ItemType Directory -Force -Path .\dist\docs | Out-Null
Copy-Item ".\User Manual GUI PLAOSV1.docx" ".\dist\docs\" -Force -ErrorAction SilentlyContinue
Copy-Item ".\Metode Estimasi Luas Daun.docx" ".\dist\docs\" -Force -ErrorAction SilentlyContinue

# ===== I. SINKRON VERSION DI .ISS =====
if (Test-Path $ISS_PATH) {
  $issText = Get-Content $ISS_PATH -Raw
  $issText = $issText -replace '(?m)^#define\s+MyVersion\s+"[^"]+"', "#define MyVersion `"$APP_VERSION`""
  $issText = $issText -replace '(?m)^VersionInfoVersion\s*=.*$', 'VersionInfoVersion={#MyVersion}'
  Set-Content $ISS_PATH -Value $issText -Encoding UTF8
  Write-Host "[Setup] Updated $ISS_PATH -> MyVersion=$APP_VERSION"
}

# ===== J. COMPILE INSTALLER (opsional) =====
if (Test-Path $ISCC) {
  if (-not (Test-Path $ISS_PATH)) { throw "Installer script not found: $ISS_PATH" }
  Write-Host "`n[Setup] Compiling Inno Setup..."
  & "$ISCC" "$ISS_PATH"
  if ($LASTEXITCODE -ne 0) { throw "Inno Setup compile failed: $LASTEXITCODE" }
  Write-Host "`n[OK] Installer: dist\installer\$APP_NAME-Setup-$APP_VERSION-win.exe"
} else {
  Write-Host "`n[SKIP] Inno Setup not found. Portable build ready in dist\"
  Write-Host "  GUI: dist\PLAOSV1_GUI\PLAOSV1_GUI.exe"
  Write-Host "  CLI: dist\plaosv1.exe"
}
