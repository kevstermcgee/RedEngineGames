; Inno Setup script for one game. `release_tool.py` writes defines.iss beside this file:
; AppId, AppName, AppSlug, AppVersion, VersionInfo, Publisher, SiteUrl, StageDir, OutDir, OutName.
;
; Per-user install (no administrator prompt) into %LOCALAPPDATA%\Programs\<game>. The AppId is the same for every version of a game, so running a newer installer
; is an update in place: the old files are replaced, the shortcuts and the uninstall entry stay, and the player's saves (Saved Games\<game>) are never touched.
#include "defines.iss"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#Publisher}
AppPublisherURL={#SiteUrl}
AppSupportURL={#SiteUrl}
AppUpdatesURL={#SiteUrl}
VersionInfoVersion={#VersionInfo}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} setup
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutDir}
OutputBaseFilename={#OutName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayName={#AppName}
#if FileExists(StageDir + "\game.ico")
SetupIconFile={#StageDir}\game.ico
UninstallDisplayIcon={app}\game.ico
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; An update replaces the game's content wholesale, so a file the new version no longer has does not linger.
Type: filesandordirs; Name: "{app}\content"

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\Play-{#AppSlug}.exe"; WorkingDir: "{app}"; IconFilename: "{app}\game.ico"; Check: HasIcon
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\Play-{#AppSlug}.exe"; WorkingDir: "{app}"; Check: not HasIcon
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Play-{#AppSlug}.exe"; WorkingDir: "{app}"; IconFilename: "{app}\game.ico"; Tasks: desktopicon; Check: HasIcon
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Play-{#AppSlug}.exe"; WorkingDir: "{app}"; Tasks: desktopicon; Check: not HasIcon

[Run]
; Also runs after a silent update (the game's own updater starts this installer with /SILENT), which is how the game comes back up.
Filename: "{app}\Play-{#AppSlug}.exe"; Parameters: "--no-update"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall

[Code]
function HasIcon: Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\game.ico'));
end;

function SaveFolder: String;
begin
  Result := ExpandConstant('{%USERPROFILE}\Saved Games\{#AppName}');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and DirExists(SaveFolder) and (not UninstallSilent) then
    if MsgBox('Also delete your saved games and settings?' + #13#10 + #13#10 + SaveFolder + #13#10 + #13#10 +
              'Choose No to keep them for a later reinstall.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(SaveFolder, True, True, True);
end;
