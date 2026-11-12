# -*- coding: utf-8 -*-
"""
ViewImage 现代深色工业主题与样式定义 (QSS)
为图像对比与质检工作设计的高对比度、低视觉疲劳的专业深色主题。
"""

DARK_THEME_QSS = """
/* 全局基础设置 */
QWidget {
    background-color: #1a1b22;
    color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
    font-size: 12px;
    outline: none;
}

/* 主窗口与主工作区 */
QMainWindow {
    background-color: #13141a;
}

/* 卡片容器与面板 */
QFrame[frameShape="1"], QFrame[frameShape="2"], QFrame[frameShape="4"], QFrame[frameShape="5"] {
    border: 1px solid #2d3342;
    border-radius: 6px;
}

.CardPanel {
    background-color: #21242d;
    border: 1px solid #2e3444;
    border-radius: 6px;
}

/* 工具栏与顶部区域 */
.TopRibbon {
    background-color: #1d2028;
    border-bottom: 1px solid #2c3242;
    padding: 6px;
}

/* 标签文本 */
QLabel {
    background: transparent;
    color: #cbd5e1;
}

QLabel[heading="true"] {
    font-size: 13px;
    font-weight: bold;
    color: #f8fafc;
}

QLabel[secondary="true"] {
    color: #94a3b8;
    font-size: 11px;
}

/* 徽章标签 */
.BadgeLabel {
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 600;
    font-size: 11px;
}

.BadgeLeft {
    background-color: #0369a1;
    color: #f0f9ff;
    border: 1px solid #0284c7;
}

.BadgeRight {
    background-color: #047857;
    color: #ecfdf5;
    border: 1px solid #059669;
}

.BadgeNeutral {
    background-color: #334155;
    color: #f1f5f9;
    border: 1px solid #475569;
}

.BadgeSuccess {
    background-color: #065f46;
    color: #d1fae5;
    border: 1px solid #059669;
}

.BadgeWarning {
    background-color: #854d0e;
    color: #fef9c3;
    border: 1px solid #a16207;
}

/* 输入框 */
QLineEdit {
    background-color: #171920;
    border: 1px solid #333a4c;
    border-radius: 5px;
    padding: 4px 8px;
    color: #f8fafc;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
    min-height: 22px;
}

QLineEdit:hover {
    border: 1px solid #475569;
}

QLineEdit:focus {
    border: 1px solid #3b82f6;
    background-color: #191c25;
}

QLineEdit:disabled {
    background-color: #13141a;
    border-color: #262a36;
    color: #64748b;
}

/* 按钮样式 */
QPushButton, QToolButton {
    background-color: #282d3b;
    border: 1px solid #394154;
    border-radius: 5px;
    padding: 5px 12px;
    color: #e2e8f0;
    font-weight: 500;
    min-height: 20px;
}

QPushButton:hover, QToolButton:hover {
    background-color: #333a4c;
    border-color: #4a556d;
    color: #ffffff;
}

QPushButton:pressed, QToolButton:pressed {
    background-color: #1f232e;
    border-color: #2b3240;
}

QPushButton:checked, QToolButton:checked {
    background-color: #2563eb;
    border: 1px solid #3b82f6;
    color: #ffffff;
    font-weight: 600;
}

QPushButton:checked:hover, QToolButton:checked:hover {
    background-color: #3b82f6;
    border-color: #60a5fa;
}

QPushButton:disabled, QToolButton:disabled {
    background-color: #1a1c24;
    border-color: #272c38;
    color: #556075;
}

/* 主操作按钮 (Primary) */
QPushButton[primary="true"], QToolButton[primary="true"] {
    background-color: #2563eb;
    border: 1px solid #3b82f6;
    color: #ffffff;
    font-weight: 600;
}

QPushButton[primary="true"]:hover, QToolButton[primary="true"]:hover {
    background-color: #3b82f6;
    border-color: #60a5fa;
}

QPushButton[primary="true"]:pressed, QToolButton[primary="true"]:pressed {
    background-color: #1d4ed8;
    border-color: #1e40af;
}

QPushButton[primary="true"]:disabled, QToolButton[primary="true"]:disabled {
    background-color: #1e3a5f;
    border-color: #20406d;
    color: #607594;
}

/* 成功/强调按钮 */
QPushButton[success="true"], QToolButton[success="true"] {
    background-color: #059669;
    border: 1px solid #10b981;
    color: #ffffff;
}

QPushButton[success="true"]:hover, QToolButton[success="true"]:hover {
    background-color: #10b981;
}

/* 紧凑微型按钮 */
QPushButton[small="true"], QToolButton[small="true"] {
    padding: 3px 8px;
    font-size: 11px;
    min-height: 18px;
}

QToolButton::menu-button {
    border-left: 1px solid #394154;
    width: 14px;
}

/* 单选框与复选框 */
QRadioButton, QCheckBox {
    spacing: 6px;
    color: #cbd5e1;
}

QRadioButton:hover, QCheckBox:hover {
    color: #ffffff;
}

QRadioButton::indicator, QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid #475569;
    background-color: #171920;
    border-radius: 3px;
}

QRadioButton::indicator {
    border-radius: 8px;
}

QRadioButton::indicator:hover, QCheckBox::indicator:hover {
    border-color: #3b82f6;
}

QCheckBox::indicator:checked {
    background-color: #2563eb;
    border-color: #3b82f6;
    image: none;
}

QRadioButton::indicator:checked {
    background-color: #2563eb;
    border: 3px solid #171920;
}

QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
    border-color: #2c3240;
    background-color: #16181f;
}

/* 下拉框 */
QComboBox {
    background-color: #1a1d26;
    border: 1px solid #343b4c;
    border-radius: 5px;
    padding: 4px 10px;
    color: #e2e8f0;
    min-height: 22px;
}

QComboBox:hover {
    border-color: #475569;
}

QComboBox:focus {
    border-color: #3b82f6;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    border-left: 1px solid #2e3444;
}

QComboBox QAbstractItemView {
    background-color: #1a1d26;
    border: 1px solid #3b82f6;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
    padding: 4px;
    border-radius: 4px;
}

/* 滑块控件 */
QSlider::groove:horizontal {
    height: 5px;
    background: #2b3140;
    border-radius: 2px;
}

QSlider::sub-page:horizontal {
    background: #3b82f6;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: #ffffff;
    border: 2px solid #2563eb;
    width: 14px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 7px;
}

QSlider::handle:horizontal:hover {
    background: #dbeafe;
    border-color: #3b82f6;
    transform: scale(1.1);
}

/* 列表控件 */
QListWidget {
    background-color: #16181f;
    border: 1px solid #292f3d;
    border-radius: 5px;
    padding: 3px;
    color: #cbd5e1;
}

QListWidget::item {
    height: 24px;
    padding: 2px 6px;
    border-radius: 3px;
    margin: 1px 0px;
}

QListWidget::item:hover {
    background-color: #232834;
    color: #ffffff;
}

QListWidget::item:selected {
    background-color: #1e3a8a;
    color: #ffffff;
    font-weight: 500;
}

/* 拆分器 */
QSplitter::handle {
    background-color: #232733;
}

QSplitter::handle:horizontal {
    width: 4px;
}

QSplitter::handle:vertical {
    height: 4px;
}

QSplitter::handle:hover {
    background-color: #3b82f6;
}

/* 滚动条 */
QScrollBar:vertical {
    background: #14161d;
    width: 8px;
    margin: 0;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #333a4d;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #475569;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background: #14161d;
    height: 8px;
    margin: 0;
    border-radius: 4px;
}

QScrollBar::handle:horizontal {
    background: #333a4d;
    min-width: 20px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background: #475569;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* 状态栏 */
QStatusBar {
    background-color: #14161c;
    border-top: 1px solid #242936;
    color: #94a3b8;
    padding: 2px 8px;
}

QStatusBar QLabel {
    color: #94a3b8;
}

/* 提示气泡 */
QToolTip {
    background-color: #0f172a;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 11px;
}

/* 弹窗对话框 */
QDialog {
    background-color: #181a22;
}

QGroupBox {
    border: 1px solid #2d3342;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 12px;
    font-weight: bold;
    color: #f1f5f9;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: #93c5fd;
}

/* 顶部菜单栏与下拉菜单 */
QMenuBar {
    background-color: #14161d;
    color: #cbd5e1;
    border-bottom: 1px solid #232733;
    padding: 2px 6px;
    font-size: 12px;
}

QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
    border-radius: 4px;
    color: #cbd5e1;
}

QMenuBar::item:selected {
    background-color: #272c3a;
    color: #38bdf8;
}

QMenuBar::item:pressed {
    background-color: #1e3a8a;
    color: #ffffff;
}

QMenu {
    background-color: #1c1f29;
    color: #e2e8f0;
    border: 1px solid #2f3647;
    border-radius: 6px;
    padding: 4px 0;
    font-size: 12px;
}

QMenu::item {
    padding: 6px 26px 6px 20px;
    border-radius: 3px;
    margin: 1px 4px;
}

QMenu::item:selected {
    background-color: #2563eb;
    color: #ffffff;
}

QMenu::item:disabled {
    color: #64748b;
}

QMenu::separator {
    height: 1px;
    background-color: #2a3142;
    margin: 4px 8px;
}

QMenu::indicator {
    width: 14px;
    height: 14px;
    margin-left: 4px;
}
"""
