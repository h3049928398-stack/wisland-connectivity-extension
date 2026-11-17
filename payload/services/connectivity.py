"""Native Windows network list and paired Bluetooth devices; no shell commands.

Wi-Fi actions run only after an explicit UI action. Passwords are used for a
temporary Windows profile, never logged or saved by this extension.
"""
from __future__ import annotations
import asyncio
import ctypes as C
from ctypes import wintypes as W
from concurrent.futures import ThreadPoolExecutor
import uuid
import time
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
from PySide6 import QtCore


class NativeError(Exception):
    def __init__(self, code):
        self.code = int(code)
        super().__init__(f'Windows 无线接口返回错误 {self.code}')


class GUID(C.Structure):
    _fields_ = [('data', C.c_ubyte * 16)]
    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)
    def __str__(self):
        return str(uuid.UUID(bytes_le=bytes(self)))


class SSID(C.Structure):
    _fields_ = [('length', W.DWORD), ('bytes', C.c_ubyte * 32)]


class Interface(C.Structure):
    _fields_ = [('guid', GUID), ('description', W.WCHAR * 256), ('state', W.DWORD)]


class AvailableNetwork(C.Structure):
    _fields_ = [('profile', W.WCHAR * 256), ('ssid', SSID), ('bss', W.DWORD),
                ('bssid_count', W.DWORD), ('connectable', W.BOOL), ('reason', W.DWORD),
                ('phy_count', W.DWORD), ('phys', W.DWORD * 8), ('more_phy', W.BOOL),
                ('signal', W.DWORD), ('secure', W.BOOL), ('auth', W.DWORD),
                ('cipher', W.DWORD), ('flags', W.DWORD), ('reserved', W.DWORD)]


class ConnectionParameters(C.Structure):
    _fields_ = [('mode', W.DWORD), ('profile', W.LPCWSTR), ('ssid', C.POINTER(SSID)),
                ('bssids', C.c_void_p), ('bss', W.DWORD), ('flags', W.DWORD)]


class WlanClient:
    def __init__(self):
        self.api = C.WinDLL('wlanapi')
        signatures = {
            'WlanOpenHandle': ([W.DWORD, C.c_void_p, C.POINTER(W.DWORD), C.POINTER(W.HANDLE)], W.DWORD),
            'WlanCloseHandle': ([W.HANDLE, C.c_void_p], W.DWORD),
            'WlanEnumInterfaces': ([W.HANDLE, C.c_void_p, C.POINTER(C.c_void_p)], W.DWORD),
            'WlanGetAvailableNetworkList': ([W.HANDLE, C.POINTER(GUID), W.DWORD, C.c_void_p, C.POINTER(C.c_void_p)], W.DWORD),
            'WlanScan': ([W.HANDLE, C.POINTER(GUID), C.c_void_p, C.c_void_p, C.c_void_p], W.DWORD),
            'WlanConnect': ([W.HANDLE, C.POINTER(GUID), C.POINTER(ConnectionParameters), C.c_void_p], W.DWORD),
            'WlanDisconnect': ([W.HANDLE, C.POINTER(GUID), C.c_void_p], W.DWORD),
            'WlanFreeMemory': ([C.c_void_p], None),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.api, name); fn.argtypes = args; fn.restype = result
        self.handle = W.HANDLE()

    @staticmethod
    def check(code):
        if code:
            raise NativeError(code)

    def __enter__(self):
        version = W.DWORD()
        self.check(self.api.WlanOpenHandle(2, None, C.byref(version), C.byref(self.handle)))
        return self

    def __exit__(self, *_):
        self.api.WlanCloseHandle(self.handle, None)

    def _list(self, pointer, record, limit):
        count = W.DWORD.from_address(pointer.value).value
        if count > limit:
            raise ValueError('Windows 返回的列表大小无效')
        address = pointer.value + 8
        return [record.from_buffer_copy(C.string_at(address + n * C.sizeof(record), C.sizeof(record)))
                for n in range(count)]

    def interfaces(self):
        pointer = C.c_void_p()
        self.check(self.api.WlanEnumInterfaces(self.handle, None, C.byref(pointer)))
        try:
            return self._list(pointer, Interface, 64)
        finally:
            self.api.WlanFreeMemory(pointer)

    def networks(self, interface):
        pointer = C.c_void_p()
        self.check(self.api.WlanGetAvailableNetworkList(self.handle, C.byref(interface.guid), 2, None, C.byref(pointer)))
        try:
            return self._list(pointer, AvailableNetwork, 4096)
        finally:
            self.api.WlanFreeMemory(pointer)


def wifi_networks(scan=False):
    items, errors = {}, []
    with WlanClient() as client:
        interfaces = client.interfaces()
        for interface in interfaces:
            try:
                if scan:
                    client.check(client.api.WlanScan(client.handle, C.byref(interface.guid), None, None, None))
                for network in client.networks(interface):
                    raw = bytes(network.ssid.bytes[:min(network.ssid.length, 32)])
                    if not raw:
                        continue
                    key = f'{interface.guid}:{raw.hex()}:{network.auth}'
                    entry = dict(id=key, interface=str(interface.guid), adapter=interface.description,
                                 name=raw.decode('utf-8', 'replace'), ssid=raw.hex(), profile=network.profile,
                                 connected=bool(network.flags & 1), signal=int(network.signal),
                                 secure=bool(network.secure), auth=int(network.auth), cipher=int(network.cipher),
                                 bss=int(network.bss), connectable=bool(network.connectable))
                    # Prefer the current/saved profile when Windows lists the
                    # same SSID with more than one profile on an interface.
                    old = items.get(key)
                    if old is None or (entry['connected'], bool(entry['profile'])) > (old['connected'], bool(old['profile'])):
                        items[key] = entry
            except NativeError as error:
                errors.append(error.code)
    if errors and not items:
        raise NativeError(errors[0])
    return dict(items=sorted(items.values(), key=lambda n: (not n['connected'], -n['signal'], n['name'])),
                available=bool(interfaces), scanRequested=scan, permissionRequired=False)


def temporary_profile(network, password):
    secure = network['secure']
    auth = {4: 'WPAPSK', 7: 'WPA2PSK'}.get(network['auth']) if secure else 'open'
    if auth is None:
        raise ValueError('这种安全类型请在 Windows 无线设置中连接')
    if secure and not (8 <= len(password or '') <= 63 or
                       len(password or '') == 64 and all(c in '0123456789abcdefABCDEF' for c in password)):
        raise ValueError('请输入 8–63 位密码，或 64 位十六进制密钥')
    root = ET.Element('WLANProfile', xmlns='http://www.microsoft.com/networking/WLAN/profile/v1')
    ET.SubElement(root, 'name').text = 'wisland-' + network['ssid']
    ssid_config = ET.SubElement(root, 'SSIDConfig')
    ssid = ET.SubElement(ssid_config, 'SSID'); ET.SubElement(ssid, 'hex').text = network['ssid']
    ET.SubElement(root, 'connectionType').text = 'ESS'
    ET.SubElement(root, 'connectionMode').text = 'manual'
    security = ET.SubElement(ET.SubElement(root, 'MSM'), 'security')
    encryption = ET.SubElement(security, 'authEncryption')
    ET.SubElement(encryption, 'authentication').text = auth
    ET.SubElement(encryption, 'encryption').text = ('TKIP' if network['cipher'] == 2 else 'AES') if secure else 'none'
    ET.SubElement(encryption, 'useOneX').text = 'false'
    if secure:
        key = ET.SubElement(security, 'sharedKey')
        ET.SubElement(key, 'keyType').text = 'networkKey' if len(password) == 64 else 'passPhrase'
        ET.SubElement(key, 'protected').text = 'false'; ET.SubElement(key, 'keyMaterial').text = password
    return ET.tostring(root, encoding='unicode')


def wifi_connect(network, password=None):
    if not network.get('connectable') or network.get('bss') != 1:
        raise ValueError('这个网络目前不能直接连接，请刷新或使用系统设置')
    profile = network.get('profile')
    mode = 0 if profile else 1
    if not profile:
        profile = temporary_profile(network, password)
    params = ConnectionParameters(mode, profile, None, None, network['bss'], 0)
    guid = GUID.parse(network['interface'])
    with WlanClient() as client:
        client.check(client.api.WlanConnect(client.handle, C.byref(guid), C.byref(params), None))
    # WlanConnect only accepts a request. The next query must confirm success.
    return dict(message='正在连接…', pending=network['id'], expectConnected=True)


def wifi_disconnect(network):
    guid = GUID.parse(network['interface'])
    with WlanClient() as client:
        client.check(client.api.WlanDisconnect(client.handle, C.byref(guid), None))
    return dict(message='正在断开…', pending=network['id'], expectConnected=False)


async def _bluetooth_devices():
    from winrt.windows.devices.enumeration import DeviceInformation
    from winrt.windows.devices.bluetooth import BluetoothDevice, BluetoothLEDevice
    from winrt.system import unbox_boolean, unbox_string
    properties = ['System.Devices.Aep.IsConnected', 'System.Devices.Aep.DeviceAddress']
    items = {}
    for api, transport in ((BluetoothDevice, '经典蓝牙'), (BluetoothLEDevice, '低功耗蓝牙')):
        devices = await DeviceInformation.find_all_async_aqs_filter_and_additional_properties(
            api.get_device_selector_from_pairing_state(True), properties)
        for info in devices:
            props = info.properties
            raw_address = props.get('System.Devices.Aep.DeviceAddress')
            address = unbox_string(raw_address) if raw_address is not None and not isinstance(raw_address, str) else raw_address or ''
            raw_connected = props.get('System.Devices.Aep.IsConnected')
            connected = unbox_boolean(raw_connected) if raw_connected is not None and not isinstance(raw_connected, bool) else raw_connected
            entry = dict(id=info.id, name=info.name or '蓝牙设备', paired=True,
                         connected=connected, transport=transport)
            key = address.casefold().replace(':', '').replace('-', '') or info.id
            old = items.get(key)
            if old is None or entry['connected'] and not old['connected']:
                items[key] = entry
    return dict(items=sorted(items.values(), key=lambda n: (not n['connected'], n['name'].casefold())))


def bluetooth_devices():
    async def bounded():
        return await asyncio.wait_for(_bluetooth_devices(), timeout=15)
    return asyncio.run(bounded())


def worker_call(operation, payload):
    """Bound native calls, including an unresponsive Windows RPC provider."""
    python = Path(sys.executable).with_name('python.exe')
    result = subprocess.run([str(python), '-B', str(Path(__file__).resolve()), '--worker', operation],
                            input=json.dumps(payload, ensure_ascii=False), encoding='utf-8',
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
                            creationflags=0x08000000)
    if len(result.stdout) > 4 * 1024 * 1024:
        raise ValueError('系统返回的设备列表过大')
    try:
        reply = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise ValueError('暂时无法读取 Windows 设备列表，请刷新') from None
    if not reply.get('ok'):
        if reply.get('code') is not None: raise NativeError(reply['code'])
        raise ValueError(reply.get('message', '系统操作失败，请重试'))
    return reply['data']


class ConnectivityService(QtCore.QObject):
    changed = QtCore.Signal(dict)
    _result = QtCore.Signal(str, object)
    _error = QtCore.Signal(str, object)

    def __init__(self, parent=None, wifi_reader=None, bt_reader=None,
                 connector=None, disconnector=None):
        super().__init__(parent)
        self.state = {kind: dict(items=[], loading=False, message='') for kind in ('wifi', 'bt')}
        self.readers = {'wifi': wifi_reader or (lambda scan: worker_call('wifi', {'scan': scan})),
                        'bt': bt_reader or (lambda: worker_call('bt', {}))}
        self.connector = connector or (lambda network, password: worker_call('connect', {'network': network, 'password': password}))
        self.disconnector = disconnector or (lambda network: worker_call('disconnect', {'network': network}))
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='connections')
        self._busy = set(); self._stopped = False
        self._deadlines = {}
        self._result.connect(self._done, QtCore.Qt.ConnectionType.QueuedConnection)
        self._error.connect(self._failed, QtCore.Qt.ConnectionType.QueuedConnection)
        app = QtCore.QCoreApplication.instance()
        if app:
            app.aboutToQuit.connect(self.stop)

    def stop(self):
        self._stopped = True; self._pool.shutdown(wait=False, cancel_futures=True)

    def _submit(self, kind, fn, *args):
        if self._stopped or kind in self._busy:
            return False
        self._busy.add(kind)
        self.state[kind].update(loading=True, message='')
        self.changed.emit(self.state)
        def work():
            try:
                result = fn(*args)
                if not self._stopped: self._result.emit(kind, result)
            except Exception as error:
                if not self._stopped:
                    try: self._error.emit(kind, error)
                    except RuntimeError: pass
        self._pool.submit(work)
        return True

    def refresh(self, kind, scan=False):
        self._submit(kind, self.readers[kind], *([scan] if kind == 'wifi' else []))

    def connect(self, key, password=None):
        item = next((n for n in self.state['wifi']['items'] if n['id'] == key), None)
        if item is None:
            self.state['wifi']['message'] = '网络列表已变化，请刷新后重试'
            self.changed.emit(self.state); return
        self._submit('wifi', self.connector, dict(item), password)

    def disconnect(self, key):
        item = next((n for n in self.state['wifi']['items'] if n['id'] == key and n.get('connected')), None)
        if item:
            self._submit('wifi', self.disconnector, dict(item))

    def _done(self, kind, result):
        if self._stopped: return
        self._busy.discard(kind)
        current = self.state[kind]
        if result.get('pending'):
            self._deadlines[kind] = time.monotonic() + 20
        if 'items' in result and current.get('pending'):
            key = current['pending']; expected = current.get('expectConnected', True)
            connected = any(n['id'] == key and n.get('connected') for n in result['items'])
            if connected == expected:
                result['message'] = '连接已建立' if expected else '已断开连接'
                current.pop('pending', None)
            elif time.monotonic() >= self._deadlines.get(kind, 0):
                result['message'] = '尚未完成，请检查密码或网络后重试'
                current.pop('pending', None)
            else:
                result['message'] = '正在连接…' if expected else '正在断开…'
        self.state[kind].update(result, loading=False)
        self.changed.emit(self.state)
        if self.state[kind].get('pending') or result.get('scanRequested'):
            QtCore.QTimer.singleShot(2500, lambda: self.refresh(kind) if not self._stopped else None)

    def _failed(self, kind, error):
        if self._stopped: return
        self._busy.discard(kind)
        permission = isinstance(error, NativeError) and error.code == 5
        message = 'Windows 需要位置权限才能显示附近网络，请在位置设置中允许后刷新。' if permission else (
            str(error) if isinstance(error, (NativeError, ValueError)) else '暂时无法读取设备，请刷新或打开系统设置。')
        self.state[kind].update(loading=False, message=message, permissionRequired=permission)
        if permission:
            self.state[kind]['items'] = []
        self.changed.emit(self.state)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        if len(sys.argv) != 3 or sys.argv[1] != '--worker': raise ValueError('无效的操作')
        raw = sys.stdin.buffer.read(16385)
        if len(raw) > 16384: raise ValueError('请求过大')
        request = json.loads(raw.decode('utf-8'))
        operation = sys.argv[2]
        if operation == 'wifi': data = wifi_networks(bool(request.get('scan')))
        elif operation == 'bt': data = bluetooth_devices()
        elif operation == 'connect': data = wifi_connect(request['network'], request.get('password'))
        elif operation == 'disconnect': data = wifi_disconnect(request['network'])
        else: raise ValueError('无效的操作')
        reply = dict(ok=True, data=data)
    except Exception as error:
        reply = dict(ok=False, code=error.code if isinstance(error, NativeError) else None,
                     message=str(error) if isinstance(error, (ValueError, NativeError)) else '系统设备操作暂时不可用')
    print(json.dumps(reply, ensure_ascii=False))
