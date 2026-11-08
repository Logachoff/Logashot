; Inno Setup скрипт установщика LogaShot v0.3.0
; Собирается из той же onedir-сборки, что и portable-версия.
; Установленная копия НЕ содержит маркера portable — настройки пойдут
; через QSettings в реестр/профиль пользователя.
;
; ВАЖНО: [Files] копирует dist\LogaShot\*, а dev/build.py кладёт
; туда маркер portable. Поэтому маркер и settings.ini исключаются из [Files],
; иначе установленная копия попадала в portable-режим и пыталась писать
; settings.ini в Program Files (без прав) — настройки сбрасывались.
;
; Бесшумная установка: setup.exe /VERYSILENT /NORESTART

#define AppName      "LogaShot"
#define AppVersion   "0.3.0"
#define AppPublisher "Мастерская Logachoff"
#define AppURL       "https://logachoff.ru"
#define AppExe       "LogaShot.exe"

[Setup]
AppId={{F4C7E2B1-8A9D-4F3E-B123-9D2A4E5F6A7B}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
; Python 3.14-рантайм не работает на Windows 7/8: без MinVersion установщик
; падает системной ошибкой про DLL, с ним — останавливается понятным
; сообщением «нужна Windows 10 1809 или новее».
MinVersion=10.0.17763
DisableProgramGroupPage=yes
PrivilegesRequiredOverridesAllowed=commandline
OutputDir=..\dist
OutputBaseFilename=LogaShot_0.3.0_setup
SetupIconFile=..\assets\LogaShot.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
VersionInfoVersion={#AppVersion}.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=Установщик {#AppName} {#AppVersion}
VersionInfoTextVersion={#AppVersion}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Excludes — ключ: dist\LogaShot\portable создан для portable-сборки,
; в установленную копию он попадать не должен (иначе QSettings пишет
; settings.ini в {app} и на Program Files без прав молча теряет настройки).
Source: "..\dist\LogaShot\*"; DestDir: "{app}"; Excludes: "portable,settings.ini"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[InstallDelete]
; Установленная версия не является portable — убираем маркер и settings.ini,
; чтобы QSettings писал в профиль, а не рядом с exe.
Type: files; Name: "{app}\portable"
Type: files; Name: "{app}\settings.ini"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
