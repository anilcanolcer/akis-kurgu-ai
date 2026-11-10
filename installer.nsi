Unicode true
!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "StrFunc.nsh"
${StrStr}
!define PRODUCT_NAME "Akis Kurgu AI"
!define PRODUCT_VERSION "0.4.1"
Name "${PRODUCT_NAME}"
OutFile "dist\AkisKurguAI-Setup.exe"
InstallDir "$PROGRAMFILES64\AkisKurguAI"
RequestExecutionLevel admin
SetCompressor /SOLID lzma
Icon "app.ico"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Turkish"
Var LegacyLog
Function .onInit
  ${GetParameters} $R0
  ${StrStr} $R1 $R0 "/VERYSILENT"
  StrCmp $R1 "" +2
    SetSilent silent
  ClearErrors
  ${GetOptions} $R0 "/DIR=" $R1
  IfErrors +2
    StrCpy $INSTDIR $R1
  ClearErrors
  ${GetOptions} $R0 "/LOG=" $LegacyLog
FunctionEnd
Section "Install"
  SetOutPath "$INSTDIR"
  SetOverwrite on
  ClearErrors
  File /r "dist\AkisKurguAI\*"
  IfErrors 0 +3
    MessageBox MB_OK|MB_ICONSTOP "Dosyalar yüklenemedi. Uygulamayı kapatıp yeniden deneyin." /SD IDOK
    Abort
  WriteUninstaller "$INSTDIR\Uninstall-Akis.exe"
  SetShellVarContext all
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortcut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\AkisKurguAI.exe"
  SetRegView 64
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AkisKurguAI" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AkisKurguAI" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AkisKurguAI" "UninstallString" '"$INSTDIR\Uninstall-Akis.exe"'
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AkisKurguAI" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AkisKurguAI" "NoRepair" 1
  ReadRegStr $R0 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\{3F3FE53D-553B-4D25-9169-4493F9AFD241}_is1" "InstallLocation"
  StrCmp $R0 "$INSTDIR\" 0 +2
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\{3F3FE53D-553B-4D25-9169-4493F9AFD241}_is1"
  StrCmp $LegacyLog "" done
  ClearErrors
  FileOpen $R0 $LegacyLog w
  IfErrors done
  FileWrite $R0 "NSIS installation completed.$\r$\n"
  FileClose $R0
  done:
SectionEnd
Section "Uninstall"
  !include "dist\uninstall-files.nsh"
  Delete "$INSTDIR\Uninstall-Akis.exe"
  RMDir "$INSTDIR"
  SetShellVarContext all
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
  RMDir "$SMPROGRAMS\${PRODUCT_NAME}"
  SetRegView 64
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AkisKurguAI"
SectionEnd
