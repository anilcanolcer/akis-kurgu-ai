"""Uninstall manifest generation, and static checks of installer.nsi's update mode and safe file swap.

The installer logic itself is exercised for real by scripts/installer-scenarios.ps1 (needs makensis; CI
runs it). These checks keep the properties that script relies on from silently regressing.
"""
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from akis import update_service

ROOT = Path(__file__).resolve().parents[1]
NSI = (ROOT / 'installer.nsi').read_text(encoding='utf-8-sig').replace('\r\n', '\n')


def block(start, end='SectionEnd'):
    """Text of installer.nsi from the line starting `start` up to the next `end` line."""
    match = re.search(rf'^{re.escape(start)}.*?^{re.escape(end)}', NSI, re.M | re.S)
    if match is None:
        raise AssertionError(f'{start!r} not found in installer.nsi')
    return match.group(0)


def code_lines(text):
    return '\n'.join(line for line in text.splitlines() if not line.strip().startswith(';'))


class InstallerManifestTests(unittest.TestCase):
    def generate(self, root, output):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/generate-nsis-uninstall.py'), str(root), str(output)],
                              capture_output=True, text=True)

    def test_uninstall_manifest_only_targets_packaged_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'package'
            nested = root / '_internal' / 'media$test'
            nested.mkdir(parents=True)
            (root / 'AkisKurguAI.exe').write_bytes(b'app')
            (nested / 'dep.dll').write_bytes(b'dep')
            output = Path(folder) / 'uninstall.nsh'
            self.assertEqual(self.generate(root, output).returncode, 0)
            data = output.read_text(encoding='utf-8-sig')
            self.assertIn('Delete "$INSTDIR\\AkisKurguAI.exe"', data)
            self.assertIn('Delete "$INSTDIR\\_internal\\media$$test\\dep.dll"', data)
            self.assertIn('RMDir "$INSTDIR\\_internal\\media$$test"', data)
            self.assertNotIn('RMDir /r', data)

    def test_generator_rejects_a_layout_the_installer_would_not_swap(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'package'
            root.mkdir()
            (root / 'AkisKurguAI.exe').write_bytes(b'app')
            output = Path(folder) / 'uninstall.nsh'
            self.assertNotEqual(self.generate(root, output).returncode, 0)  # no _internal
            (root / '_internal').mkdir()
            (root / 'stray.dll').write_bytes(b'x')
            result = self.generate(root, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('stray.dll', result.stderr)


class InstallerScriptTests(unittest.TestCase):
    def test_update_switch_and_legacy_flags_select_update_mode(self):
        init = block('Function .onInit', 'FunctionEnd')
        self.assertRegex(init, r'GetOptions\} \$R0 "/UPDATE" \$R1\s+\$\{IfNot\} \$\{Errors\}\s+StrCpy \$UpdateMode 1')
        self.assertRegex(init, r'GetOptions\} \$R0 "/VERYSILENT" \$R1\s+\$\{IfNot\} \$\{Errors\}\s+StrCpy \$UpdateMode 1')
        self.assertIn('"/DIR="', init)
        self.assertIn('"/LOG="', init)

    def test_update_mode_shows_only_the_progress_page_and_closes_itself(self):
        pages = re.findall(r'^(!define MUI_PAGE_CUSTOMFUNCTION_PRE \w+\n)?!insertmacro (MUI_PAGE_\w+)', NSI, re.M)
        skipped = {page for pre, page in pages if 'SkipPageInUpdateMode' in pre}
        self.assertEqual(skipped, {'MUI_PAGE_WELCOME', 'MUI_PAGE_DIRECTORY', 'MUI_PAGE_FINISH'})
        self.assertIn('MUI_PAGE_INSTFILES', {page for _, page in pages})
        self.assertRegex(block('Function SkipPageInUpdateMode', 'FunctionEnd'), r'\$UpdateMode == 1\s+Abort')
        self.assertRegex(block('Section "Install"'), r'\$UpdateMode == 1\s+SetDetailsView hide\s+SetAutoClose true')

    def test_no_blocking_message_box_when_unattended(self):
        boxes = [line for line in code_lines(NSI).splitlines() if 'MessageBox' in line]
        self.assertTrue(boxes)
        for line in boxes:
            # /SD answers the box in silent mode; a Retry/Cancel box must default to cancelling.
            self.assertIn('/SD IDCANCEL' if 'MB_RETRYCANCEL' in line else '/SD IDOK', line)
        fail = block('!macro FAIL', '!macroend')
        self.assertLess(fail.index('Quit'), fail.index('MessageBox'))  # update/silent mode quits before any box
        self.assertRegex(fail, r'\$UpdateMode == 1\s+\$\{OrIf\} \$\{Silent\}\s+Quit')
        self.assertIn('SetErrorLevel ${code}', fail)

    def test_old_copy_is_moved_aside_before_extracting_and_deleted_only_at_the_end(self):
        section = code_lines(block('Section "Install"'))
        order = [section.index(text) for text in (
            'Call RecoverInterrupted',
            'Call TryMoveAside',
            'File /r',
            'File "/oname=AkisKurguAI.exe.new"',
            'Rename "$INSTDIR\AkisKurguAI.exe.new" "$INSTDIR\AkisKurguAI.exe"',
            'WriteUninstaller',
            'WriteRegStr',
            'CreateShortcut',
            'NSIS installation completed.',
            'RMDir /r "$INSTDIR\_internal.old"',
            'Delete "$INSTDIR\AkisKurguAI.exe.old"',
        )]
        self.assertEqual(order, sorted(order))
        self.assertEqual(section.count('RMDir /r "$INSTDIR\_internal.old"'), 1)
        self.assertIn('SetOverwrite try', section)
        self.assertNotIn('SetOverwrite on', section)
        aside = code_lines(block('Function TryMoveAside', 'FunctionEnd'))
        steps = [aside.index(text) for text in (
            'CHECK_NOT_RUNNING "$INSTDIR\AkisKurguAI.exe"',
            'Rename "$INSTDIR\AkisKurguAI.exe" "$INSTDIR\AkisKurguAI.exe.old"',
            'Rename "$INSTDIR\_internal" "$INSTDIR\_internal.old"',
        )]
        self.assertEqual(steps, sorted(steps))

    def test_failed_move_aside_is_undone_before_reporting_in_use(self):
        aside = block('Function TryMoveAside', 'FunctionEnd')
        refused = aside[aside.index('Rename "$INSTDIR\_internal" "$INSTDIR\_internal.old"'):]
        refused = refused[:refused.index('StrCpy $MovedLib 1')]
        self.assertLess(refused.index('Rename "$INSTDIR\AkisKurguAI.exe.old" "$INSTDIR\AkisKurguAI.exe"'),
                        refused.index('StrCpy $Failed 1'))

    def test_update_mode_waits_and_restarts_the_app_unelevated(self):
        self.assertIn('"/WAIT="', NSI)
        self.assertIn('$WINDIR\explorer.exe" "$INSTDIR\AkisKurguAI.exe"', NSI)
        self.assertIn('VIProductVersion', NSI)

    def test_errors_roll_back_to_the_old_copy(self):
        self.assertEqual(block('Section "Install"').count('Call Rollback'), 2)  # extraction, finishing steps
        rollback = block('Function Rollback', 'FunctionEnd')
        self.assertIn('${If} $Swapping == 1', rollback)
        self.assertIn('RMDir /r "$INSTDIR\\_internal"', rollback)
        lib = rollback.index('Rename "$INSTDIR\\_internal.old" "$INSTDIR\\_internal"')
        exe = rollback.index('Rename "$INSTDIR\\AkisKurguAI.exe.old" "$INSTDIR\\AkisKurguAI.exe"')
        self.assertLess(lib, exe)  # exe last, and only when _internal came back
        self.assertIn('$RollbackFailed == 0', rollback[lib:exe])
        self.assertIn('Call Rollback', block('Function .onInstFailed', 'FunctionEnd'))

    def test_recovery_restores_exe_only_after_internal(self):
        recover = block('Function RecoverInterrupted', 'FunctionEnd')
        lib = recover.index('Rename "$INSTDIR\\_internal.old" "$INSTDIR\\_internal"')
        exe = recover.index('Rename "$INSTDIR\\AkisKurguAI.exe.old" "$INSTDIR\\AkisKurguAI.exe"')
        self.assertLess(lib, exe)
        self.assertIn('$RecoverFailed == 0', recover[lib:exe])

    def test_exit_codes_match_the_helper_texts(self):
        codes = {int(value) for value in re.findall(r'^!define ERR_\w+ (\d+)', NSI, re.M)}
        self.assertEqual(codes, set(update_service.INSTALLER_EXIT_CODES) - {1, 2})

    def test_uninstaller_removes_leftover_old_copies_but_no_user_files(self):
        uninstall = code_lines(block('Section "Uninstall"'))
        self.assertIn('RMDir /r "$INSTDIR\\_internal.old"', uninstall)
        self.assertIn('Delete "$INSTDIR\\AkisKurguAI.exe.old"', uninstall)
        self.assertIn('RMDir "$INSTDIR"', uninstall)
        self.assertNotIn('RMDir /r "$INSTDIR"', uninstall)

    def test_test_build_is_user_level_and_keeps_out_of_hklm_and_the_start_menu(self):
        test = re.search(r'!ifdef TEST_USER_LEVEL(.*?)!else(.*?)!endif', NSI, re.S)
        self.assertIn('RequestExecutionLevel user', test.group(1))
        self.assertIn('!define REG_ROOT HKCU', test.group(1))
        self.assertNotIn('SMPROGRAMS', test.group(1))
        self.assertIn('RequestExecutionLevel admin', test.group(2))
        for line in code_lines(NSI).splitlines():
            if 'HKLM' in line and '!define' not in line:
                self.assertIn('LEGACY_KEY', line)  # the only literal HKLM use, compiled out in test builds
        self.assertRegex(NSI, r'!ifndef TEST_USER_LEVEL\s+ReadRegStr \$1 HKLM')

    def test_version_comes_from_the_app_package(self):
        self.assertNotRegex(NSI, r'!define PRODUCT_VERSION "\d')  # no hard-coded default that can drift
        match = re.search(r'^!searchparse /file "akis\\__init__.py" "([^"]*)" APP_SOURCE_VERSION "([^"]*)"$', NSI, re.M)
        self.assertIsNotNone(match)
        source = (ROOT / 'akis' / '__init__.py').read_text(encoding='utf-8')
        found = re.search(re.escape(match.group(1)) + r'(.*?)' + re.escape(match.group(2)), source)
        self.assertIsNotNone(found, 'the !searchparse pattern no longer matches akis/__init__.py')
        import akis
        self.assertEqual(found.group(1), akis.__version__)
        self.assertRegex(NSI, r'!ifndef TEST_USER_LEVEL\s+!if "\$\{PRODUCT_VERSION\}" != "\$\{APP_SOURCE_VERSION\}"\s+!error')

    def test_uninstaller_refuses_while_the_app_runs(self):
        init = code_lines(block('Function un.onInit', 'FunctionEnd'))
        self.assertIn('CHECK_NOT_RUNNING "$INSTDIR\\AkisKurguAI.exe"', init)
        self.assertIn('CHECK_NOT_RUNNING "$INSTDIR\\_internal\\ffmpeg.exe"', init)
        self.assertRegex(init, r'\$\{If\} \$\{Silent\}\s+SetErrorLevel \$\{ERR_IN_USE\}\s+Quit')
        self.assertLess(init.index('${Silent}'), init.index('MessageBox'))  # silent never reaches the box
        self.assertIn('MB_RETRYCANCEL', init)

    def test_install_location_is_remembered_and_proposed_again(self):
        section = code_lines(block('Section "Install"'))
        checked = section[section.index('WriteUninstaller'):section.index('CreateShortcut')]
        for value in ('InstallLocation', 'DisplayIcon', 'Publisher', 'URLInfoAbout', 'EstimatedSize'):
            self.assertIn(f'"{value}"', checked)  # inside the error-checked, rolled-back registry step
        self.assertIn('"InstallLocation" "$INSTDIR"', checked)
        self.assertIn('"DisplayName" "${DISPLAY_NAME}"', checked)
        self.assertIn('!define DISPLAY_NAME "Ak\u0131\u015f Kurgu AI"', NSI)
        init = code_lines(block('Function .onInit', 'FunctionEnd'))
        read = init.index('ReadRegStr $R1 ${REG_ROOT} "${UNINSTALL_KEY}" "InstallLocation"')
        self.assertLess(init.index('$INSTDIR == "$PROGRAMFILES64\\AkisKurguAI"'), read)  # /D= wins
        self.assertLess(read, init.index('"/DIR="'))  # /DIR= wins
        self.assertIn('InstallDir "$PROGRAMFILES64\\AkisKurguAI"', NSI)

    def test_directory_page_refuses_another_programs_internal_folder(self):
        self.assertRegex(NSI, r'!define MUI_PAGE_CUSTOMFUNCTION_LEAVE CheckInstallDir\n'
                              r'!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipPageInUpdateMode\n'
                              r'!insertmacro MUI_PAGE_DIRECTORY')
        check = code_lines(block('Function CheckInstallDir', 'FunctionEnd'))
        self.assertIn('${If} ${FileExists} "$INSTDIR\\_internal\\*.*"', check)
        for ours in ('AkisKurguAI.exe', 'AkisKurguAI.exe.old', 'AkisKurguAI.exe.new', '_internal.old\\*.*'):
            self.assertIn(f'${{AndIfNot}} ${{FileExists}} "$INSTDIR\\{ours}"', check)
        self.assertIn('Abort', check)

    def test_finish_page_offers_an_unelevated_launch(self):
        finish = NSI[NSI.index('!insertmacro MUI_PAGE_INSTFILES'):NSI.index('!insertmacro MUI_PAGE_FINISH')]
        self.assertIn('!define MUI_FINISHPAGE_RUN\n', finish)
        self.assertIn('!define MUI_FINISHPAGE_RUN_FUNCTION RelaunchApp', finish)
        self.assertIn('explorer.exe', block('Function RelaunchApp', 'FunctionEnd'))

    def test_finish_page_offers_a_desktop_shortcut_that_uninstall_removes(self):
        finish = NSI[NSI.index('!insertmacro MUI_PAGE_INSTFILES'):NSI.index('!insertmacro MUI_PAGE_FINISH')]
        self.assertIn('!define MUI_FINISHPAGE_SHOWREADME_TEXT "Masaüstüne kısayol ekle"', finish)
        self.assertIn('!define MUI_FINISHPAGE_SHOWREADME_FUNCTION CreateDesktopShortcut', finish)
        self.assertNotIn('MUI_FINISHPAGE_SHOWREADME_NOTCHECKED', NSI)  # ticked by default
        create = code_lines(block('Function CreateDesktopShortcut', 'FunctionEnd'))
        self.assertIn('CreateShortcut "${DESKTOP_LINK}"', create)
        self.assertIn('Delete "${DESKTOP_LINK}"', block('Section "Uninstall"'))
        test = re.search(r'!ifdef TEST_USER_LEVEL(.*?)!else', NSI, re.S).group(1)
        self.assertNotIn('$DESKTOP', test)  # test builds never touch the real desktop
        self.assertNotIn('CreateDesktopShortcut', block('Section "Install"'))  # updates leave it alone

    def test_ffmpeg_is_pinned_and_its_notice_ships(self):
        workflow = (ROOT / '.github' / 'workflows' / 'windows-build.yml').read_text(encoding='utf-8')
        pinned = re.search(r"\$ffmpegVersion = '([\d.]+)'", workflow)
        self.assertIsNotNone(pinned, 'the build must install one fixed FFmpeg version')
        self.assertIn('choco install ffmpeg --version $ffmpegVersion', workflow)
        self.assertIn('-notmatch "^ffmpeg version', workflow)            # and check it got that one
        notice = (ROOT / 'THIRD_PARTY_NOTICES.txt').read_text(encoding='utf-8')
        version = pinned.group(1)
        self.assertIn(f'FFmpeg {version} (ffmpeg.exe)', notice)
        self.assertIn(f'ffmpeg-{version}.tar.xz', notice)
        self.assertIn(f'version {version}.', notice)
        spec = (ROOT / 'AkisKurguAI.spec').read_text(encoding='utf-8')
        self.assertIn('"THIRD_PARTY_NOTICES.txt"', spec)
        self.assertIn('licence_datas', spec[spec.index('datas='):])

    def test_release_notes_come_from_the_repository(self):
        workflow = (ROOT / '.github' / 'workflows' / 'windows-build.yml').read_text(encoding='utf-8')
        release = workflow[workflow.index('\n  release:'):]
        self.assertNotIn("--notes '", release)  # no hard-coded notes of one version
        self.assertIn('$notesFile = "docs/release-notes/v$env:APP_VERSION.md"', release)
        self.assertIn("@('--notes-file', $notesFile)", release)
        self.assertEqual(release.count('::warning::'), 2)  # release exists; notes file missing
        self.assertLess(release.index('actions/checkout'), release.index('actions/download-artifact'))
        self.assertIn('sparse-checkout: docs/release-notes', release)
        notes = list((ROOT / 'docs' / 'release-notes').iterdir())
        self.assertTrue(notes)
        for path in notes:
            self.assertRegex(path.name, r'^v\d+\.\d+\.\d+\.md$')
            data = path.read_bytes()
            self.assertFalse(data.startswith(b'\xef\xbb\xbf'), f'{path.name} has a BOM')
            self.assertTrue(data.decode('utf-8').strip())

    @unittest.skipUnless(shutil.which('powershell.exe'), 'Windows PowerShell not available')
    def test_end_to_end_script_parses(self):
        script = ROOT / 'scripts' / 'installer-scenarios.ps1'
        check = ('$t=$null;$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('
                 f"'{script}',[ref]$t,[ref]$e);$e.Count")
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', check],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.stdout.strip(), '0', result.stderr)

    def test_ci_runs_the_update_scenarios(self):
        workflow = (ROOT / '.github' / 'workflows' / 'windows-build.yml').read_text(encoding='utf-8')
        self.assertIn('scripts/installer-scenarios.ps1 -MakeNsis', workflow)
        self.assertIn('python update_smoke.py', workflow)


if __name__ == '__main__':
    unittest.main()
