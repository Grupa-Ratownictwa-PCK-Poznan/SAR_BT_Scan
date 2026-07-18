import unittest
from unittest.mock import patch

import storage


class TestStoragePathResolution(unittest.TestCase):
    def test_prefers_env_override_when_writable(self):
        with patch.dict('os.environ', {'BTS_DB_PATH': '/custom/env.db'}, clear=False):
            with patch('storage._can_use_db_path', side_effect=lambda p: p == '/custom/env.db'):
                resolved = storage.resolve_db_path()

        self.assertEqual(resolved, '/custom/env.db')

    def test_prefers_configured_path_when_writable(self):
        configured = storage.os.path.abspath(storage.os.path.join(storage.SD_STORAGE, storage.DB_FILE))

        with patch.dict('os.environ', {}, clear=False):
            with patch('storage._can_use_db_path', side_effect=lambda p: p == configured):
                resolved = storage.resolve_db_path()

        self.assertEqual(resolved, configured)

    def test_falls_back_when_configured_unwritable(self):
        tmp_fallback = storage.os.path.abspath(storage.os.path.join('/tmp', storage.DB_FILE))

        with patch.dict('os.environ', {}, clear=False):
            with patch('storage._can_use_db_path', side_effect=lambda p: p == tmp_fallback):
                resolved = storage.resolve_db_path()

        self.assertEqual(resolved, tmp_fallback)


if __name__ == '__main__':
    unittest.main()
