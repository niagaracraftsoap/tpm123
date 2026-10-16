"""Exercise startup and provisioning with synthetic values and mocked TPM tools."""
import os
from pathlib import Path
import pwd
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Tpm123Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.blobs = self.base / 'blobs'
        self.run = self.base / 'run'
        self.bin = self.base / 'bin'
        for directory in (self.blobs, self.run, self.bin):
            directory.mkdir()
        self.user = pwd.getpwuid(os.getuid()).pw_name
        self.env = dict(os.environ, PATH=f'{self.bin}:{os.environ["PATH"]}')
        self.env['MOCK_VALUE'] = 'synthetic-secret'
        self.env['MOCK_STATUS'] = '0'
        self.mock('chown', 'exit 0')
        self.mock('install', 'mkdir -p -- "${@: -1}"; chmod 700 -- "${@: -1}"')
        self.mock('tpm_unsealdata', 'printf "%s" "$MOCK_VALUE"; exit "$MOCK_STATUS"')
        self.mock('tpm_sealdata', 'cat >/dev/null; printf sealed > "$3"; exit "$MOCK_STATUS"')
        for name in ('tpm123',):
            source = (ROOT / name).read_text()
            source = source.replace('readonly BLOB_DIR="/etc/blobs"', f'readonly BLOB_DIR="{self.blobs}"')
            source = source.replace('readonly TMPFS_BASE="/run"', f'readonly TMPFS_BASE="{self.run}"')
            (self.base / name).write_text(source)

    def mock(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/bash\nset -eu\n' + body + '\n')
        path.chmod(0o755)

    def execute(self, name='tpm123', *args):
        return subprocess.run(['bash', str(self.base / name), *args], env=self.env,
                              capture_output=True, text=True)

    def blob(self, key='SECRET', value=b'sealed'):
        path = self.blobs / f'{self.user}_{key}.blob'
        path.write_bytes(value)
        return path

    def test_success_quotes_and_permissions(self):
        self.blob()
        value = "space 'quote' \"double\" \\ $HOME `id` # ; end"
        self.env['MOCK_VALUE'] = value
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        folder = self.run / self.user
        shell = subprocess.run(['bash', '-c', 'source "$1"; printf "%s" "$SECRET"',
                                'test', str(folder / '.env')], capture_output=True, text=True)
        self.assertEqual(shell.returncode, 0, shell.stderr)
        self.assertEqual(shell.stdout, value)
        # Double-quoted EnvironmentFile values only need backslash and quote escaped.
        expected = 'SECRET="' + value.replace('\\', '\\\\').replace('"', '\\"') + '"\n'
        self.assertEqual((folder / 'env').read_text(), expected)
        for name in ('env', '.env'):
            self.assertEqual((folder / name).stat().st_mode & 0o777, 0o400)
        self.assertNotIn(value, result.stdout + result.stderr)
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ['.env', 'env'])

    def test_unseal_failure_reports_status_without_secret(self):
        self.blob()
        self.env['MOCK_STATUS'] = '17'
        result = self.execute()
        self.assertEqual(result.returncode, 17)
        self.assertIn('Unseal failed', result.stderr)
        self.assertIn('exit 17', result.stderr)
        self.assertNotIn(self.env['MOCK_VALUE'], result.stdout + result.stderr)
        self.assertEqual(list((self.run / self.user).iterdir()), [])

    def test_empty_blob_generates_at_startup_and_is_not_regenerated(self):
        blob = self.blob(value=b'')
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(blob.read_bytes(), b'sealed')
        self.assertEqual(blob.stat().st_mode & 0o777, 0o600)
        self.assertTrue((self.run / self.user / 'env').is_file())
        self.assertEqual(list(self.blobs.iterdir()), [blob])
        self.mock('tpm_sealdata', 'echo UNEXPECTED-SEAL >&2; exit 90')
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('UNEXPECTED-SEAL', result.stderr)
        self.assertEqual(blob.read_bytes(), b'sealed')

    def test_later_failure_preserves_existing_runtime_files(self):
        self.blob('A')
        (self.blobs / f'{self.user}_Z.blob').mkdir()
        folder = self.run / self.user
        folder.mkdir()
        for name in ('env', '.env'):
            (folder / name).write_text('previous-output')
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ['.env', 'env'])
        for name in ('env', '.env'):
            self.assertEqual((folder / name).read_text(), 'previous-output')

    def test_missing_blob_is_not_generated_at_boot(self):
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.blobs.iterdir()), [])
        self.assertEqual(list(self.run.iterdir()), [])

    def test_failed_sealing_preserves_empty_request(self):
        blob = self.blob(value=b'')
        self.env['MOCK_STATUS'] = '19'
        result = self.execute()
        self.assertEqual(result.returncode, 19)
        self.assertIn('Sealing failed', result.stderr)
        self.assertIn('exit 19', result.stderr)
        self.assertEqual(blob.read_bytes(), b'')
        self.assertEqual(list(self.blobs.iterdir()), [blob])
        self.assertEqual(list((self.run / self.user).iterdir()), [])

    def test_successful_seal_with_empty_output_is_refused(self):
        blob = self.blob(value=b'')
        self.mock('tpm_sealdata', 'cat >/dev/null; : > "$3"')
        result = self.execute()
        self.assertEqual(result.returncode, 1)
        self.assertIn('Sealing produced an empty blob', result.stderr)
        self.assertEqual(blob.read_bytes(), b'')
        self.assertEqual(list(self.blobs.iterdir()), [blob])


if __name__ == '__main__':
    unittest.main()
