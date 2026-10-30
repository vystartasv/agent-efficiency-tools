import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('npm'), 'requires npm')
class PackageTest(unittest.TestCase):
    def test_packed_install_and_command(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            pack = subprocess.run(['npm', 'pack', '--ignore-scripts', '--json', '--pack-destination', d],
                                  cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(pack.returncode, 0, pack.stderr)
            archive = directory / json.loads(pack.stdout)[0]['filename']
            with tarfile.open(archive, 'r:gz') as tar:
                names = tar.getnames()
                self.assertIn('package/LICENSE', names)
                self.assertIn('package/skills/agent-tools/SKILL.md', names)
                self.assertIn('package/bin/agent-tools', names)
                self.assertIn('package/bin/image-batch', names)
                self.assertIn('package/bin/log-scan', names)
                self.assertFalse(any('__pycache__' in name or name.endswith('.pyc') for name in names))
            prefix = directory / 'installation'
            install = subprocess.run(['npm', 'install', '--prefix', str(prefix), '--ignore-scripts',
                                      '--no-audit', '--no-fund', '--no-save', '--package-lock=false', str(archive)],
                                     cwd=directory, capture_output=True, text=True)
            self.assertEqual(install.returncode, 0, install.stderr)
            cli = prefix / 'node_modules/.bin/agent-tools'
            help_result = subprocess.run([str(cli), '--help'], cwd=directory, capture_output=True, text=True)
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertIn('output-capture', help_result.stdout)
            self.assertIn('log-scan', help_result.stdout)
            log = directory / 'captured.log'
            capture = subprocess.run([str(cli), 'output-capture', '--output', str(log), '--', 'python3', '-c',
                                      'print("package smoke test")'], cwd=directory, capture_output=True, text=True)
            self.assertEqual(capture.returncode, 0, capture.stderr)
            self.assertIn('package smoke test', log.read_text())

if __name__ == '__main__':
    unittest.main()
