# -*- coding: utf-8 -*-
"""
目标目录重名文件冲突提醒与决策对话框
支持单文件冲突（重命名/覆盖/取消）与批量冲突策略（批量重命名/批量覆盖/全部跳过/取消）
"""

from ..core.file_ops import POLICY_OVERWRITE, POLICY_RENAME, POLICY_SKIP
from ..core.qt_compat import ALIGN_CENTER, DIALOG_ACCEPTED, _dialog_exec, QtCore, QtGui, QtWidgets


class SingleConflictDialog(QtWidgets.QDialog):
    """单文件重名冲突提示对话框"""

    def __init__(self, parent, filename, action="拷贝"):
        super().__init__(parent)
        self.setWindowTitle("重名文件提醒")
        self.resize(460, 200)
        self.policy = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        icon_label = QtWidgets.QLabel("⚠️ 目标输出目录中已存在同名文件：")
        icon_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #f59e0b;")
        layout.addWidget(icon_label)

        file_label = QtWidgets.QLabel(filename)
        file_label.setStyleSheet("""
            background-color: #1e222d;
            border: 1px solid #333a4c;
            border-radius: 4px;
            padding: 8px;
            color: #93c5fd;
            font-family: monospace;
            font-size: 12px;
        """)
        file_label.setWordWrap(True)
        layout.addWidget(file_label)

        tip = QtWidgets.QLabel("请选择此文件的%s处理方式：" % action)
        tip.setStyleSheet("color: #94a3b8;")
        layout.addWidget(tip)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)

        btn_rename = QtWidgets.QPushButton("✔ 递增重命名 (加 _1)")
        btn_rename.setProperty("primary", "true")
        btn_rename.clicked.connect(lambda: self._choose(POLICY_RENAME))

        btn_overwrite = QtWidgets.QPushButton("⚠️ 覆盖目标文件")
        btn_overwrite.setStyleSheet("background-color: #991b1b; color: #ffffff; border: 1px solid #dc2626;")
        btn_overwrite.clicked.connect(lambda: self._choose(POLICY_OVERWRITE))

        btn_cancel = QtWidgets.QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(btn_rename)
        btn_row.addWidget(btn_overwrite)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _choose(self, policy):
        self.policy = policy
        self.accept()


class BatchConflictDialog(QtWidgets.QDialog):
    """批量文件重名冲突提示对话框"""

    def __init__(self, parent, conflict_files, action="拷贝"):
        super().__init__(parent)
        self.setWindowTitle("批量重名文件冲突提醒")
        self.resize(520, 320)
        self.policy = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QtWidgets.QLabel(
            "⚠️ 检测到目标输出目录中已存在 %d 个同名文件：" % len(conflict_files)
        )
        header.setStyleSheet("font-size: 13px; font-weight: bold; color: #f59e0b;")
        layout.addWidget(header)

        list_widget = QtWidgets.QListWidget()
        list_widget.setMaximumHeight(120)
        for name in conflict_files:
            item = QtWidgets.QListWidgetItem(name)
            item.setForeground(QtGui.QColor("#fca5a5"))
            list_widget.addItem(item)
        layout.addWidget(list_widget)

        tip = QtWidgets.QLabel("请选择所有冲突文件的批量%s策略：" % action)
        tip.setStyleSheet("color: #cbd5e1; font-weight: 500;")
        layout.addWidget(tip)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(6)

        btn_rename = QtWidgets.QPushButton("递增重命名 (推荐)")
        btn_rename.setProperty("primary", "true")
        btn_rename.setToolTip("所有重名文件自动添加 _1, _2 等后缀保存")
        btn_rename.clicked.connect(lambda: self._choose(POLICY_RENAME))

        btn_skip = QtWidgets.QPushButton("全部跳过")
        btn_skip.setToolTip("跳过已存在的文件，仅复制/移动不重复的文件")
        btn_skip.clicked.connect(lambda: self._choose(POLICY_SKIP))

        btn_overwrite = QtWidgets.QPushButton("全部覆盖")
        btn_overwrite.setStyleSheet("background-color: #991b1b; color: #ffffff; border: 1px solid #dc2626;")
        btn_overwrite.setToolTip("强制替换目标目录中的同名文件")
        btn_overwrite.clicked.connect(lambda: self._choose(POLICY_OVERWRITE))

        btn_cancel = QtWidgets.QPushButton("取消操作")
        btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(btn_rename)
        btn_row.addWidget(btn_skip)
        btn_row.addWidget(btn_overwrite)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _choose(self, policy):
        self.policy = policy
        self.accept()


def prompt_single_conflict(parent, filename, action="拷贝"):
    """
    提示单文件冲突，返回 POLICY_RENAME, POLICY_OVERWRITE 或 None (取消)
    """
    dlg = SingleConflictDialog(parent, filename, action=action)
    res = _dialog_exec(dlg)
    if res == DIALOG_ACCEPTED:
        return dlg.policy
    return None


def prompt_batch_conflict(parent, conflict_files, action="拷贝"):
    """
    提示批量冲突，返回 POLICY_RENAME, POLICY_OVERWRITE, POLICY_SKIP 或 None (取消)
    """
    dlg = BatchConflictDialog(parent, conflict_files, action=action)
    res = _dialog_exec(dlg)
    if res == DIALOG_ACCEPTED:
        return dlg.policy
    return None
