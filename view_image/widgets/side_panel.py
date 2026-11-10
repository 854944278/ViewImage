# -*- coding: utf-8 -*-
"""
单侧图像面板：集成视口、导航控制、滤镜调节、带复选框的文件列表及批量拷贝/剪切工具条
"""

import os
from pathlib import Path

from ..core.qt_compat import (
    CHECK_STATE_CHECKED,
    CHECK_STATE_UNCHECKED,
    HORIZONTAL,
    ITEM_IS_USER_CHECKABLE,
    QColor,
    QtCore,
    QtGui,
    QtWidgets,
    pyqtSignal,
)
from .image_view import ImageView


class SidePanel(QtWidgets.QWidget):
    """
    单侧图像视图面板（左侧 / 右侧）：
      - 顶部操作条：侧别标识、当前文件名显示、单张拷贝、单张剪切、翻页导航、页码徽章
      - 实时滤镜条：灰度开关、亮度滑块、对比度滑块、一键重置
      - 可折叠文件列表区：
          * 实时文件名关键字过滤搜索
          * 批量选择控制：全选、清空、反选、已选计数徽章
          * 批量文件操作：批量拷贝、批量剪切
          * 文件复选框状态跨搜索持久化记忆
      - 图像画板：高性能缩放、平移、双击适应、拖放目录
    """

    prevRequested = pyqtSignal()
    nextRequested = pyqtSignal()
    itemActivated = pyqtSignal(int)
    copyRequested = pyqtSignal()
    cutRequested = pyqtSignal()
    saveRequested = pyqtSignal()  # 兼容旧接口，等价于 copyRequested
    batchCopyRequested = pyqtSignal(list)
    batchCutRequested = pyqtSignal(list)
    folderDropped = pyqtSignal(str)
    checkedChanged = pyqtSignal(int)

    def __init__(self, title, is_left=True, parent=None):
        super().__init__(parent)
        self.title = title
        self.is_left = is_left
        self._all_rows = []           # [(path, mate_path_or_None), ...]
        self._row_indices = []        # 过滤后的行映射回原始行索引
        self._checked_paths = set()   # 跨搜索记忆已勾选的文件绝对路径字符串集合

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ---------------- 顶部操作栏 ----------------
        top_bar = QtWidgets.QFrame()
        top_bar.setObjectName("PanelTopBar")
        top_bar.setStyleSheet("""
            #PanelTopBar {
                background-color: #1e212b;
                border: 1px solid #2d3342;
                border-radius: 5px;
                padding: 2px 4px;
            }
        """)
        top_layout = QtWidgets.QHBoxLayout(top_bar)
        top_layout.setContentsMargins(4, 4, 4, 4)
        top_layout.setSpacing(5)

        # 侧别徽章
        self.lbl_badge = QtWidgets.QLabel(title)
        self.lbl_badge.setProperty("class", "BadgeLabel")
        if is_left:
            self.lbl_badge.setStyleSheet("""
                background-color: #0369a1;
                color: #f0f9ff;
                border-radius: 4px;
                padding: 3px 8px;
                font-weight: bold;
                font-size: 11px;
            """)
        else:
            self.lbl_badge.setStyleSheet("""
                background-color: #047857;
                color: #ecfdf5;
                border-radius: 4px;
                padding: 3px 8px;
                font-weight: bold;
                font-size: 11px;
            """)
        top_layout.addWidget(self.lbl_badge)

        # 当前文件名展示
        self.lbl_filename = QtWidgets.QLabel("未加载")
        self.lbl_filename.setStyleSheet("color: #e2e8f0; font-weight: 500;")
        self.lbl_filename.setToolTip("当前图片文件名")
        top_layout.addWidget(self.lbl_filename, 1)

        # 单张拷贝按钮
        self.btn_copy = QtWidgets.QPushButton("📋 拷贝")
        self.btn_copy.setProperty("small", "true")
        self.btn_copy.setToolTip("将当前原始图像文件复制到输出目录（快捷键：Ctrl+S / Ctrl+C）")
        self.btn_copy.clicked.connect(self._on_copy_clicked)
        self.btn_save = self.btn_copy  # 兼容旧代码引用

        # 单张剪切按钮
        self.btn_cut = QtWidgets.QPushButton("✂ 剪切")
        self.btn_cut.setProperty("small", "true")
        self.btn_cut.setToolTip("将当前原始图像文件移动到输出目录并自动跳至下一张（快捷键：Ctrl+X）")
        self.btn_cut.clicked.connect(lambda: self.cutRequested.emit())

        top_layout.addWidget(self.btn_copy)
        top_layout.addWidget(self.btn_cut)
        top_layout.addSpacing(4)

        # 翻页按钮组
        self.btn_prev = QtWidgets.QPushButton("◀ 上一张")
        self.btn_prev.setProperty("small", "true")
        self.btn_prev.setToolTip("模式 B 快捷键：Shift+← / PgUp（鼠标在本侧时）")
        self.btn_prev.clicked.connect(lambda: self.prevRequested.emit())

        self.btn_next = QtWidgets.QPushButton("下一张 ▶")
        self.btn_next.setProperty("small", "true")
        self.btn_next.setToolTip("模式 B 快捷键：Shift+→ / PgDown（鼠标在本侧时）")
        self.btn_next.clicked.connect(lambda: self.nextRequested.emit())

        self.lbl_pos = QtWidgets.QLabel("0 / 0")
        self.lbl_pos.setStyleSheet("""
            background-color: #272c3b;
            color: #94a3b8;
            border-radius: 4px;
            padding: 2px 6px;
            font-weight: bold;
            font-size: 11px;
        """)

        top_layout.addWidget(self.btn_prev)
        top_layout.addWidget(self.btn_next)
        top_layout.addWidget(self.lbl_pos)
        layout.addWidget(top_bar)

        # ---------------- 实时图像调节栏 ----------------
        adj_bar = QtWidgets.QFrame()
        adj_bar.setObjectName("AdjBar")
        adj_bar.setStyleSheet("""
            #AdjBar {
                background-color: #1a1d26;
                border: 1px solid #282d3b;
                border-radius: 5px;
                padding: 1px 4px;
            }
        """)
        adj_layout = QtWidgets.QHBoxLayout(adj_bar)
        adj_layout.setContentsMargins(6, 2, 6, 2)
        adj_layout.setSpacing(8)

        self.chk_gray = QtWidgets.QCheckBox("灰度")
        self.chk_gray.setToolTip("切换当前视图黑白灰度显示（仅显示层，不改原图）")

        lbl_b = QtWidgets.QLabel("亮度:")
        lbl_b.setStyleSheet("color:#94a3b8;")
        self.lbl_b_val = QtWidgets.QLabel("0")
        self.lbl_b_val.setFixedWidth(28)
        self.lbl_b_val.setStyleSheet("color:#cbd5e1; font-family: monospace;")
        self.sld_brightness = QtWidgets.QSlider(HORIZONTAL)
        self.sld_brightness.setRange(-100, 100)
        self.sld_brightness.setValue(0)
        self.sld_brightness.setSingleStep(5)
        self.sld_brightness.setToolTip("调节亮度（-100 到 +100）")

        lbl_c = QtWidgets.QLabel("对比度:")
        lbl_c.setStyleSheet("color:#94a3b8;")
        self.lbl_c_val = QtWidgets.QLabel("0")
        self.lbl_c_val.setFixedWidth(28)
        self.lbl_c_val.setStyleSheet("color:#cbd5e1; font-family: monospace;")
        self.sld_contrast = QtWidgets.QSlider(HORIZONTAL)
        self.sld_contrast.setRange(-100, 100)
        self.sld_contrast.setValue(0)
        self.sld_contrast.setSingleStep(5)
        self.sld_contrast.setToolTip("调节对比度（-100 到 +100）")

        self.btn_reset_display = QtWidgets.QPushButton("⟲ 重置")
        self.btn_reset_display.setProperty("small", "true")
        self.btn_reset_display.setToolTip("重置灰度与亮度对比度")

        adj_layout.addWidget(self.chk_gray)
        adj_layout.addSpacing(4)
        adj_layout.addWidget(lbl_b)
        adj_layout.addWidget(self.sld_brightness, 1)
        adj_layout.addWidget(self.lbl_b_val)
        adj_layout.addSpacing(4)
        adj_layout.addWidget(lbl_c)
        adj_layout.addWidget(self.sld_contrast, 1)
        adj_layout.addWidget(self.lbl_c_val)
        adj_layout.addWidget(self.btn_reset_display)
        layout.addWidget(adj_bar)

        # ---------------- 可折叠文件列表区 ----------------
        self.list_container = QtWidgets.QFrame()
        self.list_container.setObjectName("ListContainer")
        self.list_container.setStyleSheet("""
            #ListContainer {
                background-color: #181a22;
                border: 1px solid #282d3b;
                border-radius: 5px;
            }
        """)
        list_vbox = QtWidgets.QVBoxLayout(self.list_container)
        list_vbox.setContentsMargins(4, 4, 4, 4)
        list_vbox.setSpacing(4)

        # 1. 搜索过滤行
        search_row = QtWidgets.QHBoxLayout()
        search_row.setSpacing(4)
        self.edt_filter = QtWidgets.QLineEdit()
        self.edt_filter.setPlaceholderText("🔍 过滤当前列表文件名...")
        self.edt_filter.textChanged.connect(self._apply_filter)
        self.btn_clear_filter = QtWidgets.QPushButton("✕")
        self.btn_clear_filter.setProperty("small", "true")
        self.btn_clear_filter.setFixedWidth(24)
        self.btn_clear_filter.clicked.connect(lambda: self.edt_filter.clear())
        search_row.addWidget(self.edt_filter, 1)
        search_row.addWidget(self.btn_clear_filter)
        list_vbox.addLayout(search_row)

        # 2. 批量选择与操作工具栏 (Batch Toolbar)
        batch_row = QtWidgets.QHBoxLayout()
        batch_row.setSpacing(4)

        btn_all = QtWidgets.QPushButton("☑ 全选")
        btn_all.setProperty("small", "true")
        btn_all.setToolTip("勾选当前可见列表中的全部图像")
        btn_all.clicked.connect(self.select_all)

        btn_none = QtWidgets.QPushButton("□ 清空")
        btn_none.setProperty("small", "true")
        btn_none.setToolTip("清空所有勾选项")
        btn_none.clicked.connect(self.unselect_all)

        btn_invert = QtWidgets.QPushButton("反选")
        btn_invert.setProperty("small", "true")
        btn_invert.setToolTip("反转当前可见列表的勾选状态")
        btn_invert.clicked.connect(self.invert_selection)

        self.lbl_checked = QtWidgets.QLabel("已选: 0")
        self.lbl_checked.setStyleSheet("""
            color: #38bdf8;
            font-weight: bold;
            font-size: 11px;
            padding: 0 4px;
        """)

        self.btn_batch_copy = QtWidgets.QPushButton("📋 批量拷贝")
        self.btn_batch_copy.setProperty("small", "true")
        self.btn_batch_copy.setToolTip("将所有勾选的图像文件复制到输出目录")
        self.btn_batch_copy.clicked.connect(self._on_batch_copy_clicked)

        self.btn_batch_cut = QtWidgets.QPushButton("✂ 批量剪切")
        self.btn_batch_cut.setProperty("small", "true")
        self.btn_batch_cut.setToolTip("将所有勾选的图像文件剪切（移动）到输出目录")
        self.btn_batch_cut.clicked.connect(self._on_batch_cut_clicked)

        batch_row.addWidget(btn_all)
        batch_row.addWidget(btn_none)
        batch_row.addWidget(btn_invert)
        batch_row.addWidget(self.lbl_checked)
        batch_row.addStretch(1)
        batch_row.addWidget(self.btn_batch_copy)
        batch_row.addWidget(self.btn_batch_cut)
        list_vbox.addLayout(batch_row)

        # 3. 带复选框的文件列表
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setMaximumHeight(150)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemChanged.connect(self._on_item_changed)
        list_vbox.addWidget(self.list_widget)
        layout.addWidget(self.list_container)

        # ---------------- 图像主画板 ----------------
        self.view = ImageView()
        layout.addWidget(self.view, 1)

        # 信号绑定
        self.chk_gray.toggled.connect(self.view.set_gray)
        self.sld_brightness.valueChanged.connect(self._on_brightness_changed)
        self.sld_contrast.valueChanged.connect(self._on_contrast_changed)
        self.btn_reset_display.clicked.connect(self._reset_display)
        self.view.folderDropped.connect(lambda p: self.folderDropped.emit(p))

    def _on_copy_clicked(self):
        self.copyRequested.emit()
        self.saveRequested.emit()

    def _on_brightness_changed(self, val):
        self.lbl_b_val.setText(("%+d" if val > 0 else "%d") % val)
        self.view.set_brightness(val)

    def _on_contrast_changed(self, val):
        self.lbl_c_val.setText(("%+d" if val > 0 else "%d") % val)
        self.view.set_contrast(val)

    def set_nav_enabled(self, enabled):
        self.btn_prev.setEnabled(enabled)
        self.btn_next.setEnabled(enabled)

    def set_list_visible(self, visible):
        self.list_container.setVisible(visible)

    def toggle_list(self):
        self.set_list_visible(not self.list_container.isVisible())

    def _reset_display(self):
        for widget in (self.chk_gray, self.sld_brightness, self.sld_contrast):
            widget.blockSignals(True)
        self.chk_gray.setChecked(False)
        self.sld_brightness.setValue(0)
        self.sld_contrast.setValue(0)
        self.lbl_b_val.setText("0")
        self.lbl_c_val.setText("0")
        for widget in (self.chk_gray, self.sld_brightness, self.sld_contrast):
            widget.blockSignals(False)
        self.view.reset_display()

    def set_position(self, current, total):
        self.lbl_pos.setText("%d / %d" % (current, total))

    def update_filename(self, path):
        if path:
            name = os.path.basename(str(path))
            self.lbl_filename.setText(name)
            self.lbl_filename.setToolTip(str(path))
        else:
            self.lbl_filename.setText("未加载")
            self.lbl_filename.setToolTip("暂无加载图片")

    # ---- 列表填充与勾选维护 ----
    def fill_list(self, rows, mark_unmatched):
        """rows: [(path, mate_path_or_None), ...]；红色表示未匹配。"""
        self._all_rows = list(rows)
        self._mark_unmatched = mark_unmatched
        # 清理已不存在于当前列表中的失效路径
        valid_paths = {str(p) for p, _ in self._all_rows}
        self._checked_paths.intersection_update(valid_paths)
        self._apply_filter(self.edt_filter.text())

    def _apply_filter(self, filter_text=""):
        filter_text = (filter_text or "").strip().lower()
        widget = self.list_widget
        widget.blockSignals(True)
        widget.clear()
        self._row_indices = []

        for idx, (path, mate) in enumerate(self._all_rows):
            name = path.name
            if filter_text and filter_text not in name.lower():
                continue
            self._row_indices.append(idx)
            item = QtWidgets.QListWidgetItem(name)
            # 支持 Checkbox
            item.setFlags(item.flags() | ITEM_IS_USER_CHECKABLE)
            is_checked = (str(path) in self._checked_paths)
            item.setCheckState(CHECK_STATE_CHECKED if is_checked else CHECK_STATE_UNCHECKED)

            if self._mark_unmatched and mate is None:
                item.setForeground(QColor("#f87171"))  # 亮红标示未匹配
                item.setToolTip("未匹配文件：%s" % path)
            else:
                item.setToolTip(str(path))
            widget.addItem(item)
        widget.blockSignals(False)
        self._update_checked_label()

    def _on_item_changed(self, item):
        filtered_row = self.list_widget.row(item)
        if 0 <= filtered_row < len(self._row_indices):
            actual_row = self._row_indices[filtered_row]
            path = self._all_rows[actual_row][0]
            if item.checkState() == CHECK_STATE_CHECKED:
                self._checked_paths.add(str(path))
            else:
                self._checked_paths.discard(str(path))
            self._update_checked_label()

    def _update_checked_label(self):
        count = len(self._checked_paths)
        self.lbl_checked.setText("已选: %d" % count)
        self.checkedChanged.emit(count)

    # ---- 批量选择动作 ----
    def select_all(self):
        """勾选当前可见列表中的所有项"""
        widget = self.list_widget
        widget.blockSignals(True)
        for i in range(widget.count()):
            item = widget.item(i)
            item.setCheckState(CHECK_STATE_CHECKED)
            actual_row = self._row_indices[i]
            path = self._all_rows[actual_row][0]
            self._checked_paths.add(str(path))
        widget.blockSignals(False)
        self._update_checked_label()

    def unselect_all(self):
        """清空所有已勾选项"""
        widget = self.list_widget
        widget.blockSignals(True)
        for i in range(widget.count()):
            widget.item(i).setCheckState(CHECK_STATE_UNCHECKED)
        self._checked_paths.clear()
        widget.blockSignals(False)
        self._update_checked_label()

    def invert_selection(self):
        """反转当前可见列表的勾选状态"""
        widget = self.list_widget
        widget.blockSignals(True)
        for i in range(widget.count()):
            item = widget.item(i)
            actual_row = self._row_indices[i]
            path = self._all_rows[actual_row][0]
            if item.checkState() == CHECK_STATE_CHECKED:
                item.setCheckState(CHECK_STATE_UNCHECKED)
                self._checked_paths.discard(str(path))
            else:
                item.setCheckState(CHECK_STATE_CHECKED)
                self._checked_paths.add(str(path))
        widget.blockSignals(False)
        self._update_checked_label()

    def get_checked_paths(self):
        """获取所有已勾选的文件路径列表（按原始列表顺序排序）"""
        checked = []
        for path, _ in self._all_rows:
            if str(path) in self._checked_paths:
                checked.append(path)
        return checked

    def set_checked_indices(self, indices_set):
        """通过原始行索引集合批量勾选（供双侧配对同步勾选调用）"""
        self._checked_paths.clear()
        for idx in indices_set:
            if 0 <= idx < len(self._all_rows):
                self._checked_paths.add(str(self._all_rows[idx][0]))
        self._apply_filter(self.edt_filter.text())

    def _on_batch_copy_clicked(self):
        paths = self.get_checked_paths()
        if not paths:
            QtWidgets.QMessageBox.information(self, "提示", "请先在列表中勾选要拷贝的图像。")
            return
        self.batchCopyRequested.emit(paths)

    def _on_batch_cut_clicked(self):
        paths = self.get_checked_paths()
        if not paths:
            QtWidgets.QMessageBox.information(self, "提示", "请先在列表中勾选要剪切的图像。")
            return
        self.batchCutRequested.emit(paths)

    def select_row(self, row):
        widget = self.list_widget
        widget.blockSignals(True)
        if 0 <= row < len(self._all_rows):
            try:
                filtered_idx = self._row_indices.index(row)
                widget.setCurrentRow(filtered_idx)
                widget.scrollToItem(widget.item(filtered_idx))
            except ValueError:
                widget.setCurrentRow(-1)
        else:
            widget.setCurrentRow(-1)
        widget.blockSignals(False)

    def _on_item_clicked(self, item):
        filtered_row = self.list_widget.row(item)
        if 0 <= filtered_row < len(self._row_indices):
            actual_row = self._row_indices[filtered_row]
            self.itemActivated.emit(actual_row)
