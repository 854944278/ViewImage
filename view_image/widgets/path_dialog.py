# -*- coding: utf-8 -*-
"""
文件夹路径设置弹窗：管理左、右图像文件夹与输出目标目录，支持一键互换
"""

import os
from ..core.qt_compat import QtWidgets


class PathSettingsDialog(QtWidgets.QDialog):
    """文件夹路径设置与管理弹窗"""

    def __init__(self, parent, left_dir="", right_dir="", output_dir=""):
        super().__init__(parent)
        self.setWindowTitle("文件夹路径设置")
        self.resize(620, 260)
        self.result_paths = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        grid = QtWidgets.QGridLayout()
        grid.setSpacing(10)

        # 左文件夹
        lbl_l = QtWidgets.QLabel("🟦 左侧文件夹:")
        lbl_l.setStyleSheet("color: #38bdf8; font-weight: bold;")
        self.edt_left = QtWidgets.QLineEdit(left_dir)
        self.edt_left.setPlaceholderText("选择包含左侧图像的文件夹")
        btn_browse_l = QtWidgets.QPushButton("📁 浏览…")
        btn_browse_l.clicked.connect(lambda: self._browse(self.edt_left, "选择左侧图像文件夹"))

        # 互换按钮
        btn_swap = QtWidgets.QPushButton("⇄ 互换左右")
        btn_swap.setProperty("small", "true")
        btn_swap.setToolTip("对调左文件夹与右文件夹")
        btn_swap.clicked.connect(self._swap)

        # 右文件夹
        lbl_r = QtWidgets.QLabel("🟩 右侧文件夹:")
        lbl_r.setStyleSheet("color: #34d399; font-weight: bold;")
        self.edt_right = QtWidgets.QLineEdit(right_dir)
        self.edt_right.setPlaceholderText("选择包含右侧图像的文件夹")
        btn_browse_r = QtWidgets.QPushButton("📁 浏览…")
        btn_browse_r.clicked.connect(lambda: self._browse(self.edt_right, "选择右侧图像文件夹"))

        # 输出目录
        lbl_out = QtWidgets.QLabel("📂 输出目录:")
        lbl_out.setStyleSheet("color: #94a3b8; font-weight: bold;")
        self.edt_output = QtWidgets.QLineEdit(output_dir)
        self.edt_output.setPlaceholderText("用于保存/拷贝/剪切图像的目标文件夹")
        btn_browse_out = QtWidgets.QPushButton("📁 浏览…")
        btn_browse_out.clicked.connect(lambda: self._browse(self.edt_output, "选择输出目标文件夹"))

        grid.addWidget(lbl_l, 0, 0)
        grid.addWidget(self.edt_left, 0, 1)
        grid.addWidget(btn_browse_l, 0, 2)
        grid.addWidget(btn_swap, 0, 3)

        grid.addWidget(lbl_r, 1, 0)
        grid.addWidget(self.edt_right, 1, 1)
        grid.addWidget(btn_browse_r, 1, 2)

        grid.addWidget(lbl_out, 2, 0)
        grid.addWidget(self.edt_output, 2, 1)
        grid.addWidget(btn_browse_out, 2, 2)

        layout.addLayout(grid)
        layout.addStretch(1)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)

        btn_cancel = QtWidgets.QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QtWidgets.QPushButton("✔ 确认应用")
        btn_ok.setProperty("primary", "true")
        btn_ok.clicked.connect(self._on_ok)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _browse(self, line_edit, title):
        start = line_edit.text().strip()
        if not start or not os.path.isdir(start):
            start = os.path.expanduser("~")
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, title, start)
        if folder:
            line_edit.setText(folder)

    def _swap(self):
        l = self.edt_left.text().strip()
        r = self.edt_right.text().strip()
        self.edt_left.setText(r)
        self.edt_right.setText(l)

    def _on_ok(self):
        self.result_paths = {
            "left_dir": self.edt_left.text().strip(),
            "right_dir": self.edt_right.text().strip(),
            "output_dir": self.edt_output.text().strip(),
        }
        self.accept()
