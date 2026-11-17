"""Wi-Fi and Bluetooth details in the same glass island as AirDrop."""
from PySide6 import QtCore, QtGui, QtWidgets
from .theme import theme, ui_font, W
from .control_skin import GlassButton, draw_symbol
from .detail_layer import DetailLayer, ConnectionSymbol
from .widgets import ScrollArea

Qt = QtCore.Qt


class ConnectionRow(GlassButton):
    def __init__(self, kind, item):
        super().__init__(item['name'], height=58, choice=True)
        self.kind, self.item = kind, item
        self.setChecked(item.get('connected') is True)
        self.setToolTip(item['name'])
        if kind == 'wifi':
            self.subtitle = ('已连接' if item.get('connected') else '已保存' if item.get('profile') else
                             '需要密码' if item.get('secure') else '开放网络') + f" · {item.get('signal', 0)}%"
        else:
            self.subtitle = '已连接' if item.get('connected') is True else '未连接' if item.get('connected') is False else '状态待确认'
        self.setAccessibleDescription(self.subtitle)

    def draw_label(self, painter, alignment):
        color = QtGui.QColor('white') if self.isChecked() else theme.text()
        draw_symbol(painter, self.kind, QtCore.QRectF(13, 20, 18, 18), color)
        text_rect = QtCore.QRectF(41, 8, self.width() - 82, 21)
        painter.setFont(ui_font(12.5, W.Medium)); painter.setPen(color)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter,
                         QtGui.QFontMetrics(painter.font()).elidedText(self.text(), Qt.TextElideMode.ElideRight, int(text_rect.width())))
        painter.setFont(ui_font(10.5)); painter.setPen(QtGui.QColor(255, 255, 255, 205) if self.isChecked() else theme.text2())
        painter.drawText(text_rect.translated(0, 21), Qt.AlignmentFlag.AlignVCenter, self.subtitle)


class RadioPanel(DetailLayer):
    def __init__(self, service, page, kind):
        self.service = service
        super().__init__(page, kind)
        self.radio = getattr(page.ctx, 'radio', None)
        self._radio_state = dict(getattr(self.radio, 'state', {}))
        self._selected = None; self._signature = None
        self._rows = []; self._power_pending = False
        layout = QtWidgets.QVBoxLayout(self.body)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(8)
        header = QtWidgets.QHBoxLayout(); header.setSpacing(10)
        header.addWidget(ConnectionSymbol(kind))
        header.addWidget(self.label('无线局域网' if kind == 'wifi' else '蓝牙', 17, W.DemiBold), 1)
        self.close_button = GlassButton('收起', height=32); self.close_button.setFixedWidth(60)
        self.close_button.clicked.connect(self.close); header.addWidget(self.close_button)
        layout.addLayout(header)
        self.power = GlassButton('正在读取…', height=36); self.power.clicked.connect(self.toggle_power)
        layout.addWidget(self.power)
        self.status = self.label('', 11); self.status.setWordWrap(True); self.status.setMaximumHeight(66)
        layout.addWidget(self.status)
        self.scroll = ScrollArea(); self.scroll.setFixedHeight(184)
        self.list_body = self.scroll.inner
        self.list_layout = QtWidgets.QVBoxLayout(self.list_body)
        self.list_layout.setContentsMargins(0, 0, 3, 0); self.list_layout.setSpacing(7)
        layout.addWidget(self.scroll)
        self.form = QtWidgets.QWidget()
        form_layout = QtWidgets.QVBoxLayout(self.form); form_layout.setContentsMargins(0, 0, 0, 0); form_layout.setSpacing(7)
        self.selection = self.label('', 11); self.selection.setWordWrap(True); self.selection.setMaximumHeight(42)
        form_layout.addWidget(self.selection)
        self.password = QtWidgets.QLineEdit(); self.password.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText('输入网络密码'); self.password.setFixedHeight(34)
        self.password.setMaxLength(64)
        self.password.setInputMethodHints(Qt.InputMethodHint.ImhSensitiveData | Qt.InputMethodHint.ImhNoPredictiveText)
        self.password.returnPressed.connect(self.submit)
        form_layout.addWidget(self.password)
        self.cancel = GlassButton('取消', height=34); self.cancel.clicked.connect(self.hide_form)
        self.connect = GlassButton('连接', height=34, primary=True); self.connect.clicked.connect(self.submit)
        actions = QtWidgets.QHBoxLayout(); actions.addWidget(self.cancel); actions.addWidget(self.connect)
        form_layout.addLayout(actions); layout.addWidget(self.form); self.form.hide()
        footer = QtWidgets.QHBoxLayout()
        self.refresh_button = GlassButton('刷新', height=32)
        self.refresh_button.clicked.connect(lambda: self.service.refresh(kind, scan=kind == 'wifi'))
        self.settings = GlassButton('无线设置…' if kind == 'wifi' else '蓝牙设置…', height=32)
        self.settings.clicked.connect(self.open_settings)
        footer.addWidget(self.refresh_button); footer.addWidget(self.settings); layout.addLayout(footer)
        self.buttons = (self.close_button, self.power, self.cancel, self.connect, self.refresh_button, self.settings)
        self.poll = QtCore.QTimer(self, interval=6000, timeout=lambda: self.service.refresh(kind))
        service.changed.connect(self.render)
        if self.radio and hasattr(self.radio, 'changed'):
            self.radio.changed.connect(self.update_radio)
        self.restyle(); self.render(service.state)

    def restyle(self):
        fg = theme.text().name()
        self.setStyleSheet(f'QLabel{{color:{fg};background:transparent}}'
                           f'QLineEdit{{color:{fg};background:rgba(128,128,128,30);border:1px solid rgba(128,128,128,80);border-radius:16px;padding:0 12px}}')
        self.update(); self.card.update(); self.refresh_backdrop()

    def present(self):
        self._radio_state = dict(getattr(self.radio, 'state', None) or getattr(self.page, '_radio', self._radio_state))
        super().present()
        self.poll.start(); self.service.refresh(self.kind)

    def _settled(self):
        super()._settled()
        if not self._opening:
            self.poll.stop(); self.password.clear(); self._selected = None
            self.form.hide(); self.scroll.setFixedHeight(184)

    def update_radio(self, state):
        self._radio_state = dict(state); self._power_pending = False
        self.render(self.service.state)

    def render(self, state):
        data = state.get(self.kind, {})
        on = bool(self._radio_state.get(self.kind + '_on'))
        available = bool(self._radio_state.get(self.kind + '_available'))
        loading = data.get('loading', False)
        title = 'Wi-Fi' if self.kind == 'wifi' else '蓝牙'
        self.power.setText(('关闭' if on else '打开') + title)
        self.power.setEnabled(available and not self._power_pending)
        self.refresh_button.setEnabled(on and not loading)
        self.connect.setEnabled(on and not loading)
        self.settings.setText('位置设置…' if data.get('permissionRequired') else '无线设置…' if self.kind == 'wifi' else '蓝牙设置…')
        message = data.get('message') or ('正在读取列表…' if loading else title + ('已开启' if on else '已关闭'))
        if not available:
            message = '未检测到可用的' + title + '，可打开系统设置检查。'
        self.status.setText(message)
        items = data.get('items', []) if on else []
        signature = tuple((i['id'], i['name'], i.get('connected'), i.get('signal'), i.get('profile')) for i in items)
        if signature != self._signature:
            position = self.scroll.verticalScrollBar().value()
            self._signature = signature; self._rows = []
            while self.list_layout.count():
                child = self.list_layout.takeAt(0).widget()
                if child: child.hide(); child.deleteLater()
            for item in items[:100]:
                row = ConnectionRow(self.kind, item)
                row.clicked.connect(lambda checked=False, item=item, row=row: self.select(item, row))
                self.list_layout.addWidget(row); self._rows.append(row)
            if not items:
                empty = self.label('没有可显示的网络' if self.kind == 'wifi' else '没有已配对的设备', 11)
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter); empty.setMinimumHeight(68)
                self.list_layout.addWidget(empty)
            self.list_layout.addStretch(1)
            self.scroll.verticalScrollBar().setValue(position)
        for row in self._rows:
            row.setEnabled(on and not loading)
        if self.isVisible() and self._animation.state() != QtCore.QAbstractAnimation.State.Running:
            self._fit()

    def select(self, item, row):
        row.setChecked(item.get('connected') is True)
        self._selected = dict(item); self.password.clear()
        connected = item.get('connected') is True
        needs_password = self.kind == 'wifi' and not connected and not item.get('profile') and item.get('secure') and item.get('auth') in (4, 7)
        self.password.setVisible(bool(needs_password))
        self.selection.setText(item['name'][:120] + ('\n连接、断开和配对请在 Windows 蓝牙设置中完成。' if self.kind == 'bt' else ''))
        self.connect.setText('系统中管理' if self.kind == 'bt' else '断开连接' if connected else
                             '系统中连接' if item.get('secure') and not item.get('profile') and item.get('auth') not in (4, 7) else '连接')
        self.form.show(); self.scroll.setFixedHeight(100)
        if self.isVisible(): self._fit()
        if needs_password: self.password.setFocus()

    def hide_form(self):
        self.password.clear(); self._selected = None; self.form.hide(); self.scroll.setFixedHeight(184)
        if self.isVisible(): self._fit()

    def submit(self):
        item = self._selected
        if item is None or not self.connect.isEnabled(): return
        if self.kind == 'bt' or self.connect.text() == '系统中连接':
            self.open_settings(); return
        if item.get('connected'):
            self.service.disconnect(item['id'])
        else:
            self.service.connect(item['id'], self.password.text())
        self.hide_form()

    def toggle_power(self):
        if not self.power.isEnabled(): return
        self._power_pending = True; self.power.setEnabled(False)
        self.page._toggle(self.kind)
        def finished():
            self._power_pending = False
            self.update_radio(getattr(self.radio, 'state', self._radio_state))
            if self.isVisible(): self.service.refresh(self.kind)
        QtCore.QTimer.singleShot(2500, finished)

    def open_settings(self):
        permission = self.service.state.get(self.kind, {}).get('permissionRequired')
        target = 'privacy-location' if permission else 'network-wifi' if self.kind == 'wifi' else 'bluetooth'
        QtGui.QDesktopServices.openUrl(QtCore.QUrl('ms-settings:' + target))
