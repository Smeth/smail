; Installateur Windows de Smail (Inno Setup 6).
; Construire depuis la racine, après PyInstaller :
;   ISCC.exe /DAppVersion=1.0.0 installer\Smail.iss
; La version est normalement fournie par la CI depuis mailclient/__init__.py.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; Identifiant stable : ne jamais le changer, il relie les mises à jour et la désinstallation.
AppId={{BEC3FF36-BEB3-4906-94C3-4C842D3CAA1B}
AppName=Smail
AppVersion={#AppVersion}
AppVerName=Smail {#AppVersion}
AppPublisher=Smail
VersionInfoVersion={#AppVersion}
; Installation par utilisateur, sans droits administrateur.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\Smail
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=Smail-{#AppVersion}-installation
SetupIconFile=..\mailclient\ui\assets\smail.ico
UninstallDisplayIcon={app}\Smail.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Tout le dossier produit par PyInstaller est nécessaire (WebEngine notamment).
Source: "..\dist\Smail\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Smail"; Filename: "{app}\Smail.exe"
Name: "{autodesktop}\Smail"; Filename: "{app}\Smail.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Smail.exe"; Description: "{cm:LaunchProgram,Smail}"; Flags: nowait postinstall skipifsilent

; La désinstallation retire le programme seulement. Les comptes, le cache (%LOCALAPPDATA%\SmailDesktop\Smail)
; et les secrets du Gestionnaire d’identifiants Windows sont conservés : supprimez d’abord vos comptes dans
; Smail pour tout effacer.
