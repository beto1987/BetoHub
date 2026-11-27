; Instalador do StarHub (Inno Setup 6). Rode pelo compilar.ps1, que passa a versão e,
; se houver certificado, liga a assinatura digital (/DASSINAR e /Sstarhub=...).
;
; - Instala por usuário (sem pedir administrador) em %LOCALAPPDATA%\Programs\StarHub;
;   na tela inicial dá para escolher instalar para todos os usuários.
; - Página "Idioma do aplicativo": grava {app}\idioma_instalacao.txt, que o StarHub aplica
;   uma vez ao abrir (beto_hub.core.i18n.escolher_idioma).
; - Instalação silenciosa: /VERYSILENT /APPLANG=en-US (pt-BR, en-US, es, fr ou it).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "StarHub"
#define AppExe "StarHub.exe"

[Setup]
AppId={{6F2B1C8E-3D4A-4E5F-9A7B-2C1D0E9F8A6B}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=StarHub
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} Setup
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\build\instalador
OutputBaseFilename={#AppName}-{#AppVersion}-Setup
SetupIconFile=..\beto_hub\ui\theme\icone.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=yes
CloseApplications=yes
RestartApplications=no
#ifdef ASSINAR
SignTool=starhub
SignedUninstaller=yes
#endif

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[CustomMessages]
brazilianportuguese.IdiomaTitulo=Idioma do aplicativo
brazilianportuguese.IdiomaSubtitulo=Em qual idioma o StarHub deve abrir?
brazilianportuguese.IdiomaTexto=Você pode trocar depois em Configurações › Geral › Idioma.
brazilianportuguese.AbrirApp=Abrir o StarHub
english.IdiomaTitulo=Application language
english.IdiomaSubtitulo=Which language should StarHub open in?
english.IdiomaTexto=You can change it later in Settings › General › Language.
english.AbrirApp=Open StarHub
spanish.IdiomaTitulo=Idioma de la aplicación
spanish.IdiomaSubtitulo=¿En qué idioma debe abrirse StarHub?
spanish.IdiomaTexto=Puedes cambiarlo después en Configuración › General › Idioma.
spanish.AbrirApp=Abrir StarHub
french.IdiomaTitulo=Langue de l'application
french.IdiomaSubtitulo=Dans quelle langue StarHub doit-il s'ouvrir ?
french.IdiomaTexto=Vous pourrez la changer plus tard dans Paramètres › Général › Langue.
french.AbrirApp=Ouvrir StarHub
italian.IdiomaTitulo=Lingua dell'applicazione
italian.IdiomaSubtitulo=In quale lingua deve aprirsi StarHub?
italian.IdiomaTexto=Potrai cambiarla in seguito in Impostazioni › Generale › Lingua.
italian.AbrirApp=Apri StarHub

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\build\dist\StarHub\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[InstallDelete]
; Remove arquivos de uma versão anterior que não existem mais (os dados do jogador ficam em %APPDATA%/%LOCALAPPDATA%)
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:AbrirApp}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\idioma_instalacao.txt"

[Code]
var
  PaginaIdioma: TInputOptionWizardPage;

function CodigoIdioma(Indice: Integer): String;
begin
  case Indice of
    1: Result := 'en-US';
    2: Result := 'es';
    3: Result := 'fr';
    4: Result := 'it';
  else
    Result := 'pt-BR';
  end;
end;

function IndicePadrao(): Integer;
var
  Parametro: String;
  I: Integer;
begin
  { /APPLANG=xx na linha de comando vence; senão, o idioma escolhido para o instalador }
  Parametro := ExpandConstant('{param:APPLANG|}');
  for I := 0 to 4 do
    if CompareText(Parametro, CodigoIdioma(I)) = 0 then
    begin
      Result := I;
      Exit;
    end;
  if ActiveLanguage = 'english' then Result := 1
  else if ActiveLanguage = 'spanish' then Result := 2
  else if ActiveLanguage = 'french' then Result := 3
  else if ActiveLanguage = 'italian' then Result := 4
  else Result := 0;
end;

procedure InitializeWizard;
begin
  PaginaIdioma := CreateInputOptionPage(wpSelectTasks, CustomMessage('IdiomaTitulo'),
    CustomMessage('IdiomaSubtitulo'), CustomMessage('IdiomaTexto'), True, False);
  PaginaIdioma.Add('Português (Brasil)');
  PaginaIdioma.Add('English (US)');
  PaginaIdioma.Add('Español');
  PaginaIdioma.Add('Français');
  PaginaIdioma.Add('Italiano');
  PaginaIdioma.SelectedValueIndex := IndicePadrao();
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SaveStringToFile(ExpandConstant('{app}\idioma_instalacao.txt'),
      CodigoIdioma(PaginaIdioma.SelectedValueIndex), False);
end;
