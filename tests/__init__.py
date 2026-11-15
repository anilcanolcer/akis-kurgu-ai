"""Tests run with the Turkish interface whatever the computer's language (CI runners are English), and with
their own scratch settings file instead of the settings of whoever uses the computer."""
import atexit
import os
import shutil
import tempfile

os.environ["AKIS_LANGUAGE"] = "tr"
_settings = tempfile.mkdtemp(prefix="akis-test-settings-")
atexit.register(shutil.rmtree, _settings, True)
os.environ["AKIS_SETTINGS_FILE"] = os.path.join(_settings, "settings.ini")
