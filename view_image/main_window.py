# -*- coding: utf-8 -*-
"""
双栏图像查看器主窗口模块
支持单张与批量安全拷贝、剪切、成对同步勾选与现代化交互
"""

import os
import shutil
import sys
from pathlib import Path

from .core.config import ConfigManager
from .core.file_ops import (
    batch_copy_files,
    batch_move_files,
    copy_file_safe,
    move_file_safe,
)
from .core.qt_compat import (
    HORIZONTAL,
    ALIGN_CENTER,
    QColor,
    QShortcut,
    _dialog_exec,
    _enable_high_dpi,
    QtCore,
    QtGui,
    QtWidgets,
    QT_BINDING,
)
from .core.rules import PairRule, RuleError, build_pairs
from .core.scanner import scan_images
from .widgets.help_dialog import HelpDialog
from .widgets.rule_dialog import RuleDialog
from .widgets.side_panel import SidePanel
from .widgets.styles import DARK_THEME_QSS


class MainWindow(QtWidgets.QMainWindow):
    """
    双栏图像查看器主窗口
    """

    def __init__(self, config_path=None):
        super().__init__()
        self.setWindowTitle("ViewImage 双栏图像查看器  |  %s" % QT_BINDING)
        self.resize(1400, 880)
        self.setMinimumSize(960, 640)

        # 配置管理
        self.config_manager = ConfigManager(config_path)

        # 数据状态
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
        self._syncing_checks = False
        self._loading = False
        self._show_file_list = True

        self._build_ui()
        self._load_config()
        self._refresh_all()

    # =========================================================================
    # UI 构建
    # =========================================================================
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # ---------------- 顶部控制卡片区 ----------------
        top_card = QtWidgets.QFrame()
        top_card.setObjectName("TopCard")
        top_card.setStyleSheet("""
            #TopCard {
                background-color: #1a1d26;
                border: 1px solid #282d3b;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        card_layout = QtWidgets.QVBoxLayout(top_card)
        card_layout.setContentsMargins(6, 6, 6, 6)
        card_layout.setSpacing(6)

        # ---- 第 1 行：目录配置栏 ----
        row_paths = QtWidgets.QHBoxLayout()
        row_paths.setSpacing(8)

        # 左文件夹
        lbl_l = QtWidgets.QLabel("左文件夹:")
        lbl_l.setStyleSheet("color: #38bdf8; font-weight: bold;")
        self.edt_left = QtWidgets.QLineEdit()
        self.edt_left.setPlaceholderText("选择或输入左侧图像文件夹路径 (可直接拖拽文件夹到左画板)")
        btn_browse_l = QtWidgets.QPushButton("📁 浏览…")
        btn_browse_l.setProperty("small", "true")
        btn_browse_l.clicked.connect(lambda: self._browse("L"))
        self.edt_left.editingFinished.connect(self._on_dirs_changed)

        # 左右互换按钮
        btn_swap = QtWidgets.QPushButton("⇄ 互换")
        btn_swap.setProperty("small", "true")
        btn_swap.setToolTip("快速对调左文件夹与右文件夹")
        btn_swap.clicked.connect(self._swap_dirs)

        # 右文件夹
        lbl_r = QtWidgets.QLabel("右文件夹:")
        lbl_r.setStyleSheet("color: #34d399; font-weight: bold;")
        self.edt_right = QtWidgets.QLineEdit()
        self.edt_right.setPlaceholderText("选择或输入右侧图像文件夹路径 (可直接拖拽文件夹到右画板)")
        btn_browse_r = QtWidgets.QPushButton("📁 浏览…")
        btn_browse_r.setProperty("small", "true")
        btn_browse_r.clicked.connect(lambda: self._browse("R"))
        self.edt_right.editingFinished.connect(self._on_dirs_changed)

        # 输出目录
        lbl_out = QtWidgets.QLabel("输出目录:")
        lbl_out.setStyleSheet("color: #94a3b8; font-weight: bold;")
        self.edt_output = QtWidgets.QLineEdit()
        self.edt_output.setPlaceholderText("输出目录 (拷贝/剪切图像文件的目标存储路径)")
        btn_browse_output = QtWidgets.QPushButton("📁 浏览…")
        btn_browse_output.setProperty("small", "true")
        btn_browse_output.clicked.connect(self._browse_output)
        self.edt_output.editingFinished.connect(self._save_config)

        row_paths.addWidget(lbl_l)
        row_paths.addWidget(self.edt_left, 4)
        row_paths.addWidget(btn_browse_l)
        row_paths.addWidget(btn_swap)
        row_paths.addWidget(lbl_r)
        row_paths.addWidget(self.edt_right, 4)
        row_paths.addWidget(btn_browse_r)
        row_paths.addSpacing(6)
        row_paths.addWidget(lbl_out)
        row_paths.addWidget(self.edt_output, 3)
        row_paths.addWidget(btn_browse_output)
        card_layout.addLayout(row_paths)

        # ---- 第 2 行：模式与功能工具栏 ----
        row_toolbar = QtWidgets.QHBoxLayout()
        row_toolbar.setSpacing(8)

        # 模式切换单选按钮
        self.rb_mode_a = QtWidgets.QRadioButton("模式 A：配对同步翻页")
        self.rb_mode_b = QtWidgets.QRadioButton("模式 B：独立翻页")
        self.rb_mode_a.setChecked(True)
        self.rb_mode_a.setStyleSheet("font-weight: 500;")
        self.rb_mode_b.setStyleSheet("font-weight: 500;")

        mode_group = QtWidgets.QButtonGroup(self)
        mode_group.addButton(self.rb_mode_a)
        mode_group.addButton(self.rb_mode_b)
        self.rb_mode_a.clicked.connect(lambda: self._on_mode_clicked("A"))
        self.rb_mode_b.clicked.connect(lambda: self._on_mode_clicked("B"))

        row_toolbar.addWidget(self.rb_mode_a)
        row_toolbar.addWidget(self.rb_mode_b)
        row_toolbar.addSpacing(10)

        # 配对规则控制
        self.btn_rule = QtWidgets.QPushButton("⚙ 设置配对规则")
        self.btn_rule.setProperty("primary", "true")
        self.btn_rule.setProperty("small", "true")
        self.btn_rule.clicked.connect(self._open_rule_dialog)

        self.btn_clear_rule = QtWidgets.QPushButton("✕ 清除")
        self.btn_clear_rule.setProperty("small", "true")
        self.btn_clear_rule.clicked.connect(self._clear_rule)

        self.lbl_rule = QtWidgets.QLabel("规则：未设置")
        self.lbl_rule.setStyleSheet("""
            background-color: #242938;
            color: #93c5fd;
            border: 1px solid #333d54;
            border-radius: 4px;
            padding: 3px 8px;
            font-size: 11px;
        """)

        row_toolbar.addWidget(self.btn_rule)
        row_toolbar.addWidget(self.btn_clear_rule)
        row_toolbar.addWidget(self.lbl_rule)
        row_toolbar.addSpacing(10)

        # 模式 A 成对同步勾选开关
        self.chk_sync_check = QtWidgets.QCheckBox("成对联动勾选")
        self.chk_sync_check.setChecked(True)
        self.chk_sync_check.setToolTip("模式 A 下，在左侧或右侧勾选某项时，对应的配对项自动同步勾选")
        row_toolbar.addWidget(self.chk_sync_check)
        row_toolbar.addSpacing(10)

        # 视口控制
        self.chk_link = QtWidgets.QCheckBox("⇋ 视图联动")
        self.chk_link.setChecked(True)
        self.chk_link.setToolTip("缩放与平移完全保持两边同步")
        self.chk_link.toggled.connect(self._on_link_toggled)

        btn_fit = QtWidgets.QPushButton("适应窗口")
        btn_fit.setProperty("small", "true")
        btn_fit.setToolTip("双击任意画板也可自适应窗口 (Ctrl+0)")
        btn_fit.clicked.connect(lambda: self._fit_both())

        btn_100 = QtWidgets.QPushButton("1:1 原图")
        btn_100.setProperty("small", "true")
        btn_100.setToolTip("以原始 100% 像素大小显示 (Ctrl+1)")
        btn_100.clicked.connect(lambda: self._one_to_one_both())

        btn_zoom_in = QtWidgets.QPushButton("＋ 放大")
        btn_zoom_in.setProperty("small", "true")
        btn_zoom_in.clicked.connect(lambda: self._zoom_both(1.25))

        btn_zoom_out = QtWidgets.QPushButton("－ 缩小")
        btn_zoom_out.setProperty("small", "true")
        btn_zoom_out.clicked.connect(lambda: self._zoom_both(0.8))

        # 文件列表展开/收起
        self.btn_toggle_list = QtWidgets.QPushButton("📋 列表 (F3)")
        self.btn_toggle_list.setProperty("small", "true")
        self.btn_toggle_list.setToolTip("展开或收起侧栏文件列表与批量工具条 (快捷键：F3)")
        self.btn_toggle_list.clicked.connect(self._toggle_file_lists)

        # 帮助按钮
        btn_help = QtWidgets.QPushButton("❓ 帮助 (F1)")
        btn_help.setProperty("small", "true")
        btn_help.clicked.connect(self._open_help_dialog)

        row_toolbar.addWidget(self.chk_link)
        row_toolbar.addWidget(btn_fit)
        row_toolbar.addWidget(btn_100)
        row_toolbar.addWidget(btn_zoom_in)
        row_toolbar.addWidget(btn_zoom_out)
        row_toolbar.addStretch(1)
        row_toolbar.addWidget(self.btn_toggle_list)
        row_toolbar.addWidget(btn_help)

        card_layout.addLayout(row_toolbar)
        root.addWidget(top_card)

        # ---------------- 中间双栏画板区 ----------------
        self.left_panel = SidePanel("🟦 左视图", is_left=True)
        self.right_panel = SidePanel("🟩 右视图", is_left=False)

        splitter = QtWidgets.QSplitter(HORIZONTAL)
        splitter.addWidget(self.left_panel)
        splitter.addWidget(self.right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        # ---------------- 底部状态栏 ----------------
        status_bar = self.statusBar()

        self.lbl_status = QtWidgets.QLabel("")
        status_bar.addWidget(self.lbl_status, 1)

        # 鼠标像素级探针小部件 (带实时色彩色块)
        pixel_widget = QtWidgets.QWidget()
        p_layout = QtWidgets.QHBoxLayout(pixel_widget)
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.setSpacing(6)

        self.swatch_box = QtWidgets.QLabel()
        self.swatch_box.setFixedSize(14, 14)
        self.swatch_box.setStyleSheet("""
            background-color: transparent;
            border: 1px solid #475569;
            border-radius: 2px;
        """)

        self.lbl_pixel = QtWidgets.QLabel("光标 —")
        self.lbl_pixel.setStyleSheet("font-family: monospace; font-size: 11px;")
        p_layout.addWidget(self.swatch_box)
        p_layout.addWidget(self.lbl_pixel)

        status_bar.addPermanentWidget(pixel_widget)

        # ---------------- 信号绑定 ----------------
        # 单张拷贝与剪切
        self.left_panel.copyRequested.connect(lambda: self._copy_current("L"))
        self.right_panel.copyRequested.connect(lambda: self._copy_current("R"))
        self.left_panel.cutRequested.connect(lambda: self._cut_current("L"))
        self.right_panel.cutRequested.connect(lambda: self._cut_current("R"))

        # 批量拷贝与剪切
        self.left_panel.batchCopyRequested.connect(lambda paths: self._batch_copy(paths))
        self.right_panel.batchCopyRequested.connect(lambda paths: self._batch_copy(paths))
        self.left_panel.batchCutRequested.connect(lambda paths: self._batch_cut("L", paths))
        self.right_panel.batchCutRequested.connect(lambda paths: self._batch_cut("R", paths))

        # 成对同步勾选联动
        self.left_panel.checkedChanged.connect(lambda _: self._on_panel_checked_changed("L"))
        self.right_panel.checkedChanged.connect(lambda _: self._on_panel_checked_changed("R"))

        self.left_panel.folderDropped.connect(lambda p: self._on_folder_dropped("L", p))
        self.right_panel.folderDropped.connect(lambda p: self._on_folder_dropped("R", p))

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

        # Ctrl+S 与 Ctrl+C 拷贝当前悬停侧图片
        copy_shortcut_s = QShortcut(QtGui.QKeySequence("Ctrl+S"), self)
        copy_shortcut_s.activated.connect(self._copy_hovered)
        copy_shortcut_c = QShortcut(QtGui.QKeySequence("Ctrl+C"), self)
        copy_shortcut_c.activated.connect(self._copy_hovered)

        # Ctrl+X 剪切当前悬停侧图片
        cut_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+X"), self)
        cut_shortcut.activated.connect(self._cut_hovered)

        f1_shortcut = QShortcut(QtGui.QKeySequence("F1"), self)
        f1_shortcut.activated.connect(self._open_help_dialog)

        f3_shortcut = QShortcut(QtGui.QKeySequence("F3"), self)
        f3_shortcut.activated.connect(self._toggle_file_lists)

        fit_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+0"), self)
        fit_shortcut.activated.connect(self._fit_both)

        one_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+1"), self)
        one_shortcut.activated.connect(self._one_to_one_both)

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

    # =========================================================================
    # 配置管理
    # =========================================================================
    def _load_config(self):
        data = self.config_manager.load()
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
        self.pair_index = int(data.get("pair_index", 0) or 0)
        self.left_index = int(data.get("left_index", 0) or 0)
        self.right_index = int(data.get("right_index", 0) or 0)
        self._show_file_list = bool(data.get("show_file_list", True))
        self.left_panel.set_list_visible(self._show_file_list)
        self.right_panel.set_list_visible(self._show_file_list)
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
            "show_file_list": self._show_file_list,
        }
        self.config_manager.save(data)

    # =========================================================================
    # 动作与交互
    # =========================================================================
    def _browse(self, side):
        edit = self.edt_left if side == "L" else self.edt_right
        start = edit.text().strip()
        if not start or not os.path.isdir(start):
            start = os.path.expanduser("~")
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "选择%s侧图像文件夹" % ("左" if side == "L" else "右"), start)
        if folder:
            edit.setText(folder)
            self._on_dirs_changed()

    def _browse_output(self):
        start = self.edt_output.text().strip()
        if not start or not os.path.isdir(start):
            start = os.path.expanduser("~")
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "选择输出目标文件夹", start)
        if folder:
            self.edt_output.setText(folder)
            self._save_config()

    def _swap_dirs(self):
        """对调左右文件夹"""
        left_val = self.edt_left.text().strip()
        right_val = self.edt_right.text().strip()
        self.edt_left.setText(right_val)
        self.edt_right.setText(left_val)
        self._on_dirs_changed()

    def _on_folder_dropped(self, side, path):
        """响应拖入文件夹"""
        edit = self.edt_left if side == "L" else self.edt_right
        edit.setText(path)
        self._on_dirs_changed()

    # ---- 单张与批量拷贝/剪切 ----
    def _validate_output_dir(self):
        out_dir = self.edt_output.text().strip()
        if not out_dir or not os.path.isdir(out_dir):
            QtWidgets.QMessageBox.information(
                self, "提示", "请先在顶部设置有效的「输出目录」。")
            return None
        return out_dir

    def _copy_current(self, side):
        """拷贝当前侧图片至输出目录"""
        view = self.left_panel.view if side == "L" else self.right_panel.view
        source = view.current_path()
        if not source or not os.path.isfile(source):
            QtWidgets.QMessageBox.information(
                self, "提示", "当前%s侧没有可拷贝的图像。" % ("左" if side == "L" else "右"))
            return
        out_dir = self._validate_output_dir()
        if not out_dir:
            return
        try:
            target = copy_file_safe(source, out_dir)
            self.statusBar().showMessage("已拷贝至：%s" % target, 3500)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "拷贝失败", str(exc))

    def _cut_current(self, side):
        """剪切当前侧图片至输出目录，并自动跳转至下一张"""
        view = self.left_panel.view if side == "L" else self.right_panel.view
        source = view.current_path()
        if not source or not os.path.isfile(source):
            QtWidgets.QMessageBox.information(
                self, "提示", "当前%s侧没有可剪切的图像。" % ("左" if side == "L" else "右"))
            return
        out_dir = self._validate_output_dir()
        if not out_dir:
            return
        try:
            target = move_file_safe(source, out_dir)
            self.statusBar().showMessage("已剪切至：%s（自动跳转下一张）" % target, 3500)
            # 刷新文件列表并跳转
            self._refresh_all_after_removal()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "剪切失败", str(exc))

    def _save_current(self, side):
        """兼容旧接口"""
        self._copy_current(side)

    def _copy_hovered(self):
        self._copy_current(self._hover_side() or "L")

    def _cut_hovered(self):
        self._cut_current(self._hover_side() or "L")

    def _batch_copy(self, paths):
        """批量拷贝已勾选图像"""
        if not paths:
            return
        out_dir = self._validate_output_dir()
        if not out_dir:
            return
        successes, failures = batch_copy_files(paths, out_dir)
        msg = "批量拷贝完成：成功复制 %d 个文件。" % len(successes)
        if failures:
            msg += " 失败 %d 个文件：%s" % (len(failures), failures[0][1])
            QtWidgets.QMessageBox.warning(self, "批量拷贝完成（含错误）", msg)
        else:
            self.statusBar().showMessage(msg, 4000)
            QtWidgets.QMessageBox.information(self, "完成", msg)

    def _batch_cut(self, side, paths):
        """批量剪切已勾选图像"""
        if not paths:
            return
        out_dir = self._validate_output_dir()
        if not out_dir:
            return
        ret = QtWidgets.QMessageBox.question(
            self, "确认批量剪切",
            "确认将选中的 %d 个图像文件剪切（移动）到输出目录吗？\n"
            "文件将从原始文件夹中移出。" % len(paths),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes
        )
        if ret != QtWidgets.QMessageBox.Yes:
            return

        successes, failures = batch_move_files(paths, out_dir)
        msg = "批量剪切完成：成功移动 %d 个文件。" % len(successes)
        if failures:
            msg += " 失败 %d 个文件：%s" % (len(failures), failures[0][1])
            QtWidgets.QMessageBox.warning(self, "批量剪切完成（含错误）", msg)
        else:
            self.statusBar().showMessage(msg, 4000)
            QtWidgets.QMessageBox.information(self, "完成", msg)

        # 刷新视图列表
        self._refresh_all_after_removal()

    def _refresh_all_after_removal(self):
        """文件移动/删除后重新扫描并就绪下一张"""
        self.left_files = scan_images(self.edt_left.text().strip())
        self.right_files = scan_images(self.edt_right.text().strip())
        self._rebuild_pairs()
        self._clamp_indices()
        self._refresh_lists()
        self._show_current()

    # ---- 成对勾选联动 ----
    def _on_panel_checked_changed(self, source_side):
        if not self.chk_sync_check.isChecked() or self._syncing_checks:
            return
        if self.mode != "A" or not self.rule_text or not self.pairs:
            return

        self._syncing_checks = True
        source_panel = self.left_panel if source_side == "L" else self.right_panel
        target_panel = self.right_panel if source_side == "L" else self.left_panel

        checked_paths = {str(p) for p in source_panel.get_checked_paths()}
        target_indices = set()

        for idx, (l_path, r_path) in enumerate(self.pairs):
            match_path = str(l_path) if source_side == "L" else str(r_path)
            if match_path in checked_paths:
                target_indices.add(idx)

        target_panel.set_checked_indices(target_indices)
        self._syncing_checks = False

    def _on_pixel_hovered(self, side, data):
        if data is None:
            self.lbl_pixel.setText("光标 —")
            self.swatch_box.setStyleSheet("background-color: transparent; border: 1px solid #475569;")
            return
        x, y, gray, red, green, blue = data
        hex_color = "#%02x%02x%02x" % (red, green, blue)
        self.swatch_box.setStyleSheet("background-color: %s; border: 1px solid #94a3b8;" % hex_color)
        self.lbl_pixel.setText(
            "%s (%d, %d) ｜ 灰度 %d ｜ RGB(%d,%d,%d) %s" % (
                "左" if side == "L" else "右",
                x, y, gray, red, green, blue, hex_color.upper()))

    def _on_dirs_changed(self):
        self._save_config()
        self._refresh_all()

    def _on_mode_clicked(self, mode):
        self.mode = mode
        self.chk_sync_check.setEnabled(mode == "A")
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

    def _toggle_file_lists(self):
        self._show_file_list = not self._show_file_list
        self.left_panel.set_list_visible(self._show_file_list)
        self.right_panel.set_list_visible(self._show_file_list)
        self.btn_toggle_list.setText("📋 列表 (%s)" % ("隐藏" if self._show_file_list else "展开"))
        self._save_config()

    def _open_help_dialog(self):
        dialog = HelpDialog(self)
        _dialog_exec(dialog)

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
        panel = self.left_panel if side == "L" else self.right_panel
        path = rows[row][0]
        panel.view.load_path(path)
        panel.update_filename(path)
        self._update_status()

    # =========================================================================
    # 数据刷新与视图展示
    # =========================================================================
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
                self.lbl_rule.setStyleSheet("""
                    background-color: #1e3a5f;
                    color: #93c5fd;
                    border: 1px solid #2563eb;
                    border-radius: 4px;
                    padding: 3px 8px;
                    font-size: 11px;
                """)
            except RuleError as exc:
                self.lbl_rule.setText("规则无效：%s" % exc)
                self.lbl_rule.setStyleSheet("""
                    background-color: #451a1a;
                    color: #fca5a5;
                    border: 1px solid #ef4444;
                    border-radius: 4px;
                    padding: 3px 8px;
                    font-size: 11px;
                """)
        else:
            self.lbl_rule.setText("规则：未设置（模式 A 需先设置，翻页已禁用）")
            self.lbl_rule.setStyleSheet("""
                background-color: #242938;
                color: #94a3b8;
                border: 1px solid #333d54;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
            """)

    def _show_current(self):
        left_view, right_view = self.left_panel.view, self.right_panel.view
        if self.mode == "A" and self.rule_text:
            total = len(self.pairs)
            if total and 0 <= self.pair_index < total:
                left, right = self.pairs[self.pair_index]
                left_view.load_path(left)
                right_view.load_path(right)
                self.left_panel.update_filename(left)
                self.right_panel.update_filename(right)
                selected = self.pair_index
            else:
                left_view.load_path(None)
                right_view.load_path(None)
                self.left_panel.update_filename(None)
                self.right_panel.update_filename(None)
                selected = -1
            self.left_panel.select_row(selected)
            self.right_panel.select_row(selected)
            self.left_panel.set_position(self.pair_index + 1 if total else 0, total)
            self.right_panel.set_position(self.pair_index + 1 if total else 0, total)
        elif self.mode == "A":
            left_path = self.left_files[0] if self.left_files else None
            right_path = self.right_files[0] if self.right_files else None
            left_view.load_path(left_path)
            right_view.load_path(right_path)
            self.left_panel.update_filename(left_path)
            self.right_panel.update_filename(right_path)
            self.left_panel.set_position(1 if self.left_files else 0, len(self.left_files))
            self.right_panel.set_position(1 if self.right_files else 0, len(self.right_files))
        else:
            left_path = self.left_files[self.left_index] if self.left_files else None
            right_path = self.right_files[self.right_index] if self.right_files else None
            left_view.load_path(left_path)
            right_view.load_path(right_path)
            self.left_panel.update_filename(left_path)
            self.right_panel.update_filename(right_path)
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
                parts.append("未设置配对规则，请点「设置配对规则」")
        else:
            parts.append("左 %d/%d" % (self.left_index + 1 if self.left_files else 0,
                                       len(self.left_files)))
            parts.append("右 %d/%d" % (self.right_index + 1 if self.right_files else 0,
                                       len(self.right_files)))
        parts.append("左：" + self.left_panel.view.info_text())
        parts.append("右：" + self.right_panel.view.info_text())
        self.lbl_status.setText("   ｜   ".join(parts))


def main():
    _enable_high_dpi()
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("DualImageView")
    app.setStyleSheet(DARK_THEME_QSS)
    window = MainWindow()
    window.show()
    exec_fn = getattr(app, "exec", None) or getattr(app, "exec_", None)
    sys.exit(exec_fn())
