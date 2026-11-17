"""UI and service checks using fixtures only; no radio/connection changes."""
import ctypes
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
from check_extension import (app, BASE, ARTIFACTS, ControlSurface, FakeService, QtCore, QtGui, QtWidgets, QtTest, theme)
from wisland.ui.airdrop import AirDropPanel
from wisland.ui.connections import RadioPanel
from wisland.services import connectivity as native


NETWORK = dict(id='fixture-wifi', name='Home Wi-Fi', interface='11111111-1111-1111-1111-111111111111',
               adapter='Fixture adapter', ssid=b'Home Wi-Fi'.hex(), profile='', connected=False,
               signal=85, secure=True, auth=7, cipher=4, bss=1, connectable=True)


class FixtureConnections(QtCore.QObject):
    changed = QtCore.Signal(dict)
    def __init__(self):
        super().__init__(); self.calls = []
        self.state = dict(wifi=dict(items=[dict(NETWORK), dict(NETWORK, id='current', name='Current Wi-Fi', connected=True, profile='saved')], loading=False),
                          bt=dict(items=[dict(id='headset', name='Headphones', connected=True),
                                         dict(id='controller', name='Wireless Controller', connected=False)], loading=False))
    def refresh(self, kind, scan=False): self.calls.append(('refresh', kind, scan))
    def connect(self, key, password=None): self.calls.append(('connect', key, password))
    def disconnect(self, key): self.calls.append(('disconnect', key))


class RadioChecks(unittest.TestCase):
    def setUp(self):
        self.page = ControlSurface()
        self.radio = SimpleNamespace(state=dict(wifi_on=True, wifi_available=True, bt_on=True, bt_available=True))
        self.page.ctx = SimpleNamespace(radio=self.radio)
        self.page._radio = dict(self.radio.state); self.power_calls = []
        self.page._toggle = lambda kind: self.power_calls.append(kind)
        self.service = FixtureConnections()
        self.wifi = RadioPanel(self.service, self.page, 'wifi')
        self.bt = RadioPanel(self.service, self.page, 'bt')
        self.airdrop = AirDropPanel(FakeService(), self.page)
        self.page.show()

    def tearDown(self):
        for panel in (self.wifi, self.bt, self.airdrop):
            panel.close(immediate=True); panel.deleteLater()
        self.page.close(); self.page.deleteLater(); app.processEvents()

    def test_panels_switch_in_same_window_and_airdrop_request_preempts(self):
        for panel in (self.wifi, self.bt, self.airdrop, self.wifi):
            panel.present(); QtTest.QTest.qWait(320)
            self.assertIs(self.page._connection_layer, panel)
            self.assertEqual(sum(p.isVisible() for p in (self.wifi, self.bt, self.airdrop)), 1)
            self.assertFalse(panel.isWindow()); self.assertIs(panel.window(), self.page)
            self.assertTrue(panel.rect().contains(panel.card.geometry()))
        self.wifi.close(); self.airdrop.present(); QtTest.QTest.qWait(320)
        self.assertTrue(self.airdrop.isVisible()); self.assertFalse(self.wifi.isVisible())
        self.airdrop.close(immediate=True)
        self.assertEqual(self.page.preferred_height(), 220); self.assertEqual(self.page.island.locks, set())
        self.assertEqual(self.power_calls, [])

    def test_password_is_masked_and_clears_on_cancel_switch_and_parent_hide(self):
        for action in ('cancel', 'switch', 'hide'):
            self.page.show(); self.wifi.present(); QtTest.QTest.qWait(320)
            self.wifi._rows[0].click()
            self.assertEqual(self.wifi.password.echoMode(), QtWidgets.QLineEdit.EchoMode.Password)
            self.wifi.password.setText('fixture-secret')
            if action == 'cancel': self.wifi.cancel.click()
            elif action == 'switch': self.bt.present()
            else: self.page.hide(); app.processEvents()
            self.assertEqual(self.wifi.password.text(), '')
            self.assertFalse(any(call[0] == 'connect' for call in self.service.calls))
            self.wifi.close(immediate=True); self.bt.close(immediate=True)

    def test_selection_needs_explicit_connect_and_connected_network_needs_disconnect(self):
        self.wifi.present(); QtTest.QTest.qWait(320)
        self.wifi._rows[0].click()
        self.assertFalse(any(call[0] == 'connect' for call in self.service.calls))
        self.wifi.password.setText('fixture-password'); self.wifi.connect.click()
        self.assertIn(('connect', NETWORK['id'], 'fixture-password'), self.service.calls)
        self.assertEqual(self.wifi.password.text(), '')
        self.wifi._rows[1].click(); self.assertEqual(self.wifi.connect.text(), '断开连接')
        self.assertFalse(any(call[0] == 'disconnect' for call in self.service.calls))
        self.wifi.connect.click(); self.assertIn(('disconnect', 'current'), self.service.calls)

    def test_bluetooth_management_and_location_settings_route_truthfully(self):
        self.bt.present(); QtTest.QTest.qWait(320)
        self.bt._rows[1].click()
        self.assertIn('Windows', self.bt.selection.text())
        with mock.patch.object(QtGui.QDesktopServices, 'openUrl', return_value=True) as open_url:
            self.bt.connect.click(); self.assertEqual(open_url.call_args.args[0].toString(), 'ms-settings:bluetooth')
        self.service.state['wifi'].update(permissionRequired=True, items=[], message='需要位置权限')
        self.wifi.present(); QtTest.QTest.qWait(320)
        self.assertIn('位置', self.wifi.settings.text())
        with mock.patch.object(QtGui.QDesktopServices, 'openUrl', return_value=True) as open_url:
            self.wifi.settings.click(); self.assertEqual(open_url.call_args.args[0].toString(), 'ms-settings:privacy-location')

    def test_power_changes_only_on_explicit_power_button(self):
        self.wifi.present(); QtTest.QTest.qWait(320)
        self.assertEqual(self.power_calls, [])
        self.wifi.power.click(); self.assertEqual(self.power_calls, ['wifi'])

    def test_both_radio_layouts_and_password_form_fit_light_and_dark(self):
        for mode in ('light', 'dark'):
            theme.set_mode(mode)
            for panel, name in ((self.wifi, 'wifi'), (self.bt, 'bluetooth')):
                panel.present(); QtTest.QTest.qWait(450)
                self.assertTrue(panel.rect().contains(panel.card.geometry()))
                for button in panel.buttons:
                    if button.isVisible():
                        self.assertGreaterEqual(button.text_rect().width(), QtGui.QFontMetrics(button.font()).horizontalAdvance(button.text()))
                self.page.grab().save(str(ARTIFACTS / f'wisland-{name}-{mode}.png'))
                panel.close(immediate=True)
            self.wifi.present(); QtTest.QTest.qWait(320); self.wifi._rows[0].click(); app.processEvents()
            self.assertTrue(self.wifi.card.rect().contains(QtCore.QRect(self.wifi.form.mapTo(self.wifi.card, QtCore.QPoint()), self.wifi.form.size())))
            self.page.grab().save(str(ARTIFACTS / f'wisland-wifi-password-{mode}.png'))
            self.wifi.close(immediate=True)


class ServiceChecks(unittest.TestCase):
    def test_native_structure_layout_matches_windows_abi(self):
        self.assertEqual(ctypes.sizeof(native.GUID), 16)
        self.assertEqual(ctypes.sizeof(native.Interface), 532)
        self.assertEqual(ctypes.sizeof(native.AvailableNetwork), 628)
        self.assertEqual(native.AvailableNetwork.flags.offset, 620)
        self.assertEqual(ctypes.sizeof(native.ConnectionParameters), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 24)

    def test_temporary_password_profile_escapes_xml_and_rejects_unsupported_auth(self):
        password = 'fixture<&"password'
        xml = native.temporary_profile(NETWORK, password)
        root = ET.fromstring(xml); ns = {'w': 'http://www.microsoft.com/networking/WLAN/profile/v1'}
        self.assertEqual(root.find('.//w:keyMaterial', ns).text, password)
        self.assertEqual(root.find('.//w:SSID/w:hex', ns).text, NETWORK['ssid'])
        with self.assertRaises(ValueError): native.temporary_profile(NETWORK, 'short')
        with self.assertRaises(ValueError): native.temporary_profile(dict(NETWORK, auth=6), password)

    def test_worker_password_stays_off_command_line_and_has_timeout(self):
        with mock.patch.object(native.subprocess, 'run', return_value=SimpleNamespace(stdout='{"ok":true,"data":{}}')) as run:
            native.worker_call('connect', {'network': NETWORK, 'password': 'fixture-secret'})
            self.assertNotIn('fixture-secret', str(run.call_args.args))
            self.assertIn('fixture-secret', run.call_args.kwargs['input'])
            self.assertEqual(run.call_args.kwargs['timeout'], 20)
            self.assertEqual(run.call_args.kwargs['creationflags'], 0x08000000)

    def test_stale_selection_permission_and_pending_are_not_false_success(self):
        calls = []
        service = native.ConnectivityService(wifi_reader=lambda scan: {'items': [dict(NETWORK)]}, bt_reader=lambda: {'items': []},
                                             connector=lambda network, password: calls.append(network['id']) or
                                             {'pending': network['id'], 'expectConnected': True, 'message': '正在连接…'})
        try:
            service.connect('stale', 'fixture-password'); self.assertEqual(calls, [])
            service.state['wifi']['items'] = [dict(NETWORK)]
            service.connect(NETWORK['id'], 'fixture-password')
            for _ in range(50):
                if not service.state['wifi']['loading']: break
                QtTest.QTest.qWait(20)
            self.assertEqual(calls, [NETWORK['id']])
            self.assertFalse(service.state['wifi']['items'][0]['connected'])
            self.assertIn('正在', service.state['wifi']['message'])
            service.readers['wifi'] = lambda scan: {'items': [dict(NETWORK, connected=True)]}
            service.refresh('wifi')
            for _ in range(50):
                if not service.state['wifi']['loading']: break
                QtTest.QTest.qWait(20)
            self.assertNotIn('pending', service.state['wifi']); self.assertEqual(service.state['wifi']['message'], '连接已建立')
            service._failed('wifi', native.NativeError(5))
            self.assertTrue(service.state['wifi']['permissionRequired']); self.assertEqual(service.state['wifi']['items'], [])
        finally:
            service.stop()


if __name__ == '__main__':
    unittest.main(verbosity=2)
