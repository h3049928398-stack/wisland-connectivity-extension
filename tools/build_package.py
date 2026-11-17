"""Reproducible, allowlisted source and local companion-runtime packages."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

ROOT_FILES = {'.gitignore', '.gitattributes', 'AGENTS.md', 'LICENSE', 'LICENSE-wisland.txt',
              'README.md', 'VERSION', 'requirements-extension.txt', 'install.py',
              'Install.ps1', 'Restore.ps1', 'runtime-manifest.json', 'CHANGELOG.md'}
SOURCE_DIRS = {'payload', 'tests', 'tools', 'docs'}
FORBIDDEN_PARTS = {'.git', '.venv', '.build', '__pycache__', 'data', 'runtime', 'artifacts', 'dist'}
FORBIDDEN_SUFFIXES = {'.pem', '.key', '.pcap', '.log', '.exe', '.dll', '.pyd', '.pdb', '.zip', '.pyc'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '\\' in name or ':' in name or any(p in ('', '.', '..') for p in name.split('/')):
        raise ValueError('Unsafe archive path: ' + name)
    return path


def source_allowed(name):
    path = safe_name(name)
    if set(path.parts) & FORBIDDEN_PARTS or path.suffix.lower() in FORBIDDEN_SUFFIXES or '.local.' in path.name:
        return False
    if path.name in ('config.json', 'preferences.json'):
        return False
    return name in ROOT_FILES or len(path.parts) > 1 and path.parts[0] in SOURCE_DIRS


def collect_source(root):
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode('utf-8').split('\0')
    result = {}
    for name in filter(None, names):
        if not source_allowed(name):
            raise ValueError('Tracked file is outside the release allowlist: ' + name)
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Release files must be regular files: ' + name)
        # Package normalized committed/staged blobs, not checkout-dependent
        # CRLF bytes. main() requires the index to match the clean HEAD.
        result[name] = subprocess.check_output(['git', 'show', ':' + name], cwd=root)
    return result


def collect_runtime(root, runtime):
    expected = json.loads((root / 'runtime-manifest.json').read_text(encoding='utf-8'))['files']
    result = {}
    runtime = Path(runtime).resolve()
    for entry in expected:
        name = entry['path']; safe_name(name)
        path = (runtime / name).resolve()
        if runtime not in path.parents or not path.is_file():
            raise ValueError('Runtime file is missing or outside its root: ' + name)
        data = path.read_bytes()
        if digest(data) != entry['sha256'] or len(data) != entry['size']:
            raise ValueError('Runtime file does not match the reviewed build: ' + name)
        result['runtime/AirDrop/' + name] = data
    return result


def write_archive(destination, prefix, files, version, commit, kind):
    if len(safe_name(prefix).parts) != 1:
        raise ValueError('Archive root must be one safe directory name')
    for name in files: safe_name(name)
    manifest = {'format': 1, 'version': version, 'sourceCommit': commit, 'kind': kind,
                'files': [{'path': name, 'size': len(data), 'sha256': digest(data)} for name, data in sorted(files.items())]}
    entries = dict(files)
    entries['PACKAGE-MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(prefix + '/' + name, date_time=(2026, 11, 17, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED; info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    verify_archive(destination)
    data = destination.read_bytes()
    sidecar = destination.with_suffix(destination.suffix + '.sha256')
    sidecar.write_text(digest(data) + '  ' + destination.name + '\n', encoding='ascii')
    return {'file': destination.name, 'size': len(data), 'sha256': digest(data), 'sourceCommit': commit, 'kind': kind}


def verify_archive(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names): raise ValueError('Duplicate ZIP entries')
        for name in names: safe_name(name)
        roots = {name.split('/', 1)[0] for name in names}
        if len(roots) != 1: raise ValueError('ZIP must have exactly one root')
        prefix = roots.pop() + '/'
        manifest_name = prefix + 'PACKAGE-MANIFEST.json'
        manifest = json.loads(archive.read(manifest_name))
        expected_names = {manifest_name}
        for entry in manifest['files']:
            safe_name(entry['path']); name = prefix + entry['path']; expected_names.add(name)
            content = archive.read(name)
            if len(content) != entry['size'] or digest(content) != entry['sha256']:
                raise ValueError('Package content failed verification: ' + entry['path'])
        if expected_names != set(names): raise ValueError('Unlisted files in package')
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--airdrop-runtime', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=root).strip():
        raise RuntimeError('Commit tracked changes before building a package.')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root).decode().strip()
    version = (root / 'VERSION').read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?', version):
        raise ValueError('Invalid release version')
    output = (args.output or root / 'dist').resolve(); output.mkdir(parents=True, exist_ok=True)
    prefix = 'wisland-connectivity-extension-' + version
    files = collect_source(root)
    results = [write_archive(output / (prefix + '-source.zip'), prefix, files, version, commit, 'source')]
    if args.airdrop_runtime:
        files.update(collect_runtime(root, args.airdrop_runtime))
        results.append(write_archive(output / (prefix + '-full-local.zip'), prefix, files, version, commit, 'full-local'))
    (output / 'PACKAGES.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
