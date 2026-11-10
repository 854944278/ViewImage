# -*- coding: utf-8 -*-
"""
双栏图像查看器主窗口模块
极致轻量、流线型单行顶栏、侧边抽屉文件列表与按需图像调色
支持目标目录重名提醒决策与安全递增重命名
"""

import os
import shutil
import sys
from pathlib import Path

from .core.config import ConfigManager
from .core.file_ops import (
    POLICY_OVERWRITE,
    POLICY_RENAME,
    POLICY_SKIP,
    batch_copy_files,
    batch_move_files,
    check_conflicts,
    copy_file_safe,
    move_file_safe,
)
from .core.qt_compat import (
    HORIZONTAL,
    VERTICAL,
    ALIGN_CENTER,
    DIALOG_ACCEPTED,
    TOOLBUTTON_MENU_BUTTON_POPUP,
    QColor,
    QShortcut,
    QAction,
    QActionGroup,
    _dialog_exec,
    _enable_high_dpi,
    QtCore,
    QtGui,
    QtWidgets,
    QT_BINDING,
)
from .core.rules import PairRule, RuleError, build_pairs
from .core.scanner import scan_images
from .widgets.adjustment_bar import ImageAdjustmentBar
from .widgets.conflict_dialog import prompt_batch_conflict, prompt_single_conflict
from .widgets.help_dialog import HelpDialog
from .widgets.image_view import ImageView
from .widgets.path_dialog import PathSettingsDialog
from .widgets.rule_dialog import RuleDialog
from .widgets.side_panel import SidePanel
from .widgets.sidebar_drawer import SidebarDrawer
from .widgets.styles import DARK_THEME_QSS


class MainWindow(QtWidgets.QMainWindow):
    """
    双栏图像查看器主窗口（极简工业版）
    """

    def __init__(self, config_path=None):
        super().__init__()
        setup_exception_hook()
        self.setWindowTitle("ViewImage 双栏图像查看器  |  %s" % QT_BINDING)
        self.resize(1400, 880)
        self.setMinimumSize(960, 600)

        # 配置管理
        self.config_manager = ConfigManager(config_path)

        # 核心数据状态
        self.left_files = []
        self.right_files = []
        self.pairs = []
        self.unmatched_l = []
        self.unmatched_r = []
        self.rule_text = ""
        self.mode = "A"
        self.pair_index = 0
        self.left_index = 0
        self.right_index = 0
        self._syncing = False
        self._loading = False
        self._show_sidebar = True
        self._show_file_list = True
        self.layout_orientation = "horizontal"

        # 兼容性属性（保留供测试套件与脚本访问）
        self.edt_left = QtWidgets.QLineEdit()
        self.edt_right = QtWidgets.QLineEdit()
        self.edt_output = QtWidgets.QLineEdit()

        self._build_ui()
        self._load_config()
        self._refresh_all()

    # =========================================================================
    # UI 构建
    # =========================================================================
    def _build_ui(self):
        self._build_menu_bar()

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ---------------- 1. 极简单行流线型顶栏 ----------------
        top_bar = QtWidgets.QFrame()
        top_bar.setObjectName("TopRibbon")
        top_bar.setStyleSheet("""
            #TopRibbon {
                background-color: #1a1d26;
                border: 1px solid #282d3b;
                border-radius: 6px;
                padding: 2px 6px;
            }
        """)
        top_layout = QtWidgets.QHBoxLayout(top_bar)
        top_layout.setContentsMargins(4, 3, 4, 3)
        top_layout.setSpacing(6)

        # 左区：路径胶囊与模式
        self.btn_paths = QtWidgets.QPushButton("📁 路径设置 ▾")
        self.btn_paths.setProperty("small", "true")
        self.btn_paths.setToolTip("点击设置左/右源文件夹与输出目录")
        self.btn_paths.clicked.connect(self._open_path_dialog)

        self.btn_swap = QtWidgets.QPushButton("⇄")
        self.btn_swap.setProperty("small", "true")
        self.btn_swap.setFixedWidth(26)
        self.btn_swap.setToolTip("一键对调左文件夹与右文件夹")
        self.btn_swap.clicked.connect(self._swap_dirs)

        self.rb_mode_a = QtWidgets.QRadioButton("模式 A (同步)")
        self.rb_mode_b = QtWidgets.QRadioButton("模式 B (独立)")
        self.rb_mode_a.setChecked(True)
        self.rb_mode_a.setStyleSheet("font-weight: 500;")
        self.rb_mode_b.setStyleSheet("font-weight: 500;")
        mode_grp = QtWidgets.QButtonGroup(self)
        mode_grp.addButton(self.rb_mode_a)
        mode_grp.addButton(self.rb_mode_b)
        self.rb_mode_a.clicked.connect(lambda: self._on_mode_clicked("A"))
        self.rb_mode_b.clicked.connect(lambda: self._on_mode_clicked("B"))

        # 规则指示胶囊
        self.btn_rule = QtWidgets.QPushButton("规则: 未设置")
        self.btn_rule.setProperty("small", "true")
        self.btn_rule.setStyleSheet("""
            background-color: #1e293b;
            color: #93c5fd;
            border: 1px solid #334155;
            border-radius: 4px;
            padding: 2px 8px;
            font-size: 11px;
        """)
        self.btn_rule.clicked.connect(self._open_rule_dialog)

        top_layout.addWidget(self.btn_paths)
        top_layout.addWidget(self.btn_swap)
        top_layout.addSpacing(4)
        top_layout.addWidget(self.rb_mode_a)
        top_layout.addWidget(self.rb_mode_b)
        top_layout.addWidget(self.btn_rule)

        top_layout.addStretch(1)

        # 中区：全局统一导航器
        self.btn_prev = QtWidgets.QPushButton("◀ 上一张")
        self.btn_prev.setProperty("small", "true")
        self.btn_prev.clicked.connect(lambda: self._turn_global(-1))

        self.lbl_pos = QtWidgets.QLabel("0 / 0")
        self.lbl_pos.setStyleSheet("""
            background-color: #272c3b;
            color: #f1f5f9;
            border-radius: 4px;
            padding: 3px 10px;
            font-weight: bold;
            font-size: 12px;
        """)

        self.btn_next = QtWidgets.QPushButton("下一张 ▶")
        self.btn_next.setProperty("small", "true")
        self.btn_next.clicked.connect(lambda: self._turn_global(1))

        top_layout.addWidget(self.btn_prev)
        top_layout.addWidget(self.lbl_pos)
        top_layout.addWidget(self.btn_next)

        top_layout.addStretch(1)

        # 右区：视口、分屏排列切换、单张拷贝/剪切与功能开关
        self.btn_layout = QtWidgets.QPushButton("◫ 左右")
        self.btn_layout.setProperty("small", "true")
        self.btn_layout.setToolTip("切换图像窗口排列：左右分屏 ⇄ 上下分屏 (Alt+L)")
        self.btn_layout.clicked.connect(self._toggle_layout_orientation)

        self.chk_link = QtWidgets.QCheckBox("⇋ 联动")
        self.chk_link.setChecked(True)
        self.chk_link.setToolTip("缩放与平移两边保持绝对同步")
        self.chk_link.toggled.connect(self._on_link_toggled)

        btn_fit = QtWidgets.QPushButton("适应")
        btn_fit.setProperty("small", "true")
        btn_fit.setToolTip("自适应窗口 (Ctrl+0)")
        btn_fit.clicked.connect(self._fit_both)

        # 单张操作按钮（支持直达主点击，并提供下拉独立选择左侧/右侧操作）
        self.btn_copy = QtWidgets.QToolButton()
        self.btn_copy.setText("📋 拷贝")
        self.btn_copy.setProperty("small", "true")
        self.btn_copy.setToolTip("拷贝当前悬停侧（或左侧）图像至输出目录 (Ctrl+C / Ctrl+S)；右侧下拉可单独选择拷贝左图或右图")
        self.btn_copy.setPopupMode(TOOLBUTTON_MENU_BUTTON_POPUP)
        self.btn_copy.clicked.connect(self._copy_hovered)

        menu_btn_copy = QtWidgets.QMenu(self.btn_copy)
        menu_btn_copy.addAction("📋 拷贝当前悬停图像 (Ctrl+C / Ctrl+S)", self._copy_hovered)
        self.act_btn_copy_l = menu_btn_copy.addAction("🟦 仅拷贝左侧图像 (Shift+C)", self._copy_left)
        self.act_btn_copy_r = menu_btn_copy.addAction("🟩 仅拷贝右侧图像 (Alt+C)", self._copy_right)
        self.btn_copy.setMenu(menu_btn_copy)

        self.btn_cut = QtWidgets.QToolButton()
        self.btn_cut.setText("✂ 剪切")
        self.btn_cut.setProperty("small", "true")
        self.btn_cut.setToolTip("剪切当前悬停侧（或左侧）图像至输出目录并跳转 (Ctrl+X)；右侧下拉可单独选择剪切左图或右图")
        self.btn_cut.setPopupMode(TOOLBUTTON_MENU_BUTTON_POPUP)
        self.btn_cut.clicked.connect(self._cut_hovered)

        menu_btn_cut = QtWidgets.QMenu(self.btn_cut)
        menu_btn_cut.addAction("✂ 剪切当前悬停图像 (Ctrl+X)", self._cut_hovered)
        self.act_btn_cut_l = menu_btn_cut.addAction("🟦 仅剪切左侧图像 (Shift+X)", self._cut_left)
        self.act_btn_cut_r = menu_btn_cut.addAction("🟩 仅剪切右侧图像 (Alt+X)", self._cut_right)
        self.btn_cut.setMenu(menu_btn_cut)

        # 调色条与侧栏开关
        self.btn_adj = QtWidgets.QPushButton("🎛 调色")
        self.btn_adj.setProperty("small", "true")
        self.btn_adj.setToolTip("展开/收起图像黑白与亮度对比度调色条")
        self.btn_adj.clicked.connect(self._toggle_adjustment_bar)

        self.btn_toggle_sidebar = QtWidgets.QPushButton("📑 列表 (F3)")
        self.btn_toggle_sidebar.setProperty("small", "true")
        self.btn_toggle_sidebar.setToolTip("展开/收起侧边文件列表与批量管理栏 (F3)")
        self.btn_toggle_sidebar.clicked.connect(self._toggle_sidebar)

        top_layout.addWidget(self.btn_layout)
        top_layout.addWidget(self.chk_link)
        top_layout.addWidget(btn_fit)
        top_layout.addSpacing(4)
        top_layout.addWidget(self.btn_copy)
        top_layout.addWidget(self.btn_cut)
        top_layout.addSpacing(4)
        top_layout.addWidget(self.btn_adj)
        top_layout.addWidget(self.btn_toggle_sidebar)

        root.addWidget(top_bar)

        # ---------------- 2. 按需折叠的图像调色条 ----------------
        self.adj_bar = ImageAdjustmentBar()
        self.adj_bar.setVisible(False)
        self.adj_bar.adjustmentChanged.connect(self._on_adjustment_changed)
        self.adj_bar.resetRequested.connect(self._on_adjustment_reset)
        root.addWidget(self.adj_bar)

        # ---------------- 3. 主体工作区分割器 ----------------
        self.main_splitter = QtWidgets.QSplitter(HORIZONTAL)

        # 左侧边抽屉列表
        self.sidebar = SidebarDrawer()
        self.sidebar.itemActivated.connect(self._on_sidebar_item_activated)
        self.sidebar.batchCopyRequested.connect(self._batch_copy)
        self.sidebar.batchCutRequested.connect(self._batch_cut)
        self.sidebar.closeRequested.connect(self._toggle_sidebar)
        self.main_splitter.addWidget(self.sidebar)

        # 右侧双栏沉浸式画板
        self.canvas_splitter = QtWidgets.QSplitter(HORIZONTAL)
        self.left_view = ImageView()
        self.right_view = ImageView()
        self.left_view.set_panel_info("🟦 左", is_left=True)
        self.right_view.set_panel_info("🟩 右", is_left=False)

        self.canvas_splitter.addWidget(self.left_view)
        self.canvas_splitter.addWidget(self.right_view)
        self.canvas_splitter.setStretchFactor(0, 1)
        self.canvas_splitter.setStretchFactor(1, 1)

        self.main_splitter.addWidget(self.canvas_splitter)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        root.addWidget(self.main_splitter, 1)

        # 兼容性代理（维持旧代码与测试的 win.left_panel / win.right_panel 访问）
        self.left_panel = SidePanel("🟦 左视图", is_left=True)
        self.right_panel = SidePanel("🟩 右视图", is_left=False)
        self.left_panel.view = self.left_view
        self.right_panel.view = self.right_view
        self.left_panel.batchCutRequested.connect(self._batch_cut)
        self.right_panel.batchCutRequested.connect(self._batch_cut)
        self.left_panel.batchCopyRequested.connect(self._batch_copy)
        self.right_panel.batchCopyRequested.connect(self._batch_copy)

        # ---------------- 4. 底部状态栏 ----------------
        status_bar = self.statusBar()
        self.lbl_status = QtWidgets.QLabel("")
        status_bar.addWidget(self.lbl_status, 1)

        pixel_widget = QtWidgets.QWidget()
        p_layout = QtWidgets.QHBoxLayout(pixel_widget)
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.setSpacing(6)
        self.swatch_box = QtWidgets.QLabel()
        self.swatch_box.setFixedSize(14, 14)
        self.swatch_box.setStyleSheet("background-color: transparent; border: 1px solid #475569; border-radius: 2px;")
        self.lbl_pixel = QtWidgets.QLabel("光标 —")
        self.lbl_pixel.setStyleSheet("font-family: monospace; font-size: 11px;")
        p_layout.addWidget(self.swatch_box)
        p_layout.addWidget(self.lbl_pixel)
        status_bar.addPermanentWidget(pixel_widget)

        # ---------------- 信号绑定 ----------------
        self.left_view.viewChanged.connect(self._on_left_view_changed)
        self.right_view.viewChanged.connect(self._on_right_view_changed)
        self.left_view.pixelHovered.connect(lambda data: self._on_pixel_hovered("L", data))
        self.right_view.pixelHovered.connect(lambda data: self._on_pixel_hovered("R", data))
        self.left_view.folderDropped.connect(lambda p: self._on_folder_dropped("L", p))
        self.right_view.folderDropped.connect(lambda p: self._on_folder_dropped("R", p))
        self.left_view.copyRequested.connect(self._copy_left)
        self.left_view.cutRequested.connect(self._cut_left)
        self.right_view.copyRequested.connect(self._copy_right)
        self.right_view.cutRequested.connect(self._cut_right)

        self.edt_left.editingFinished.connect(self._on_dirs_changed)
        self.edt_right.editingFinished.connect(self._on_dirs_changed)
        self.edt_output.editingFinished.connect(self._save_config)

        self._build_shortcuts()

    def _build_menu_bar(self):
        menu_bar = self.menuBar()

        # ---------------- 文件菜单 ----------------
        menu_file = menu_bar.addMenu("文件(&F)")

        act_paths = menu_file.addAction("📁 路径设置(&P)...")
        act_paths.setShortcut("Ctrl+O")
        act_paths.setStatusTip("设置左/右源文件夹与输出目录")
        act_paths.triggered.connect(self._open_path_dialog)

        act_swap = menu_file.addAction("⇄ 对调左右目录(&S)")
        act_swap.setStatusTip("对调左目录与右目录")
        act_swap.triggered.connect(self._swap_dirs)

        menu_file.addSeparator()

        act_refresh = menu_file.addAction("🔄 刷新图像列表(&R)")
        act_refresh.setShortcut("F5")
        act_refresh.setStatusTip("重新扫描左右目录中的图像")
        act_refresh.triggered.connect(self._refresh_all)

        menu_file.addSeparator()

        act_exit = menu_file.addAction("退出(&X)")
        act_exit.setShortcut("Ctrl+Q")
        act_exit.setStatusTip("退出 ViewImage")
        act_exit.triggered.connect(self.close)

        # ---------------- 视图菜单 ----------------
        menu_view = menu_bar.addMenu("视图(&V)")

        # 排列布局子菜单
        menu_layout = menu_view.addMenu("◫ 分屏排列(&L)")
        self.layout_action_group = QActionGroup(self)

        self.act_layout_h = menu_layout.addAction("◫ 左右排列 (水平分屏)(&H)")
        self.act_layout_h.setCheckable(True)
        self.act_layout_h.setChecked(True)
        self.act_layout_h.setShortcut("Alt+H")
        self.act_layout_h.triggered.connect(lambda: self.set_layout_orientation("horizontal"))
        self.layout_action_group.addAction(self.act_layout_h)

        self.act_layout_v = menu_layout.addAction("⬒ 上下排列 (垂直分屏)(&V)")
        self.act_layout_v.setCheckable(True)
        self.act_layout_v.setShortcut("Alt+V")
        self.act_layout_v.triggered.connect(lambda: self.set_layout_orientation("vertical"))
        self.layout_action_group.addAction(self.act_layout_v)

        menu_layout.addSeparator()

        act_toggle_layout = menu_layout.addAction("🔀 快速切换排列方向")
        act_toggle_layout.setShortcut("Alt+L")
        act_toggle_layout.triggered.connect(self._toggle_layout_orientation)

        menu_view.addSeparator()

        self.act_link = menu_view.addAction("⇋ 缩放与平移双侧联动")
        self.act_link.setCheckable(True)
        self.act_link.setChecked(True)
        self.act_link.toggled.connect(self._on_link_toggled)

        act_fit = menu_view.addAction("自适应窗口(&F)")
        act_fit.triggered.connect(self._fit_both)

        act_100 = menu_view.addAction("1:1 原始比例(&1)")
        act_100.triggered.connect(self._one_to_one_both)

        act_zoom_in = menu_view.addAction("放大(&I)")
        act_zoom_in.triggered.connect(lambda: self._zoom_both(1.25))

        act_zoom_out = menu_view.addAction("缩小(&O)")
        act_zoom_out.triggered.connect(lambda: self._zoom_both(0.8))

        menu_view.addSeparator()

        self.act_sidebar = menu_view.addAction("📑 侧边文件列表(&S)")
        self.act_sidebar.setCheckable(True)
        self.act_sidebar.setChecked(True)
        self.act_sidebar.triggered.connect(self._toggle_sidebar)

        self.act_adj = menu_view.addAction("🎛 图像调色工具栏(&A)")
        self.act_adj.setCheckable(True)
        self.act_adj.setChecked(False)
        self.act_adj.triggered.connect(self._toggle_adjustment_bar)

        # ---------------- 操作菜单 ----------------
        menu_ops = menu_bar.addMenu("操作(&O)")

        self.mode_action_group = QActionGroup(self)
        self.act_mode_a = menu_ops.addAction("模式 A (成对同步翻页)")
        self.act_mode_a.setCheckable(True)
        self.act_mode_a.setChecked(True)
        self.act_mode_a.triggered.connect(lambda: self._set_mode("A"))
        self.mode_action_group.addAction(self.act_mode_a)

        self.act_mode_b = menu_ops.addAction("模式 B (双侧独立翻页)")
        self.act_mode_b.setCheckable(True)
        self.act_mode_b.setChecked(False)
        self.act_mode_b.triggered.connect(lambda: self._set_mode("B"))
        self.mode_action_group.addAction(self.act_mode_b)

        menu_ops.addSeparator()

        act_rule = menu_ops.addAction("📐 设置配对规则(&R)...")
        act_rule.triggered.connect(self._open_rule_dialog)

        menu_ops.addSeparator()

        # 拷贝子菜单
        menu_copy = menu_ops.addMenu("📋 拷贝图像(&C)")
        act_copy_hover = menu_copy.addAction("📋 拷贝当前悬停图像")
        act_copy_hover.setShortcut("Ctrl+C")
        act_copy_hover.triggered.connect(self._copy_hovered)

        self.act_menu_copy_l = menu_copy.addAction("🟦 仅拷贝左侧图像")
        self.act_menu_copy_l.setShortcut("Shift+C")
        self.act_menu_copy_l.triggered.connect(self._copy_left)

        self.act_menu_copy_r = menu_copy.addAction("🟩 仅拷贝右侧图像")
        self.act_menu_copy_r.setShortcut("Alt+C")
        self.act_menu_copy_r.triggered.connect(self._copy_right)

        # 剪切子菜单
        menu_cut = menu_ops.addMenu("✂ 剪切图像(&X)")
        act_cut_hover = menu_cut.addAction("✂ 剪切当前悬停图像")
        act_cut_hover.setShortcut("Ctrl+X")
        act_cut_hover.triggered.connect(self._cut_hovered)

        self.act_menu_cut_l = menu_cut.addAction("🟦 仅剪切左侧图像")
        self.act_menu_cut_l.setShortcut("Shift+X")
        self.act_menu_cut_l.triggered.connect(self._cut_left)

        self.act_menu_cut_r = menu_cut.addAction("🟩 仅剪切右侧图像")
        self.act_menu_cut_r.setShortcut("Alt+X")
        self.act_menu_cut_r.triggered.connect(self._cut_right)

        # ---------------- 帮助菜单 ----------------
        menu_help = menu_bar.addMenu("帮助(&H)")

        act_help = menu_help.addAction("📖 快捷键与使用说明(&H)...")
        act_help.triggered.connect(self._open_help_dialog)

        act_about = menu_help.addAction("ℹ️ 关于 ViewImage(&A)")
        act_about.triggered.connect(self._show_about_dialog)

    def _build_shortcuts(self):
        bindings = (
            ("Left", -1, "R"), ("Right", 1, "R"),
            ("Up", -1, "R"), ("Down", 1, "R"),
            ("Shift+Left", -1, "L"), ("Shift+Right", 1, "L"),
            ("Shift+Up", -1, "L"), ("Shift+Down", 1, "L"),
            ("PgUp", -1, None), ("PgDown", 1, None),
        )
        for key, delta, side in bindings:
            shortcut = QShortcut(QtGui.QKeySequence(key), self)
            shortcut.activated.connect(lambda d=delta, s=side: self._shortcut_page(d, s))

        # 拷贝快捷键 Ctrl+C / Ctrl+S / Shift+C / Alt+C
        QShortcut(QtGui.QKeySequence("Ctrl+S"), self).activated.connect(self._copy_hovered)
        QShortcut(QtGui.QKeySequence("Ctrl+C"), self).activated.connect(self._copy_hovered)
        QShortcut(QtGui.QKeySequence("Shift+C"), self).activated.connect(self._copy_left)
        QShortcut(QtGui.QKeySequence("Alt+C"), self).activated.connect(self._copy_right)

        # 剪切快捷键 Ctrl+X / Shift+X / Alt+X
        QShortcut(QtGui.QKeySequence("Ctrl+X"), self).activated.connect(self._cut_hovered)
        QShortcut(QtGui.QKeySequence("Shift+X"), self).activated.connect(self._cut_left)
        QShortcut(QtGui.QKeySequence("Alt+X"), self).activated.connect(self._cut_right)

        # 布局切换快捷键
        QShortcut(QtGui.QKeySequence("Alt+L"), self).activated.connect(self._toggle_layout_orientation)
        QShortcut(QtGui.QKeySequence("Alt+H"), self).activated.connect(lambda: self.set_layout_orientation("horizontal"))
        QShortcut(QtGui.QKeySequence("Alt+V"), self).activated.connect(lambda: self.set_layout_orientation("vertical"))

        # 辅助功能快捷键
        QShortcut(QtGui.QKeySequence("F1"), self).activated.connect(self._open_help_dialog)
        QShortcut(QtGui.QKeySequence("F3"), self).activated.connect(self._toggle_sidebar)
        QShortcut(QtGui.QKeySequence("Ctrl+0"), self).activated.connect(self._fit_both)
        QShortcut(QtGui.QKeySequence("Ctrl+1"), self).activated.connect(self._one_to_one_both)

    def _shortcut_page(self, delta, side):
        focus = QtWidgets.QApplication.focusWidget()
        if isinstance(focus, (QtWidgets.QLineEdit, QtWidgets.QTextEdit)):
            return
        if self.mode == "A":
            self._turn_pair(delta)
            return
        target = side or self._hover_side()
        self._turn_side(target or "R", delta)

    def _hover_side(self):
        global_pos = QtGui.QCursor.pos()
        for side, view in (("L", self.left_view), ("R", self.right_view)):
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
        self._show_sidebar = bool(data.get("show_file_list", True))
        self._show_file_list = self._show_sidebar
        self.sidebar.setVisible(self._show_sidebar)
        self.set_layout_orientation(data.get("layout_orientation", "horizontal"), save=False)
        self._loading = False
        self._update_path_button_tooltip()

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
            "show_file_list": self._show_sidebar,
            "layout_orientation": getattr(self, "layout_orientation", "horizontal"),
        }
        self.config_manager.save(data)
        self._update_path_button_tooltip()

    def _update_path_button_tooltip(self):
        l_name = os.path.basename(self.edt_left.text().strip()) or "未设"
        r_name = os.path.basename(self.edt_right.text().strip()) or "未设"
        out_name = os.path.basename(self.edt_output.text().strip()) or "未设"
        tip = "左目录: %s\n右目录: %s\n输出目录: %s" % (
            self.edt_left.text().strip(), self.edt_right.text().strip(), self.edt_output.text().strip())
        self.btn_paths.setToolTip(tip)
        self.btn_paths.setText("📁 [%s ⇄ %s ➔ %s]" % (l_name, r_name, out_name))

    # =========================================================================
    # 动作与交互
    # =========================================================================
    def _open_path_dialog(self):
        dlg = PathSettingsDialog(
            self,
            left_dir=self.edt_left.text().strip(),
            right_dir=self.edt_right.text().strip(),
            output_dir=self.edt_output.text().strip()
        )
        if _dialog_exec(dlg) == DIALOG_ACCEPTED and dlg.result_paths:
            self.edt_left.setText(dlg.result_paths["left_dir"])
            self.edt_right.setText(dlg.result_paths["right_dir"])
            self.edt_output.setText(dlg.result_paths["output_dir"])
            self._on_dirs_changed()

    def _swap_dirs(self):
        l = self.edt_left.text().strip()
        r = self.edt_right.text().strip()
        self.edt_left.setText(r)
        self.edt_right.setText(l)
        self._on_dirs_changed()

    def _on_folder_dropped(self, side, path):
        if side == "L":
            self.edt_left.setText(path)
        else:
            self.edt_right.setText(path)
        self._on_dirs_changed()

    def set_layout_orientation(self, orientation, save=True):
        """
        设置图像窗口分屏排列方式：
        'horizontal' (左右分屏) 或 'vertical' (上下分屏)
        """
        if orientation not in ("horizontal", "vertical"):
            orientation = "horizontal"
        self.layout_orientation = orientation

        if orientation == "vertical":
            self.canvas_splitter.setOrientation(VERTICAL)
            self.left_view.set_panel_info("🟦 上", is_left=True)
            self.right_view.set_panel_info("🟩 下", is_left=False)
            if hasattr(self, "btn_layout"):
                self.btn_layout.setText("⬒ 上下")
                self.btn_layout.setToolTip("当前布局：上下排列。点击切换为左右排列 (Alt+L)")
            if hasattr(self, "act_layout_v"):
                self.act_layout_v.setChecked(True)
            if hasattr(self, "act_layout_h"):
                self.act_layout_h.setChecked(False)
        else:
            self.canvas_splitter.setOrientation(HORIZONTAL)
            self.left_view.set_panel_info("🟦 左", is_left=True)
            self.right_view.set_panel_info("🟩 右", is_left=False)
            if hasattr(self, "btn_layout"):
                self.btn_layout.setText("◫ 左右")
                self.btn_layout.setToolTip("当前布局：左右排列。点击切换为上下排列 (Alt+L)")
            if hasattr(self, "act_layout_h"):
                self.act_layout_h.setChecked(True)
            if hasattr(self, "act_layout_v"):
                self.act_layout_v.setChecked(False)

        self.canvas_splitter.setSizes([1, 1])

        if hasattr(self, "sidebar") and hasattr(self.sidebar, "set_layout_orientation"):
            self.sidebar.set_layout_orientation(orientation)

        side_l = "上" if orientation == "vertical" else "左"
        side_r = "下" if orientation == "vertical" else "右"
        if hasattr(self, "act_btn_copy_l"):
            self.act_btn_copy_l.setText(f"🟦 仅拷贝{side_l}侧图像 (Shift+C)")
        if hasattr(self, "act_btn_copy_r"):
            self.act_btn_copy_r.setText(f"🟩 仅拷贝{side_r}侧图像 (Alt+C)")
        if hasattr(self, "act_btn_cut_l"):
            self.act_btn_cut_l.setText(f"🟦 仅剪切{side_l}侧图像 (Shift+X)")
        if hasattr(self, "act_btn_cut_r"):
            self.act_btn_cut_r.setText(f"🟩 仅剪切{side_r}侧图像 (Alt+X)")
        if hasattr(self, "act_menu_copy_l"):
            self.act_menu_copy_l.setText(f"🟦 仅拷贝{side_l}侧图像")
        if hasattr(self, "act_menu_copy_r"):
            self.act_menu_copy_r.setText(f"🟩 仅拷贝{side_r}侧图像")
        if hasattr(self, "act_menu_cut_l"):
            self.act_menu_cut_l.setText(f"🟦 仅剪切{side_l}侧图像")
        if hasattr(self, "act_menu_cut_r"):
            self.act_menu_cut_r.setText(f"🟩 仅剪切{side_r}侧图像")

        # 若处于自适应状态，重新计算视图以适配新视口宽高比
        if self.left_view.is_loaded() and getattr(self.left_view, "_fit_mode", False):
            self.left_view.fit(emit=False)
        if self.right_view.is_loaded() and getattr(self.right_view, "_fit_mode", False):
            self.right_view.fit(emit=False)

        if save:
            self._save_config()

    def _toggle_layout_orientation(self):
        """快捷切换排列方向"""
        new_orient = "vertical" if self.layout_orientation == "horizontal" else "horizontal"
        self.set_layout_orientation(new_orient, save=True)
        tip = "上下排列" if new_orient == "vertical" else "左右排列"
        self.statusBar().showMessage(f"已切换图像排列方式为：{tip}", 2500)

    def _toggle_sidebar(self):
        self._show_sidebar = not self._show_sidebar
        self._show_file_list = self._show_sidebar
        self.sidebar.setVisible(self._show_sidebar)
        self.btn_toggle_sidebar.setText("📑 列表 (%s)" % ("收起" if self._show_sidebar else "展开"))
        if hasattr(self, "act_sidebar") and self.act_sidebar.isChecked() != self._show_sidebar:
            self.act_sidebar.setChecked(self._show_sidebar)
        self._save_config()

    def _toggle_file_lists(self):
        """兼容接口"""
        self._toggle_sidebar()

    def _toggle_adjustment_bar(self):
        vis = not self.adj_bar.isVisible()
        self.adj_bar.setVisible(vis)
        self.btn_adj.setText("🎛 调色 (%s)" % ("收起" if vis else "展开"))
        if hasattr(self, "act_adj") and self.act_adj.isChecked() != vis:
            self.act_adj.setChecked(vis)

    def _on_adjustment_changed(self, target, gray, brightness, contrast):
        if target in ("BOTH", "L"):
            self.left_view.set_gray(gray)
            self.left_view.set_brightness(brightness)
            self.left_view.set_contrast(contrast)
        if target in ("BOTH", "R"):
            self.right_view.set_gray(gray)
            self.right_view.set_brightness(brightness)
            self.right_view.set_contrast(contrast)

    def _on_adjustment_reset(self, target):
        if target in ("BOTH", "L"):
            self.left_view.reset_display()
        if target in ("BOTH", "R"):
            self.right_view.reset_display()

    # ---- 拷贝与剪切（含重复文件提醒与处理） ----
    def _validate_output_dir(self):
        out_dir = self.edt_output.text().strip()
        if not out_dir or not os.path.isdir(out_dir):
            QtWidgets.QMessageBox.information(
                self, "提示", "请先在「路径设置」中设置有效的输出目录。")
            self._open_path_dialog()
            return None
        return out_dir

    def _copy_current(self, side, policy=None):
        view = self.left_view if side == "L" else self.right_view
        source = view.current_path()
        if not source or not os.path.isfile(source):
            QtWidgets.QMessageBox.information(
                self, "提示", "当前%s侧没有可拷贝的图像。" % ("左" if side == "L" else "右"))
            return
        out_dir = self._validate_output_dir()
        if not out_dir:
            return

        filename = os.path.basename(source)
        exact_target = os.path.join(out_dir, filename)

        # 重名检测与提醒（若外部未指定 policy）
        if policy is None:
            if os.path.exists(exact_target):
                policy = prompt_single_conflict(self, filename, action="拷贝")
                if not policy:
                    return
            else:
                policy = POLICY_RENAME

        try:
            status, target = copy_file_safe(source, out_dir, policy=policy)
            msg = "已拷贝至：%s" % target if status != "skipped" else "已跳过：%s" % filename
            self.statusBar().showMessage(msg, 3500)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "拷贝失败", str(exc))

    def _cut_current(self, side, policy=None):
        view = self.left_view if side == "L" else self.right_view
        source = view.current_path()
        if not source or not os.path.isfile(source):
            QtWidgets.QMessageBox.information(
                self, "提示", "当前%s侧没有可剪切的图像。" % ("左" if side == "L" else "右"))
            return
        out_dir = self._validate_output_dir()
        if not out_dir:
            return

        filename = os.path.basename(source)
        exact_target = os.path.join(out_dir, filename)

        # 重名检测与提醒（若外部未指定 policy）
        if policy is None:
            if os.path.exists(exact_target):
                policy = prompt_single_conflict(self, filename, action="剪切")
                if not policy:
                    return
            else:
                policy = POLICY_RENAME

        try:
            status, target = move_file_safe(source, out_dir, policy=policy)
            if status != "skipped":
                self.statusBar().showMessage("已剪切至：%s（自动跳转下一张）" % target, 3500)
                self._refresh_all_after_removal()
            else:
                self.statusBar().showMessage("已跳过剪切：%s" % filename, 3500)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "剪切失败", str(exc))

    def _save_current(self, side, policy=None):
        self._copy_current(side, policy=policy)

    def _copy_hovered(self):
        self._copy_current(self._hover_side() or "L")

    def _cut_hovered(self):
        self._cut_current(self._hover_side() or "L")

    def _copy_left(self):
        self._copy_current("L")

    def _copy_right(self):
        self._copy_current("R")

    def _cut_left(self):
        self._cut_current("L")

    def _cut_right(self):
        self._cut_current("R")

    def _batch_copy(self, *args, **kwargs):
        # 兼容单参数 (paths) 与双参数 (side, paths)
        prompt = kwargs.get("prompt", True)
        if len(args) >= 2 and isinstance(args[0], str) and (isinstance(args[1], (list, set, tuple)) or args[1] is None):
            paths = list(args[1]) if args[1] else []
            policy = args[2] if len(args) > 2 else kwargs.get("policy", None)
        elif len(args) >= 1:
            paths = list(args[0]) if args[0] else []
            policy = args[1] if len(args) > 1 else kwargs.get("policy", None)
        else:
            paths = list(kwargs.get("paths", []))
            policy = kwargs.get("policy", None)

        if not paths:
            if prompt:
                QtWidgets.QMessageBox.information(self, "提示", "请先在列表中勾选要拷贝的图像。")
            return
        out_dir = self._validate_output_dir()
        if not out_dir:
            return

        # 批量重名预检
        try:
            if policy is None:
                conflicts = check_conflicts(paths, out_dir)
                if conflicts:
                    policy = prompt_batch_conflict(self, conflicts, action="拷贝")
                    if not policy:
                        return
                else:
                    policy = POLICY_RENAME
        except Exception as exc:
            if prompt:
                QtWidgets.QMessageBox.warning(self, "预检异常", f"预检目标冲突时出错：{exc}")
            return

        try:
            successes, skipped, failures = batch_copy_files(paths, out_dir, policy=policy)
        except Exception as exc:
            if prompt:
                QtWidgets.QMessageBox.critical(self, "批量拷贝异常", f"执行批量拷贝时出错：{exc}")
            return

        msg = "批量拷贝完成：成功 %d 个" % len(successes)
        if skipped:
            msg += "，跳过 %d 个" % len(skipped)
        if failures:
            msg += "，失败 %d 个" % len(failures)
            err_details = "\n".join(["• %s: %s" % (os.path.basename(str(p)), err) for p, err in failures[:5]])
            if len(failures) > 5:
                err_details += "\n... 等共 %d 个错误" % len(failures)
            if prompt:
                QtWidgets.QMessageBox.warning(self, "批量拷贝完成（含错误）", "%s\n\n失败明细：\n%s" % (msg, err_details))
        else:
            self.statusBar().showMessage(msg, 4000)
            if prompt:
                QtWidgets.QMessageBox.information(self, "完成", msg)

    def _batch_cut(self, *args, **kwargs):
        # 兼容单参数 (paths) 与双参数 (side, paths)
        prompt = kwargs.get("prompt", True)
        if len(args) >= 2 and isinstance(args[0], str) and (isinstance(args[1], (list, set, tuple)) or args[1] is None):
            paths = list(args[1]) if args[1] else []
            policy = args[2] if len(args) > 2 else kwargs.get("policy", None)
        elif len(args) >= 1:
            paths = list(args[0]) if args[0] else []
            policy = args[1] if len(args) > 1 else kwargs.get("policy", None)
        else:
            paths = list(kwargs.get("paths", []))
            policy = kwargs.get("policy", None)

        if not paths:
            if prompt:
                QtWidgets.QMessageBox.information(self, "提示", "请先在列表中勾选要剪切的图像。")
            return
        out_dir = self._validate_output_dir()
        if not out_dir:
            return

        # 批量重名预检与用户确认
        try:
            if policy is None:
                conflicts = check_conflicts(paths, out_dir)
                if conflicts:
                    policy = prompt_batch_conflict(self, conflicts, action="剪切")
                    if not policy:
                        return
                else:
                    ret = QtWidgets.QMessageBox.question(
                        self, "确认批量剪切",
                        "确认将选中的 %d 个图像文件剪切（移动）到输出目录吗？\n"
                        "文件将从原始文件夹中移出。" % len(paths),
                        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                        QtWidgets.QMessageBox.Yes
                    )
                    if ret != QtWidgets.QMessageBox.Yes:
                        return
                    policy = POLICY_RENAME
        except Exception as exc:
            if prompt:
                QtWidgets.QMessageBox.warning(self, "预检异常", f"准备批量剪切时发生错误：{exc}")
            return

        # 在剪切移动前，若当前左右视口中展示的图片正是待剪切的文件之一，
        # 预先安全释放视图路径与内存，杜绝 Windows OS 文件锁 (WinError 32) 或悬空句柄导致的异常
        try:
            path_set = {os.path.abspath(str(p)) for p in paths}
            if self.left_view.current_path() and os.path.abspath(str(self.left_view.current_path())) in path_set:
                self.left_view.unload()
            if self.right_view.current_path() and os.path.abspath(str(self.right_view.current_path())) in path_set:
                self.right_view.unload()
        except Exception:
            pass

        # 执行移动
        try:
            successes, skipped, failures = batch_move_files(paths, out_dir, policy=policy)
        except Exception as exc:
            if prompt:
                QtWidgets.QMessageBox.critical(self, "批量剪切异常", f"执行文件剪切时发生异常：{exc}")
            self._refresh_all_after_removal()
            return

        # 核心防闪退逻辑：在弹出完成提示弹窗之前，立即刷新并同步列表与内部索引状态，
        # 避免模态弹窗事件循环中主窗口与视口处于非一致状态
        try:
            self._refresh_all_after_removal()
        except Exception as exc:
            import traceback
            traceback.print_exc()

        msg = "批量剪切完成：成功移动 %d 个" % len(successes)
        if skipped:
            msg += "，跳过 %d 个" % len(skipped)
        if failures:
            msg += "，失败 %d 个" % len(failures)
            err_details = "\n".join(["• %s: %s" % (os.path.basename(str(p)), err) for p, err in failures[:5]])
            if len(failures) > 5:
                err_details += "\n... 等共 %d 个错误" % len(failures)
            if prompt:
                QtWidgets.QMessageBox.warning(self, "批量剪切完成（含错误）", "%s\n\n失败明细：\n%s" % (msg, err_details))
        else:
            self.statusBar().showMessage(msg, 4000)
            if prompt:
                QtWidgets.QMessageBox.information(self, "完成", msg)

    def _refresh_all_after_removal(self):
        try:
            self.left_files = scan_images(self.edt_left.text().strip())
            self.right_files = scan_images(self.edt_right.text().strip())
            self._rebuild_pairs()
            self._clamp_indices()
            self._refresh_sidebar()
            self._show_current()
        except Exception as exc:
            import traceback
            traceback.print_exc()

    # ---- 导航控制 ----
    def _turn_global(self, delta):
        if self.mode == "A":
            self._turn_pair(delta)
        else:
            target = self._hover_side() or "R"
            self._turn_side(target, delta)

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

    def _on_sidebar_item_activated(self, row_type, raw_idx):
        if row_type == "PAIR":
            self.pair_index = raw_idx
            self._show_current()
            self._save_config()
        elif row_type == "L":
            self.left_index = raw_idx
            self._show_current()
            self._save_config()
        elif row_type == "R":
            self.right_index = raw_idx
            self._show_current()
            self._save_config()
        elif row_type == "UNMATCHED_L":
            if 0 <= raw_idx < len(self.unmatched_l):
                p = self.unmatched_l[raw_idx]
                self.left_view.load_path(p)
                self.left_view.set_image_title(p.name, str(p))
                self._update_status()
        elif row_type == "UNMATCHED_R":
            if 0 <= raw_idx < len(self.unmatched_r):
                p = self.unmatched_r[raw_idx]
                self.right_view.load_path(p)
                self.right_view.set_image_title(p.name, str(p))
                self._update_status()

    # ---- 视口变换与联动 ----
    def _on_link_toggled(self, checked):
        if hasattr(self, "act_link") and self.act_link.isChecked() != checked:
            self.act_link.setChecked(checked)
        if hasattr(self, "chk_link") and self.chk_link.isChecked() != checked:
            self.chk_link.setChecked(checked)
        if checked and not self._loading:
            scale, rel_x, rel_y = self.left_view.current_view()
            self.right_view.apply_view(scale, rel_x, rel_y)
        self._save_config()

    def _on_left_view_changed(self, scale, rel_x, rel_y):
        if self._syncing or not self.chk_link.isChecked():
            return
        self._syncing = True
        self.right_view.apply_view(scale, rel_x, rel_y)
        self._syncing = False
        self._update_status()

    def _on_right_view_changed(self, scale, rel_x, rel_y):
        if self._syncing or not self.chk_link.isChecked():
            return
        self._syncing = True
        self.left_view.apply_view(scale, rel_x, rel_y)
        self._syncing = False
        self._update_status()

    def _fit_both(self):
        self.left_view.fit(emit=False)
        self.right_view.fit(emit=False)
        self._update_status()

    def _one_to_one_both(self):
        self.left_view.set_one_to_one(emit=False)
        self.right_view.set_one_to_one(emit=False)
        self._update_status()

    def _zoom_both(self, factor):
        if self.chk_link.isChecked():
            self.left_view.zoom_by(factor)
        else:
            self.left_view.zoom_by(factor)
            self.right_view.zoom_by(factor)
        self._update_status()

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

    def _set_mode(self, mode):
        if mode == "A":
            self.rb_mode_a.setChecked(True)
        else:
            self.rb_mode_b.setChecked(True)
        self._on_mode_clicked(mode)

    def _on_mode_clicked(self, mode):
        self.mode = mode
        if hasattr(self, "act_mode_a"):
            self.act_mode_a.setChecked(mode == "A")
        if hasattr(self, "act_mode_b"):
            self.act_mode_b.setChecked(mode == "B")
        self._refresh_all()
        self._save_config()

    def _open_rule_dialog(self):
        if not self.left_files or not self.right_files:
            QtWidgets.QMessageBox.information(
                self, "提示", "请先在两侧选择包含图像的文件夹。")
            self._open_path_dialog()
            return
        dialog = RuleDialog(self, self.left_files, self.right_files, self.rule_text)
        _dialog_exec(dialog)
        if dialog.result_rule:
            self.rule_text = dialog.result_rule
            self.pair_index = 0
            self._refresh_all()
            self._save_config()

    def _open_help_dialog(self):
        dialog = HelpDialog(self)
        _dialog_exec(dialog)

    def _show_about_dialog(self):
        QtWidgets.QMessageBox.about(
            self,
            "关于 ViewImage",
            "<h3>ViewImage 双栏图像查看器</h3>"
            "<p>轻量、极速的高清工业级图像对比与质检工具。</p>"
            "<p><b>核心特性：</b></p>"
            "<ul>"
            "<li><b>分屏布局自由切换</b>：支持左右分屏 (水平) 与上下分屏 (垂直) 动态无缝切换 (Alt+L)</li>"
            "<li><b>双浏览模式</b>：模式 A 智能配对同步翻页，模式 B 双侧独立翻页</li>"
            "<li><b>无锁二进制加载</b>：杜绝 Windows 文件占用锁死，随时剪切/移动/删除不闪退</li>"
            "<li><b>安全文件流转</b>：单张与批量防覆盖递增重命名、目标冲突预检与决策</li>"
            "<li><b>实时物理取色</b>：光标悬停原图像素坐标、灰度值、RGB 色值及物理色块探针</li>"
            "</ul>"
            "<p>当前 Qt 绑定：<b>%s</b></p>" % QT_BINDING,
        )

    # =========================================================================
    # 数据刷新与展示
    # =========================================================================
    def _refresh_all(self):
        self.left_files = scan_images(self.edt_left.text().strip())
        self.right_files = scan_images(self.edt_right.text().strip())
        self._rebuild_pairs()
        self._clamp_indices()
        self._refresh_sidebar()
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

    def _refresh_sidebar(self):
        self.sidebar.set_data(
            self.mode, self.rule_text, self.pairs,
            self.unmatched_l, self.unmatched_r,
            self.left_files, self.right_files
        )

        # 同步填充兼容代理的 left_panel 与 right_panel
        paired_mode = (self.mode == "A" and bool(self.rule_text))
        left_rows = []
        right_rows = []
        if paired_mode:
            for l, r in self.pairs:
                left_rows.append((l, r))
                right_rows.append((r, l))
            for p in self.unmatched_l:
                left_rows.append((p, None))
            for p in self.unmatched_r:
                right_rows.append((p, None))
        else:
            for p in self.left_files:
                left_rows.append((p, None))
            for p in self.right_files:
                right_rows.append((p, None))
        self.left_panel.fill_list(left_rows, paired_mode)
        self.right_panel.fill_list(right_rows, paired_mode)

        if self.rule_text:
            try:
                desc = PairRule(self.rule_text).describe()
                self.btn_rule.setText("规则: " + desc)
                self.btn_rule.setStyleSheet("""
                    background-color: #1e3a5f;
                    color: #93c5fd;
                    border: 1px solid #2563eb;
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-size: 11px;
                """)
            except RuleError:
                self.btn_rule.setText("规则无效")
        else:
            self.btn_rule.setText("规则: 未设置")
            self.btn_rule.setStyleSheet("""
                background-color: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            """)

    def _show_current(self):
        if self.mode == "A" and self.rule_text:
            total = len(self.pairs)
            if total and 0 <= self.pair_index < total:
                left, right = self.pairs[self.pair_index]
                self.left_view.load_path(left)
                self.right_view.load_path(right)
                self.left_view.set_image_title(left.name, str(left))
                self.right_view.set_image_title(right.name, str(right))
                self.sidebar.select_row("PAIR", self.pair_index)
            else:
                self.left_view.load_path(None)
                self.right_view.load_path(None)
                self.left_view.set_image_title("", "")
                self.right_view.set_image_title("", "")
                self.sidebar.select_row("PAIR", -1)
            self.lbl_pos.setText("%d / %d" % (self.pair_index + 1 if total else 0, total))
        elif self.mode == "A":
            left_path = self.left_files[0] if self.left_files else None
            right_path = self.right_files[0] if self.right_files else None
            self.left_view.load_path(left_path)
            self.right_view.load_path(right_path)
            self.left_view.set_image_title(left_path.name if left_path else "", str(left_path) if left_path else "")
            self.right_view.set_image_title(right_path.name if right_path else "", str(right_path) if right_path else "")
            total_cnt = max(len(self.left_files), len(self.right_files), 0)
            self.lbl_pos.setText("%d / %d" % (1 if total_cnt else 0, total_cnt))
        else:
            left_path = self.left_files[self.left_index] if (self.left_files and 0 <= self.left_index < len(self.left_files)) else None
            right_path = self.right_files[self.right_index] if (self.right_files and 0 <= self.right_index < len(self.right_files)) else None
            self.left_view.load_path(left_path)
            self.right_view.load_path(right_path)
            self.left_view.set_image_title(left_path.name if left_path else "", str(left_path) if left_path else "")
            self.right_view.set_image_title(right_path.name if right_path else "", str(right_path) if right_path else "")
            self.sidebar.select_row("L", self.left_index if self.left_files else -1)
            self.lbl_pos.setText("左 %d/%d ｜ 右 %d/%d" % (
                self.left_index + 1 if self.left_files else 0, len(self.left_files),
                self.right_index + 1 if self.right_files else 0, len(self.right_files)
            ))
        self._update_status()

    def _update_status(self):
        parts = ["模式 %s" % self.mode]
        if self.mode == "A":
            if self.rule_text:
                try:
                    parts.append(PairRule(self.rule_text).describe())
                except RuleError:
                    parts.append("规则无效")
                parts.append("配对 %d/%d" % (self.pair_index + 1 if self.pairs else 0, len(self.pairs)))
                parts.append("未匹配 左%d / 右%d" % (len(self.unmatched_l), len(self.unmatched_r)))
            else:
                parts.append("未设置配对规则，请点「规则」进行配置")
        else:
            parts.append("左 %d/%d" % (self.left_index + 1 if self.left_files else 0, len(self.left_files)))
            parts.append("右 %d/%d" % (self.right_index + 1 if self.right_files else 0, len(self.right_files)))
        parts.append("左：" + self.left_view.info_text())
        parts.append("右：" + self.right_view.info_text())
        self.lbl_status.setText("   ｜   ".join(parts))


def setup_exception_hook():
    """
    安装全局未捕获异常捕获器，杜绝 Qt 槽函数未捕获异常导致的程序瞬间闪退。
    记录完整调用栈并通过友好弹窗提示用户。
    """
    old_hook = sys.excepthook

    def _custom_excepthook(exc_type, exc_value, exc_tb):
        import traceback
        lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        err_msg = "".join(lines)
        sys.stderr.write(err_msg)
        try:
            app = QtWidgets.QApplication.instance()
            if app:
                QtWidgets.QMessageBox.critical(
                    None,
                    "ViewImage 运行提示",
                    "程序运行中发生异常，已安全拦截并记录：\n\n%s\n\n如需排查请参考控制台日志。" % exc_value
                )
        except Exception:
            pass
        if old_hook and old_hook is not _custom_excepthook:
            try:
                old_hook(exc_type, exc_value, exc_tb)
            except Exception:
                pass

    sys.excepthook = _custom_excepthook


def main():
    _enable_high_dpi()
    setup_exception_hook()
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("DualImageView")
    app.setStyleSheet(DARK_THEME_QSS)
    window = MainWindow()
    window.show()
    exec_fn = getattr(app, "exec", None) or getattr(app, "exec_", None)
    sys.exit(exec_fn())
