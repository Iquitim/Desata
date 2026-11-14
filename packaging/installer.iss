; Inno Setup: instalador do programa (spec 008, RF-805). A marca vem do build.py (spec 036):
; /DAppVersion, /DSourceDir, /DAppId, /DAppName, /DShortName e /DPublisher.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef ShortName
  #error Rode pelo packaging/build.py, que passa a marca.
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\" + ShortName
#endif

[Setup]
AppId={{{#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#Publisher}
; Instalação por usuário: não pede administrador.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#ShortName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#ShortName}.exe
SetupIconFile=prodata.ico
; Telas do instalador com a marca (geradas por make_icon.py)
WizardImageFile=wizard-100.bmp,wizard-150.bmp,wizard-200.bmp
WizardSmallImageFile=wizard-small-100.bmp,wizard-small-150.bmp,wizard-small-200.bmp
OutputDir=..\dist
OutputBaseFilename={#ShortName}-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#ShortName}.exe"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#ShortName}.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ShortName}.exe"; Description: "Abrir o {#AppName} agora"; Flags: nowait postinstall skipifsilent

; Os dados do usuário ficam em %LOCALAPPDATA%\<pasta de dados da marca> (fora de {app}) e não são
; removidos na desinstalação: fluxos, datasets e conexões sobrevivem a reinstalações.
