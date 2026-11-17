"""Local AirDrop controller. No USB access or duplicate radio processes here."""
from __future__ import annotations
import ctypes
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

from PySide6 import QtCore
from ..core.config import cfg, ROOT

PIPE = r"\\.\pipe\LiquidGlassWinAirDrop.Control.v1"
_kernel = ctypes.WinDLL('kernel32', use_last_error=True)
_kernel.PeekNamedPipe.argtypes = [W.HANDLE, ctypes.c_void_p, W.DWORD, ctypes.c_void_p, ctypes.POINTER(W.DWORD), ctypes.c_void_p]
_kernel.PeekNamedPipe.restype = W.BOOL
_kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, ctypes.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
_kernel.CreateFileW.restype = W.HANDLE
_kernel.WriteFile.argtypes = [W.HANDLE, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD), ctypes.c_void_p]
_kernel.ReadFile.argtypes = [W.HANDLE, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD), ctypes.c_void_p]
_kernel.CloseHandle.argtypes = [W.HANDLE]


def exchange(command: dict, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    handle = _kernel.CreateFileW(PIPE, 0xC0000000, 0, None, 3, 0, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        request = (json.dumps(command, ensure_ascii=False) + '\n').encode('utf-8')
        sent = W.DWORD()
        if not _kernel.WriteFile(handle, request, len(request), ctypes.byref(sent), None) or sent.value != len(request):
            raise ctypes.WinError(ctypes.get_last_error())
        response = bytearray()
        while time.monotonic() < deadline:
            available = W.DWORD()
            if not _kernel.PeekNamedPipe(handle, None, 0, None, ctypes.byref(available), None):
                raise OSError(ctypes.get_last_error(), 'AirDrop control disconnected')
            if available.value:
                buffer = ctypes.create_string_buffer(min(available.value, 65536 - len(response)))
                count = W.DWORD()
                if not _kernel.ReadFile(handle, buffer, len(buffer), ctypes.byref(count), None):
                    raise ctypes.WinError(ctypes.get_last_error())
                response.extend(buffer.raw[:count.value])
                if b'\n' in response:
                    result = json.loads(response.split(b'\n', 1)[0])
                    if not isinstance(result, dict):
                        raise ValueError('Invalid AirDrop control response')
                    return result
                if len(response) >= 65536:
                    raise ValueError('AirDrop control response too large')
            time.sleep(.02)
    finally:
        _kernel.CloseHandle(handle)
    raise TimeoutError('AirDrop control timed out')


def locate_runtime() -> Path:
    configured = cfg.get('airdrop.executable', '')
    if configured:
        return Path(os.path.expandvars(str(configured))).expanduser()
    extension_settings = ROOT / 'data/extensions/connectivity.json'
    if extension_settings.is_file():
        try:
            settings = json.loads(extension_settings.read_text(encoding='utf-8'))
            configured = settings.get('airdropExecutable') if isinstance(settings, dict) else None
            if configured:
                return Path(os.path.expandvars(str(configured))).expanduser()
        except (OSError, ValueError, TypeError):
            pass
    return ROOT.parent / 'AirDrop-Windows' / 'runtime' / 'AirDrop' / 'AirDrop.exe'


class AirDropService(QtCore.QObject):
    changed = QtCore.Signal(dict)
    request_received = QtCore.Signal()
    _result = QtCore.Signal(object)
    _failure = QtCore.Signal(object)

    def __init__(self, parent=None, transport=exchange):
        super().__init__(parent)
        self.transport = transport
        self.state = {'ok': False, 'message': '点击设置接收方式', 'requests': []}
        self._busy = False
        self._stopped = False
        self._known = set()
        self._queued = []
        self._launch_at = 0.0
        # System/media/weather work shares wisland's global pool. Control and
        # consent must remain responsive even when those jobs block on IO.
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='airdrop-ipc')
        self._result.connect(self._done, QtCore.Qt.ConnectionType.QueuedConnection)
        self._failure.connect(self._error, QtCore.Qt.ConnectionType.QueuedConnection)
        self.timer = QtCore.QTimer(self, interval=1500, timeout=self.refresh)
        self.timer.start()
        QtCore.QTimer.singleShot(0, self.refresh)
        app = QtCore.QCoreApplication.instance()
        if app:
            app.aboutToQuit.connect(self.stop)

    def stop(self):
        self._stopped = True
        self.timer.stop()
        self._queued.clear()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def refresh(self):
        self._send({'command': 'status', 'client': 'wisland'}, poll=True)

    def command(self, command: str, **values):
        self._send({'command': command, 'client': 'wisland', **values})

    def connect_backend(self):
        """Explicit panel open may launch the single-instance host, never RF."""
        if self.state.get('ok'):
            self.command('attach')
            return
        if time.monotonic() - self._launch_at < 10:
            return
        executable = locate_runtime()
        if not executable.is_file():
            self._error(ValueError('未找到 AirDrop 接收程序，请检查 airdrop.executable 配置。'))
            return
        self._launch_at = time.monotonic()
        try:
            subprocess.Popen([str(executable), '--startup'], cwd=str(executable.parent),
                             creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
            self.state['message'] = '正在连接接收程序…'
            self.changed.emit(dict(self.state))
        except OSError as error:
            self._error(error)
        self.refresh()

    def _send(self, data: dict, poll=False):
        if self._stopped:
            return
        if self._busy:
            if not poll:
                self._queued.append(data)
            return
        self._busy = True
        def task():
            try:
                result = self.transport(data)
            except Exception as error:
                if not self._stopped:
                    self._failure.emit(error)
            else:
                if not self._stopped:
                    self._result.emit(result)
        self._pool.submit(task)

    def _next(self):
        self._busy = False
        if self._queued and not self._stopped:
            self._send(self._queued.pop(0))

    def _done(self, state):
        if self._stopped:
            return
        if not state.get('ok'):
            # Command errors should not discard the last truthful running state.
            self.state['message'] = state.get('error', '控制请求未完成')
            self.changed.emit(dict(self.state))
            self._next()
            return
        self.state = state
        requests = {r['id'] for r in state.get('requests', [])}
        new = requests - self._known
        self._known = requests
        self.changed.emit(dict(state))
        if new:
            self.request_received.emit()
        self._next()

    def _error(self, error):
        if self._stopped:
            return
        message = '接收程序未连接，请重新点击隔空投送磁贴' if isinstance(error, OSError) else str(error)
        self.state = {'ok': False, 'isRunning': False, 'isStarting': False, 'message': message, 'requests': []}
        self._known.clear()
        self.changed.emit(dict(self.state))
        self._next()
