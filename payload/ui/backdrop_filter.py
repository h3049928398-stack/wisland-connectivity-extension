"""Opaque, DPR-aware offscreen blur. Never attaches an effect to live widgets."""
from PySide6 import QtCore, QtGui, QtWidgets
from .theme import theme

Qt = QtCore.Qt


def blur_frame(frame: QtGui.QImage, radius: float = 24) -> QtGui.QImage:
    """Quality blur with replicated edge padding (no dark/transparent border)."""
    if frame.isNull():
        return QtGui.QImage()
    dpr = frame.devicePixelRatio()
    pixels = frame.copy(); pixels.setDevicePixelRatio(1)
    pad = max(4, round(radius * dpr * 2))
    w, h = pixels.width(), pixels.height()
    padded = QtGui.QImage(w + 2 * pad, h + 2 * pad, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    padded.fill(Qt.GlobalColor.transparent)
    p = QtGui.QPainter(padded)
    p.drawImage(pad, pad, pixels)
    # Extend the last pixel instead of blurring into transparent black.
    for target, source in (
        (QtCore.QRect(pad, 0, w, pad), QtCore.QRect(0, 0, w, 1)),
        (QtCore.QRect(pad, pad + h, w, pad), QtCore.QRect(0, h - 1, w, 1)),
        (QtCore.QRect(0, pad, pad, h), QtCore.QRect(0, 0, 1, h)),
        (QtCore.QRect(pad + w, pad, pad, h), QtCore.QRect(w - 1, 0, 1, h)),
    ):
        p.drawImage(target, pixels, source)
    for x, y, sx, sy in ((0, 0, 0, 0), (w + pad, 0, w - 1, 0),
                         (0, h + pad, 0, h - 1), (w + pad, h + pad, w - 1, h - 1)):
        p.fillRect(x, y, pad, pad, pixels.pixelColor(sx, sy))
    p.end()
    scene = QtWidgets.QGraphicsScene()
    item = scene.addPixmap(QtGui.QPixmap.fromImage(padded))
    effect = QtWidgets.QGraphicsBlurEffect()
    effect.setBlurRadius(radius * dpr)
    effect.setBlurHints(QtWidgets.QGraphicsBlurEffect.BlurHint.QualityHint)
    item.setGraphicsEffect(effect)
    output = QtGui.QImage(padded.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    output.fill(Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(output)
    area = QtCore.QRectF(0, 0, padded.width(), padded.height())
    scene.render(painter, area, area, Qt.AspectRatioMode.IgnoreAspectRatio)
    painter.end()
    # Qt's blur kernel can round constant alpha down a few units. The input is
    # an opaque composite; keep it opaque so no live sharp widget leaks through.
    result = output.copy(pad, pad, w, h).convertToFormat(QtGui.QImage.Format.Format_RGB32)
    result.setDevicePixelRatio(dpr)
    return result


def composite_widget(widget, island=None) -> QtGui.QImage:
    """Capture an app-owned surface over its actual glass, with alpha=255."""
    dpr = widget.devicePixelRatioF()
    size = QtCore.QSize(round(widget.size().width() * dpr), round(widget.size().height() * dpr))
    result = QtGui.QImage(size, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    result.setDevicePixelRatio(dpr)
    result.fill(QtGui.QColor('#242731' if theme.dark else '#edf0f5'))
    p = QtGui.QPainter(result)
    backdrop = getattr(island, 'backdrop', None)
    if backdrop is not None:
        brush = backdrop.brush_for(backdrop.state, widget.mapToGlobal(QtCore.QPoint()))
        if brush is not None:
            p.fillRect(widget.rect(), brush)
            p.fillRect(widget.rect(), theme.tint_brush(QtCore.QRectF(widget.rect())))
    # QWidget.grab() also forces DrawWindowBackground on a transparent child,
    # introducing the default palette as a rectangular patch. Render only the
    # widget's own paint and children directly over the composed glass.
    widget.render(p, QtCore.QPoint(), QtGui.QRegion(), QtWidgets.QWidget.RenderFlag.DrawChildren)
    p.end()
    return result
