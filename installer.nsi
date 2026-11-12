Unicode true
!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"

; Build-time overrides (makensis /D...), used by scripts/installer-scenarios.ps1 so the real dist is
; never needed there: SOURCE_DIR, OUTPUT_FILE, UNINSTALL_LIST, PRODUCT_NAME, UNINSTALL_KEY_NAME, and
; TEST_USER_LEVEL (no UAC prompt; registry and shortcut go to the current user).
!ifndef PRODUCT_NAME
  !define PRODUCT_NAME "Akis Kurgu AI"
!endif
!ifndef PRODUCT_VERSION
  !define PRODUCT_VERSION "0.5.1"
!endif
!ifndef SOURCE_DIR
  !define SOURCE_DIR "dist\AkisKurguAI"
!endif
!ifndef OUTPUT_FILE
  !define OUTPUT_FILE "dist\AkisKurguAI-Setup.exe"
!endif
!ifndef UNINSTALL_LIST
  !define UNINSTALL_LIST "dist\uninstall-files.nsh"
!endif
!ifndef UNINSTALL_KEY_NAME
  !define UNINSTALL_KEY_NAME "AkisKurguAI"
!endif
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${UNINSTALL_KEY_NAME}"
!define LEGACY_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\{3F3FE53D-553B-4D25-9169-4493F9AFD241}_is1"
!ifdef TEST_USER_LEVEL
  RequestExecutionLevel user
  !define REG_ROOT HKCU
  !define SHELL_CONTEXT current
  !define SHORTCUT_DIR "$INSTDIR\..\StartMenu\${PRODUCT_NAME}"  ; beside the test folder, not the real Start Menu
!else
  RequestExecutionLevel admin
  !define REG_ROOT HKLM
  !define SHELL_CONTEXT all
  !define SHORTCUT_DIR "$SMPROGRAMS\${PRODUCT_NAME}"
!endif

; Exit codes besides 0 (1 = cancelled by the user and 2 = aborted are NSIS defaults); keep in sync with
; INSTALLER_EXIT_CODES in akis/update_service.py.
!define ERR_IN_USE 10    ; the app or its files are in use: nothing was changed
!define ERR_EXTRACT 11   ; new files could not be written: the previous version was restored
!define ERR_ROLLBACK 12  ; new files could not be written and restoring the previous version failed
!define ERR_FINISH 13    ; uninstaller, registry or shortcut failed: the previous version was restored
!define ERR_RECOVER 14   ; an earlier interrupted update could not be undone

; The application folder holds only AkisKurguAI.exe and _internal (PyInstaller onedir; checked by
; scripts/generate-nsis-uninstall.py). Nothing user-owned lives there: settings are in the registry
; (QSettings), logs and recovery files in %LOCALAPPDATA%, Whisper models in the Hugging Face cache and
; scratch files in %TEMP%. So an update moves both aside as .old, extracts the new copy, and deletes the
; .old copies only once everything else succeeded; any failure puts the .old copies back.
Name "Akış Kurgu AI"
Caption "Akış Kurgu AI ${PRODUCT_VERSION} Kurulumu"
BrandingText "Akış Kurgu AI ${PRODUCT_VERSION}"
OutFile "${OUTPUT_FILE}"
InstallDir "$PROGRAMFILES64\AkisKurguAI"
SetCompressor /SOLID lzma
Icon "app.ico"

Var UpdateMode     ; 1: /UPDATE (or legacy /VERYSILENT): only the progress page, no prompts, auto close
Var Relaunch       ; 1: /UPDATE from the app: wait for it to exit, start it again afterwards, report failures
Var WaitSeconds    ; how long to wait for the app's files to be free (/WAIT=, default 90 with /UPDATE)
Var Waited
Var FailMessage
Var LegacyLog      ; /LOG= path; the app and update helpers of every version read it
Var LogText
Var LogHandle
Var MovedExe       ; 1 once AkisKurguAI.exe was renamed to AkisKurguAI.exe.old
Var MovedLib       ; 1 once _internal was renamed to _internal.old
Var Swapping       ; 1 while the old copy is aside and the new one is not committed yet
Var RollbackFailed
Var RecoverFailed
Var Failed

!define MUI_CUSTOMFUNCTION_GUIINIT OnGuiInit
!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipPageInUpdateMode
!insertmacro MUI_PAGE_WELCOME
!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipPageInUpdateMode
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipPageInUpdateMode
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Turkish"

; Version resource of the installer itself (Explorer > Properties > Details; security products use it).
VIProductVersion "${PRODUCT_VERSION}.0"
VIAddVersionKey /LANG=${LANG_TURKISH} "ProductName" "Akış Kurgu AI"
VIAddVersionKey /LANG=${LANG_TURKISH} "CompanyName" "Anılcan Ölçer"
VIAddVersionKey /LANG=${LANG_TURKISH} "FileDescription" "Akış Kurgu AI Kurulumu"
VIAddVersionKey /LANG=${LANG_TURKISH} "FileVersion" "${PRODUCT_VERSION}"
VIAddVersionKey /LANG=${LANG_TURKISH} "ProductVersion" "${PRODUCT_VERSION}"
VIAddVersionKey /LANG=${LANG_TURKISH} "LegalCopyright" "© Anılcan Ölçer"

; Log the failure (after any rollback), set the exit code and stop.
;  - /UPDATE from the app: one message naming the reason and the log, then the previous version is started
;    again (unless it is still running) and the installer quits. /S suppresses the message (/SD).
;  - Legacy /VERYSILENT update or /S: quit at once with the exit code, no message box.
;  - Interactive install: the message, then the usual "aborted" page.
!macro FAIL code reason message
  StrCpy $LogText "NSIS installation failed (code ${code}): ${reason}"
  Call WriteLogLine
  SetErrorLevel ${code}
  ${If} $Relaunch == 1
    StrCpy $FailMessage "${message}"
    Call ReportAndRelaunch
    Quit
  ${EndIf}
  ${If} $UpdateMode == 1
  ${OrIf} ${Silent}
    Quit
  ${EndIf}
  MessageBox MB_OK|MB_ICONSTOP "${message}" /SD IDOK
  Abort
!macroend

; Sets $Failed to 1 when `file` exists but cannot be opened for writing: a running program's image file
; cannot be (renaming its folder would still succeed, so this has to be checked explicitly).
!macro CHECK_NOT_RUNNING file
  ${If} ${FileExists} "${file}"
    ClearErrors
    FileOpen $0 "${file}" a
    ${If} ${Errors}
      StrCpy $Failed 1
    ${Else}
      FileClose $0
    ${EndIf}
  ${EndIf}
!macroend

Function .onInit
  StrCpy $UpdateMode 0
  StrCpy $Relaunch 0
  StrCpy $WaitSeconds 0
  StrCpy $Swapping 0
  ${GetParameters} $R0
  ClearErrors
  ${GetOptions} $R0 "/UPDATE" $R1
  ${IfNot} ${Errors}
    StrCpy $UpdateMode 1
    StrCpy $Relaunch 1
    StrCpy $WaitSeconds 90
  ${EndIf}
  ClearErrors
  ${GetOptions} $R0 "/WAIT=" $R1
  ${IfNot} ${Errors}
    IntOp $WaitSeconds $R1 + 0
  ${EndIf}
  ; Update helpers up to 0.4.2 pass /VERYSILENT /NORESTART /SP- /DIR= /LOG=. They get the visible update
  ; mode too: a progress window instead of minutes of nothing, still without any prompt.
  ClearErrors
  ${GetOptions} $R0 "/VERYSILENT" $R1
  ${IfNot} ${Errors}
    StrCpy $UpdateMode 1
  ${EndIf}
  ClearErrors
  ${GetOptions} $R0 "/DIR=" $R1
  ${IfNot} ${Errors}
    StrCpy $INSTDIR $R1
  ${EndIf}
  ClearErrors
  ${GetOptions} $R0 "/LOG=" $LegacyLog
  ${If} ${Errors}
    StrCpy $LegacyLog ""
  ${EndIf}
  ClearErrors
FunctionEnd

Function OnGuiInit
  ${If} $UpdateMode == 1
    BringToFront
  ${EndIf}
FunctionEnd

Function SkipPageInUpdateMode
  ${If} $UpdateMode == 1
    Abort
  ${EndIf}
FunctionEnd

; Appends $LogText to the /LOG= file, if any. Never fails the installation.
Function WriteLogLine
  ${If} $LegacyLog != ""
    ClearErrors
    FileOpen $LogHandle $LegacyLog a
    ${IfNot} ${Errors}
      FileSeek $LogHandle 0 END
      FileWrite $LogHandle "$LogText$\r$\n"
      FileClose $LogHandle
    ${EndIf}
  ${EndIf}
  ClearErrors
FunctionEnd

; Finish or undo an update that was interrupted (power loss, killed installer). The swap renames the new
; exe into place as its very last file step, so: exe present = the swap completed and any .old copies are
; leftovers; exe missing with .old copies = interrupted, so the .old copies are put back.
Function RecoverInterrupted
  StrCpy $RecoverFailed 0
  ${If} ${FileExists} "$INSTDIR\AkisKurguAI.exe"
    Delete "$INSTDIR\AkisKurguAI.exe.old"
    RMDir /r "$INSTDIR\_internal.old"
  ${Else}
    Delete "$INSTDIR\AkisKurguAI.exe.new"
    ${If} ${FileExists} "$INSTDIR\_internal.old\*.*"
      RMDir /r "$INSTDIR\_internal"
      ClearErrors
      Rename "$INSTDIR\_internal.old" "$INSTDIR\_internal"
      ${If} ${Errors}
        StrCpy $RecoverFailed 1
      ${EndIf}
    ${EndIf}
    ; The exe only after _internal is back: an exe next to a stale _internal.old would make the next run
    ; take the swap as completed and delete _internal.old, the only good copy.
    ${If} $RecoverFailed == 0
    ${AndIf} ${FileExists} "$INSTDIR\AkisKurguAI.exe.old"
      ClearErrors
      Rename "$INSTDIR\AkisKurguAI.exe.old" "$INSTDIR\AkisKurguAI.exe"
      ${If} ${Errors}
        StrCpy $RecoverFailed 1
      ${EndIf}
    ${EndIf}
  ${EndIf}
  ClearErrors
FunctionEnd

; Undo a swap that has not been committed: delete every new file (after the move-aside nothing else is
; at these paths) and rename the .old copies back, _internal first and the exe last.
Function Rollback
  StrCpy $RollbackFailed 0
  ${If} $Swapping == 1
    Delete "$INSTDIR\AkisKurguAI.exe.new"
    Delete "$INSTDIR\AkisKurguAI.exe"
    RMDir /r "$INSTDIR\_internal"
    ${If} $MovedLib == 1
      ClearErrors
      Rename "$INSTDIR\_internal.old" "$INSTDIR\_internal"
      ${If} ${Errors}
        StrCpy $RollbackFailed 1
      ${EndIf}
    ${EndIf}
    ; Same rule as RecoverInterrupted: the exe last, and only after _internal is back.
    ${If} $MovedExe == 1
    ${AndIf} $RollbackFailed == 0
      ClearErrors
      Rename "$INSTDIR\AkisKurguAI.exe.old" "$INSTDIR\AkisKurguAI.exe"
      ${If} ${Errors}
        StrCpy $RollbackFailed 1
      ${EndIf}
    ${EndIf}
    StrCpy $Swapping 0
  ${EndIf}
  ClearErrors
FunctionEnd

; Starts the installed app as the signed-in user, not elevated: explorer.exe hands the start to the
; running shell, so an app started by this (possibly elevated) installer does not inherit admin rights.
Function RelaunchApp
  ${If} ${FileExists} "$INSTDIR\AkisKurguAI.exe"
    Exec '"$WINDIR\explorer.exe" "$INSTDIR\AkisKurguAI.exe"'
  ${EndIf}
FunctionEnd

; /UPDATE failure: tell the user why and where the log is, then start the previous version again unless
; it still runs (exit code 10 after the wait: the app never closed).
Function ReportAndRelaunch
  ${If} $LegacyLog != ""
    StrCpy $FailMessage "$FailMessage$\r$\n$\r$\nAyrıntılar: $LegacyLog"
  ${EndIf}
  StrCpy $Failed 0
  !insertmacro CHECK_NOT_RUNNING "$INSTDIR\AkisKurguAI.exe"
  ${If} $Failed == 0
  ${AndIf} ${FileExists} "$INSTDIR\AkisKurguAI.exe"
    MessageBox MB_OK|MB_ICONEXCLAMATION "$FailMessage$\r$\n$\r$\nKullandığınız sürüm yeniden açılıyor." /SD IDOK
    Call RelaunchApp
  ${Else}
    MessageBox MB_OK|MB_ICONEXCLAMATION "$FailMessage" /SD IDOK
  ${EndIf}
FunctionEnd

; One attempt to move the current copy aside. $Failed = 0: nothing runs from $INSTDIR and the exe and
; _internal (where present) are now .old; $Failed = 1: something is in use and nothing was changed.
Function TryMoveAside
  StrCpy $Failed 0
  !insertmacro CHECK_NOT_RUNNING "$INSTDIR\AkisKurguAI.exe"
  !insertmacro CHECK_NOT_RUNNING "$INSTDIR\_internal\ffmpeg.exe"
  ${If} $Failed == 1
    Return
  ${EndIf}
  ${If} ${FileExists} "$INSTDIR\AkisKurguAI.exe"
    ClearErrors
    Rename "$INSTDIR\AkisKurguAI.exe" "$INSTDIR\AkisKurguAI.exe.old"
    ${If} ${Errors}
      StrCpy $Failed 1
      Return
    ${EndIf}
    StrCpy $MovedExe 1
  ${EndIf}
  ; A rename of _internal fails cleanly while any file in it is open.
  ${If} ${FileExists} "$INSTDIR\_internal\*.*"
    ClearErrors
    Rename "$INSTDIR\_internal" "$INSTDIR\_internal.old"
    ${If} ${Errors}
      ${If} $MovedExe == 1
        ClearErrors
        Rename "$INSTDIR\AkisKurguAI.exe.old" "$INSTDIR\AkisKurguAI.exe"
        ${IfNot} ${Errors}
          StrCpy $MovedExe 0
        ${EndIf}
      ${EndIf}
      StrCpy $Failed 1
      Return
    ${EndIf}
    StrCpy $MovedLib 1
  ${EndIf}
FunctionEnd

Section "Install"
  StrCpy $MovedExe 0
  StrCpy $MovedLib 0
  StrCpy $Swapping 0
  ${If} $UpdateMode == 1
    SetDetailsView hide
    SetAutoClose true
  ${EndIf}
  SetOverwrite try  ; a file that cannot be written sets the error flag instead of prompting
  CreateDirectory "$INSTDIR"
  SetOutPath "$INSTDIR"

  ; 1. Recover from an earlier interrupted update.
  Call RecoverInterrupted
  ${If} $RecoverFailed == 1
    !insertmacro FAIL ${ERR_RECOVER} "an interrupted earlier update could not be undone" "Yarım kalmış önceki bir güncelleme onarılamadı. Bilgisayarı yeniden başlatıp kurulumu yeniden çalıştırın."
  ${EndIf}

  ; 2+3. Nothing may run from here; then move the current copy aside. With /UPDATE the app has just been
  ;      asked to close, so retry once a second for up to $WaitSeconds; otherwise refuse at once. A refusal
  ;      changes nothing.
  StrCpy $Waited 0
  ${Do}
    Call TryMoveAside
    ${If} $Failed == 0
    ${OrIf} $Waited >= $WaitSeconds
      ${ExitDo}
    ${EndIf}
    ${If} $Waited == 0
      DetailPrint "Akış Kurgu AI'ın kapanması bekleniyor…"
    ${EndIf}
    Sleep 1000
    IntOp $Waited $Waited + 1
  ${Loop}
  ${If} $Failed == 1
    !insertmacro FAIL ${ERR_IN_USE} "the application or its files are in use (waited $Waited s)" "Akış Kurgu AI açık ya da dosyaları kullanımda olduğu için güncelleme kurulamadı. Hiçbir dosya değiştirilmedi. Uygulamayı kapatıp güncellemeyi yeniden deneyin."
  ${EndIf}
  StrCpy $Swapping 1

  ; 4. Extract the new copy: _internal first, the exe last and under a temporary name, renamed into
  ;    place only when everything else is written. The error flag is tested exactly once.
  StrCpy $Failed 0
  ClearErrors
  SetOutPath "$INSTDIR\_internal"
  File /r "${SOURCE_DIR}\_internal\*"
  SetOutPath "$INSTDIR"
  File "/oname=AkisKurguAI.exe.new" "${SOURCE_DIR}\AkisKurguAI.exe"
  ${If} ${Errors}
    StrCpy $Failed 1
  ${Else}
    Rename "$INSTDIR\AkisKurguAI.exe.new" "$INSTDIR\AkisKurguAI.exe"
    ${If} ${Errors}
      StrCpy $Failed 1
    ${EndIf}
  ${EndIf}
  ${If} $Failed == 1
    Call Rollback
    ${If} $RollbackFailed == 1
      !insertmacro FAIL ${ERR_ROLLBACK} "files could not be written; restoring the previous version failed" "Yeni dosyalar yazılamadı ve önceki sürüm geri yüklenemedi. Kurulumu yeniden çalıştırın."
    ${EndIf}
    !insertmacro FAIL ${ERR_EXTRACT} "files could not be written; the previous version was restored" "Yeni dosyalar yazılamadı (disk dolu olabilir). Önceki sürüm geri yüklendi."
  ${EndIf}

  ; 5. Uninstaller, registry and shortcut.
  StrCpy $Failed 0
  ClearErrors
  WriteUninstaller "$INSTDIR\Uninstall-Akis.exe"
  SetRegView 64
  WriteRegStr ${REG_ROOT} "${UNINSTALL_KEY}" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr ${REG_ROOT} "${UNINSTALL_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr ${REG_ROOT} "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\Uninstall-Akis.exe"'
  WriteRegDWORD ${REG_ROOT} "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD ${REG_ROOT} "${UNINSTALL_KEY}" "NoRepair" 1
  ${If} ${Errors}
    StrCpy $Failed 1
  ${EndIf}
  SetShellVarContext ${SHELL_CONTEXT}
  CreateDirectory "${SHORTCUT_DIR}"
  ClearErrors
  CreateShortcut "${SHORTCUT_DIR}\${PRODUCT_NAME}.lnk" "$INSTDIR\AkisKurguAI.exe"
  ${If} ${Errors}
    StrCpy $Failed 1
  ${EndIf}
  ${If} $Failed == 1
    Call Rollback
    ${If} $RollbackFailed == 1
      !insertmacro FAIL ${ERR_ROLLBACK} "uninstaller, registry or shortcut failed; restoring the previous version failed" "Kurulum son adımda başarısız oldu ve önceki sürüm geri yüklenemedi. Kurulumu yeniden çalıştırın."
    ${EndIf}
    !insertmacro FAIL ${ERR_FINISH} "uninstaller, registry or shortcut failed; the previous version was restored" "Kurulum son adımda başarısız oldu. Önceki sürüm geri yüklendi."
  ${EndIf}

  ; 6. Committed. Remove the uninstall entry of the old Inno Setup build for this folder, log, and only
  ;    now delete the previous copy (a leftover is removed by the next run or the uninstaller).
  StrCpy $Swapping 0
  !ifndef TEST_USER_LEVEL
    ReadRegStr $1 HKLM "${LEGACY_KEY}" "InstallLocation"
    ${If} $1 == "$INSTDIR\"
      DeleteRegKey HKLM "${LEGACY_KEY}"
    ${EndIf}
  !endif
  StrCpy $LogText "NSIS installation completed."
  Call WriteLogLine
  RMDir /r "$INSTDIR\_internal.old"
  Delete "$INSTDIR\AkisKurguAI.exe.old"
  ClearErrors
  ${If} $Relaunch == 1
    Call RelaunchApp
  ${EndIf}
SectionEnd

; Reached when NSIS itself aborts the section (e.g. a write error while decompressing, disk full).
Function .onInstFailed
  ${If} $Swapping == 1
    Call Rollback
    ${If} $RollbackFailed == 1
      StrCpy $LogText "NSIS installation failed (code ${ERR_ROLLBACK}): aborted; restoring the previous version failed"
      SetErrorLevel ${ERR_ROLLBACK}
    ${Else}
      StrCpy $LogText "NSIS installation failed (code ${ERR_EXTRACT}): aborted; the previous version was restored"
      SetErrorLevel ${ERR_EXTRACT}
    ${EndIf}
    Call WriteLogLine
  ${EndIf}
  ; NSIS has already shown its own error; just start the restored previous version again.
  ${If} $Relaunch == 1
    Call RelaunchApp
  ${EndIf}
FunctionEnd

Section "Uninstall"
  !include "${UNINSTALL_LIST}"
  ; Copies an update left behind are the installer's own, never user files.
  Delete "$INSTDIR\AkisKurguAI.exe.new"
  Delete "$INSTDIR\AkisKurguAI.exe.old"
  RMDir /r "$INSTDIR\_internal.old"
  Delete "$INSTDIR\Uninstall-Akis.exe"
  RMDir "$INSTDIR"
  SetShellVarContext ${SHELL_CONTEXT}
  Delete "${SHORTCUT_DIR}\${PRODUCT_NAME}.lnk"
  RMDir "${SHORTCUT_DIR}"
  SetRegView 64
  DeleteRegKey ${REG_ROOT} "${UNINSTALL_KEY}"
SectionEnd
