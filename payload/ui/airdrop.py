"""AirDrop receive UI, using the common internal connection detail layer."""
from PySide6 import QtCore, QtGui, QtWidgets
from .theme import theme, W
from .control_skin import GlassButton
from .detail_layer import DetailLayer, ConnectionSymbol

Qt = QtCore.Qt


class AirDropPanel(DetailLayer):
    def __init__(self, service, page):
        self.service = service
        super().__init__(page, 'airdrop')
        self._request_id = None
        layout = QtWidgets.QVBoxLayout(self.body)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(9)
        header = QtWidgets.QHBoxLayout(); header.setSpacing(10)
        header.addWidget(ConnectionSymbol())
        titles = QtWidgets.QVBoxLayout(); titles.setSpacing(2)
        titles.addWidget(self.label('隔空投送', 18, W.DemiBold))
        self.name = self.label('AirDrop', 11)
        titles.addWidget(self.name); header.addLayout(titles, 1)
        self.close_button = GlassButton('收起', height=32)
        self.close_button.setAccessibleName('收起隔空投送')
        self.close_button.setFixedWidth(60)
        self.close_button.clicked.connect(self.close)
        header.addWidget(self.close_button)
        layout.addLayout(header)
        self.status = self.label('正在连接…', 11)
        self.status.setWordWrap(True); self.status.setMaximumHeight(58)
        layout.addWidget(self.status)
        self.off = GlassButton('接收关闭', height=44, choice=True)
        self.everyone = GlassButton('所有人，10 分钟', height=44, choice=True)
        self.choices = QtWidgets.QButtonGroup(self)
        self.choices.setExclusive(True)
        for button in (self.off, self.everyone):
            self.choices.addButton(button)
            layout.addWidget(button)
        self.off.clicked.connect(lambda: self.service.command('stop'))
        self.everyone.clicked.connect(lambda: self.service.command('start'))
        self.hint = self.label('附近的 iPhone 可通过分享菜单发送文件。\n每次接收都会征求你的同意。', 10.5)
        self.hint.setWordWrap(True); layout.addWidget(self.hint)
        self.request_card = QtWidgets.QWidget()
        request_layout = QtWidgets.QVBoxLayout(self.request_card)
        request_layout.setContentsMargins(0, 3, 0, 0)
        self.request_text = self.label('', 12)
        self.request_text.setWordWrap(True); self.request_text.setMaximumHeight(100)
        request_layout.addWidget(self.request_text)
        actions = QtWidgets.QHBoxLayout()
        self.decline = GlassButton('拒绝'); self.accept = GlassButton('接收', primary=True)
        self.decline.clicked.connect(lambda: self.respond(False))
        self.accept.clicked.connect(lambda: self.respond(True))
        actions.addWidget(self.decline); actions.addWidget(self.accept)
        request_layout.addLayout(actions); layout.addWidget(self.request_card)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100); self.progress.setFixedHeight(6); self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.open_folder = GlassButton('打开接收文件夹', height=36)
        self.open_folder.clicked.connect(self.folder)
        layout.addWidget(self.open_folder)
        self.buttons = (self.close_button, self.off, self.everyone, self.decline, self.accept, self.open_folder)
        self.request_card.hide(); self.progress.hide()
        service.changed.connect(self.render)
        service.request_received.connect(self.present)
        self.restyle(); self.render(service.state)
        self.hide()

    def restyle(self):
        fg = theme.text().name()
        self.setStyleSheet(f'QLabel{{color:{fg};background:transparent}}'
                           'QProgressBar{background:rgba(128,128,128,40);border:0;border-radius:3px}'
                           'QProgressBar::chunk{background:#0a9fff;border-radius:3px}')
        for button in self.buttons:
            button.update()
        self.update(); self.card.update()
        self.refresh_backdrop()

    def render(self, state):
        on, starting = state.get('isRunning', False), state.get('isStarting', False)
        self.name.setText(state.get('deviceName', 'AirDrop'))
        message = state.get('message', '点击控制磁贴重新连接')
        remaining = state.get('remainingSeconds')
        if remaining is not None and (on or starting):
            message += f'\n剩余 {remaining // 60:02d}:{remaining % 60:02d}'
        self.status.setText(message); self.status.setToolTip(message)
        self.off.setChecked(not on and not starting); self.everyone.setChecked(on or starting)
        self.everyone.setText('正在准备接收…' if starting else '所有人，10 分钟')
        self.everyone.setEnabled(state.get('ok', False) and not starting)
        self.off.setEnabled(state.get('ok', False))
        requests = state.get('requests') or []
        self._request_id = requests[0]['id'] if requests else None
        self.request_card.setVisible(bool(requests))
        if requests:
            request = requests[0]
            full = '来自 ' + request.get('sender', '附近的设备') + '\n' + '\n'.join(request.get('files', [])[:6])
            self.request_text.setText(full[:420]); self.request_text.setToolTip(full)
        self.accept.setEnabled(bool(requests)); self.decline.setEnabled(bool(requests))
        transfer = state.get('transfer') or {}; phase = transfer.get('phase')
        self.progress.setVisible(phase == 'receiving')
        if phase == 'receiving':
            total = transfer.get('total', 0)
            self.progress.setRange(0, 100 if total else 0)
            self.progress.setValue(min(99, int(transfer.get('bytes', 0) * 100 / max(1, total))))
        if phase == 'received':
            self.status.setText('接收完成\n' + transfer.get('lastFile', '文件已保存'))
        self.open_folder.setEnabled(bool(state.get('receiveDirectory')))
        if self.isVisible() and self._animation.state() != QtCore.QAbstractAnimation.State.Running:
            self._fit()

    def respond(self, accept):
        if self._request_id:
            self.accept.setEnabled(False); self.decline.setEnabled(False)
            self.service.command('respond', id=self._request_id, accept=accept)

    def folder(self):
        directory = self.service.state.get('receiveDirectory')
        if directory:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(directory))
