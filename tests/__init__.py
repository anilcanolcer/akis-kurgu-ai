import os
import tempfile

# Keep test runs away from the user's real settings (recent projects, language, saved options).
os.environ.setdefault('AKIS_SETTINGS_FILE', os.path.join(tempfile.mkdtemp(prefix='akis_test_settings_'), 'settings.ini'))
