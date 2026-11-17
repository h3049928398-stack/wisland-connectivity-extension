"""Application-owned Qt tests. No USB, BLE, desktop input, or configuration writes."""
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
import threading
import tempfile
from unittest import mock

BASE = Path(__file__).resolve().parents[1]
WISLAND_ROOT = Path(os.environ.get('WISLAND_ROOT', str(BASE.parent / 'wisland'))).resolve()
if not (WISLAND_ROOT / 'wisland').is_dir():
    raise RuntimeError('Set WISLAND_ROOT to the wisland source/install directory.')
sys.path.insert(0, str(WISLAND_ROOT))
ARTIFACTS = BASE / 'artifacts'
ARTIFACTS.mkdir(exist_ok=True)
ORIGINAL_SYSTEM = (BASE / 'tests/fixtures/wisland-system.original.py').read_bytes()
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6 import QtCore, QtWidgets, QtGui, QtTest
from wisland.core import bg
import wisland.services
import wisland.ui
wisland.services.__path__.insert(0, str(BASE / 'payload/services'))
wisland.ui.__path__.insert(0, str(BASE / 'payload/ui'))
from wisland.services.airdrop import AirDropService
from wisland.services import airdrop as control_module
from wisland.ui.airdrop import AirDropPanel
from wisland.ui.backdrop_filter import blur_frame, composite_widget
from wisland.ui.control_skin import GlassButton
from wisland.ui.theme import theme

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
# The offscreen plugin has no native Windows font database. Explicitly load
# system fonts for meaningful screenshots; the installed GUI uses Windows.
QtGui.QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'msyh.ttc'))
QtGui.QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'segoeui.ttf'))
QtGui.QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'segmdl2.ttf'))
bg.init()


class FakeService(QtCore.QObject):
    changed = QtCore.Signal(dict)
    request_received = QtCore.Signal()
    def __init__(self):
        super().__init__()
        self.state = {'ok': True, 'isRunning': False, 'deviceName': 'Windows PC', 'message': '接收已关闭', 'requests': []}
        self.calls = []
    def command(self, command, **values): self.calls.append((command, values))


class ControlSurface(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.island = SimpleNamespace(locks=set(), expand=lambda page: None)
        self._height = 220
        self.resize(620, 220)
        self.setObjectName('surface')
        self.setStyleSheet('#surface{background:#242731}')
    def preferred_height(self): return self._height
    def set_height(self, height):
        self._height = height
        self.resize(self.width(), height)


class ExtensionChecks(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        self.page = ControlSurface()
        self.panel = AirDropPanel(self.service, self.page)
        self.page.show()
    def tearDown(self):
        self.panel.close(immediate=True); self.page.close(); self.panel.deleteLater(); self.page.deleteLater()
        app.processEvents()
    def test_runtime_locator_private_config_and_explicit_override(self):
        with tempfile.TemporaryDirectory(prefix='connectivity-locator-') as directory:
            root = Path(directory)
            settings = root / 'data/extensions/connectivity.json'; settings.parent.mkdir(parents=True)
            receiver = root / 'companion/AirDrop.exe'
            settings.write_text(json.dumps({'airdropExecutable': str(receiver)}), encoding='utf-8')
            with mock.patch.object(control_module, 'ROOT', root), mock.patch.object(control_module, 'cfg', SimpleNamespace(get=lambda *a: '')):
                self.assertEqual(control_module.locate_runtime(), receiver)
                settings.write_text('[]', encoding='utf-8')
                self.assertEqual(control_module.locate_runtime(), root.parent / 'AirDrop-Windows/runtime/AirDrop/AirDrop.exe')
            with mock.patch.object(control_module, 'ROOT', root), mock.patch.object(control_module, 'cfg', SimpleNamespace(get=lambda *a: str(root / 'explicit/AirDrop.exe'))):
                self.assertEqual(control_module.locate_runtime(), root / 'explicit/AirDrop.exe')
    def test_choices_dispatch_real_control_commands(self):
        self.panel.everyone.click(); self.panel.off.click()
        self.assertEqual(self.service.calls, [('start', {}), ('stop', {})])
    def test_truthful_starting_and_countdown(self):
        self.panel.render({**self.service.state, 'isStarting': True, 'remainingSeconds': 599})
        self.assertFalse(self.panel.everyone.isEnabled())
        self.assertIn('09:59', self.panel.status.text())
        self.assertTrue(self.panel.off.isEnabled())
    def test_request_requires_explicit_id_and_acceptance(self):
        request = {'id': 'local-test', 'sender': '<iPhone>', 'files': ['photo.JPG']}
        self.panel.render({**self.service.state, 'requests': [request]})
        self.panel.accept.click()
        self.assertEqual(self.service.calls, [('respond', {'id': 'local-test', 'accept': True})])
        self.assertEqual(self.panel.request_text.textFormat(), QtCore.Qt.TextFormat.PlainText)
    def test_expired_request_disables_confirmation(self):
        self.panel.render({**self.service.state, 'requests': []})
        self.panel.respond(True)
        self.assertEqual(self.service.calls, [])
    def test_detail_buttons_all_keep_capsule_corners_in_interaction_states(self):
        self.assertEqual(len(self.panel.findChildren(QtWidgets.QAbstractButton)), 6)
        self.assertEqual(self.panel.findChildren(QtWidgets.QPushButton), [])
        self.service.state = {**self.service.state,
                              'requests': [{'id': 'corners-only', 'sender': 'iPhone', 'files': ['photo.JPG']}]}
        self.panel.present(); QtTest.QTest.qWait(330)
        for button in self.panel.buttons:
            self.assertIsInstance(button, GlassButton)
            for mode in ('light', 'dark'):
                theme.set_mode(mode)
                for state in ('normal', 'hover', 'pressed', 'disabled'):
                    button.setEnabled(state != 'disabled')
                    button._hovered = state == 'hover'
                    button.setDown(state == 'pressed')
                    frame = QtGui.QImage(button.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                    frame.fill(QtCore.Qt.GlobalColor.transparent)
                    p = QtGui.QPainter(frame)
                    button.render(p, QtCore.QPoint(), QtGui.QRegion(), QtWidgets.QWidget.RenderFlag.DrawChildren)
                    p.end()
                    self.assertEqual(frame.pixelColor(0, 0).alpha(), 0, (button.text(), mode, state))
                    self.assertEqual(frame.pixelColor(frame.width()-1, frame.height()-1).alpha(), 0, (button.text(), mode, state))
                    self.assertGreater(frame.pixelColor(frame.width()//2, frame.height()//2).alpha(), 0)
            button.setEnabled(True); button.setDown(False)
    def test_button_keyboard_selection_is_exclusive_and_disabled_does_not_dispatch(self):
        self.panel.present(); QtTest.QTest.qWait(330)
        self.panel.everyone.setFocus()
        for _ in range(2):
            QtTest.QTest.keyClick(self.panel.everyone, QtCore.Qt.Key.Key_Space)
            self.assertTrue(self.panel.everyone.isChecked())
            self.assertFalse(self.panel.off.isChecked())
        self.assertEqual(self.service.calls, [('start', {}), ('start', {})])
        self.panel.off.setEnabled(False)
        self.panel.off.click()
        self.assertEqual(len(self.service.calls), 2)
        self.panel.off.setEnabled(True); self.panel.off.click()
        self.assertTrue(self.panel.off.isChecked()); self.assertFalse(self.panel.everyone.isChecked())
        self.assertEqual(self.service.calls[-1], ('stop', {}))
    def test_all_six_buttons_fit_in_pending_request_layout_and_both_themes(self):
        self.service.state = {**self.service.state, 'isRunning': True, 'remainingSeconds': 599, 'message': '接收已开启',
                              'receiveDirectory': str(ARTIFACTS / 'fixture-received'),
                              'requests': [{'id': 'layout-only', 'sender': 'iPhone', 'files': ['photo.JPG']}]}
        for mode in ('light', 'dark'):
            theme.set_mode(mode)
            self.panel.present(); QtTest.QTest.qWait(450)
            for button in self.panel.buttons:
                self.assertTrue(button.isVisible(), button.text())
                self.assertGreaterEqual(button.text_rect().width(),
                                        QtGui.QFontMetrics(button.font()).horizontalAdvance(button.text()), button.text())
                self.assertTrue(self.panel.card.rect().contains(QtCore.QRect(
                    button.mapTo(self.panel.card, QtCore.QPoint()), button.size())), button.text())
            self.page.grab().save(str(ARTIFACTS / f'wisland-buttons-{mode}.png'))
            self.panel.close(immediate=True)
    def test_close_unlocks_island_without_stopping_receiving(self):
        self.panel.present(); app.processEvents()
        self.assertIn('airdrop', self.page.island.locks)
        self.panel.close(); QtTest.QTest.qWait(320)
        self.assertNotIn('airdrop', self.page.island.locks)
        self.assertEqual(self.service.calls, [])
    def test_offline_does_not_claim_receiver_enabled(self):
        self.panel.render({'ok': False, 'message': '未连接'})
        self.assertFalse(self.panel.everyone.isEnabled())
        self.assertTrue(self.panel.off.isChecked())
    def test_progress_and_completion(self):
        self.panel.render({**self.service.state, 'transfer': {'phase': 'receiving', 'bytes': 50, 'total': 100}})
        self.assertEqual(self.panel.progress.value(), 50)
        self.panel.render({**self.service.state, 'transfer': {'phase': 'received', 'lastFile': 'photo.JPG'}})
        self.assertIn('photo.JPG', self.panel.status.text())
    def test_control_stays_responsive_when_shared_pool_is_saturated(self):
        gate = threading.Event()
        barrier = threading.Barrier(9)
        def blocked_job():
            barrier.wait(timeout=3)
            gate.wait(timeout=3)
        jobs = [bg.run_bg(blocked_job) for _ in range(8)]
        barrier.wait(timeout=3)
        service = AirDropService(transport=lambda command: {'ok': True, 'message': 'responsive', 'requests': []})
        loop = QtCore.QEventLoop()
        service.changed.connect(lambda state: loop.quit())
        QtCore.QTimer.singleShot(1000, loop.quit)
        try:
            loop.exec()
            self.assertTrue(service.state.get('ok'))
        finally:
            service.stop(); gate.set()
            for job in jobs: job.result(timeout=4)
    def test_control_page_patch_builds_with_existing_controls(self):
        spec = importlib.util.spec_from_file_location('local_installer', BASE / 'install.py')
        installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
        original = ORIGINAL_SYSTEM
        source = installer.system_source(original)
        module = {'__name__': 'wisland.ui.pages.system', '__package__': 'wisland.ui.pages'}
        exec(compile(source, '<patched control page>', 'exec'), module)
        noop = SimpleNamespace(set_sysproxy=lambda *a: None, set_tun=lambda *a: None)
        ctx = SimpleNamespace(clash=noop)
        page = module['ControlsPage'](ctx)
        page.airdrop_service.stop()
        # These are layout fixtures, not hardware/transfer evidence.
        page.airdrop_service.state = dict(self.service.state)
        page._airdrop_state(page.airdrop_service.state)
        page.wifi.set_state(True, '已开启')
        page.bt.set_state(True, '打开')
        theme.set_mode('dark')
        page.setObjectName('testControlSurface')
        page.setStyleSheet('#testControlSurface{background:#242731;}')
        self.assertEqual(page.airdrop.title, '隔空投送')
        page.resize(620, 220); page.show(); app.processEvents()
        self.assertLessEqual(page.airdrop.mapTo(page, QtCore.QPoint(0, page.airdrop.height())).y(), page.rect().height())
        page.grab().save(str(ARTIFACTS / 'wisland-controls.png'))
        page.island = SimpleNamespace(locks=set(), expand=lambda p: None, page_size_changed=lambda: page.resize(620, page.preferred_height()))
        page.airdrop_panel.present(); QtTest.QTest.qWait(330)
        self.assertFalse(page.airdrop_panel.isWindow())
        self.assertIs(page.airdrop_panel.window(), page.window())
        self.assertTrue(page.airdrop_panel.rect().contains(page.airdrop_panel.card.geometry()))
        page.grab().save(str(ARTIFACTS / 'wisland-controls-expanded.png'))
        page.airdrop_panel.close(immediate=True); page.close(); page.deleteLater()
    def test_current_theme_layout_renders_without_overflow(self):
        output = ARTIFACTS
        for mode in ('light', 'dark'):
            theme.set_mode(mode)
            self.panel.render(self.service.state); self.panel.present(); QtTest.QTest.qWait(330)
            self.assertLessEqual(self.panel.height(), 620)
            self.assertFalse(self.panel.isWindow())
            self.assertTrue(self.panel.rect().contains(self.panel.card.geometry()))
            self.page.grab().save(str(output / f'wisland-airdrop-{mode}.png'))
            self.panel.close(immediate=True)
    def test_click_outside_and_escape_close_with_no_radio_command(self):
        for escape in (False, True):
            self.panel.present(); QtTest.QTest.qWait(300)
            if escape:
                self.panel.setFocus()
                QtTest.QTest.keyClick(self.panel, QtCore.Qt.Key.Key_Escape)
            else:
                QtTest.QTest.mouseClick(self.panel, QtCore.Qt.MouseButton.LeftButton, pos=QtCore.QPoint(12, 12))
            QtTest.QTest.qWait(320)
            self.assertFalse(self.panel.isVisible())
            self.assertEqual(self.page.preferred_height(), 220)
        self.assertEqual(self.service.calls, [])
    def test_reopening_does_not_create_any_secondary_window(self):
        for _ in range(3):
            self.panel.present(); QtTest.QTest.qWait(300)
            self.assertIs(self.panel.window(), self.page)
            self.assertNotIn(self.panel, app.topLevelWidgets())
            self.panel.close(immediate=True)
        self.assertEqual(self.page.island.locks, set())
    def test_parent_hiding_cleans_up_overlay_and_restores_page(self):
        self.panel.present(); QtTest.QTest.qWait(300)
        self.page.hide(); app.processEvents()
        self.assertEqual(self.page.preferred_height(), 220)
        self.assertNotIn('airdrop', self.page.island.locks)
        self.assertIsNone(self.panel._height_before)
    def test_request_during_close_reopens_same_embedded_card(self):
        self.panel.present(); QtTest.QTest.qWait(300)
        self.panel.close()
        self.panel.present(); QtTest.QTest.qWait(300)
        self.assertTrue(self.panel.isVisible())
        self.assertTrue(self.panel.body.isVisible())
        self.assertFalse(self.panel.isWindow())
        self.assertEqual(self.service.calls, [])
    def test_blur_preserves_dpr_and_uniform_edges(self):
        for dpr in (1, 1.5, 2):
            frame = QtGui.QImage(round(160 * dpr), round(100 * dpr), QtGui.QImage.Format.Format_RGB32)
            frame.setDevicePixelRatio(dpr); frame.fill(QtGui.QColor('#fafafa'))
            blurred = blur_frame(frame)
            self.assertEqual(blurred.size(), frame.size())
            self.assertEqual(blurred.devicePixelRatio(), dpr)
            for x, y in ((0, 0), (blurred.width()-1, 0), (0, blurred.height()-1),
                         (blurred.width()-1, blurred.height()-1), (blurred.width()//2, blurred.height()//2)):
                color = blurred.pixelColor(x, y)
                self.assertGreaterEqual(color.red(), 248)
                self.assertGreaterEqual(color.alpha(), 254)
    def test_blur_removes_sharp_pattern_without_affecting_live_widgets(self):
        frame = QtGui.QImage(320, 180, QtGui.QImage.Format.Format_RGB32)
        frame.fill(QtCore.Qt.GlobalColor.white)
        p = QtGui.QPainter(frame)
        for x in range(0, 320, 8): p.fillRect(x, 0, 4, 180, QtCore.Qt.GlobalColor.black)
        p.end()
        blurred = blur_frame(frame)
        samples = [blurred.pixelColor(x, 90).red() for x in range(60, 260)]
        self.assertLess(max(samples) - min(samples), 15)
        self.panel.present(); QtTest.QTest.qWait(450)
        for widget in (self.page, self.panel, self.panel.card, self.panel.body):
            self.assertIsNone(widget.graphicsEffect())
    def test_composite_and_overlay_prevent_sharp_content_bleeding_through(self):
        self.page.setStyleSheet('#surface{background:transparent}')
        background = QtWidgets.QLabel('Underlying sharp text', self.page)
        background.setGeometry(8, 80, 270, 40)
        background.setStyleSheet('color:white;font-size:23px')
        background.show(); app.processEvents()
        frame = composite_widget(self.page, self.page.island)
        self.assertEqual(min(frame.pixelColor(x, y).alpha() for x, y in
                             ((0, 0), (20, 90), (300, 100), (619, 219))), 255)
        self.panel.present(); QtTest.QTest.qWait(450)
        before = self.page.grab().toImage().copy(0, 50, 280, 100)
        # Alter the still-live widget beneath a settled overlay. The image must
        # not change until an explicit backdrop refresh supplies a new frame.
        self.panel._capture_timer.stop()
        background.setText('Completely different sharp text')
        app.processEvents()
        after = self.page.grab().toImage().copy(0, 50, 280, 100)
        self.assertEqual(before, after)
    def test_blur_recaptures_full_resized_page_and_releases_cache(self):
        self.panel.present(); QtTest.QTest.qWait(450)
        self.page.resize(690, 420); QtTest.QTest.qWait(210)
        self.assertEqual(self.panel._blurred.deviceIndependentSize().toSize(), self.page.size())
        self.assertEqual(self.panel.geometry(), self.page.rect())
        self.panel.close(immediate=True)
        self.assertTrue(self.panel._blurred.isNull())
        self.assertTrue(self.panel._original.isNull())
        self.assertFalse(self.panel._capture_timer.isActive())
    def test_transparent_surface_keeps_glass_instead_of_palette_rectangle(self):
        surface = QtWidgets.QWidget(); surface.resize(80, 60)
        palette = surface.palette(); palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor('magenta'))
        surface.setPalette(palette)
        backdrop = SimpleNamespace(state=None, brush_for=lambda *a: QtGui.QBrush(QtGui.QColor('#456789')))
        image = composite_widget(surface, SimpleNamespace(backdrop=backdrop))
        expected = QtGui.QImage(1, 1, QtGui.QImage.Format.Format_RGB32)
        expected.fill(QtGui.QColor('#456789'))
        p = QtGui.QPainter(expected)
        p.fillRect(expected.rect(), theme.tint_brush(QtCore.QRectF(surface.rect()))); p.end()
        self.assertEqual(image.pixelColor(40, 30), expected.pixelColor(0, 0))
        surface.deleteLater()
    def test_navigation_blurs_in_same_window_and_closes_with_panel(self):
        root = QtWidgets.QWidget(); root.resize(620, 440)
        nav = QtWidgets.QLabel('控制    媒体    设置', root); nav.setGeometry(0, 0, 620, 36)
        self.page.setParent(root); self.page.move(0, 40)
        self.page.island.nav = nav; self.page.island.content = root
        root.show(); self.page.show()
        try:
            self.panel.present(); QtTest.QTest.qWait(450)
            overlay = self.panel
            self.assertTrue(overlay.isVisible())
            self.assertFalse(overlay.isWindow())
            self.assertIs(overlay.window(), root)
            self.assertIs(overlay.parentWidget(), root)
            self.assertEqual(overlay._blurred.deviceIndependentSize().toSize(), root.size())
            QtTest.QTest.mouseClick(overlay, QtCore.Qt.MouseButton.LeftButton, pos=QtCore.QPoint(10, 10))
            QtTest.QTest.qWait(320)
            self.assertFalse(overlay.isVisible())
            self.assertTrue(overlay._blurred.isNull())
            self.assertFalse(self.panel.isVisible())
            self.assertEqual(self.service.calls, [])
            self.panel.present(); QtTest.QTest.qWait(450)
            root.hide(); app.processEvents()
            self.assertIsNone(self.panel._height_before)
            self.assertEqual(self.page.preferred_height(), 220)
            self.assertEqual(self.page.island.locks, set())
            self.assertFalse(self.panel._capture_timer.isActive())
        finally:
            self.panel.setParent(self.page); self.page.setParent(None)
            root.close(); root.deleteLater()
    def test_installer_refuses_unknown_existing_file_without_partial_write(self):
        spec = importlib.util.spec_from_file_location('guard_installer', BASE / 'install.py')
        installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
        original = ORIGINAL_SYSTEM
        with tempfile.TemporaryDirectory(prefix='wisland-install-') as directory:
            root = Path(directory)
            system = root / 'wisland/ui/pages/system.py'
            system.parent.mkdir(parents=True); system.write_bytes(original)
            unknown = root / 'wisland/ui/airdrop.py'; unknown.write_bytes(b'user-local-module')
            with self.assertRaises(RuntimeError): installer.install(root)
            self.assertEqual(system.read_bytes(), original)
            self.assertEqual(unknown.read_bytes(), b'user-local-module')
            self.assertFalse((root / 'data').exists())


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ExtensionChecks))
    sys.exit(not result.wasSuccessful())
