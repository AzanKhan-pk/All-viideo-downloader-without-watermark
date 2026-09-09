#define MyAppName "All Video Downloader Without Watermark"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Azan Khan"
#define MyAppExeName "All-Video-Downloader.exe"

[Setup]
AppId={{8F5E6D74-5F93-4C44-8A31-5E1E0E8A5C3A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\All Video Downloader Without Watermark
DefaultGroupName={#MyAppName}
OutputDir=..\release
OutputBaseFilename=All-Video-Downloader-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
Uninstallable=yes
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\dist\All-Video-Downloader.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\All-Video-Downloader\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "app.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\All Video Downloader Without Watermark"
