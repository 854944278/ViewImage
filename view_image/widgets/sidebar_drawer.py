# -*- coding: utf-8 -*-
"""
统一侧边抽屉文件列表与批量管理组件
支持模式 A 单列显示配对关系与模式 B 双选项卡切换，自带复选框与批量工具条
"""

import os
from pathlib import Path

from ..core.qt_compat import (
    CHECK_STATE_CHECKED,
    CHECK_STATE_UNCHECKED,
    ITEM_IS_USER_CHECKABLE,
    QColor,
    QtCore,
    QtGui,
    QtWidgets,
    pyqtSignal,
)


class SidebarDrawer(QtWidgets.QFrame):
    """侧边抽屉文件列表管理面板"""

    itemActivated = pyqtSignal(str, int)     # ("PAIR"|"L"|"R", index)
    batchCopyRequested = pyqtSignal(list)    # [Path, ...]
    batchCutRequested = pyqtSignal(list)     # [Path, ...]
    closeRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarDrawer")
        self.setFixedWidth(340)
        self.setStyleSheet("""
            #SidebarDrawer {
                background-color: #161820;
                border-right: 1px solid #282d3b;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. 抽屉标题栏
        top_bar = QtWidgets.QHBoxLayout()
        lbl_title = QtWidgets.QLabel("📑 文件列表与管理")
        lbl_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #f1f5f9;")
        btn_close = QtWidgets.QPushButton("✕")
        btn_close.setProperty("small", "true")
        btn_close.setFixedWidth(24)
        btn_close.setToolTip("收起侧栏 (F3)")
        btn_close.clicked.connect(self.closeRequested.emit)
        top_bar.addWidget(lbl_title)
        top_bar.addStretch(1)
        top_bar.addWidget(btn_close)
        layout.addLayout(top_bar)

        # 2. 搜索过滤行
        search_row = QtWidgets.QHBoxLayout()
        search_row.setSpacing(4)
        self.edt_filter = QtWidgets.QLineEdit()
        self.edt_filter.setPlaceholderText("🔍 搜索过滤文件名...")
        self.edt_filter.textChanged.connect(self._apply_filter)
        self.btn_clear_filter = QtWidgets.QPushButton("✕")
        self.btn_clear_filter.setProperty("small", "true")
        self.btn_clear_filter.setFixedWidth(24)
        self.btn_clear_filter.clicked.connect(lambda: self.edt_filter.clear())
        search_row.addWidget(self.edt_filter, 1)
        search_row.addWidget(self.btn_clear_filter)
        layout.addLayout(search_row)

        # 3. 批量选择与操作工具栏
        batch_row = QtWidgets.QHBoxLayout()
        batch_row.setSpacing(4)
        btn_all = QtWidgets.QPushButton("☑ 全选")
        btn_all.setProperty("small", "true")
        btn_all.clicked.connect(self.select_all)

        btn_none = QtWidgets.QPushButton("□ 清空")
        btn_none.setProperty("small", "true")
        btn_none.clicked.connect(self.unselect_all)

        btn_invert = QtWidgets.QPushButton("反选")
        btn_invert.setProperty("small", "true")
        btn_invert.clicked.connect(self.invert_selection)

        self.lbl_checked = QtWidgets.QLabel("已选: 0")
        self.lbl_checked.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 11px;")

        batch_row.addWidget(btn_all)
        batch_row.addWidget(btn_none)
        batch_row.addWidget(btn_invert)
        batch_row.addWidget(self.lbl_checked)
        batch_row.addStretch(1)
        layout.addLayout(batch_row)

        action_row = QtWidgets.QHBoxLayout()
        action_row.setSpacing(6)
        btn_batch_copy = QtWidgets.QPushButton("📋 批量拷贝")
        btn_batch_copy.setProperty("small", "true")
        btn_batch_copy.clicked.connect(self._on_batch_copy)

        btn_batch_cut = QtWidgets.QPushButton("✂ 批量剪切")
        btn_batch_cut.setProperty("small", "true")
        btn_batch_cut.clicked.connect(self._on_batch_cut)

        action_row.addWidget(btn_batch_copy)
        action_row.addWidget(btn_batch_cut)
        layout.addLayout(action_row)

        # 4. 模式 B 选项卡（模式 A 下自动隐藏）
        self.tab_mode_b = QtWidgets.QTabBar()
        self.tab_mode_b.addTab("🟦 左列表")
        self.tab_mode_b.addTab("🟩 右列表")
        self.tab_mode_b.currentChanged.connect(self._on_tab_changed)
        self.tab_mode_b.setVisible(False)
        layout.addWidget(self.tab_mode_b)

        # 5. 主列表部件
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.list_widget, 1)

        # 状态数据
        self._mode = "A"
        self._rule_text = ""
        self._pairs = []              # [(left, right), ...]
        self._unmatched_l = []
        self._unmatched_r = []
        self._left_files = []
        self._right_files = []

        self._all_display_items = []  # [(display_text, [Path1, Path2], row_type, raw_index), ...]
        self._filtered_indices = []
        self._checked_paths = set()   # 跨搜索记忆已勾选的文件绝对路径

    def set_data(self, mode, rule_text, pairs, unmatched_l, unmatched_r, left_files, right_files):
        """更新文件与配对数据并刷新展示"""
        self._mode = mode
        self._rule_text = rule_text
        self._pairs = list(pairs)
        self._unmatched_l = list(unmatched_l)
        self._unmatched_r = list(unmatched_r)
        self._left_files = list(left_files)
        self._right_files = list(right_files)

        is_paired_mode = (mode == "A" and bool(rule_text))
        self.tab_mode_b.setVisible(not is_paired_mode)

        self._rebuild_items()
        self._apply_filter(self.edt_filter.text())

    def _rebuild_items(self):
        self._all_display_items = []
        is_paired_mode = (self._mode == "A" and bool(self._rule_text))

        if is_paired_mode:
            # 模式 A：以配对对为单位展示
            for idx, (l, r) in enumerate(self._pairs):
                text = "%03d. %s  ↔  %s" % (idx + 1, l.name, r.name)
                self._all_display_items.append((text, [l, r], "PAIR", idx))
            for idx, l in enumerate(self._unmatched_l):
                text = "[左未匹配] %s" % l.name
                self._all_display_items.append((text, [l], "UNMATCHED_L", idx))
            for idx, r in enumerate(self._unmatched_r):
                text = "[右未匹配] %s" % r.name
                self._all_display_items.append((text, [r], "UNMATCHED_R", idx))
        else:
            # 模式 B 或未配对：根据选项卡展示
            active_tab = self.tab_mode_b.currentIndex()
            if active_tab == 0:
                for idx, path in enumerate(self._left_files):
                    self._all_display_items.append(("%03d. %s" % (idx + 1, path.name), [path], "L", idx))
            else:
                for idx, path in enumerate(self._right_files):
                    self._all_display_items.append(("%03d. %s" % (idx + 1, path.name), [path], "R", idx))

        # 清理失效的已勾选路径
        all_paths = {str(p) for _, paths, _, _ in self._all_display_items for p in paths}
        self._checked_paths.intersection_update(all_paths)

    def _on_tab_changed(self, _):
        self._rebuild_items()
        self._apply_filter(self.edt_filter.text())

    def _apply_filter(self, filter_text=""):
        filter_text = (filter_text or "").strip().lower()
        widget = self.list_widget
        widget.blockSignals(True)
        widget.clear()
        self._filtered_indices = []

        for idx, (display_text, paths, row_type, raw_idx) in enumerate(self._all_display_items):
            if filter_text and filter_text not in display_text.lower():
                continue
            self._filtered_indices.append(idx)
            item = QtWidgets.QListWidgetItem(display_text)
            item.setFlags(item.flags() | ITEM_IS_USER_CHECKABLE)

            # 判断当前项是否已勾选 (若包含的路径均在 _checked_paths 中则置为 checked)
            is_checked = any(str(p) in self._checked_paths for p in paths)
            item.setCheckState(CHECK_STATE_CHECKED if is_checked else CHECK_STATE_UNCHECKED)

            if "UNMATCHED" in row_type:
                item.setForeground(QColor("#f87171"))
            widget.addItem(item)

        widget.blockSignals(False)
        self._update_checked_label()

    def _on_item_changed(self, item):
        filtered_row = self.list_widget.row(item)
        if 0 <= filtered_row < len(self._filtered_indices):
            actual_idx = self._filtered_indices[filtered_row]
            _, paths, _, _ = self._all_display_items[actual_idx]
            if item.checkState() == CHECK_STATE_CHECKED:
                for p in paths:
                    self._checked_paths.add(str(p))
            else:
                for p in paths:
                    self._checked_paths.discard(str(p))
            self._update_checked_label()

    def _update_checked_label(self):
        self.lbl_checked.setText("已选: %d" % len(self._checked_paths))

    def select_all(self):
        widget = self.list_widget
        widget.blockSignals(True)
        for i in range(widget.count()):
            widget.item(i).setCheckState(CHECK_STATE_CHECKED)
            actual_idx = self._filtered_indices[i]
            _, paths, _, _ = self._all_display_items[actual_idx]
            for p in paths:
                self._checked_paths.add(str(p))
        widget.blockSignals(False)
        self._update_checked_label()

    def unselect_all(self):
        widget = self.list_widget
        widget.blockSignals(True)
        for i in range(widget.count()):
            widget.item(i).setCheckState(CHECK_STATE_UNCHECKED)
        self._checked_paths.clear()
        widget.blockSignals(False)
        self._update_checked_label()

    def invert_selection(self):
        widget = self.list_widget
        widget.blockSignals(True)
        for i in range(widget.count()):
            item = widget.item(i)
            actual_idx = self._filtered_indices[i]
            _, paths, _, _ = self._all_display_items[actual_idx]
            if item.checkState() == CHECK_STATE_CHECKED:
                item.setCheckState(CHECK_STATE_UNCHECKED)
                for p in paths:
                    self._checked_paths.discard(str(p))
            else:
                item.setCheckState(CHECK_STATE_CHECKED)
                for p in paths:
                    self._checked_paths.add(str(p))
        widget.blockSignals(False)
        self._update_checked_label()

    def get_checked_paths(self):
        """返回已勾选的所有文件 Path 列表"""
        return [Path(p) for p in self._checked_paths]

    def _on_item_clicked(self, item):
        filtered_row = self.list_widget.row(item)
        if 0 <= filtered_row < len(self._filtered_indices):
            actual_idx = self._filtered_indices[filtered_row]
            _, _, row_type, raw_idx = self._all_display_items[actual_idx]
            self.itemActivated.emit(row_type, raw_idx)

    def select_row(self, row_type, raw_index):
        """外部同步高亮当前行"""
        widget = self.list_widget
        widget.blockSignals(True)
        found_filtered_row = -1
        for filtered_row, actual_idx in enumerate(self._filtered_indices):
            _, _, r_type, r_idx = self._all_display_items[actual_idx]
            if r_type == row_type and r_idx == raw_index:
                found_filtered_row = filtered_row
                break
        widget.setCurrentRow(found_filtered_row)
        if found_filtered_row >= 0:
            widget.scrollToItem(widget.item(found_filtered_row))
        widget.blockSignals(False)

    def _on_batch_copy(self):
        paths = self.get_checked_paths()
        if not paths:
            QtWidgets.QMessageBox.information(self, "提示", "请先在列表中勾选要拷贝的图像。")
            return
        self.batchCopyRequested.emit(paths)

    def _on_batch_cut(self):
        paths = self.get_checked_paths()
        if not paths:
            QtWidgets.QMessageBox.information(self, "提示", "请先在列表中勾选要剪切的图像。")
            return
        self.batchCutRequested.emit(paths)
