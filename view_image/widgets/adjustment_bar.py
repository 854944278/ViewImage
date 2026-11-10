# -*- coding: utf-8 -*-
"""
按需图像调色条：支持黑白灰度、亮度与对比度无损调节，支持左右同步或单侧独立调节
平时完全收起，点击顶栏「🎛 调色」按需展开
"""

from ..core.qt_compat import HORIZONTAL, QtCore, QtWidgets, pyqtSignal


class ImageAdjustmentBar(QtWidgets.QFrame):
    """按需折叠的紧凑图像显示滤镜调节条"""

    adjustmentChanged = pyqtSignal(str, bool, int, int)  # target ("BOTH"|"L"|"R"), gray, brightness, contrast
    resetRequested = pyqtSignal(str)                     # target ("BOTH"|"L"|"R")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ImageAdjustmentBar")
        self.setStyleSheet("""
            #ImageAdjustmentBar {
                background-color: #1e222d;
                border: 1px solid #333a4d;
                border-radius: 6px;
                padding: 2px 6px;
            }
        """)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        # 调节目标选择
        lbl_target = QtWidgets.QLabel("调节目标:")
        lbl_target.setStyleSheet("color: #94a3b8; font-weight: bold;")
        self.cmb_target = QtWidgets.QComboBox()
        self.cmb_target.addItem("左右双侧同步", "BOTH")
        self.cmb_target.addItem("仅调节左侧", "L")
        self.cmb_target.addItem("仅调节右侧", "R")
        self.cmb_target.currentIndexChanged.connect(self._emit_change)

        # 灰度开关
        self.chk_gray = QtWidgets.QCheckBox("黑白灰度")
        self.chk_gray.toggled.connect(self._emit_change)

        # 亮度滑块
        lbl_b = QtWidgets.QLabel("亮度:")
        lbl_b.setStyleSheet("color: #94a3b8;")
        self.lbl_b_val = QtWidgets.QLabel("0")
        self.lbl_b_val.setFixedWidth(28)
        self.lbl_b_val.setStyleSheet("color: #cbd5e1; font-family: monospace;")
        self.sld_brightness = QtWidgets.QSlider(HORIZONTAL)
        self.sld_brightness.setRange(-100, 100)
        self.sld_brightness.setValue(0)
        self.sld_brightness.setSingleStep(5)
        self.sld_brightness.valueChanged.connect(self._on_b_slider)

        # 对比度滑块
        lbl_c = QtWidgets.QLabel("对比度:")
        lbl_c.setStyleSheet("color: #94a3b8;")
        self.lbl_c_val = QtWidgets.QLabel("0")
        self.lbl_c_val.setFixedWidth(28)
        self.lbl_c_val.setStyleSheet("color: #cbd5e1; font-family: monospace;")
        self.sld_contrast = QtWidgets.QSlider(HORIZONTAL)
        self.sld_contrast.setRange(-100, 100)
        self.sld_contrast.setValue(0)
        self.sld_contrast.setSingleStep(5)
        self.sld_contrast.valueChanged.connect(self._on_c_slider)

        # 重置与关闭
        btn_reset = QtWidgets.QPushButton("⟲ 重置")
        btn_reset.setProperty("small", "true")
        btn_reset.clicked.connect(self._on_reset)

        btn_close = QtWidgets.QPushButton("✕")
        btn_close.setProperty("small", "true")
        btn_close.setFixedWidth(24)
        btn_close.setToolTip("收起调色条")
        btn_close.clicked.connect(lambda: self.setVisible(False))

        layout.addWidget(lbl_target)
        layout.addWidget(self.cmb_target)
        layout.addSpacing(6)
        layout.addWidget(self.chk_gray)
        layout.addSpacing(6)
        layout.addWidget(lbl_b)
        layout.addWidget(self.sld_brightness, 1)
        layout.addWidget(self.lbl_b_val)
        layout.addSpacing(6)
        layout.addWidget(lbl_c)
        layout.addWidget(self.sld_contrast, 1)
        layout.addWidget(self.lbl_c_val)
        layout.addWidget(btn_reset)
        layout.addWidget(btn_close)

    def _on_b_slider(self, val):
        self.lbl_b_val.setText(("%+d" if val > 0 else "%d") % val)
        self._emit_change()

    def _on_c_slider(self, val):
        self.lbl_c_val.setText(("%+d" if val > 0 else "%d") % val)
        self._emit_change()

    def _emit_change(self):
        target = self.cmb_target.currentData() or "BOTH"
        gray = self.chk_gray.isChecked()
        brightness = self.sld_brightness.value()
        contrast = self.sld_contrast.value()
        self.adjustmentChanged.emit(target, gray, brightness, contrast)

    def _on_reset(self):
        target = self.cmb_target.currentData() or "BOTH"
        for w in (self.chk_gray, self.sld_brightness, self.sld_contrast):
            w.blockSignals(True)
        self.chk_gray.setChecked(False)
        self.sld_brightness.setValue(0)
        self.sld_contrast.setValue(0)
        self.lbl_b_val.setText("0")
        self.lbl_c_val.setText("0")
        for w in (self.chk_gray, self.sld_brightness, self.sld_contrast):
            w.blockSignals(False)
        self.resetRequested.emit(target)
