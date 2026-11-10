# -*- coding: utf-8 -*-
"""
配对规则配置对话框：支持多样本智能推断、自定义表达式与实时匹配预览
"""

from ..core.qt_compat import (
    ALIGN_CENTER,
    QColor,
    QtCore,
    QtGui,
    QtWidgets,
)
from ..core.rules import PairRule, RuleError, build_pairs, infer_rules


class RuleDialog(QtWidgets.QDialog):
    """
    配对规则设置对话框（模式 A）：
      1. 在左右列表中各挑选 2 对确认对应的样本图像
      2. 算法自动推断出高可行性的命名对应规则，支持候选下拉切换或手动微调表达式
      3. 实时预览配对数量与未匹配数量，验证通过后一键保存生效
    """

    def __init__(self, parent, left_files, right_files, current_rule=""):
        super().__init__(parent)
        self.setWindowTitle("设置配对规则（模式 A）")
        self.resize(860, 680)
        self.setMinimumSize(780, 600)
        self.left_files = left_files
        self.right_files = right_files
        self.candidates = []
        self.result_rule = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ---------------- 步骤 1 卡片 ----------------
        card1 = QtWidgets.QGroupBox("📌 步骤 1：在左右列表中各挑选 2 对互相对应的样本图")
        c1_layout = QtWidgets.QVBoxLayout(card1)
        c1_layout.setContentsMargins(12, 16, 12, 12)
        c1_layout.setSpacing(8)

        lbl_intro = QtWidgets.QLabel(
            "提示：请挑选编号不同的两对图像作为基准样本，以便算法准确识别其前缀、后缀、编号或固定结构差异。"
        )
        lbl_intro.setProperty("secondary", "true")
        lbl_intro.setWordWrap(True)
        c1_layout.addWidget(lbl_intro)

        grid = QtWidgets.QGridLayout()
        grid.setSpacing(10)

        self.cb_l1 = QtWidgets.QComboBox()
        self.cb_r1 = QtWidgets.QComboBox()
        self.cb_l2 = QtWidgets.QComboBox()
        self.cb_r2 = QtWidgets.QComboBox()

        for cb in (self.cb_l1, self.cb_r1, self.cb_l2, self.cb_r2):
            cb.setMaxVisibleItems(16)

        grid.addWidget(QtWidgets.QLabel("样本 1 · 左侧图:"), 0, 0)
        grid.addWidget(self.cb_l1, 0, 1)
        grid.addWidget(QtWidgets.QLabel("↔"), 0, 2, ALIGN_CENTER)
        grid.addWidget(QtWidgets.QLabel("样本 1 · 右侧图:"), 0, 3)
        grid.addWidget(self.cb_r1, 0, 4)

        grid.addWidget(QtWidgets.QLabel("样本 2 · 左侧图:"), 1, 0)
        grid.addWidget(self.cb_l2, 1, 1)
        grid.addWidget(QtWidgets.QLabel("↔"), 1, 2, ALIGN_CENTER)
        grid.addWidget(QtWidgets.QLabel("样本 2 · 右侧图:"), 1, 3)
        grid.addWidget(self.cb_r2, 1, 4)

        c1_layout.addLayout(grid)
        layout.addWidget(card1)

        self._fill_combos()

        # ---------------- 步骤 2 卡片 ----------------
        card2 = QtWidgets.QGroupBox("⚡ 步骤 2：自动推断或自定义规则表达式")
        c2_layout = QtWidgets.QVBoxLayout(card2)
        c2_layout.setContentsMargins(12, 16, 12, 12)
        c2_layout.setSpacing(10)

        row_infer = QtWidgets.QHBoxLayout()
        btn_infer = QtWidgets.QPushButton("① 从这 2 对样本推断规则")
        btn_infer.setProperty("primary", "true")
        btn_infer.clicked.connect(self._infer)
        self.cmb_candidates = QtWidgets.QComboBox()
        self.cmb_candidates.setMinimumWidth(400)
        self.cmb_candidates.currentIndexChanged.connect(self._on_candidate)

        row_infer.addWidget(btn_infer)
        row_infer.addWidget(self.cmb_candidates, 1)
        c2_layout.addLayout(row_infer)

        row_edit = QtWidgets.QHBoxLayout()
        lbl_rule_title = QtWidgets.QLabel("规则表达式:")
        lbl_rule_title.setStyleSheet("font-weight: bold;")
        self.txt_rule = QtWidgets.QLineEdit()
        self.txt_rule.setPlaceholderText("例如: prefix:8 / number / strip:L_|_L|R_|_R / regex:(\\d+)")
        self.txt_rule.setText(current_rule or "")
        self.txt_rule.editingFinished.connect(self._preview)

        btn_preview = QtWidgets.QPushButton("② 预览匹配")
        btn_preview.clicked.connect(self._preview)

        row_edit.addWidget(lbl_rule_title)
        row_edit.addWidget(self.txt_rule, 1)
        row_edit.addWidget(btn_preview)
        c2_layout.addLayout(row_edit)

        syntax_tips = QtWidgets.QLabel(
            "支持表达式：same (忽略后缀同名) ｜ same_ext (全名相同) ｜ prefix:N (前N位) ｜ suffix:N (后N位) ｜ "
            "number (数字编号相同) ｜ strip:左前|左后|右前|右后 (去除前后缀) ｜ regex:正则 (取第1捕获组)"
        )
        syntax_tips.setProperty("secondary", "true")
        syntax_tips.setWordWrap(True)
        c2_layout.addWidget(syntax_tips)

        layout.addWidget(card2)

        # ---------------- 步骤 3 卡片 ----------------
        card3 = QtWidgets.QGroupBox("🔍 步骤 3：规则验证与结果预览")
        c3_layout = QtWidgets.QVBoxLayout(card3)
        c3_layout.setContentsMargins(12, 16, 12, 12)
        c3_layout.setSpacing(8)

        self.lbl_preview = QtWidgets.QLabel("尚未预览匹配结果")
        self.lbl_preview.setStyleSheet("color: #93c5fd; font-weight: bold;")
        c3_layout.addWidget(self.lbl_preview)

        self.list_preview = QtWidgets.QListWidget()
        self.list_preview.setMaximumHeight(150)
        c3_layout.addWidget(self.list_preview)

        layout.addWidget(card3, 1)

        # ---------------- 底部按钮行 ----------------
        bottom_row = QtWidgets.QHBoxLayout()
        bottom_row.addStretch(1)

        btn_cancel = QtWidgets.QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QtWidgets.QPushButton("✔ 确认保存")
        btn_ok.setProperty("primary", "true")
        btn_ok.clicked.connect(self._on_ok)

        bottom_row.addWidget(btn_cancel)
        bottom_row.addWidget(btn_ok)
        layout.addLayout(bottom_row)

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
                self, "提示", "请把 4 个下拉框都选好（左右各 2 张确认对应的图片）。")
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
                "或直接在下方输入规则表达式。")
            return
        for item in self.candidates:
            self.cmb_candidates.addItem(
                "%s  → 匹配 %d 对（未匹配: 左%d / 右%d）" % (
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
            self.list_preview.addItem("（没有任何图像能按此规则配对）")
        for left, right in pairs[:10]:
            item = QtWidgets.QListWidgetItem("%s   ↔   %s" % (left.name, right.name))
            self.list_preview.addItem(item)
        if len(pairs) > 10:
            self.list_preview.addItem("…… 其余 %d 对已省略" % (len(pairs) - 10))

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
