# -*- coding: utf-8 -*-
"""
dual_image_viewer.py —— 双栏图像查看器与对比工具 (ViewImage)

模式 A（配对同步）：必须先在「设置配对规则」里手动挑 2 对对应图像，工具据此
    推断出文件名对应逻辑并展示成可编辑的规则表达式，确认保存后才自动配对；
    配对完成后左右同步翻页。未设置规则时不自动配对、翻页按钮禁用。
模式 B（独立翻页）：两侧各自维护文件列表与索引，各自独立翻页。

基础看图功能：滚轮以光标为中心缩放、左键拖动平移、适应窗口、1:1、放大/缩小、
    复位、状态栏、可折叠实时搜索文件列表、左右视图联动（可开关，默认开）。

扩展功能：把当前图像原样拷贝/保存到指定输出目录（重名自动加后缀，不覆盖）；
    左右各自独立的灰度开关与亮度/对比度滑块（仅显示层，不改原文件）；
    状态栏实时显示鼠标所在原图像素坐标、灰度值、RGB 色值及色彩预览色块。

启动方式：
    python dual_image_viewer.py

依赖：PyQt5 / PySide6 / PyQt6 + Python 标准库。
图像读取走 QPixmap / QImage，不依赖 Pillow / numpy / OpenCV。
配置自动保存在同目录 viewer_config.json。
"""

import os
import sys

# 将工程目录添加至 sys.path 以支持模块化导入
_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
if _CUR_DIR not in sys.path:
    sys.path.insert(0, _CUR_DIR)

from view_image.core.qt_compat import (
    QT_BINDING,
    QtCore,
    QtGui,
    QtWidgets,
    Qt,
    pyqtSignal,
    QColor,
    QPainter,
    QPixmap,
    QImage,
    QRectF,
    _qt_const,
    LEFT_BUTTON,
    ALIGN_CENTER,
    HORIZONTAL,
    VERTICAL,
    CURSOR_OPEN_HAND,
    CURSOR_CLOSED_HAND,
    QShortcut,
    _SMOOTH_PIXMAP_HINT,
    _image_format,
    FORMAT_GRAY8,
    FORMAT_RGB888,
    _mouse_pos,
    _dialog_exec,
    _enable_high_dpi,
    DIALOG_ACCEPTED,
    DIALOG_REJECTED,
    QAction,
    QActionGroup,
)

from view_image.core.scanner import (
    IMAGE_EXTS,
    natural_key,
    scan_images,
)

from view_image.core.rules import (
    RuleError,
    PairRule,
    build_pairs,
    common_prefix_len,
    common_suffix_len,
    longest_common_substring,
    strip_core,
    infer_rules,
)

from view_image.core.config import (
    ConfigManager,
    DEFAULT_CONFIG_NAME,
)

from view_image.core.file_ops import (
    POLICY_OVERWRITE,
    POLICY_RENAME,
    POLICY_SKIP,
    batch_copy_files,
    batch_move_files,
    check_conflicts,
    copy_file_safe,
    get_unique_target_path,
    move_file_safe,
)

from view_image.widgets.image_view import (
    ImageView,
    MIN_SCALE,
    MAX_SCALE,
)

from view_image.widgets.adjustment_bar import ImageAdjustmentBar
from view_image.widgets.conflict_dialog import (
    BatchConflictDialog,
    SingleConflictDialog,
    prompt_batch_conflict,
    prompt_single_conflict,
)
from view_image.widgets.help_dialog import HelpDialog
from view_image.widgets.path_dialog import PathSettingsDialog
from view_image.widgets.rule_dialog import RuleDialog
from view_image.widgets.side_panel import SidePanel
from view_image.widgets.sidebar_drawer import SidebarDrawer
from view_image.widgets.styles import DARK_THEME_QSS
from view_image.main_window import MainWindow, main, setup_exception_hook

CONFIG_NAME = DEFAULT_CONFIG_NAME

__all__ = [
    "QT_BINDING",
    "QtCore",
    "QtGui",
    "QtWidgets",
    "Qt",
    "pyqtSignal",
    "QColor",
    "QPainter",
    "QPixmap",
    "QImage",
    "QRectF",
    "LEFT_BUTTON",
    "ALIGN_CENTER",
    "HORIZONTAL",
    "VERTICAL",
    "CURSOR_OPEN_HAND",
    "CURSOR_CLOSED_HAND",
    "_mouse_pos",
    "_dialog_exec",
    "_enable_high_dpi",
    "DIALOG_ACCEPTED",
    "DIALOG_REJECTED",
    "QAction",
    "QActionGroup",
    "IMAGE_EXTS",
    "MIN_SCALE",
    "MAX_SCALE",
    "CONFIG_NAME",
    "get_unique_target_path",
    "check_conflicts",
    "copy_file_safe",
    "move_file_safe",
    "batch_copy_files",
    "batch_move_files",
    "natural_key",
    "scan_images",
    "RuleError",
    "PairRule",
    "build_pairs",
    "common_prefix_len",
    "common_suffix_len",
    "longest_common_substring",
    "strip_core",
    "infer_rules",
    "ImageView",
    "SidePanel",
    "RuleDialog",
    "HelpDialog",
    "DARK_THEME_QSS",
    "MainWindow",
    "setup_exception_hook",
    "main",
]

if __name__ == "__main__":
    main()
