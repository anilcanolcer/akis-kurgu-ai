"""The update check keeps working when the GitHub API refuses the request (anonymous rate limit)."""
import io
import json
import unittest
import urllib.error

from akis import update_service
from akis.update_service import check_update

SHA = 'ab' * 32
TAG_PAGE = 'https://github.com/anilcanolcer/akis-kurgu-ai/releases/tag/'
DOWNLOAD = 'https://github.com/anilcanolcer/akis-kurgu-ai/releases/download/'


class Reply(io.BytesIO):
    def __init__(self, body=b'', url=''):
        super().__init__(body)
        self.url = url

    def geturl(self):
        return self.url


def refused(code=403):
    return urllib.error.HTTPError(update_service.API, code, 'rate limit exceeded', {}, io.BytesIO(b''))


class Web:
    """Answers by URL; an exception as the answer is raised. Records what was asked."""
    def __init__(self, answers):
        self.answers, self.asked = answers, []

    def __call__(self, request, timeout=None):
        self.asked.append((request.get_method(), request.full_url))
        answer = self.answers[request.full_url]
        if isinstance(answer, Exception):
            raise answer
        return answer


def api_release(tag):
    asset = {'name': 'AkisKurguAI-Setup.exe', 'browser_download_url': f'{DOWNLOAD}{tag}/AkisKurguAI-Setup.exe',
             'digest': 'sha256:' + SHA, 'size': 123}
    return Reply(json.dumps({'tag_name': tag, 'assets': [asset]}).encode())


class UpdateCheckTests(unittest.TestCase):
    def pages(self, tag, checksum=f'{SHA}  AkisKurguAI-Setup.exe\n', api=None):
        answers = {update_service.API: api or refused(),
                   update_service.LATEST_PAGE: Reply(url=TAG_PAGE + tag)}
        if checksum is not None:
            answers[f'{DOWNLOAD}{tag}/AkisKurguAI-Setup.exe.sha256'] = (
                checksum if isinstance(checksum, Exception) else Reply(checksum.encode()))
        return Web(answers)

    def test_api_answer_is_used_when_it_works(self):
        web = Web({update_service.API: api_release('v9.9.9')})
        self.assertEqual(check_update('0.5.1', web)['size'], 123)
        self.assertEqual(len(web.asked), 1)

    def test_rate_limited_check_reads_the_release_pages(self):
        for code in (403, 429, 503):
            web = self.pages('v0.5.2', api=refused(code))
            found = check_update('0.5.1', web)
            self.assertEqual(found, {'version': 'v0.5.2', 'url': f'{DOWNLOAD}v0.5.2/AkisKurguAI-Setup.exe',
                                     'sha256': SHA, 'size': None})
            self.assertEqual(web.asked[1], ('HEAD', update_service.LATEST_PAGE))

    def test_current_version_asks_for_nothing_more(self):
        web = self.pages('v0.5.1', checksum=None)
        self.assertIsNone(check_update('0.5.1', web))
        self.assertEqual(len(web.asked), 2)

    def test_release_without_a_checksum_is_not_offered(self):
        missing = urllib.error.HTTPError('x', 404, 'Not Found', {}, io.BytesIO(b''))
        for checksum in (missing, 'not a hash', SHA + 'ff'):
            with self.assertRaises(ValueError):
                check_update('0.5.1', self.pages('v0.5.2', checksum=checksum))

    def test_redirect_to_anything_else_is_not_a_version(self):
        for landed in ('https://github.com/login', 'https://example.com/releases/tag/v9.9.9',
                       'https://github.com/someone/else/releases/tag/v9.9.9', TAG_PAGE + 'v9.9.9/../x', TAG_PAGE + 'latest'):
            web = Web({update_service.API: refused(), update_service.LATEST_PAGE: Reply(url=landed)})
            with self.assertRaises(ValueError):
                check_update('0.5.1', web)

    def test_other_api_errors_are_not_hidden(self):
        with self.assertRaises(urllib.error.HTTPError):
            check_update('0.5.1', Web({update_service.API: refused(404)}))

    def test_found_update_downloads_from_the_trusted_prefix(self):
        found = check_update('0.5.1', self.pages('v0.5.2'))
        self.assertTrue(found['url'].startswith(update_service.DOWNLOAD_PREFIX))
        self.assertTrue(str(update_service.installer_path('folder', found)).endswith('AkisKurguAI-Setup-0.5.2.exe'))

    def test_release_job_publishes_the_checksum_file(self):
        from pathlib import Path
        workflow = (Path(__file__).resolve().parents[1] / '.github' / 'workflows' / 'windows-build.yml').read_text(encoding='utf-8')
        self.assertIn("'package/AkisKurguAI-Setup.exe' 'package/AkisKurguAI-Setup.exe.sha256'", workflow)
        self.assertIn('Get-FileHash -Algorithm SHA256', workflow)


if __name__ == '__main__':
    unittest.main()
