# -*- coding: utf-8 -*-
"""
高性能自绘图像视图控件：支持缩放、拖拽平移、适应窗口、1:1、亮度/对比度实时滤镜与像素级悬停取色
"""

import os
from pathlib import Path

from ..core.qt_compat import (
    ALIGN_CENTER,
    CURSOR_CLOSED_HAND,
    CURSOR_CROSS,
    CURSOR_OPEN_HAND,
    DASH_LINE,
    ELIDE_MIDDLE,
    PEN_NO_PEN,
    FORMAT_GRAY8,
    FORMAT_RGB888,
    LEFT_BUTTON,
    QColor,
    QImage,
    QPainter,
    QPixmap,
    QRectF,
    _SMOOTH_PIXMAP_HINT,
    _mouse_pos,
    pyqtSignal,
    QtCore,
    QtGui,
    QtWidgets,
)

MIN_SCALE = 0.02
MAX_SCALE = 64.0


class ImageView(QtWidgets.QWidget):
    """
    高性能自绘图像控件：
      - 滚轮以鼠标光标为中心自由缩放
      - 鼠标左键拖动画布平移
      - 适应窗口 (Fit) 与 1:1 显示
      - 实时非破坏性显示滤镜：灰度、亮度调节、对比度调节（通过查表映射加速）
      - 光标悬停像素级探针：坐标、灰度、RGB与十六进制色彩
      - 支持拖放文件夹或单张图片快速加载
    """

    viewChanged = pyqtSignal(float, float, float)  # scale, rel_center_x, rel_center_y
    pixelHovered = pyqtSignal(object)              # (x, y, gray, r, g, b) 或 None
    folderDropped = pyqtSignal(str)               # 拖入文件夹路径
    fileDropped = pyqtSignal(str)                 # 拖入图片文件路径

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap()           # 原始图像 QPixmap，用于几何计算
        self._display_pixmap = QPixmap()   # 经滤镜处理后用于渲染的 QPixmap
        self._source_image = QImage()      # 原图 QImage，用于像素高精度取值
        self._path = None
        self._gray = False
        self._brightness = 0
        self._contrast = 0
        self._scale = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._fit_mode = True
        self._dragging = False
        self._last_pos = (0.0, 0.0)
        self._show_crosshair = False
        self._empty_hint = "未加载图像"

        # 悬浮标识配置
        self._panel_title = "左视图"
        self._is_left = True
        self._display_filename = ""
        self._display_fullpath = ""

        # 主题色彩
        self._bg_color = QColor("#121317")
        self._border_color = QColor("#222631")
        self._hint_color = QColor("#64748b")
        self._grid_color = QColor("#1a1d26")

        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setCursor(QtGui.QCursor(CURSOR_OPEN_HAND))

    def set_panel_info(self, title, is_left=True):
        self._panel_title = title
        self._is_left = is_left
        self.update()

    def set_image_title(self, filename, full_path=""):
        self._display_filename = filename or ""
        self._display_fullpath = full_path or ""
        self.setToolTip(self._display_fullpath if self._display_fullpath else self._display_filename)
        self.update()

    # ---- 外部交互接口 ----
    def load_path(self, path):
        """
        加载图片路径，若路径无效或格式错误返回 False。
        采用内存无锁二进制加载（open bytes + loadFromData），杜绝 Windows 下
        QImage 原生独占文件句柄导致的文件锁定 (WinError 32) 及剪切/移动/删除引发的闪退。
        """
        self._path = str(path) if path else None
        if not self._path:
            self._clear_image()
            return False
        if not os.path.isfile(self._path):
            self._empty_hint = "文件不存在"
            self._clear_image()
            return False

        image = QImage()
        data = None
        try:
            with open(self._path, "rb") as f:
                data = f.read()
            if data:
                image.loadFromData(data)
        except Exception as exc:
            image = QImage()

        # 兼容性回退：若从内存数据加载失败，尝试标准加载
        if image.isNull():
            image = QImage(self._path)
            if image.isNull():
                pixmap = QPixmap(self._path)
                if not pixmap.isNull():
                    image = pixmap.toImage()

        if image.isNull():
            self._empty_hint = "无法读取该图像文件"
            self._clear_image()
            return False

        self._source_image = image
        self._pixmap = QPixmap.fromImage(image)
        if self._fit_mode:
            self._recalc_fit()
        self._refresh_display()
        return True

    def unload(self):
        """安全释放当前图像资源并清空显示"""
        self._path = None
        self._display_filename = ""
        self._display_fullpath = ""
        self._clear_image()

    def _clear_image(self):
        self._pixmap = QPixmap()
        self._display_pixmap = QPixmap()
        self._source_image = QImage()
        self.update()

    def current_path(self):
        return self._path

    def is_loaded(self):
        return not self._pixmap.isNull()

    def image_size(self):
        if self._pixmap.isNull():
            return 0, 0
        return self._pixmap.width(), self._pixmap.height()

    # ---- 滤镜与显示层增强 ----
    def _make_lut(self):
        """生成 256 阶亮度/对比度变换查表：out = (v-127.5)*factor + 127.5 + brightness。"""
        factor = 1.0 + self._contrast / 100.0
        bias = self._brightness
        table = bytearray(256)
        for value in range(256):
            out = int(round((value - 127.5) * factor + 127.5 + bias))
            table[value] = 0 if out < 0 else (255 if out > 255 else out)
        return bytes(table)

    def _refresh_display(self):
        """仅作用于显示缓存，不修改原文件。"""
        if self._source_image.isNull():
            self._display_pixmap = QPixmap()
            self.update()
            return
        if self._gray and FORMAT_GRAY8 is not None:
            image = self._source_image.convertToFormat(FORMAT_GRAY8)
        elif FORMAT_RGB888 is not None:
            image = self._source_image.convertToFormat(FORMAT_RGB888)
        else:
            image = self._source_image
        if self._brightness == 0 and self._contrast == 0:
            self._display_pixmap = QPixmap.fromImage(image)
            self.update()
            return
        try:
            lut = self._make_lut()
            raw = image.bits()
            size = image.sizeInBytes()
            data = raw.asstring(size) if hasattr(raw, "asstring") else bytes(raw)
            transformed = data.translate(lut)
            result = QImage(transformed, image.width(), image.height(),
                            image.bytesPerLine(), image.format()).copy()
            self._display_pixmap = QPixmap.fromImage(result)
        except Exception:
            self._display_pixmap = QPixmap.fromImage(image)
        self.update()

    def set_gray(self, enabled):
        self._gray = bool(enabled)
        self._refresh_display()

    def set_brightness(self, value):
        self._brightness = int(value)
        self._refresh_display()

    def set_contrast(self, value):
        self._contrast = int(value)
        self._refresh_display()

    def reset_display(self):
        self._gray = False
        self._brightness = 0
        self._contrast = 0
        self._refresh_display()

    def toggle_crosshair(self):
        self._show_crosshair = not self._show_crosshair
        self.update()

    # ---- 像素取样 ----
    def pixel_at(self, widget_x, widget_y):
        """控件像素坐标 → 原图像素坐标，返回 (x, y, 灰度, r, g, b) 或 None。"""
        if self._source_image.isNull() or self._scale <= 0:
            return None
        img_x = int((widget_x - self._offset_x) / self._scale)
        img_y = int((widget_y - self._offset_y) / self._scale)
        if (img_x < 0 or img_y < 0 or
                img_x >= self._source_image.width() or
                img_y >= self._source_image.height()):
            return None
        color = self._source_image.pixelColor(img_x, img_y)
        red, green, blue = color.red(), color.green(), color.blue()
        gray = int(round(0.299 * red + 0.587 * green + 0.114 * blue))
        return (img_x, img_y, gray, red, green, blue)

    # ---- 视口几何与变换 ----
    def current_view(self):
        """返回 (当前缩放比例, 相对控件中心X, 相对控件中心Y)"""
        return (self._scale,
                self._offset_x - self.width() / 2.0,
                self._offset_y - self.height() / 2.0)

    def current_scale_percent(self):
        return round(self._scale * 100)

    def info_text(self):
        if self._pixmap.isNull():
            return "无图"
        return "%dx%d @ %d%%" % (self._pixmap.width(),
                                 self._pixmap.height(),
                                 round(self._scale * 100))

    def apply_view(self, scale, rel_x, rel_y):
        """应用同步视口（避免信号反弹循环）"""
        self._scale = min(max(scale, MIN_SCALE), MAX_SCALE)
        self._offset_x = self.width() / 2.0 + rel_x
        self._offset_y = self.height() / 2.0 + rel_y
        self._fit_mode = False
        self.update()

    def zoom_by(self, factor, anchor_x=None, anchor_y=None, emit=True):
        if self._pixmap.isNull():
            return
        if anchor_x is None:
            anchor_x = self.width() / 2.0
        if anchor_y is None:
            anchor_y = self.height() / 2.0
        new_scale = min(max(self._scale * factor, MIN_SCALE), MAX_SCALE)
        if abs(new_scale - self._scale) < 1e-12:
            return
        img_x = (anchor_x - self._offset_x) / self._scale
        img_y = (anchor_y - self._offset_y) / self._scale
        self._offset_x = anchor_x - img_x * new_scale
        self._offset_y = anchor_y - img_y * new_scale
        self._scale = new_scale
        self._fit_mode = False
        self.update()
        if emit:
            self._emit_view()

    def set_one_to_one(self, emit=True):
        if self._pixmap.isNull():
            return
        self._scale = 1.0
        self._offset_x = (self.width() - self._pixmap.width()) / 2.0
        self._offset_y = (self.height() - self._pixmap.height()) / 2.0
        self._fit_mode = False
        self.update()
        if emit:
            self._emit_view()

    def fit(self, emit=True):
        self._recalc_fit()
        self._fit_mode = True
        self.update()
        if emit:
            self._emit_view()

    def _recalc_fit(self):
        if self._pixmap.isNull():
            return
        w, h = self.width(), self.height()
        pw, ph = self._pixmap.width(), self._pixmap.height()
        if w <= 0 or h <= 0 or pw <= 0 or ph <= 0:
            return
        self._scale = max(min(w / pw, h / ph) * 0.98, MIN_SCALE)
        self._offset_x = (w - pw * self._scale) / 2.0
        self._offset_y = (h - ph * self._scale) / 2.0

    def _emit_view(self):
        scale, rel_x, rel_y = self.current_view()
        self.viewChanged.emit(scale, rel_x, rel_y)

    # ---- 绘制事件 ----
    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.rect()

        # 背景与边框
        painter.fillRect(rect, self._bg_color)
        painter.setPen(self._border_color)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        if self._pixmap.isNull():
            # 优雅的无图像占位提示
            painter.setPen(self._hint_color)
            font = painter.font()
            font.setPointSize(11)
            painter.setFont(font)
            msg = self._empty_hint if self._path is not None else "未加载图像\n(可在此拖入图片或文件夹)"
            painter.drawText(rect, int(ALIGN_CENTER), msg)
            painter.end()
            return

        # 图像重采样质量：放大到 4x 以上时保持像素邻近插值便于检查像素锯齿
        if _SMOOTH_PIXMAP_HINT is not None and self._scale < 4.0:
            painter.setRenderHint(_SMOOTH_PIXMAP_HINT, True)

        display = self._display_pixmap if not self._display_pixmap.isNull() else self._pixmap
        target = QRectF(self._offset_x, self._offset_y,
                        self._pixmap.width() * self._scale,
                        self._pixmap.height() * self._scale)
        source = QRectF(display.rect())
        painter.drawPixmap(target, display, source)

        # 准星对齐辅助线 (十字参考线)
        if self._show_crosshair:
            cx = self.width() / 2.0
            cy = self.height() / 2.0
            painter.setPen(QtGui.QPen(QColor(59, 130, 246, 160), 1, DASH_LINE))
            painter.drawLine(0, int(cy), self.width(), int(cy))
            painter.drawLine(int(cx), 0, int(cx), self.height())

        # 左上角悬浮半透明文件名标识胶囊 (极简无框设计)
        badge_text = "%s: %s" % (self._panel_title, self._display_filename if self._display_filename else "未加载")
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        fm = QtGui.QFontMetrics(font)
        bw = fm.horizontalAdvance(badge_text) if hasattr(fm, "horizontalAdvance") else fm.width(badge_text)
        badge_w, badge_h = min(bw + 18, self.width() - 20), 22
        badge_rect = QRectF(8, 8, badge_w, badge_h)
        painter.setPen(PEN_NO_PEN)
        painter.setBrush(QColor(3, 105, 161, 210) if self._is_left else QColor(4, 120, 87, 210))
        painter.drawRoundedRect(badge_rect, 4, 4)
        painter.setPen(QColor("#f8fafc"))
        elided = fm.elidedText(badge_text, ELIDE_MIDDLE, badge_w - 12)
        painter.drawText(badge_rect, int(ALIGN_CENTER), elided)

        # 右下角半透明缩放比 HUD
        scale_text = "%d%%" % round(self._scale * 100)
        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        fm_s = QtGui.QFontMetrics(font)
        tw = fm_s.horizontalAdvance(scale_text) if hasattr(fm_s, "horizontalAdvance") else fm_s.width(scale_text)
        hud_w, hud_h = tw + 12, 18
        hud_rect = QRectF(self.width() - hud_w - 8, self.height() - hud_h - 8, hud_w, hud_h)
        painter.setPen(PEN_NO_PEN)
        painter.setBrush(QColor(15, 23, 42, 180))
        painter.drawRoundedRect(hud_rect, 3, 3)
        painter.setPen(QColor("#94a3b8"))
        painter.drawText(hud_rect, int(ALIGN_CENTER), scale_text)

        painter.end()

    # ---- 交互与事件处理 ----
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_mode and not self._pixmap.isNull():
            self._recalc_fit()
            self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y() if hasattr(event, "angleDelta") else 0
        if not delta:
            event.ignore()
            return
        anchor_x, anchor_y = _mouse_pos(event)
        factor = 1.15 if delta > 0 else 1.0 / 1.15
        self.zoom_by(factor, anchor_x, anchor_y)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == LEFT_BUTTON and not self._pixmap.isNull():
            self._dragging = True
            self._last_pos = _mouse_pos(event)
            self.setCursor(QtGui.QCursor(CURSOR_CLOSED_HAND))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        x, y = _mouse_pos(event)
        if self._dragging:
            self._offset_x += x - self._last_pos[0]
            self._offset_y += y - self._last_pos[1]
            self._last_pos = (x, y)
            self._fit_mode = False
            self.update()
            self._emit_view()
            event.accept()
        else:
            super().mouseMoveEvent(event)
        self.pixelHovered.emit(self.pixel_at(x, y))

    def leaveEvent(self, event):
        self.pixelHovered.emit(None)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == LEFT_BUTTON:
            self._dragging = False
            self.setCursor(QtGui.QCursor(CURSOR_OPEN_HAND))
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == LEFT_BUTTON:
            self.fit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    # ---- 拖拽载入文件/文件夹 ----
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        local_path = urls[0].toLocalFile()
        if os.path.isdir(local_path):
            self.folderDropped.emit(local_path)
            event.acceptProposedAction()
        elif os.path.isfile(local_path):
            self.fileDropped.emit(local_path)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
