#define MyAppName "FORGE"
#define MyAppVersion "0.8.0"
#define MyAppPublisher "OJ Labs"
#define MyAppExeName "FORGE.exe"

[Setup]
AppId={{A371732C-529E-45D5-9E20-9B3AC7180F08}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\OJ Labs\FORGE
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
OutputDir={#SourcePath}\Output
OutputBaseFilename=FORGE_Setup_Windows_x64_v0.8.0
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\FORGE.exe
ChangesAssociations=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "reaperscript"; Description: "Install the optional REAPER 'Import Latest Stack' action"; Flags: checkedonce
Name: "desktopicon"; Description: "Create a desktop shortcut for FORGE Standalone"; Flags: unchecked

[Files]
Source: "{#SourcePath}\..\release\FORGE.vst3\*"; DestDir: "{commoncf64}\VST3\FORGE.vst3"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourcePath}\..\release\Standalone\FORGE.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourcePath}\..\release\Standalone\Engine\*"; DestDir: "{app}\Engine"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourcePath}\..\ReaperScripts\FORGE - Import Latest Stack.lua"; DestDir: "{userappdata}\REAPER\Scripts\FORGE"; Flags: ignoreversion; Tasks: reaperscript
Source: "{#SourcePath}\..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourcePath}\..\RELEASE_NOTES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\FORGE"; Filename: "{app}\FORGE.exe"
Name: "{autodesktop}\FORGE"; Filename: "{app}\FORGE.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FORGE.exe"; Description: "Launch FORGE Standalone"; Flags: nowait postinstall skipifsilent unchecked

[UninstallDelete]
Type: filesandordirs; Name: "{commoncf64}\VST3\FORGE.vst3"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := IsWin64;
  if not Result then
    MsgBox('FORGE v0.8 requires 64-bit Windows and 64-bit REAPER.', mbError, MB_OK);
end;
