; plaosv1-installer.iss — Inno Setup script (fixed & clean)
#define MyAppName     "PLA-OSv1"
#define MyVersion "1.0.0"
#define MyPublisher   "OS AI Corp."
#define MyURL         "https://example.invalid"
#define DistRoot      "..\\dist\\PLAOSV1_GUI"

[Setup]
AppId={{F9A8F5E2-7D1E-4B1C-AF42-PLAOSV1-ANYCPU}}
AppName={#MyAppName}
AppVersion={#MyVersion}
AppPublisher={#MyPublisher}
AppPublisherURL={#MyURL}

; Install ke Program Files (64-bit) jika tersedia
DefaultDirName={autopf64}\OS AI Corp\{#MyAppName}
DefaultGroupName={#MyAppName}

OutputDir=..\dist\installer
OutputBaseFilename={#MyAppName}-Setup-{#MyVersion}-win

; Arsitektur modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
DisableDirPage=no
DisableProgramGroupPage=no

VersionInfoDescription=PLA-OSv1 is a research tool for leaf area estimation.
VersionInfoProductName=PLA-OSv1
VersionInfoVersion={#MyVersion}
AppCopyright=© 2025 Oki Saputra – OS AI Corp.

; Agar broadcast PATH ke proses baru
ChangesEnvironment=yes

; ---- License page (optional) ----
#ifexist "EULA.rtf"
LicenseFile=EULA.rtf
#endif
#ifexist "EULA.txt"
LicenseFile=EULA.txt
#endif

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create Desktop shortcut (GUI)"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "addpath"; Description: "Add plaosv1 to PATH (system)"; GroupDescription: "CLI Integration:"; Flags: unchecked

[Files]
; Bundle hasil PyInstaller (GUI onedir)
Source: "{#DistRoot}\*"; DestDir: "{app}\GUI\PLAOSV1_GUI"; Flags: recursesubdirs createallsubdirs ignoreversion

; (opsional) CLI onefile kalau ada
#ifexist "..\dist\plaosv1.exe"
Source: "..\dist\plaosv1.exe"; DestDir: "{app}"; DestName: "plaosv1.exe"; Flags: ignoreversion
#endif

; Ikon untuk shortcut
#ifexist "..\logo_os_ai_corp.ico"
Source: "..\logo_os_ai_corp.ico"; DestDir: "{app}"; Flags: ignoreversion
#endif

; Dokumen (opsional)
#ifexist "..\dist\docs\User Manual GUI PLAOSV1.docx"
Source: "..\dist\docs\User Manual GUI PLAOSV1.docx"; DestDir: "{app}\docs"; Flags: ignoreversion
#endif
#ifexist "..\dist\docs\Metode Estimasi Luas Daun.docx"
Source: "..\dist\docs\Metode Estimasi Luas Daun.docx"; DestDir: "{app}\docs"; Flags: ignoreversion
#endif

; Copy EULA ke {app}\docs (jika ada)
#ifexist "EULA.rtf"
Source: "EULA.rtf"; DestDir: "{app}\docs"; DestName: "EULA.rtf"; Flags: ignoreversion
#endif
#ifexist "EULA.txt"
Source: "EULA.txt"; DestDir: "{app}\docs"; DestName: "EULA.txt"; Flags: ignoreversion
#endif

[Icons]
; Start Menu
Name: "{group}\PLA-OSv1 (GUI)"; Filename: "{app}\GUI\PLAOSV1_GUI\PLAOSV1_GUI.exe"; WorkingDir: "{app}\GUI\PLAOSV1_GUI"; IconFilename: "{app}\logo_os_ai_corp.ico"
#ifexist "..\dist\plaosv1.exe"
Name: "{group}\PLA-OSv1 (CLI)"; Filename: "{app}\plaosv1.exe"; WorkingDir: "{app}"; IconFilename: "{app}\logo_os_ai_corp.ico"
#endif
; Desktop (GUI)
Name: "{commondesktop}\PLA-OSv1 (GUI)"; Filename: "{app}\GUI\PLAOSV1_GUI\PLAOSV1_GUI.exe"; WorkingDir: "{app}\GUI\PLAOSV1_GUI"; IconFilename: "{app}\logo_os_ai_corp.ico"; Tasks: desktopicon

[Registry]
; Tambah {app} ke PATH (SYSTEM) dengan aman
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{code:AppendPath|{app}}"; Tasks: addpath; Flags: preservestringtype

[Code]
function NormalizeDir(const S: string): string;
var
  R: string;
begin
  R := Trim(S);
  StringChangeEx(R, '"', '', True);  // hapus quotes
  R := LowerCase(R);
  // Hilangkan trailing backslash jika ada (kecuali root "c:\")
  if (Length(R) > 3) and (Copy(R, Length(R), 1) = '\') then
    Delete(R, Length(R), 1);
  Result := R;
end;

function PathContainsToken(const PathValue, DirToAdd: string): Boolean;
var
  LPath, LDir: string;
begin
  LPath := ';' + NormalizeDir(PathValue) + ';';
  LDir  := ';' + NormalizeDir(DirToAdd) + ';';
  Result := Pos(LDir, LPath) > 0;
end;

function AppendPath(Param: string): string;
var
  OldPath: string;
begin
  if not RegQueryStringValue(HKLM,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
    'Path', OldPath) then
    OldPath := '';

  if (Param <> '') and (not PathContainsToken(OldPath, Param)) then
  begin
    if (OldPath <> '') and (Copy(OldPath, Length(OldPath), 1) <> ';') then
      OldPath := OldPath + ';';
    Result := OldPath + Param;
  end
  else
    Result := OldPath;
end;

function RemoveFromPath(const OrigPath, RemoveDir: string): string;
var
  S, Token, Acc, Curr: string;
  P: Integer;
  Target: string;
begin
  S := OrigPath;
  Acc := '';
  Target := NormalizeDir(RemoveDir);

  while S <> '' do
  begin
    P := Pos(';', S);
    if P = 0 then
    begin
      Token := S;
      S := '';
    end
    else
    begin
      Token := Copy(S, 1, P - 1);
      Delete(S, 1, P);
    end;

    Curr := NormalizeDir(Token);
    if (Curr <> '') and (Curr <> Target) then
    begin
      if Acc <> '' then Acc := Acc + ';';
      Acc := Acc + Token;  // simpan bentuk aslinya (tanpa mengubah case)
    end;
  end;

  Result := Acc;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  S, NewPath, AppDir: string;
begin
  if CurUninstallStep = usUninstall then
  begin
    AppDir := ExpandConstant('{app}');
    if RegQueryStringValue(HKLM,
      'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
      'Path', S) then
    begin
      NewPath := RemoveFromPath(S, AppDir);
      if S <> NewPath then
        RegWriteStringValue(HKLM,
          'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
          'Path', NewPath);
    end;
  end;
end;



