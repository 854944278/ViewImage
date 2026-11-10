# -*- coding: utf-8 -*-
"""
dual_image_viewer.py —— 双栏图像查看器

模式 A（配对同步）：必须先在「设置配对规则」里手动挑 2 对对应图像，工具据此
    推断出文件名对应逻辑并展示成可编辑的规则表达式，确认保存后才自动配对；
    配对完成后左右同步翻页。未设置规则时不自动配对、翻页按钮禁用。
模式 B（独立翻页）：两侧各自维护文件列表与索引，各自独立翻页。

基础看图功能：滚轮以光标为中心缩放、左键拖动平移、适应窗口、1:1、放大/缩小、
    复位、状态栏、文件列表侧栏、左右视图联动（可开关，默认开）。

扩展功能：把当前图像原样拷贝/保存到指定输出目录（重名自动加后缀，不覆盖）；
    左右各自独立的灰度开关与亮度/对比度滑块（仅显示层，不改原文件）；
    状态栏实时显示鼠标所在原图像素坐标、灰度值与 RGB 值。

启动方式（Anaconda Prompt）：
    conda activate qtUI
    python dual_image_viewer.py

依赖：qtUI 环境中的 PyQt5（自动兼容 PySide6 / PyQt6）+ Python 标准库。
图像读取走 QPixmap / QImage，不需要 Pillow / numpy / OpenCV，不安装任何包。
配置（文件夹路径、规则、模式等）自动保存在同目录 viewer_config.json。
"""

import json
import os
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Qt 绑定兼容层：优先 PyQt5，其次 PySide6 / PyQt6
# ---------------------------------------------------------------------------
try:
    from PyQt5 import QtCore, QtGui, QtWidgets
    from PyQt5.QtCore import Qt, pyqtSignal
    QT_BINDING = "PyQt5"
except ImportError:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        from PySide6.QtCore import Qt, Signal as pyqtSignal
        QT_BINDING = "PySide6"
    except ImportError:
        try:
            from PyQt6 import QtCore, QtGui, QtWidgets
            from PyQt6.QtCore import Qt, pyqtSignal
            QT_BINDING = "PyQt6"
        except ImportError as exc:
            raise SystemExit(
                "未找到 Qt 绑定。请在 qtUI 环境中使用 PyQt5，或改用 PySide6 / PyQt6。\n"
                "原始错误：%s" % exc
            )

QColor = QtGui.QColor
QPainter = QtGui.QPainter
QPixmap = QtGui.QPixmap
QImage = QtGui.QImage
QRectF = QtCore.QRectF


def _qt_const(*paths):
    """在 Qt / Qt.XXX 两种命名空间下解析枚举常量（Qt5 与 Qt6 差异）。"""
    for path in paths:
        obj = Qt
        for part in path.split("."):
            obj = getattr(obj, part, None)
            if obj is None:
                break
        else:
            return obj
    raise RuntimeError("无法解析 Qt 常量：%s" % (paths,))


LEFT_BUTTON = _qt_const("MouseButton.LeftButton", "LeftButton")
ALIGN_CENTER = _qt_const("AlignmentFlag.AlignCenter", "AlignCenter")
HORIZONTAL = _qt_const("Orientation.Horizontal", "Horizontal")
VERTICAL = _qt_const("Orientation.Vertical", "Vertical")
CURSOR_OPEN_HAND = _qt_const("CursorShape.OpenHandCursor", "OpenHandCursor")
CURSOR_CLOSED_HAND = _qt_const("CursorShape.ClosedHandCursor", "ClosedHandCursor")

# QShortcut 在 Qt5 属于 QtWidgets，Qt6 移到了 QtGui
QShortcut = getattr(QtWidgets, "QShortcut", None) or QtGui.QShortcut

_SMOOTH_PIXMAP_HINT = getattr(QPainter, "SmoothPixmapTransform", None)
if _SMOOTH_PIXMAP_HINT is None:
    _render_hint = getattr(QPainter, "RenderHint", None)
    _SMOOTH_PIXMAP_HINT = getattr(_render_hint, "SmoothPixmapTransform", None)


def _image_format(name):
    """QImage 格式枚举在 Qt5 / Qt6 下命名空间不同。"""
    value = getattr(QImage, name, None)
    if value is None:
        holder = getattr(QImage, "Format", None)
        value = getattr(holder, name, None) if holder is not None else None
    return value


FORMAT_GRAY8 = _image_format("Format_Grayscale8")
FORMAT_RGB888 = _image_format("Format_RGB888")


def _mouse_pos(event):
    """Qt5 用 pos()，Qt6 用 position()。"""
    if hasattr(event, "position"):
        p = event.position()
        return float(p.x()), float(p.y())
    p = event.pos()
    return float(p.x()), float(p.y())


def _dialog_exec(dialog):
    fn = getattr(dialog, "exec", None) or getattr(dialog, "exec_", None)
    return fn()


def _enable_high_dpi():
    try:
        attr = getattr(Qt, "AA_EnableHighDpiScaling", None)
        if attr is None:
            aa = getattr(Qt, "ApplicationAttribute", None)
            attr = getattr(aa, "AA_EnableHighDpiScaling", None) if aa else None
        if attr is not None and hasattr(QtWidgets.QApplication, "setAttribute"):
            QtWidgets.QApplication.setAttribute(attr, True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 文件扫描
# ---------------------------------------------------------------------------
IMAGE_EXTS = {
    ".bmp", ".png", ".jpg", ".jpeg", ".jfif", ".tif", ".tiff",
    ".gif", ".webp", ".ppm", ".pgm", ".pbm",
}

MIN_SCALE = 0.02
MAX_SCALE = 64.0
CONFIG_NAME = "viewer_config.json"


def natural_key(text):
    """自然排序：img2 排在 img10 前面。"""
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", text)]


def scan_images(folder):
    """只扫描顶层目录，返回按文件名自然排序的 Path 列表。"""
    if not folder or not os.path.isdir(folder):
        return []
    found = []
    try:
        with os.scandir(folder) as it:
            for entry in it:
                if entry.is_file() and os.path.splitext(entry.name)[1].lower() in IMAGE_EXTS:
                    found.append(Path(entry.path))
    except OSError:
        return []
    return sorted(found, key=lambda p: natural_key(p.name))


# ---------------------------------------------------------------------------
# 配对规则
# ---------------------------------------------------------------------------
class RuleError(ValueError):
    pass


def _positive_int(raw, label):
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        raise RuleError("%s必须是正整数" % label)
    if value <= 0:
        raise RuleError("%s必须是正整数" % label)
    return value


class PairRule:
    """
    规则表达式（单行文本，可直接编辑）：
        same                              文件名（不含扩展名）完全相同
        same_ext                          含扩展名的完整文件名相同
        prefix:N                          文件名前 N 位相同
        suffix:N                          文件名后 N 位相同
        number                            文件名中所有数字串按顺序相同
        strip:L前|L后|R前|R后             左右各自去掉固定前后缀后，中间部分相同
        regex:PATTERN                     正则提取：优先取 group(1)，否则 group(0)
    """

    def __init__(self, text):
        self.text = (text or "").strip()
        self.kind, self.params = self._parse(self.text)

    @staticmethod
    def _parse(text):
        if not text:
            raise RuleError("规则为空")
        if text in ("same", "same_ext", "number"):
            return text, {}
        if text.startswith("prefix:"):
            return "prefix", {"n": _positive_int(text[7:], "前 N 位的 N")}
        if text.startswith("suffix:"):
            return "suffix", {"n": _positive_int(text[7:], "后 N 位的 N")}
        if text.startswith("strip:"):
            parts = text[6:].split("|")
            if len(parts) != 4:
                raise RuleError("strip 规则需要 4 段：左前缀|左后缀|右前缀|右后缀")
            return "strip", {"lp": parts[0], "ls": parts[1],
                             "rp": parts[2], "rs": parts[3]}
        if text.startswith("regex:"):
            pattern = text[6:]
            if not pattern:
                raise RuleError("正则不能为空")
            try:
                re.compile(pattern)
            except re.error as exc:
                raise RuleError("正则无效：%s" % exc)
            return "regex", {"pattern": pattern}
        raise RuleError("无法识别的规则表达式：%s" % text)

    def key(self, filename, side):
        """把文件名映射成配对用的键；不适用该规则时返回 None。"""
        stem = os.path.splitext(filename)[0]
        kind = self.kind
        if kind == "same_ext":
            return filename
        if kind == "same":
            return stem
        if kind == "prefix":
            n = self.params["n"]
            return stem[:n] if len(stem) >= n else None
        if kind == "suffix":
            n = self.params["n"]
            return stem[-n:] if len(stem) >= n else None
        if kind == "number":
            nums = re.findall(r"\d+", stem)
            return "|".join(nums) if nums else None
        if kind == "strip":
            pre = self.params["lp"] if side == "L" else self.params["rp"]
            suf = self.params["ls"] if side == "L" else self.params["rs"]
            if not stem.startswith(pre):
                return None
            if suf and not stem.endswith(suf):
                return None
            end = len(stem) - len(suf) if suf else len(stem)
            if end < len(pre):
                return None
            core = stem[len(pre):end]
            return core or None
        if kind == "regex":
            match = re.search(self.params["pattern"], stem)
            if match is None:
                return None
            index = 1 if (match.lastindex or 0) >= 1 else 0
            try:
                return match.group(index)
            except IndexError:
                return match.group(0)
        return None

    def describe(self):
        kind = self.kind
        if kind == "same_ext":
            return "完整文件名相同"
        if kind == "same":
            return "文件名相同（忽略扩展名）"
        if kind == "prefix":
            return "文件名前 %d 位相同" % self.params["n"]
        if kind == "suffix":
            return "文件名后 %d 位相同" % self.params["n"]
        if kind == "number":
            return "文件名中的编号相同（忽略前后缀）"
        if kind == "strip":
            p = self.params
            return "去前后缀后相同：左[%s…%s] / 右[%s…%s]" % (
                p["lp"], p["ls"], p["rp"], p["rs"])
        if kind == "regex":
            return "正则提取：%s" % self.params["pattern"]
        return self.text


def build_pairs(left_files, right_files, rule_text):
    """按规则配对。返回 (pairs, 左未匹配, 右未匹配)，pairs 保持左列表顺序。"""
    rule = PairRule(rule_text)
    buckets = defaultdict(list)
    for path in right_files:
        key = rule.key(path.name, "R")
        if key is not None:
            buckets[key].append(path)

    cursor = defaultdict(int)
    pairs, unmatched_left, used_right = [], [], set()
    for left in left_files:
        key = rule.key(left.name, "L")
        bucket = buckets.get(key) if key is not None else None
        index = cursor.get(key, 0) if key is not None else 0
        if bucket and index < len(bucket):
            right = bucket[index]
            cursor[key] = index + 1
            pairs.append((left, right))
            used_right.add(str(right))
        else:
            unmatched_left.append(left)
    unmatched_right = [p for p in right_files if str(p) not in used_right]
    return pairs, unmatched_left, unmatched_right


def common_prefix_len(a, b):
    count = 0
    for x, y in zip(a, b):
        if x != y:
            break
        count += 1
    return count


def common_suffix_len(a, b):
    return common_prefix_len(a[::-1], b[::-1])


def longest_common_substring(a, b):
    if not a or not b:
        return ""
    prev = [0] * (len(b) + 1)
    best_len, best_end = 0, 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        char = a[i - 1]
        for j in range(1, len(b) + 1):
            if char == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best_len:
                    best_len, best_end = cur[j], i
        prev = cur
    return a[best_end - best_len:best_end]


def strip_core(stem, pre, suf):
    if not stem.startswith(pre):
        return None
    if suf and not stem.endswith(suf):
        return None
    end = len(stem) - len(suf) if suf else len(stem)
    if end < len(pre):
        return None
    return stem[len(pre):end]


def infer_rules(sample_pairs, left_files, right_files):
    """
    从 2 对样本推断候选规则。要求规则能同时解释两对样本，且两对样本产生
    不同的键（避免 prefix:1 这类无区分度的宽泛规则）。
    返回按「匹配对数多、未匹配少、键更具体」排序的候选列表。
    """
    (l1, r1), (l2, r2) = sample_pairs
    s1, t1 = os.path.splitext(l1)[0], os.path.splitext(r1)[0]
    s2, t2 = os.path.splitext(l2)[0], os.path.splitext(r2)[0]

    texts = []
    if l1 == r1 and l2 == r2:
        texts.append("same_ext")
    if s1 == t1 and s2 == t2:
        texts.append("same")
    n_pre = min(common_prefix_len(s1, t1), common_prefix_len(s2, t2))
    if n_pre > 0:
        texts.append("prefix:%d" % n_pre)
    n_suf = min(common_suffix_len(s1, t1), common_suffix_len(s2, t2))
    if n_suf > 0:
        texts.append("suffix:%d" % n_suf)
    nums1 = re.findall(r"\d+", s1)
    nums2 = re.findall(r"\d+", s2)
    if nums1 and nums1 == re.findall(r"\d+", t1) and nums2 == re.findall(r"\d+", t2):
        texts.append("number")

    # strip 候选：以最长公共子串或数字串作为「core」锚点，反推左右各自的前后缀
    anchors = set()
    lcs = longest_common_substring(s1, t1)
    if lcs:
        anchors.add(lcs)
    for num in re.findall(r"\d+", s1):
        if num in t1:
            anchors.add(num)
    for core in anchors:
        if "|" in core:
            continue
        i1, j1 = s1.find(core), t1.find(core)
        if i1 < 0 or j1 < 0:
            continue
        lp, ls = s1[:i1], s1[i1 + len(core):]
        rp, rs = t1[:j1], t1[j1 + len(core):]
        c2l, c2r = strip_core(s2, lp, ls), strip_core(t2, rp, rs)
        if c2l is None or c2r is None or c2l != c2r:
            continue
        if any("|" in x for x in (lp, ls, rp, rs)):
            continue
        texts.append("strip:%s|%s|%s|%s" % (lp, ls, rp, rs))

    results, seen = [], set()
    for text in texts:
        if text in seen:
            continue
        seen.add(text)
        try:
            rule = PairRule(text)
        except RuleError:
            continue
        k1l, k1r = rule.key(l1, "L"), rule.key(r1, "R")
        k2l, k2r = rule.key(l2, "L"), rule.key(r2, "R")
        if k1l is None or k1l != k1r or k2l is None or k2l != k2r:
            continue
        if k1l == k2l:  # 两对样本落到同一个键，规则过于宽泛
            continue
        try:
            pairs, ul, ur = build_pairs(left_files, right_files, text)
        except RuleError:
            continue
        results.append({
            "text": text,
            "describe": rule.describe(),
            "matched": len(pairs),
            "unmatched_l": len(ul),
            "unmatched_r": len(ur),
            "specificity": len(str(k1l)) + len(str(k2l)),
        })
    results.sort(key=lambda d: (-d["matched"],
                                d["unmatched_l"] + d["unmatched_r"],
                                -d["specificity"]))
    return results


# ---------------------------------------------------------------------------
# 图像视图
# ---------------------------------------------------------------------------
class ImageView(QtWidgets.QWidget):
    """自绘图像控件：缩放、拖动、适应窗口、1:1。"""

    viewChanged = pyqtSignal(float, float, float)  # scale, 相对控件中心的 x/y 偏移
    pixelHovered = pyqtSignal(object)              # (x, y, 灰度, r, g, b) 或 None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap()           # 原始图像，作为尺寸与几何计算基准
        self._display_pixmap = QPixmap()   # 灰度/亮度/对比度处理后的显示图像
        self._source_image = QImage()      # 原图 QImage，供鼠标像素取值
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
        self._bg = QColor("#262626")
        self._hint = QColor("#9a9a9a")
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        self.setCursor(QtGui.QCursor(CURSOR_OPEN_HAND))

    # ---- 对外接口 ----
    def load_path(self, path):
        self._path = str(path) if path else None
        if not self._path:
            self._clear_image()
            return False
        image = QImage(self._path)
        if image.isNull():
            pixmap = QPixmap(self._path)
            if not pixmap.isNull():
                image = pixmap.toImage()
        if image.isNull():
            self._clear_image()
            return False
        self._source_image = image
        self._pixmap = QPixmap.fromImage(image)
        if self._fit_mode:
            self._recalc_fit()
        self._refresh_display()
        return True

    def _clear_image(self):
        self._pixmap = QPixmap()
        self._display_pixmap = QPixmap()
        self._source_image = QImage()
        self.update()

    def current_path(self):
        return self._path

    def _make_lut(self):
        """亮度/对比度查表：out = (v-127.5)*factor + 127.5 + brightness。"""
        factor = 1.0 + self._contrast / 100.0
        bias = self._brightness
        table = bytearray(256)
        for value in range(256):
            out = int(round((value - 127.5) * factor + 127.5 + bias))
            table[value] = 0 if out < 0 else (255 if out > 255 else out)
        return bytes(table)

    def _refresh_display(self):
        """按灰度/亮度/对比度生成显示用 QPixmap；只作用于显示层，不改原文件。"""
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
            # 该 Qt 版本的像素缓冲接口不可用时，退回未增强图像，不影响看图
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

    def pixel_at(self, widget_x, widget_y):
        """控件坐标 → 原图像素坐标，返回 (x, y, 灰度, r, g, b) 或 None。"""
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

    def current_view(self):
        return (self._scale,
                self._offset_x - self.width() / 2.0,
                self._offset_y - self.height() / 2.0)

    def info_text(self):
        if self._pixmap.isNull():
            return "无图"
        return "%dx%d @ %d%%" % (self._pixmap.width(),
                                 self._pixmap.height(),
                                 round(self._scale * 100))

    def apply_view(self, scale, rel_x, rel_y):
        """应用联动过来的视图状态（不再向外发信号）。"""
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

    # ---- 内部 ----
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

    # ---- 事件 ----
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._bg)
        if self._pixmap.isNull():
            painter.setPen(self._hint)
            text = "未加载图像" if self._path is None else "无法读取该图像"
            painter.drawText(self.rect(), int(ALIGN_CENTER), text)
            painter.end()
            return
        if _SMOOTH_PIXMAP_HINT is not None and self._scale < 4.0:
            painter.setRenderHint(_SMOOTH_PIXMAP_HINT, True)
        display = self._display_pixmap if not self._display_pixmap.isNull() else self._pixmap
        target = QRectF(self._offset_x, self._offset_y,
                        self._pixmap.width() * self._scale,
                        self._pixmap.height() * self._scale)
        source = QRectF(display.rect())
        painter.drawPixmap(target, display, source)
        painter.end()

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


# ---------------------------------------------------------------------------
# 单侧面板
# ---------------------------------------------------------------------------
class SidePanel(QtWidgets.QWidget):
    prevRequested = pyqtSignal()
    nextRequested = pyqtSignal()
    itemActivated = pyqtSignal(int)
    saveRequested = pyqtSignal()

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.title = title
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        top = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel(title)
        label.setStyleSheet("font-weight:bold;")
        self.btn_prev = QtWidgets.QPushButton("◀ 上一张")
        self.btn_prev.setToolTip("模式 B 快捷键：Shift+← / PgUp（鼠标在本侧时）")
        self.btn_next = QtWidgets.QPushButton("下一张 ▶")
        self.btn_next.setToolTip("模式 B 快捷键：Shift+→ / PgDown（鼠标在本侧时）")
        self.btn_save = QtWidgets.QPushButton("保存当前图")
        self.btn_save.setToolTip("把当前原始图像文件复制到输出目录（Ctrl+S 保存鼠标所在侧）")
        self.lbl_pos = QtWidgets.QLabel("0 / 0")
        self.btn_prev.clicked.connect(lambda: self.prevRequested.emit())
        self.btn_next.clicked.connect(lambda: self.nextRequested.emit())
        self.btn_save.clicked.connect(lambda: self.saveRequested.emit())
        top.addWidget(label)
        top.addStretch(1)
        top.addWidget(self.btn_save)
        top.addWidget(self.btn_prev)
        top.addWidget(self.btn_next)
        top.addWidget(self.lbl_pos)
        layout.addLayout(top)

        display_row = QtWidgets.QHBoxLayout()
        self.chk_gray = QtWidgets.QCheckBox("灰度")
        self.sld_brightness = QtWidgets.QSlider(HORIZONTAL)
        self.sld_brightness.setRange(-100, 100)
        self.sld_brightness.setValue(0)
        self.sld_brightness.setSingleStep(5)
        self.sld_contrast = QtWidgets.QSlider(HORIZONTAL)
        self.sld_contrast.setRange(-100, 100)
        self.sld_contrast.setValue(0)
        self.sld_contrast.setSingleStep(5)
        self.btn_reset_display = QtWidgets.QPushButton("重置显示")
        display_row.addWidget(self.chk_gray)
        display_row.addWidget(QtWidgets.QLabel("亮度"))
        display_row.addWidget(self.sld_brightness, 1)
        display_row.addWidget(QtWidgets.QLabel("对比度"))
        display_row.addWidget(self.sld_contrast, 1)
        display_row.addWidget(self.btn_reset_display)
        layout.addLayout(display_row)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setMaximumHeight(180)
        self.list_widget.itemClicked.connect(
            lambda item: self.itemActivated.emit(self.list_widget.row(item)))
        layout.addWidget(self.list_widget)

        self.view = ImageView()
        layout.addWidget(self.view, 1)
        self.chk_gray.toggled.connect(self.view.set_gray)
        self.sld_brightness.valueChanged.connect(self.view.set_brightness)
        self.sld_contrast.valueChanged.connect(self.view.set_contrast)
        self.btn_reset_display.clicked.connect(self._reset_display)

    def set_nav_enabled(self, enabled):
        self.btn_prev.setEnabled(enabled)
        self.btn_next.setEnabled(enabled)

    def _reset_display(self):
        for widget in (self.chk_gray, self.sld_brightness, self.sld_contrast):
            widget.blockSignals(True)
        self.chk_gray.setChecked(False)
        self.sld_brightness.setValue(0)
        self.sld_contrast.setValue(0)
        for widget in (self.chk_gray, self.sld_brightness, self.sld_contrast):
            widget.blockSignals(False)
        self.view.reset_display()

    def set_position(self, current, total):
        self.lbl_pos.setText("%d / %d" % (current, total))

    def fill_list(self, rows, mark_unmatched):
        """rows: [(path, mate_path_or_None), ...]；红色表示未匹配。"""
        widget = self.list_widget
        widget.blockSignals(True)
        widget.clear()
        for path, mate in rows:
            item = QtWidgets.QListWidgetItem(path.name)
            if mark_unmatched and mate is None:
                item.setForeground(QColor("#d05656"))
                item.setToolTip("未匹配：%s" % path)
            else:
                item.setToolTip(str(path))
            widget.addItem(item)
        widget.blockSignals(False)

    def select_row(self, row):
        widget = self.list_widget
        widget.blockSignals(True)
        if 0 <= row < widget.count():
            widget.setCurrentRow(row)
        else:
            widget.setCurrentRow(-1)
        widget.blockSignals(False)


# ---------------------------------------------------------------------------
# 规则设置对话框
# ---------------------------------------------------------------------------
class RuleDialog(QtWidgets.QDialog):
    def __init__(self, parent, left_files, right_files, current_rule=""):
        super().__init__(parent)
        self.setWindowTitle("设置配对规则（模式 A）")
        self.resize(820, 660)
        self.left_files = left_files
        self.right_files = right_files
        self.candidates = []
        self.result_rule = None

        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(
            "第 1 步：在左右列表中各挑 2 对「确认互相对应」的图像（尽量选编号不同的两对，"
            "这样推断出的规则才有区分度）。\n"
            "第 2 步：点「推断规则」，从候选里选一条，或直接编辑下面的规则表达式。\n"
            "第 3 步：看预览匹配数量，确认后保存。保存之前模式 A 不会自动配对。")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QtWidgets.QFormLayout()
        self.cb_l1 = QtWidgets.QComboBox()
        self.cb_r1 = QtWidgets.QComboBox()
        self.cb_l2 = QtWidgets.QComboBox()
        self.cb_r2 = QtWidgets.QComboBox()
        form.addRow("样本 1 · 左侧", self.cb_l1)
        form.addRow("样本 1 · 右侧", self.cb_r1)
        form.addRow("样本 2 · 左侧", self.cb_l2)
        form.addRow("样本 2 · 右侧", self.cb_r2)
        layout.addLayout(form)
        self._fill_combos()

        row1 = QtWidgets.QHBoxLayout()
        btn_infer = QtWidgets.QPushButton("① 从这 2 对样本推断规则")
        btn_infer.clicked.connect(self._infer)
        self.cmb_candidates = QtWidgets.QComboBox()
        self.cmb_candidates.setMinimumWidth(380)
        self.cmb_candidates.currentIndexChanged.connect(self._on_candidate)
        row1.addWidget(btn_infer)
        row1.addWidget(self.cmb_candidates, 1)
        layout.addLayout(row1)

        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(QtWidgets.QLabel("规则表达式"))
        self.txt_rule = QtWidgets.QLineEdit()
        self.txt_rule.setPlaceholderText("例如 prefix:8 / number / strip:A_|_L|B_|_R / regex:(\\d+)")
        self.txt_rule.setText(current_rule or "")
        self.txt_rule.editingFinished.connect(self._preview)
        btn_preview = QtWidgets.QPushButton("② 预览匹配")
        btn_preview.clicked.connect(self._preview)
        row2.addWidget(self.txt_rule, 1)
        row2.addWidget(btn_preview)
        layout.addLayout(row2)

        syntax = QtWidgets.QLabel(
            "可用表达式： same | same_ext | prefix:N | suffix:N | number | "
            "strip:左前缀|左后缀|右前缀|右后缀 | regex:提取正则（优先取第 1 个捕获组）\n"
            "所有规则都基于「文件名（不含扩展名）」比较，扩展名可不同。")
        syntax.setWordWrap(True)
        syntax.setStyleSheet("color:#777777;")
        layout.addWidget(syntax)

        self.lbl_preview = QtWidgets.QLabel("尚未预览")
        layout.addWidget(self.lbl_preview)
        self.list_preview = QtWidgets.QListWidget()
        self.list_preview.setMaximumHeight(160)
        layout.addWidget(self.list_preview)

        row3 = QtWidgets.QHBoxLayout()
        row3.addStretch(1)
        btn_ok = QtWidgets.QPushButton("确认保存")
        btn_cancel = QtWidgets.QPushButton("取消")
        btn_ok.clicked.connect(self._on_ok)
        btn_cancel.clicked.connect(self.reject)
        row3.addWidget(btn_ok)
        row3.addWidget(btn_cancel)
        layout.addLayout(row3)

        if current_rule:
            self._preview()

    def _fill_combos(self):
        left_names = [p.name for p in self.left_files]
        right_names = [p.name for p in self.right_files]
        for combo, names in ((self.cb_l1, left_names), (self.cb_l2, left_names),
                             (self.cb_r1, right_names), (self.cb_r2, right_names)):
            combo.clear()
            combo.addItems(names)
            combo.setCurrentIndex(-1)

    def _infer(self):
        values = [c.currentText() for c in
                  (self.cb_l1, self.cb_r1, self.cb_l2, self.cb_r2)]
        if not all(values):
            QtWidgets.QMessageBox.information(
                self, "提示", "请把 4 个下拉框都选好（左右各 2 张对应图）。")
            return
        sample_pairs = [(values[0], values[1]), (values[2], values[3])]
        self.candidates = infer_rules(sample_pairs, self.left_files, self.right_files)
        self.cmb_candidates.blockSignals(True)
        self.cmb_candidates.clear()
        if not self.candidates:
            self.cmb_candidates.blockSignals(False)
            QtWidgets.QMessageBox.information(
                self, "提示",
                "无法从这两对样本推断出可靠规则。请换两对编号不同的样本，"
                "或直接填写下面的规则表达式。")
            return
        for item in self.candidates:
            self.cmb_candidates.addItem(
                "%s  → 匹配 %d 对（未匹配 左%d / 右%d）" % (
                    item["describe"], item["matched"],
                    item["unmatched_l"], item["unmatched_r"]),
                item["text"])
        self.cmb_candidates.setCurrentIndex(0)
        self.cmb_candidates.blockSignals(False)
        self.txt_rule.setText(self.candidates[0]["text"])
        self._preview()

    def _on_candidate(self, index):
        if index < 0 or index >= len(self.candidates):
            return
        self.txt_rule.setText(self.candidates[index]["text"])
        self._preview()

    def _preview(self):
        text = self.txt_rule.text().strip()
        self.list_preview.clear()
        if not text:
            self.lbl_preview.setText("未填写规则")
            return
        try:
            rule = PairRule(text)
            pairs, ul, ur = build_pairs(self.left_files, self.right_files, text)
        except RuleError as exc:
            self.lbl_preview.setText("规则错误：%s" % exc)
            return
        self.lbl_preview.setText(
            "%s ｜ 可匹配 %d 对 ｜ 左未匹配 %d ｜ 右未匹配 %d" % (
                rule.describe(), len(pairs), len(ul), len(ur)))
        if not pairs:
            self.list_preview.addItem("（没有任何图像能按此规则配上）")
        for left, right in pairs[:8]:
            self.list_preview.addItem("%s   ↔   %s" % (left.name, right.name))
        if len(pairs) > 8:
            self.list_preview.addItem("…… 其余 %d 对已省略" % (len(pairs) - 8))

    def _on_ok(self):
        text = self.txt_rule.text().strip()
        if not text:
            QtWidgets.QMessageBox.information(self, "提示", "请先填写或推断规则表达式。")
            return
        try:
            build_pairs(self.left_files, self.right_files, text)
        except RuleError as exc:
            QtWidgets.QMessageBox.warning(self, "规则无效", str(exc))
            return
        self.result_rule = text
        self.accept()


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("双栏图像查看器  |  %s" % QT_BINDING)
        self.resize(1400, 880)
        self.setMinimumSize(960, 640)

        self.config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), CONFIG_NAME)
        self.left_files = []
        self.right_files = []
        self.pairs = []
        self.unmatched_l = []
        self.unmatched_r = []
        self.left_rows = []
        self.right_rows = []
        self.rule_text = ""
        self.mode = "A"
        self.pair_index = 0
        self.left_index = 0
        self.right_index = 0
        self._syncing = False
        self._loading = False

        self._build_ui()
        self._load_config()
        self._refresh_all()

    # ---- UI ----
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        row1 = QtWidgets.QHBoxLayout()
        self.edt_left = QtWidgets.QLineEdit()
        self.edt_left.setPlaceholderText("左侧文件夹路径")
        self.edt_right = QtWidgets.QLineEdit()
        self.edt_right.setPlaceholderText("右侧文件夹路径")
        btn_browse_l = QtWidgets.QPushButton("浏览…")
        btn_browse_r = QtWidgets.QPushButton("浏览…")
        btn_browse_l.clicked.connect(lambda: self._browse("L"))
        btn_browse_r.clicked.connect(lambda: self._browse("R"))
        self.edt_left.editingFinished.connect(self._on_dirs_changed)
        self.edt_right.editingFinished.connect(self._on_dirs_changed)
        row1.addWidget(QtWidgets.QLabel("左文件夹"))
        row1.addWidget(self.edt_left, 1)
        row1.addWidget(btn_browse_l)
        row1.addSpacing(12)
        row1.addWidget(QtWidgets.QLabel("右文件夹"))
        row1.addWidget(self.edt_right, 1)
        row1.addWidget(btn_browse_r)
        root.addLayout(row1)

        row1b = QtWidgets.QHBoxLayout()
        self.edt_output = QtWidgets.QLineEdit()
        self.edt_output.setPlaceholderText("输出目录（保存/拷贝图像的目标文件夹）")
        btn_browse_output = QtWidgets.QPushButton("浏览…")
        btn_browse_output.clicked.connect(self._browse_output)
        self.edt_output.editingFinished.connect(self._save_config)
        row1b.addWidget(QtWidgets.QLabel("输出目录"))
        row1b.addWidget(self.edt_output, 1)
        row1b.addWidget(btn_browse_output)
        root.addLayout(row1b)

        row2 = QtWidgets.QHBoxLayout()
        self.rb_mode_a = QtWidgets.QRadioButton("模式 A：配对同步翻页")
        self.rb_mode_b = QtWidgets.QRadioButton("模式 B：独立翻页")
        self.rb_mode_a.setChecked(True)
        mode_group = QtWidgets.QButtonGroup(self)
        mode_group.addButton(self.rb_mode_a)
        mode_group.addButton(self.rb_mode_b)
        self.rb_mode_a.clicked.connect(lambda: self._on_mode_clicked("A"))
        self.rb_mode_b.clicked.connect(lambda: self._on_mode_clicked("B"))
        self.btn_rule = QtWidgets.QPushButton("设置配对规则")
        self.btn_clear_rule = QtWidgets.QPushButton("清除规则")
        self.lbl_rule = QtWidgets.QLabel("规则：未设置")
        self.btn_rule.clicked.connect(self._open_rule_dialog)
        self.btn_clear_rule.clicked.connect(self._clear_rule)
        row2.addWidget(self.rb_mode_a)
        row2.addWidget(self.rb_mode_b)
        row2.addSpacing(12)
        row2.addWidget(self.btn_rule)
        row2.addWidget(self.btn_clear_rule)
        row2.addWidget(self.lbl_rule, 1)
        root.addLayout(row2)

        row3 = QtWidgets.QHBoxLayout()
        self.chk_link = QtWidgets.QCheckBox("视图联动（缩放/平移同步）")
        self.chk_link.setChecked(True)
        self.chk_link.toggled.connect(self._on_link_toggled)
        btn_fit = QtWidgets.QPushButton("适应窗口")
        btn_100 = QtWidgets.QPushButton("1:1")
        btn_zoom_in = QtWidgets.QPushButton("＋")
        btn_zoom_out = QtWidgets.QPushButton("－")
        btn_fit.clicked.connect(lambda: self._fit_both())
        btn_100.clicked.connect(lambda: self._one_to_one_both())
        btn_zoom_in.clicked.connect(lambda: self._zoom_both(1.25))
        btn_zoom_out.clicked.connect(lambda: self._zoom_both(0.8))
        tip = QtWidgets.QLabel("模式 A：方向键同步翻页 ｜ 模式 B：←/→ 翻右、Shift+←/→ 翻左、PgUp/PgDn 翻鼠标所在侧 ｜ 双击适应窗口 ｜ Ctrl+S 保存当前图")
        tip.setStyleSheet("color:#777777;")
        row3.addWidget(self.chk_link)
        row3.addSpacing(10)
        row3.addWidget(btn_fit)
        row3.addWidget(btn_100)
        row3.addWidget(btn_zoom_in)
        row3.addWidget(btn_zoom_out)
        row3.addSpacing(10)
        row3.addWidget(tip, 1)
        root.addLayout(row3)

        self.left_panel = SidePanel("左视图")
        self.right_panel = SidePanel("右视图")
        splitter = QtWidgets.QSplitter(HORIZONTAL)
        splitter.addWidget(self.left_panel)
        splitter.addWidget(self.right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        self.lbl_status = QtWidgets.QLabel("")
        self.statusBar().addWidget(self.lbl_status)
        self.lbl_pixel = QtWidgets.QLabel("光标 —")
        self.statusBar().addPermanentWidget(self.lbl_pixel)

        self.left_panel.saveRequested.connect(lambda: self._save_current("L"))
        self.right_panel.saveRequested.connect(lambda: self._save_current("R"))
        self.left_panel.view.pixelHovered.connect(
            lambda data: self._on_pixel_hovered("L", data))
        self.right_panel.view.pixelHovered.connect(
            lambda data: self._on_pixel_hovered("R", data))
        self.left_panel.prevRequested.connect(lambda: self._turn_side("L", -1))
        self.left_panel.nextRequested.connect(lambda: self._turn_side("L", 1))
        self.right_panel.prevRequested.connect(lambda: self._turn_side("R", -1))
        self.right_panel.nextRequested.connect(lambda: self._turn_side("R", 1))
        self.left_panel.itemActivated.connect(lambda row: self._activate_row("L", row))
        self.right_panel.itemActivated.connect(lambda row: self._activate_row("R", row))
        self.left_panel.view.viewChanged.connect(self._on_left_view_changed)
        self.right_panel.view.viewChanged.connect(self._on_right_view_changed)
        self._build_shortcuts()

    def _build_shortcuts(self):
        bindings = (
            ("Left", -1, "R"), ("Right", 1, "R"),
            ("Shift+Left", -1, "L"), ("Shift+Right", 1, "L"),
            ("PgUp", -1, None), ("PgDown", 1, None),
        )
        for key, delta, side in bindings:
            shortcut = QShortcut(QtGui.QKeySequence(key), self)
            shortcut.activated.connect(
                lambda d=delta, s=side: self._shortcut_page(d, s))
        save_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self._save_hovered)

    def _shortcut_page(self, delta, side):
        focus = QtWidgets.QApplication.focusWidget()
        if isinstance(focus, (QtWidgets.QLineEdit, QtWidgets.QTextEdit)):
            return
        if self.mode == "A":
            self._turn_pair(delta)
            return
        target = side or self._hover_side()
        if target == "L":
            self._turn_side("L", delta)
        else:
            self._turn_side("R", delta)

    def _hover_side(self):
        global_pos = QtGui.QCursor.pos()
        for side, view in (("L", self.left_panel.view), ("R", self.right_panel.view)):
            if view.rect().contains(view.mapFromGlobal(global_pos)):
                return side
        return None

    # ---- 配置 ----
    def _load_config(self):
        if not os.path.isfile(self.config_path):
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            return
        self._loading = True
        self.edt_left.setText(data.get("left_dir", "") or "")
        self.edt_right.setText(data.get("right_dir", "") or "")
        self.edt_output.setText(data.get("output_dir", "") or "")
        self.rule_text = data.get("rule_text", "") or ""
        self.mode = data.get("mode", "A")
        if self.mode not in ("A", "B"):
            self.mode = "A"
        self.rb_mode_a.setChecked(self.mode == "A")
        self.rb_mode_b.setChecked(self.mode == "B")
        self.chk_link.setChecked(bool(data.get("link_views", True)))
        try:
            self.pair_index = int(data.get("pair_index", 0) or 0)
            self.left_index = int(data.get("left_index", 0) or 0)
            self.right_index = int(data.get("right_index", 0) or 0)
        except (TypeError, ValueError):
            self.pair_index = self.left_index = self.right_index = 0
        self._loading = False

    def _save_config(self):
        if self._loading:
            return
        data = {
            "left_dir": self.edt_left.text().strip(),
            "right_dir": self.edt_right.text().strip(),
            "output_dir": self.edt_output.text().strip(),
            "mode": self.mode,
            "rule_text": self.rule_text,
            "link_views": self.chk_link.isChecked(),
            "pair_index": self.pair_index,
            "left_index": self.left_index,
            "right_index": self.right_index,
        }
        try:
            with open(self.config_path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
        except OSError:
            pass

    # ---- 动作 ----
    def _browse(self, side):
        edit = self.edt_left if side == "L" else self.edt_right
        start = edit.text().strip()
        if not start or not os.path.isdir(start):
            start = os.path.expanduser("~")
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "选择%s侧文件夹" % ("左" if side == "L" else "右"), start)
        if folder:
            edit.setText(folder)
            self._on_dirs_changed()

    def _browse_output(self):
        start = self.edt_output.text().strip()
        if not start or not os.path.isdir(start):
            start = os.path.expanduser("~")
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "选择输出目录", start)
        if folder:
            self.edt_output.setText(folder)
            self._save_config()

    def _save_current(self, side):
        view = self.left_panel.view if side == "L" else self.right_panel.view
        source = view.current_path()
        if not source or not os.path.isfile(source):
            QtWidgets.QMessageBox.information(
                self, "提示",
                "当前%s侧没有可保存的图像。" % ("左" if side == "L" else "右"))
            return
        out_dir = self.edt_output.text().strip()
        if not out_dir or not os.path.isdir(out_dir):
            QtWidgets.QMessageBox.information(
                self, "提示", "请先在顶部设置有效的「输出目录」。")
            return
        name = os.path.basename(source)
        stem, ext = os.path.splitext(name)
        target = os.path.join(out_dir, name)
        counter = 1
        while os.path.exists(target):
            target = os.path.join(out_dir, "%s_%d%s" % (stem, counter, ext))
            counter += 1
        try:
            shutil.copy2(source, target)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "保存失败", str(exc))
            return
        self.statusBar().showMessage("已保存：%s" % target, 3000)

    def _save_hovered(self):
        self._save_current(self._hover_side() or "L")

    def _on_pixel_hovered(self, side, data):
        if data is None:
            self.lbl_pixel.setText("光标 —")
            return
        x, y, gray, red, green, blue = data
        self.lbl_pixel.setText(
            "%s (%d, %d) ｜ 灰度 %d ｜ RGB(%d,%d,%d)" % (
                "左" if side == "L" else "右",
                x, y, gray, red, green, blue))

    def _on_dirs_changed(self):
        self._save_config()
        self._refresh_all()

    def _on_mode_clicked(self, mode):
        self.mode = mode
        self._refresh_all()
        self._save_config()

    def _open_rule_dialog(self):
        if not self.left_files or not self.right_files:
            QtWidgets.QMessageBox.information(
                self, "提示", "请先在两侧选择包含图像的文件夹。")
            return
        dialog = RuleDialog(self, self.left_files, self.right_files, self.rule_text)
        _dialog_exec(dialog)
        if dialog.result_rule:
            self.rule_text = dialog.result_rule
            self.pair_index = 0
            self._refresh_all()
            self._save_config()

    def _clear_rule(self):
        self.rule_text = ""
        self.pair_index = 0
        self._refresh_all()
        self._save_config()

    def _on_link_toggled(self, checked):
        if checked and not self._loading:
            scale, rel_x, rel_y = self.left_panel.view.current_view()
            self.right_panel.view.apply_view(scale, rel_x, rel_y)
        self._save_config()

    def _on_left_view_changed(self, scale, rel_x, rel_y):
        if self._syncing or not self.chk_link.isChecked():
            return
        self._syncing = True
        self.right_panel.view.apply_view(scale, rel_x, rel_y)
        self._syncing = False
        self._update_status()

    def _on_right_view_changed(self, scale, rel_x, rel_y):
        if self._syncing or not self.chk_link.isChecked():
            return
        self._syncing = True
        self.left_panel.view.apply_view(scale, rel_x, rel_y)
        self._syncing = False
        self._update_status()

    def _fit_both(self):
        self.left_panel.view.fit(emit=False)
        self.right_panel.view.fit(emit=False)
        self._update_status()

    def _one_to_one_both(self):
        self.left_panel.view.set_one_to_one(emit=False)
        self.right_panel.view.set_one_to_one(emit=False)
        self._update_status()

    def _zoom_both(self, factor):
        if self.chk_link.isChecked():
            self.left_panel.view.zoom_by(factor)
        else:
            self.left_panel.view.zoom_by(factor)
            self.right_panel.view.zoom_by(factor)
        self._update_status()

    def _turn_pair(self, delta):
        if not self.rule_text or not self.pairs:
            return
        self.pair_index = max(0, min(len(self.pairs) - 1, self.pair_index + delta))
        self._show_current()
        self._save_config()

    def _turn_side(self, side, delta):
        if self.mode == "A":
            self._turn_pair(delta)
            return
        if side == "L":
            if not self.left_files:
                return
            self.left_index = max(0, min(len(self.left_files) - 1, self.left_index + delta))
        else:
            if not self.right_files:
                return
            self.right_index = max(0, min(len(self.right_files) - 1, self.right_index + delta))
        self._show_current()
        self._save_config()

    def _activate_row(self, side, row):
        if self.mode == "B":
            if side == "L":
                self.left_index = row
            else:
                self.right_index = row
            self._show_current()
            self._save_config()
            return
        if not self.rule_text:
            self._show_single(side, row)
            return
        if 0 <= row < len(self.pairs):
            self.pair_index = row
            self._show_current()
            self._save_config()
        else:
            self._show_single(side, row)

    def _show_single(self, side, row):
        """模式 A 未设置规则，或点击了标红的未匹配项：只切换本侧图像。"""
        rows = self.left_rows if side == "L" else self.right_rows
        if not (0 <= row < len(rows)):
            return
        view = self.left_panel.view if side == "L" else self.right_panel.view
        view.load_path(rows[row][0])
        self._update_status()

    # ---- 刷新 ----
    def _refresh_all(self):
        self.left_files = scan_images(self.edt_left.text().strip())
        self.right_files = scan_images(self.edt_right.text().strip())
        self._rebuild_pairs()
        self._clamp_indices()
        self._refresh_lists()
        self._show_current()

    def _rebuild_pairs(self):
        self.pairs, self.unmatched_l, self.unmatched_r = [], [], []
        if not self.rule_text:
            return
        try:
            self.pairs, self.unmatched_l, self.unmatched_r = build_pairs(
                self.left_files, self.right_files, self.rule_text)
        except RuleError:
            self.pairs, self.unmatched_l, self.unmatched_r = [], [], []

    def _clamp_indices(self):
        self.pair_index = max(0, min(self.pair_index, max(len(self.pairs) - 1, 0)))
        self.left_index = max(0, min(self.left_index, max(len(self.left_files) - 1, 0)))
        self.right_index = max(0, min(self.right_index, max(len(self.right_files) - 1, 0)))

    def _refresh_lists(self):
        paired_mode = (self.mode == "A" and bool(self.rule_text))
        self.left_rows = []
        self.right_rows = []
        if paired_mode:
            for left, right in self.pairs:
                self.left_rows.append((left, right))
                self.right_rows.append((right, left))
            for path in self.unmatched_l:
                self.left_rows.append((path, None))
            for path in self.unmatched_r:
                self.right_rows.append((path, None))
        else:
            for path in self.left_files:
                self.left_rows.append((path, None))
            for path in self.right_files:
                self.right_rows.append((path, None))
        self.left_panel.fill_list(self.left_rows, paired_mode)
        self.right_panel.fill_list(self.right_rows, paired_mode)

        nav_enabled = not (self.mode == "A" and not self.rule_text)
        self.left_panel.set_nav_enabled(nav_enabled)
        self.right_panel.set_nav_enabled(nav_enabled)

        if self.rule_text:
            try:
                self.lbl_rule.setText("规则：" + PairRule(self.rule_text).describe())
            except RuleError as exc:
                self.lbl_rule.setText("规则无效：%s" % exc)
        else:
            self.lbl_rule.setText("规则：未设置（模式 A 需先设置，翻页已禁用）")

    def _show_current(self):
        left_view, right_view = self.left_panel.view, self.right_panel.view
        if self.mode == "A" and self.rule_text:
            total = len(self.pairs)
            if total and 0 <= self.pair_index < total:
                left, right = self.pairs[self.pair_index]
                left_view.load_path(left)
                right_view.load_path(right)
                selected = self.pair_index
            else:
                left_view.load_path(None)
                right_view.load_path(None)
                selected = -1
            self.left_panel.select_row(selected)
            self.right_panel.select_row(selected)
            self.left_panel.set_position(self.pair_index + 1 if total else 0, total)
            self.right_panel.set_position(self.pair_index + 1 if total else 0, total)
        elif self.mode == "A":
            left_view.load_path(self.left_files[0] if self.left_files else None)
            right_view.load_path(self.right_files[0] if self.right_files else None)
            self.left_panel.set_position(1 if self.left_files else 0, len(self.left_files))
            self.right_panel.set_position(1 if self.right_files else 0, len(self.right_files))
        else:
            left_view.load_path(self.left_files[self.left_index] if self.left_files else None)
            right_view.load_path(self.right_files[self.right_index] if self.right_files else None)
            self.left_panel.select_row(self.left_index if self.left_files else -1)
            self.right_panel.select_row(self.right_index if self.right_files else -1)
            self.left_panel.set_position(self.left_index + 1 if self.left_files else 0,
                                         len(self.left_files))
            self.right_panel.set_position(self.right_index + 1 if self.right_files else 0,
                                          len(self.right_files))
        self._update_status()

    def _update_status(self):
        parts = ["模式 %s" % self.mode]
        if self.mode == "A":
            if self.rule_text:
                try:
                    parts.append(PairRule(self.rule_text).describe())
                except RuleError:
                    parts.append("规则无效")
                parts.append("配对 %d/%d" % (self.pair_index + 1 if self.pairs else 0,
                                             len(self.pairs)))
                parts.append("未匹配 左%d / 右%d" % (len(self.unmatched_l),
                                                  len(self.unmatched_r)))
            else:
                parts.append("未设置配对规则，请先点『设置配对规则』")
        else:
            parts.append("左 %d/%d" % (self.left_index + 1 if self.left_files else 0,
                                       len(self.left_files)))
            parts.append("右 %d/%d" % (self.right_index + 1 if self.right_files else 0,
                                       len(self.right_files)))
        parts.append("左：" + self.left_panel.view.info_text())
        parts.append("右：" + self.right_panel.view.info_text())
        self.lbl_status.setText("   ｜   ".join(parts))


# ---------------------------------------------------------------------------
def main():
    _enable_high_dpi()
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("DualImageView")
    window = MainWindow()
    window.show()
    exec_fn = getattr(app, "exec", None) or getattr(app, "exec_", None)
    sys.exit(exec_fn())


if __name__ == "__main__":
    main()
