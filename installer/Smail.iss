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
; Installateur en français ou en anglais selon la langue de Windows, sans question.
ShowLanguageDialog=auto

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Tout le dossier produit par PyInstaller est nécessaire (WebEngine notamment).
Source: "..\dist\Smail\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Smail"; Filename: "{app}\Smail.exe"
Name: "{autodesktop}\Smail"; Filename: "{app}\Smail.exe"; Tasks: desktopicon

[Registry]
; Liens « mailto: » : Smail est proposé comme messagerie dans Paramètres › Applications par défaut
; (le choix reste à l’utilisateur, Windows l’exige). Clés de l’utilisateur, retirées à la désinstallation.
Root: HKCU; Subkey: "Software\Classes\Smail.mailto"; ValueType: string; ValueName: ""; ValueData: "Lien de messagerie (Smail)"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Smail.mailto"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\Smail.mailto\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\Smail.exe,0"
Root: HKCU; Subkey: "Software\Classes\Smail.mailto\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Smail.exe"" --mailto ""%1"""
Root: HKCU; Subkey: "Software\Clients\Mail\Smail"; ValueType: string; ValueName: ""; ValueData: "Smail"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Clients\Mail\Smail\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "Smail"
Root: HKCU; Subkey: "Software\Clients\Mail\Smail\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Client mail de bureau Windows (IMAP/SMTP)"
Root: HKCU; Subkey: "Software\Clients\Mail\Smail\Capabilities\URLAssociations"; ValueType: string; ValueName: "mailto"; ValueData: "Smail.mailto"
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "Smail"; ValueData: "Software\Clients\Mail\Smail\Capabilities"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Smail.exe"; Description: "{cm:LaunchProgram,Smail}"; Flags: nowait postinstall skipifsilent
; Mise à jour automatique (installation silencieuse lancée par Smail avec /RELAUNCH=1) : Smail redémarre.
Filename: "{app}\Smail.exe"; Flags: nowait; Check: RelaunchRequested

; La désinstallation retire le programme seulement. Les comptes, le cache (%LOCALAPPDATA%\SmailDesktop\Smail)
; et les secrets du Gestionnaire d’identifiants Windows sont conservés : supprimez d’abord vos comptes dans
; Smail pour tout effacer.

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  // Désinstallation : Smail ne doit plus être lancé à l’ouverture de session.
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Smail');
end;

function RelaunchRequested: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:RELAUNCH|0}') = '1');
end;
