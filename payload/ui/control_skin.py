"""Original vector connectivity symbols and glass surfaces, shared by tile/detail."""
from PySide6 import QtCore, QtGui, QtWidgets
from .theme import theme, ui_font, W
from .widgets import Hoverable, painter

Qt = QtCore.Qt
BLUE = QtGui.QColor('#0a9fff')
BADGE_SIZE = 32
GLYPH_SIZE = 18


def draw_symbol(p, kind, rect, color=QtGui.QColor('white')):
    p.save()
    p.translate(rect.center()); p.scale(rect.width() / 24, rect.height() / 24)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QtGui.QPen(color, 1.65, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if kind == 'airdrop':
        for radius in (10, 7, 4):
            p.drawArc(QtCore.QRectF(-radius, -radius, radius * 2, radius * 2), 305 * 16, 290 * 16)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(color)
        p.drawEllipse(QtCore.QPointF(0, 0), 1.5, 1.5)
    elif kind == 'wifi':
        # Three concentric arcs, as requested; retain the compact 18px glyph.
        p.setPen(QtGui.QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for radius in (12, 8.5, 5):
            p.drawArc(QtCore.QRectF(-radius, 6 - radius, radius * 2, radius * 2), 45 * 16, 90 * 16)
        p.setBrush(color); p.setPen(Qt.PenStyle.NoPen)
        base = QtGui.QPainterPath(QtCore.QPointF(-2.1, 3.9))
        base.quadTo(0, 2.1, 2.1, 3.9); base.quadTo(2.4, 4.2, 2, 4.7)
        base.lineTo(.65, 6.2); base.quadTo(0, 6.9, -.65, 6.2)
        base.lineTo(-2, 4.7); base.quadTo(-2.4, 4.2, -2.1, 3.9); base.closeSubpath()
        p.drawPath(base)
    elif kind == 'bt':
        path = QtGui.QPainterPath(QtCore.QPointF(0, -10)); path.lineTo(0, 10)
        path.moveTo(-6, -5); path.lineTo(6, 5); path.lineTo(0, 10)
        path.moveTo(-6, 5); path.lineTo(6, -5); path.lineTo(0, -10)
        p.drawPath(path)
    p.restore()


def glass_surface(p, widget, rect, radius, island=None, strength=1.0, background=None, base_color=None):
    path = QtGui.QPainterPath(); path.addRoundedRect(rect, radius, radius)
    backdrop = getattr(island, 'backdrop', None)
    if background is not None:
        image, offset, extent = background
        p.save(); p.setClipPath(path)
        p.drawImage(QtCore.QRectF(-offset.x(), -offset.y(), extent.width(), extent.height()), image)
        p.restore()
    elif backdrop is not None:
        brush = backdrop.brush_for(backdrop.state, widget.mapToGlobal(QtCore.QPoint()))
        if brush is not None:
            p.fillPath(path, brush)
    tint = QtGui.QColor(base_color) if base_color is not None else theme.tint()
    tint.setAlpha(min(235, int(tint.alpha() * strength)))
    p.fillPath(path, tint)
    gloss = QtGui.QLinearGradient(rect.topLeft(), rect.bottomRight())
    gloss.setColorAt(0, QtGui.QColor(255, 255, 255, 42 if theme.dark else 115))
    gloss.setColorAt(.45, QtGui.QColor(255, 255, 255, 5))
    gloss.setColorAt(1, QtGui.QColor(255, 255, 255, 17))
    p.fillPath(path, gloss)
    rim = QtGui.QLinearGradient(rect.topLeft(), rect.bottomLeft())
    rim.setColorAt(0, QtGui.QColor(255, 255, 255, 175 if theme.dark else 235))
    rim.setColorAt(.5, QtGui.QColor(255, 255, 255, 28))
    rim.setColorAt(1, QtGui.QColor(255, 255, 255, 90))
    p.strokePath(path, QtGui.QPen(QtGui.QColor(0, 0, 0, 45), 2))
    p.strokePath(path, QtGui.QPen(QtGui.QBrush(rim), 1))


class GlassButton(QtWidgets.QAbstractButton):
    """One glass capsule renderer with native button semantics, in every state."""
    def __init__(self, text, parent=None, *, height=40, choice=False, primary=False):
        super().__init__(parent)
        self.choice, self.primary = choice, primary
        self._hovered = False
        self.setText(text); self.setFont(ui_font(12.5, W.Medium))
        self.setFixedHeight(height)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setCheckable(choice)
        self.pressed.connect(self.update); self.released.connect(self.update)
        self.toggled.connect(lambda _: self.update())
        theme.changed.connect(self.update)

    def sizeHint(self):
        return QtCore.QSize(QtGui.QFontMetrics(self.font()).horizontalAdvance(self.text()) +
                           (58 if self.choice else 32), self.minimumHeight())

    def minimumSizeHint(self):
        return self.sizeHint()

    def text_rect(self):
        return QtCore.QRectF(self.rect()).adjusted(16, 1, -42 if self.choice else -16, -1)

    def enterEvent(self, event):
        self._hovered = True; self.update(); super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False; self.update(); super().leaveEvent(event)

    def focusInEvent(self, event):
        self.update(); super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.update(); super().focusOutEvent(event)

    def changeEvent(self, event):
        if event.type() == QtCore.QEvent.Type.EnabledChange:
            self._hovered = False; self.update()
        super().changeEvent(event)

    def paintEvent(self, event):
        p = painter(self)
        rect = QtCore.QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        if self.isDown() and self.isEnabled():
            p.translate(rect.center()); p.scale(.985, .985); p.translate(-rect.center())
        if not self.isEnabled():
            p.setOpacity(.46)
        active = self.isChecked() or self.primary
        base = QtGui.QColor(BLUE) if active else theme.card()
        if active:
            base.setAlpha(225)
        glass_surface(p, self, rect, rect.height() / 2, base_color=base)
        if self._hovered and self.isEnabled():
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QtGui.QColor(255, 255, 255, 20))
            p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        if self.hasFocus() and self.isEnabled():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 210) if theme.dark or active else BLUE, 1.4))
            p.drawRoundedRect(rect.adjusted(2, 2, -2, -2), rect.height() / 2 - 2, rect.height() / 2 - 2)
        p.setFont(self.font()); p.setPen(QtGui.QColor('white') if active else theme.text())
        align = Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignLeft if self.choice else Qt.AlignmentFlag.AlignHCenter)
        self.draw_label(p, align)
        if self.choice and self.isChecked():
            p.setPen(QtGui.QPen(QtGui.QColor('white'), 1.8, Qt.PenStyle.SolidLine,
                               Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            x, y = self.width() - 24, self.height() / 2
            path = QtGui.QPainterPath(QtCore.QPointF(x - 4, y))
            path.lineTo(x - 1, y + 3); path.lineTo(x + 5, y - 4)
            p.drawPath(path)

    def draw_label(self, painter, alignment):
        painter.drawText(self.text_rect(), alignment, self.text())


class ConnectionTile(Hoverable):
    def __init__(self, kind, title, compact=False):
        super().__init__()
        self.kind, self.title, self.compact = kind, title, compact
        self.on, self.sub, self.enabled_ = False, '', True
        self.island = None
        self.setFixedHeight(62 if compact else 118)
        self.setMinimumWidth(120)
        self.setAccessibleName(title)

    def set_state(self, on, sub='', enabled=True):
        self.on, self.sub, self.enabled_ = bool(on), sub, enabled
        self.setAccessibleDescription(sub)
        self.update()

    def paintEvent(self, event):
        p = painter(self)
        rect = QtCore.QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        scale = self.press_scale()
        p.translate(rect.center()); p.scale(scale, scale); p.translate(-rect.center())
        glass_surface(p, self, rect, 27 if not self.compact else 30, self.island)
        circle = QtCore.QRectF(16, 14 if not self.compact else (self.height() - BADGE_SIZE) / 2,
                              BADGE_SIZE, BADGE_SIZE)
        p.setPen(Qt.PenStyle.NoPen)
        off_circle = QtGui.QColor(255, 255, 255, 48) if theme.dark else QtGui.QColor(105, 112, 124, 175)
        p.setBrush(BLUE if self.on else off_circle)
        p.drawEllipse(circle)
        inset = (BADGE_SIZE - GLYPH_SIZE) / 2
        draw_symbol(p, self.kind, circle.adjusted(inset, inset, -inset, -inset))
        x, y = (61, 10) if self.compact else (16, 69)
        width = self.width() - x - 13
        p.setFont(ui_font(13, W.DemiBold)); p.setPen(theme.text())
        p.drawText(QtCore.QRectF(x, y, width, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title)
        p.setFont(ui_font(10.5)); p.setPen(theme.text2())
        fm = QtGui.QFontMetrics(p.font())
        text = fm.elidedText(self.sub, Qt.TextElideMode.ElideRight, max(1, width - (16 if self.kind == 'airdrop' else 0)))
        p.drawText(QtCore.QRectF(x, y + 20, width, 17), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        if self.kind == 'airdrop':
            p.setPen(QtGui.QPen(theme.text2(), 1.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            cx, cy = rect.right() - 15, y + 29
            p.drawLine(QtCore.QPointF(cx - 2.5, cy - 2), QtCore.QPointF(cx, cy - 4.5))
            p.drawLine(QtCore.QPointF(cx, cy - 4.5), QtCore.QPointF(cx + 2.5, cy - 2))
            p.drawLine(QtCore.QPointF(cx - 2.5, cy + 2), QtCore.QPointF(cx, cy + 4.5))
            p.drawLine(QtCore.QPointF(cx, cy + 4.5), QtCore.QPointF(cx + 2.5, cy + 2))
