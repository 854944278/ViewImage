# -*- coding: utf-8 -*-
"""
快捷键与操作帮助对话框
"""

from ..core.qt_compat import QtWidgets


class HelpDialog(QtWidgets.QDialog):
    """显示双栏图像查看器的快捷键列表与功能指南"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("快捷键与使用指南  |  ViewImage")
        self.resize(680, 520)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QtWidgets.QLabel("📖 ViewImage 双栏图像查看器使用指南")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #93c5fd;")
        layout.addWidget(title)

        text_browser = QtWidgets.QTextBrowser()
        text_browser.setOpenExternalLinks(True)
        text_browser.setStyleSheet("""
            QTextBrowser {
                background-color: #181a22;
                border: 1px solid #282d3b;
                border-radius: 6px;
                padding: 12px;
                color: #e2e8f0;
                font-size: 12px;
                line-height: 1.6;
            }
        """)

        html_content = """
        <style>
            h3 { color: #60a5fa; margin-top: 10px; margin-bottom: 6px; font-size: 13px; }
            table { width: 100%; border-collapse: collapse; margin-bottom: 12px; }
            th { text-align: left; padding: 6px; background-color: #212530; color: #94a3b8; border-bottom: 1px solid #333a4c; }
            td { padding: 6px; border-bottom: 1px solid #252936; color: #cbd5e1; }
            .key { background-color: #2e3547; color: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-weight: bold; }
        </style>

        <h3>1. 模式与翻页操作</h3>
        <table>
            <tr><th>操作</th><th>快捷键 / 交互</th><th>说明</th></tr>
            <tr><td><b>分屏布局切换</b></td><td><span class="key">Alt + L</span> 或点顶部「◫ 左右」/「⬒ 上下」</td><td>支持左右分屏（水平）与上下分屏（垂直）无缝自由切换；支持菜单栏「视图 ➔ 分屏排列」</td></tr>
            <tr><td><b>模式 A 翻页</b></td><td><span class="key">←</span> / <span class="key">→</span> 或 <span class="key">↑</span> / <span class="key">↓</span></td><td>配对完成后，左右（或上下）两侧图片保持同步对应翻页</td></tr>
            <tr><td><b>模式 B 右侧/下方翻页</b></td><td><span class="key">←</span> / <span class="key">→</span> 或 <span class="key">↑</span> / <span class="key">↓</span></td><td>独立翻动右侧（或下方）图片</td></tr>
            <tr><td><b>模式 B 左侧/上方翻页</b></td><td><span class="key">Shift + ←</span> / <span class="key">Shift + →</span> / <span class="key">Shift + ↑</span> / <span class="key">Shift + ↓</span></td><td>独立翻动左侧（或上方）图片</td></tr>
            <tr><td><b>光标所在侧翻页</b></td><td><span class="key">PageUp</span> / <span class="key">PageDown</span></td><td>独立翻动鼠标当前悬停的面板</td></tr>
        </table>

        <h3>2. 画布缩放与平移</h3>
        <table>
            <tr><th>操作</th><th>快捷键 / 交互</th><th>说明</th></tr>
            <tr><td><b>光标中心缩放</b></td><td>鼠标滚轮 <span class="key">Wheel</span></td><td>以当前光标所在点为锚点无级缩放（0.02x ~ 64x）</td></tr>
            <tr><td><b>拖动画布</b></td><td>按住鼠标左键拖动</td><td>平移查看高分辨率图像细节</td></tr>
            <tr><td><b>双击适应</b></td><td>鼠标左键双击</td><td>图像居中并自适应当前窗口尺寸</td></tr>
            <tr><td><b>视图联动</b></td><td>勾选「视图联动」</td><td>两边缩放倍数和平移相对位置完全保持同步</td></tr>
        </table>

        <h3>3. 文件保存、拷贝与剪切操作</h3>
        <table>
            <tr><th>操作</th><th>快捷键 / 按钮</th><th>行为说明</th></tr>
            <tr><td><b>单张拷贝 (当前/单边)</b></td><td><span class="key">Ctrl + C</span> / <span class="key">Ctrl + S</span> 或点「📋 拷贝」</td><td>拷贝当前光标悬停图像至输出目录。支持点按钮下拉或快捷键：<span class="key">Shift + C</span> 仅拷贝左(上)图，<span class="key">Alt + C</span> 仅拷贝右(下)图；画板右键亦可直达。</td></tr>
            <tr><td><b>单张剪切 (当前/单边)</b></td><td><span class="key">Ctrl + X</span> 或点「✂ 剪切」</td><td>移动当前图像至输出目录并自动跳至下一张。支持点按钮下拉或快捷键：<span class="key">Shift + X</span> 仅剪切左(上)图，<span class="key">Alt + X</span> 仅剪切右(下)图；画板右键亦可直达。</td></tr>
            <tr><td><b>单文件夹批量处理</b></td><td>侧栏「范围: 全部 ▾」下拉选择</td><td>可在侧栏下拉选择<b>「仅左(上)侧目录」</b>或<b>「仅右(下)侧目录」</b>，无论处于模式 A 还是 B，均能精确单独拷贝/剪切单个文件夹的所有勾选图像！</td></tr>
            <tr><td><b>批量勾选</b></td><td>勾选列表复选框 / 点「☑ 全选」/「反选」</td><td>列表中每项均带复选框，输入关键字过滤时不丢失勾选状态；模式 A 下成对勾选，并按选定范围精确计数。</td></tr>
            <tr><td><b>批量拷贝/剪切</b></td><td>列表上方「📋 批量拷贝」/「✂ 批量剪切」</td><td>一键批量将勾选图片安全复制或移动至输出目录，剪切时弹窗确认防误触，处理后自动刷新。</td></tr>
            <tr><td><b>显示层滤镜</b></td><td>灰度 / 亮度 / 对比度调节</td><td>支持独立开关灰度与亮度对比度调节（-100 ~ +100），仅改变屏幕渲染，不修改原始文件。</td></tr>
            <tr><td><b>像素级探针</b></td><td>鼠标悬停画板</td><td>底部状态栏右侧实时展示原图坐标 (X, Y)、灰度值、RGB 色值及实时色彩预览色块。</td></tr>
            <tr><td><b>画板右键菜单</b></td><td>画板鼠标右键单击</td><td>直接弹出当前图片快捷拷贝、剪切、适应及 1:1 菜单，直观明确杜绝误操作。</td></tr>
            <tr><td><b>展开/收起列表</b></td><td><span class="key">F3</span> 或点顶部「📋 列表」</td><td>随时收起文件列表与批量条，将 100% 垂直空间留给图像大屏对比。</td></tr>
            <tr><td><b>拖拽加载</b></td><td>拖放至画板</td><td>可直接把文件夹从文件管理器拖放到左右画板上快速设定目录。</td></tr>
        </table>
        """
        text_browser.setHtml(html_content)
        layout.addWidget(text_browser)

        btn_close = QtWidgets.QPushButton("关闭")
        btn_close.setProperty("primary", "true")
        btn_close.setFixedWidth(80)
        btn_close.clicked.connect(self.accept)

        h_btn = QtWidgets.QHBoxLayout()
        h_btn.addStretch(1)
        h_btn.addWidget(btn_close)
        layout.addLayout(h_btn)
