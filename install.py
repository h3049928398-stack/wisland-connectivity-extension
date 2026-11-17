"""Install the local extension with hash guards and backups; no config secrets copied."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import datetime
import importlib.util

BASE = Path(__file__).resolve().parent
ORIGINAL_SYSTEM_SHA256 = '2920592a75af1471c7b3c49c88f36a5a27a0d387e0130c3da53c846780b7b368'


def system_source(original: bytes) -> bytes:
    if hashlib.sha256(original).hexdigest() != ORIGINAL_SYSTEM_SHA256:
        raise RuntimeError('控制页与已检查版本不同，停止安装以保留本地改动。')
    text = original.decode('utf-8').replace('\r\n', '\n')
    edits = [
        ('from .base import Page\n', 'from .base import Page\nfrom ..control_skin import ConnectionTile\n'),
        ('"控制", 180\n', '"控制", 220\n'),
        ('self.wifi = Tile(G.WIFI, "WLAN")', 'self.wifi = ConnectionTile("wifi", "无线局域网")'),
        ('self.bt = Tile(G.BT, "蓝牙")', 'self.bt = ConnectionTile("bt", "蓝牙", compact=True)'),
        ('        self._radio = {}\n', '''        # Local AirDrop extension (wisland-connectivity-extension).
        from ...services.airdrop import AirDropService
        from ..airdrop import AirDropPanel
        from ...services.connectivity import ConnectivityService
        from ..connections import RadioPanel
        self.airdrop_service = AirDropService(self)
        self.airdrop_panel = AirDropPanel(self.airdrop_service, self)
        self.connection_service = ConnectivityService(self)
        self.wifi_panel = RadioPanel(self.connection_service, self, "wifi")
        self.bt_panel = RadioPanel(self.connection_service, self, "bt")
        self.airdrop = ConnectionTile("airdrop", "隔空投送")
        self.airdrop.setAccessibleName("隔空投送")
        self.airdrop.clicked.connect(self._open_airdrop)
        self.airdrop_service.changed.connect(self._airdrop_state)
        if "--airdrop" in QtCore.QCoreApplication.arguments():
            QtCore.QTimer.singleShot(600, self._open_airdrop)
        for option, kind in (("--wifi", "wifi"), ("--bluetooth", "bt")):
            if option in QtCore.QCoreApplication.arguments():
                QtCore.QTimer.singleShot(600, lambda kind=kind: self._open_radio(kind))
        for argument in QtCore.QCoreApplication.arguments():
            if argument.startswith("--airdrop-layout-report="):
                path = argument.split("=", 1)[1]
                QtCore.QTimer.singleShot(3000, lambda path=path: self.airdrop_panel.write_layout_report(path))
            elif argument.startswith("--connection-layout-report="):
                path = argument.split("=", 1)[1]
                QtCore.QTimer.singleShot(3500, lambda path=path: (getattr(self, '_connection_layer', None) or self.airdrop_panel).write_layout_report(path))
        self._radio = {}
'''),
        ('        for i, t in enumerate((self.wifi, self.bt, self.proxy, self.tun)):\n            grid.addWidget(t, i // 2, i % 2)\n', '''        grid.addWidget(self.wifi, 0, 0)
        grid.addWidget(self.airdrop, 0, 1)
        grid.addWidget(self.bt, 1, 0, 1, 2)
        grid.addWidget(self.proxy, 2, 0)
        grid.addWidget(self.tun, 2, 1)
'''),
        ('vbox(None, gw, None)', 'vbox(gw, None)'),
        ('self.wifi.clicked.connect(lambda: self._toggle("wifi"))', 'self.wifi.clicked.connect(lambda: self._open_radio("wifi"))'),
        ('self.bt.clicked.connect(lambda: self._toggle("bt"))', 'self.bt.clicked.connect(lambda: self._open_radio("bt"))'),
        ('    def _toggle(self, kind: str):\n', '''    def _open_airdrop(self):
        for tile in (self.wifi, self.bt, self.airdrop):
            tile.island = self.island
        self.airdrop_panel.present()
        self.airdrop_service.connect_backend()

    def _open_radio(self, kind):
        for tile in (self.wifi, self.bt, self.airdrop):
            tile.island = self.island
        (self.wifi_panel if kind == "wifi" else self.bt_panel).present()
        radio = getattr(self.ctx, "radio", None)
        if radio is not None:
            radio.refresh()

    def _airdrop_state(self, state):
        on = state.get("isRunning", False)
        starting = state.get("isStarting", False)
        self.airdrop.set_state(on or starting,
                              "正在准备…" if starting else "所有人，10分钟" if on else "接收关闭")

    def _toggle(self, kind: str):
'''),
        ('        ok = d.get("ok")\n', '''        ok = d.get("ok")
        height = 280 if ok else 220
        layer = getattr(self, '_connection_layer', None)
        if layer is not None and layer._height_before is not None:
            layer._height_before = height
        else:
            self.set_height(height)
'''),
        ('    def on_show(self):\n        super().on_show()\n        self.ctx.brightness.refresh()', '''    def on_hide(self):
        self.airdrop_panel.close(immediate=True)
        self.wifi_panel.close(immediate=True)
        self.bt_panel.close(immediate=True)
        super().on_hide()

    def on_show(self):
        super().on_show()
        for tile in (self.wifi, self.bt, self.airdrop):
            tile.island = self.island
        if self.island and not getattr(self, '_glass_hooked', False):
            self.island.backdrop.ready.connect(self.airdrop.update)
            self.island.backdrop.ready.connect(self.wifi.update)
            self.island.backdrop.ready.connect(self.bt.update)
            self.island.backdrop.ready.connect(self.airdrop_panel.refresh_backdrop)
            self.island.backdrop.ready.connect(self.wifi_panel.refresh_backdrop)
            self.island.backdrop.ready.connect(self.bt_panel.refresh_backdrop)
            self._glass_hooked = True
        self.ctx.brightness.refresh()'''),
        ('        self.ctx.radio.refresh()\n', '        self.ctx.radio.refresh()\n        self.airdrop_service.refresh()\n'),
    ]
    for before, after in edits:
        if text.count(before) != 1:
            raise RuntimeError('控制页插入点不唯一，停止安装。')
        text = text.replace(before, after)
    return text.encode('utf-8')


CONFIG_PATH = 'data/extensions/connectivity.json'
PAYLOAD_PATHS = ('services/airdrop.py', 'services/connectivity.py', 'ui/airdrop.py',
                 'ui/control_skin.py', 'ui/backdrop_filter.py', 'ui/detail_layer.py', 'ui/connections.py')
ALLOWED_PATHS = {'wisland/ui/pages/system.py', 'docs/AIRDROP_EXTENSION.md', CONFIG_PATH,
                 *('wisland/' + path for path in PAYLOAD_PATHS)}


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def inside(root, relative):
    relative = str(relative).replace('\\', '/')
    if not relative or any(part in ('', '.', '..') for part in relative.split('/')) or ':' in relative:
        raise RuntimeError('清单包含无效相对路径。')
    path = (root / relative).resolve()
    if root not in path.parents:
        raise RuntimeError('清单路径超出目标目录。')
    return path


def installed_manifest(target, current):
    for manifest in sorted((target / 'data/extension-backups').glob('airdrop-*/manifest.json'), reverse=True):
        entries = json.loads(manifest.read_text(encoding='utf-8'))
        entry = next((e for e in entries if e['path'].replace('\\', '/') == 'wisland/ui/pages/system.py'), None)
        if entry and entry['sha256'] == sha256(current):
            return entries
    return None


def installation_plan(target, runtime=None):
    target = Path(target).resolve()
    system = inside(target, 'wisland/ui/pages/system.py')
    if not system.is_file():
        raise RuntimeError('目标不是 wisland 源码/安装目录。')
    current = system.read_bytes(); manifest = installed_manifest(target, current)
    original = current
    if sha256(current) != ORIGINAL_SYSTEM_SHA256:
        if manifest is None:
            raise RuntimeError('控制页有未知改动，停止安装。')
        originals = (target / 'data/extension-backups').glob('airdrop-*/system.py.original')
        original = next((p.read_bytes() for p in originals if sha256(p.read_bytes()) == ORIGINAL_SYSTEM_SHA256), b'')
    desired = {'wisland/ui/pages/system.py': system_source(original),
               'docs/AIRDROP_EXTENSION.md': (BASE / 'README.md').read_bytes()}
    desired.update({'wisland/' + path: (BASE / 'payload' / path).read_bytes() for path in PAYLOAD_PATHS})
    if runtime is None and (BASE / 'runtime/AirDrop/AirDrop.exe').is_file():
        runtime = BASE / 'runtime/AirDrop/AirDrop.exe'
    if runtime is not None:
        runtime = Path(runtime).expanduser().resolve()
        if runtime.name.lower() != 'airdrop.exe' or not runtime.is_file():
            raise RuntimeError('请指定实际 AirDrop.exe 的完整路径。')
        desired[CONFIG_PATH] = (json.dumps({'airdropExecutable': str(runtime)}, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    for relative in desired:
        path = inside(target, relative)
        if path.exists() and relative != 'wisland/ui/pages/system.py':
            entry = next((e for e in (manifest or []) if e['path'].replace('\\', '/') == relative), None)
            if not entry or entry['sha256'] != sha256(path.read_bytes()):
                raise RuntimeError('已有文件有未知改动，停止以保留内容：' + relative)
    return target, desired


def install(target, runtime=None, check=False):
    target, desired = installation_plan(target, runtime)
    if check:
        return {'dryRun': True, 'files': sorted(desired)}
    try:
        available = importlib.util.find_spec('winrt.windows.devices.enumeration') is not None
    except ModuleNotFoundError:
        available = False
    if not available:
        raise RuntimeError('请先使用 wisland 的 Python 安装 requirements-extension.txt。')
    backup = target / 'data/extension-backups' / ('airdrop-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(target / 'wisland/ui/pages/system.py', backup / 'system.py.original')
    manifest = []
    for relative, content in desired.items():
        path = inside(target, relative); existed = path.exists()
        saved = inside(backup, 'previous/' + relative)
        if existed:
            saved.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, saved)
        manifest.append({'path': relative, 'sha256': sha256(content), 'created': not existed,
                         'backup': 'previous/' + relative if existed else None,
                         'backup_sha256': sha256(saved.read_bytes()) if existed else None})
    # Write a complete recovery receipt before changing any live file.
    (backup / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    written = []
    try:
        for entry in manifest:
            path = inside(target, entry['path']); path.parent.mkdir(parents=True, exist_ok=True)
            written.append(entry); path.write_bytes(desired[entry['path']])
    except Exception:
        for entry in reversed(written):
            path = inside(target, entry['path'])
            if entry['created']: path.unlink(missing_ok=True)
            else: shutil.copy2(inside(backup, entry['backup']), path)
        raise
    return {'installed': sorted(desired), 'backup': str(backup)}


def restore(target, backup=None, check=False):
    target = Path(target).resolve()
    backups = inside(target, 'data/extension-backups')
    if backup is None:
        candidates = sorted(backups.glob('airdrop-*/manifest.json'), reverse=True)
        if not candidates: raise RuntimeError('未找到扩展备份。')
        backup = candidates[0].parent
    backup = Path(backup).resolve()
    if backup.parent != backups:
        raise RuntimeError('备份必须位于此 wisland 的 data/extension-backups 目录。')
    entries = json.loads((backup / 'manifest.json').read_text(encoding='utf-8'))
    # Check every path and every current/backup hash before the first mutation.
    for entry in entries:
        relative = entry['path'].replace('\\', '/')
        if relative not in ALLOWED_PATHS: raise RuntimeError('备份包含非扩展文件。')
        path = inside(target, relative)
        if not path.is_file() or sha256(path.read_bytes()) != entry['sha256']:
            raise RuntimeError('安装后文件已有变化，停止恢复：' + relative)
        if not entry.get('created', False):
            saved = inside(backup, entry.get('backup') or '')
            if not saved.is_file(): raise RuntimeError('备份文件缺失：' + relative)
            if entry.get('backup_sha256') and sha256(saved.read_bytes()) != entry['backup_sha256']:
                raise RuntimeError('备份校验失败：' + relative)
    if not check:
        for entry in reversed(entries):
            path = inside(target, entry['path'])
            if entry.get('created', False): path.unlink()
            else: shutil.copy2(inside(backup, entry['backup']), path)
    return {'dryRun': check, 'restored': [e['path'] for e in entries], 'backup': str(backup)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Install or safely restore the wisland connectivity extension.')
    parser.add_argument('target', type=Path)
    parser.add_argument('--airdrop-executable', type=Path)
    parser.add_argument('--check', action='store_true', help='Validate without writing files.')
    parser.add_argument('--restore', action='store_true')
    parser.add_argument('--backup', type=Path)
    options = parser.parse_args()
    result = restore(options.target, options.backup, options.check) if options.restore else install(
        options.target, options.airdrop_executable, options.check)
    print(json.dumps(result, ensure_ascii=False, indent=2))
