# -*- coding: utf-8 -*-
"""
Qt 绑定兼容层：优先 PyQt5，其次 PySide6 / PyQt6。
提供在不同 Qt 版本间统一的枚举访问和辅助函数。
"""

import sys

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
                "未找到 Qt 绑定。请在 Python 环境中安装 PyQt5、PySide6 或 PyQt6。\n"
                "原始错误：%s" % exc
            )

QColor = QtGui.QColor
QPainter = QtGui.QPainter
QPixmap = QtGui.QPixmap
QImage = QtGui.QImage
QRectF = QtCore.QRectF
QPointF = QtCore.QPointF
QRect = QtCore.QRect
QSize = QtCore.QSize


def _qt_const(*paths):
    """在 Qt / Qt.XXX 两种命名空间下解析枚举常量（处理 Qt5 与 Qt6 枚举作用域差异）。"""
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
RIGHT_BUTTON = _qt_const("MouseButton.RightButton", "RightButton")
MID_BUTTON = _qt_const("MouseButton.MiddleButton", "MiddleButton")

ALIGN_CENTER = _qt_const("AlignmentFlag.AlignCenter", "AlignCenter")
ALIGN_LEFT = _qt_const("AlignmentFlag.AlignLeft", "AlignLeft")
ALIGN_RIGHT = _qt_const("AlignmentFlag.AlignRight", "AlignRight")
ALIGN_VCENTER = _qt_const("AlignmentFlag.AlignVCenter", "AlignVCenter")

HORIZONTAL = _qt_const("Orientation.Horizontal", "Horizontal")
VERTICAL = _qt_const("Orientation.Vertical", "Vertical")

CURSOR_OPEN_HAND = _qt_const("CursorShape.OpenHandCursor", "OpenHandCursor")
CURSOR_CLOSED_HAND = _qt_const("CursorShape.ClosedHandCursor", "ClosedHandCursor")
CURSOR_CROSS = _qt_const("CursorShape.CrossCursor", "CrossCursor")
CURSOR_ARROW = _qt_const("CursorShape.ArrowCursor", "ArrowCursor")

PEN_NO_PEN = _qt_const("PenStyle.NoPen", "NoPen")
DASH_LINE = _qt_const("PenStyle.DashLine", "DashLine")
SOLID_LINE = _qt_const("PenStyle.SolidLine", "SolidLine")

ITEM_IS_USER_CHECKABLE = _qt_const("ItemFlag.ItemIsUserCheckable", "ItemIsUserCheckable")
ITEM_IS_SELECTABLE = _qt_const("ItemFlag.ItemIsSelectable", "ItemIsSelectable")
ITEM_IS_ENABLED = _qt_const("ItemFlag.ItemIsEnabled", "ItemIsEnabled")

CHECK_STATE_CHECKED = _qt_const("CheckState.Checked", "Checked")
CHECK_STATE_UNCHECKED = _qt_const("CheckState.Unchecked", "Unchecked")

ELIDE_MIDDLE = _qt_const("TextElideMode.ElideMiddle", "ElideMiddle")

# QShortcut 在 Qt5 属于 QtWidgets，Qt6 移到了 QtGui
QShortcut = getattr(QtWidgets, "QShortcut", None) or QtGui.QShortcut

# QAction 与 QActionGroup 在 Qt5 属于 QtWidgets，Qt6 移到了 QtGui
QAction = getattr(QtGui, "QAction", None) or getattr(QtWidgets, "QAction", None)
QActionGroup = getattr(QtGui, "QActionGroup", None) or getattr(QtWidgets, "QActionGroup", None)

_SMOOTH_PIXMAP_HINT = getattr(QPainter, "SmoothPixmapTransform", None)
if _SMOOTH_PIXMAP_HINT is None:
    _render_hint = getattr(QPainter, "RenderHint", None)
    _SMOOTH_PIXMAP_HINT = getattr(_render_hint, "SmoothPixmapTransform", None)

_ANTIALIASING_HINT = getattr(QPainter, "Antialiasing", None)
if _ANTIALIASING_HINT is None:
    _render_hint = getattr(QPainter, "RenderHint", None)
    _ANTIALIASING_HINT = getattr(_render_hint, "Antialiasing", None)


def _image_format(name):
    """QImage 格式枚举在 Qt5 / Qt6 下命名空间不同。"""
    value = getattr(QImage, name, None)
    if value is None:
        holder = getattr(QImage, "Format", None)
        value = getattr(holder, name, None) if holder is not None else None
    return value


FORMAT_GRAY8 = _image_format("Format_Grayscale8")
FORMAT_RGB888 = _image_format("Format_RGB888")
FORMAT_ARGB32 = _image_format("Format_ARGB32")


def _mouse_pos(event):
    """Qt5 用 pos()，Qt6 用 position()。返回 (float(x), float(y))。"""
    if hasattr(event, "position"):
        p = event.position()
        return float(p.x()), float(p.y())
    p = event.pos()
    return float(p.x()), float(p.y())


def _dialog_exec(dialog):
    """统一 exec() / exec_() 调用。"""
    fn = getattr(dialog, "exec", None) or getattr(dialog, "exec_", None)
    return fn()


# 对话框返回值枚举兼容（Qt5 下为 QDialog.Accepted / Rejected，Qt6 下位于 QDialog.DialogCode）
DIALOG_ACCEPTED = getattr(QtWidgets.QDialog, "Accepted", None)
if DIALOG_ACCEPTED is None:
    DIALOG_ACCEPTED = getattr(getattr(QtWidgets.QDialog, "DialogCode", None), "Accepted", 1)

DIALOG_REJECTED = getattr(QtWidgets.QDialog, "Rejected", None)
if DIALOG_REJECTED is None:
    DIALOG_REJECTED = getattr(getattr(QtWidgets.QDialog, "DialogCode", None), "Rejected", 0)

# 为 QtWidgets.QDialog 注入 Accepted / Rejected 属性，兼容 PyQt6 等新绑定
if not hasattr(QtWidgets.QDialog, "Accepted"):
    QtWidgets.QDialog.Accepted = DIALOG_ACCEPTED
if not hasattr(QtWidgets.QDialog, "Rejected"):
    QtWidgets.QDialog.Rejected = DIALOG_REJECTED

# QMessageBox 标准按钮与返回值兼容（PyQt6 枚举移至 StandardButton）
_StandardButton = getattr(QtWidgets.QMessageBox, "StandardButton", None)
if _StandardButton is not None:
    for _btn in ("Yes", "No", "Ok", "Cancel", "Close", "Apply", "Reset", "Save", "Open"):
        if not hasattr(QtWidgets.QMessageBox, _btn) and hasattr(_StandardButton, _btn):
            setattr(QtWidgets.QMessageBox, _btn, getattr(_StandardButton, _btn))

MSGBOX_YES = getattr(QtWidgets.QMessageBox, "Yes", None)
MSGBOX_NO = getattr(QtWidgets.QMessageBox, "No", None)
MSGBOX_OK = getattr(QtWidgets.QMessageBox, "Ok", None)
MSGBOX_CANCEL = getattr(QtWidgets.QMessageBox, "Cancel", None)


def _enable_high_dpi():
    """启用高分屏缩放支持。"""
    try:
        attr = getattr(Qt, "AA_EnableHighDpiScaling", None)
        if attr is None:
            aa = getattr(Qt, "ApplicationAttribute", None)
            attr = getattr(aa, "AA_EnableHighDpiScaling", None) if aa else None
        if attr is not None and hasattr(QtWidgets.QApplication, "setAttribute"):
            QtWidgets.QApplication.setAttribute(attr, True)
    except Exception:
        pass
    try:
        attr2 = getattr(Qt, "AA_UseHighDpiPixmaps", None)
        if attr2 is None:
            aa = getattr(Qt, "ApplicationAttribute", None)
            attr2 = getattr(aa, "AA_UseHighDpiPixmaps", None) if aa else None
        if attr2 is not None and hasattr(QtWidgets.QApplication, "setAttribute"):
            QtWidgets.QApplication.setAttribute(attr2, True)
    except Exception:
        pass
