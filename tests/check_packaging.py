"""Installer/recovery and ZIP checks against isolated fixtures only."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

BASE = Path(__file__).resolve().parents[1]


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


installer = module_at('extension_installer', BASE / 'install.py')
packager = module_at('extension_packager', BASE / 'tools/build_package.py')
ORIGINAL = (BASE / 'tests/fixtures/wisland-system.original.py').read_bytes()


class PackageChecks(unittest.TestCase):
    def fixture(self, directory):
        target = Path(directory) / 'wisland'
        (target / 'wisland/ui/pages').mkdir(parents=True)
        (target / 'wisland/ui/pages/system.py').write_bytes(ORIGINAL)
        (target / 'config.json').write_text('{"fixture":"keep"}', encoding='utf-8')
        return target

    def test_install_upgrade_and_restore_preserve_original_and_user_config(self):
        with tempfile.TemporaryDirectory(prefix='connectivity-roundtrip-') as directory:
            target = self.fixture(directory)
            result = installer.install(target)
            self.assertEqual(len(result['installed']), 9)
            self.assertEqual((target / 'config.json').read_text(), '{"fixture":"keep"}')
            upgraded = installer.install(target)
            installer.restore(target, upgraded['backup'])
            installer.restore(target, result['backup'])
            self.assertEqual((target / 'wisland/ui/pages/system.py').read_bytes(), ORIGINAL)
            self.assertFalse((target / 'wisland/ui/airdrop.py').exists())
            self.assertTrue((target / 'config.json').is_file())

    def test_runtime_is_private_configuration_and_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory(prefix='connectivity-runtime-') as directory:
            target = self.fixture(directory)
            runtime = Path(directory) / 'receiver/AirDrop.exe'; runtime.parent.mkdir(); runtime.write_bytes(b'fixture-not-executed')
            plan = installer.install(target, runtime, check=True)
            self.assertEqual(len(plan['files']), 10)
            self.assertFalse((target / 'data').exists())
            installed = installer.install(target, runtime)
            config = json.loads((target / installer.CONFIG_PATH).read_text(encoding='utf-8'))
            self.assertEqual(config['airdropExecutable'], str(runtime.resolve()))
            installer.restore(target, installed['backup'])
            self.assertFalse((target / installer.CONFIG_PATH).exists())
            self.assertEqual(runtime.read_bytes(), b'fixture-not-executed')

    def test_modified_file_blocks_restore_before_any_file_changes(self):
        with tempfile.TemporaryDirectory(prefix='connectivity-guard-') as directory:
            target = self.fixture(directory); installed = installer.install(target)
            system = target / 'wisland/ui/pages/system.py'; before = system.read_bytes()
            (target / 'wisland/ui/airdrop.py').write_bytes(b'local-user-change')
            with self.assertRaises(RuntimeError): installer.restore(target, installed['backup'])
            self.assertEqual(system.read_bytes(), before)
            with self.assertRaises(RuntimeError): installer.install(target)

    def test_write_failure_rolls_back_every_written_file(self):
        with tempfile.TemporaryDirectory(prefix='connectivity-rollback-') as directory:
            target = self.fixture(directory); original_write = Path.write_bytes
            def fail(path, data):
                if path == target / 'wisland/ui/airdrop.py': raise OSError('fixture write failure')
                return original_write(path, data)
            with mock.patch.object(Path, 'write_bytes', fail):
                with self.assertRaises(OSError): installer.install(target)
            self.assertEqual((target / 'wisland/ui/pages/system.py').read_bytes(), ORIGINAL)
            self.assertFalse((target / 'docs/AIRDROP_EXTENSION.md').exists())

    def test_receipt_traversal_and_unowned_file_cannot_be_restored(self):
        with tempfile.TemporaryDirectory(prefix='connectivity-paths-') as directory:
            target = self.fixture(directory); installed = installer.install(target)
            receipt = Path(installed['backup']) / 'manifest.json'
            entries = json.loads(receipt.read_text()); entries[0]['path'] = '../outside.txt'
            receipt.write_text(json.dumps(entries))
            with self.assertRaises(RuntimeError): installer.restore(target, installed['backup'])
            with self.assertRaises(RuntimeError): installer.inside(target, 'data/../../outside')

    def test_package_manifest_hashes_and_sensitive_path_rejection(self):
        with tempfile.TemporaryDirectory(prefix='connectivity-zip-') as directory:
            path = Path(directory) / 'source.zip'
            result = packager.write_archive(path, 'extension-0.1.0', {'README.md': b'fixture'}, '0.1.0', 'fixture', 'source')
            self.assertEqual(len(result['sha256']), 64)
            self.assertEqual(packager.verify_archive(path)['files'][0]['path'], 'README.md')
            for name in ('data/keys/key.pem', 'runtime/AirDrop.exe', 'docs/report.local.json', 'artifacts/native.png'):
                self.assertFalse(packager.source_allowed(name))
            with self.assertRaises(ValueError): packager.safe_name('../outside')
            with self.assertRaises(ValueError):
                packager.write_archive(Path(directory) / 'bad.zip', '../outside', {}, '0.1.0', 'fixture', 'source')


if __name__ == '__main__':
    unittest.main(verbosity=2)
