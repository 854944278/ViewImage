# -*- coding: utf-8 -*-
"""
图像文件扫描与自然排序模块
"""

import os
import re
from pathlib import Path

IMAGE_EXTS = {
    ".bmp", ".png", ".jpg", ".jpeg", ".jfif", ".tif", ".tiff",
    ".gif", ".webp", ".ppm", ".pgm", ".pbm",
}


def natural_key(text):
    """
    自然排序键：如 img2 排在 img10 前面。
    按数字与非数字段分割，数字段转换为整数参与比对。
    """
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", text)]


def scan_images(folder):
    """
    只扫描顶层目录中的支持图像格式，返回按文件名自然排序的 Path 列表。
    若路径为空、非目录或读取失败，安全返回空列表。
    """
    if not folder or not os.path.isdir(folder):
        return []
    found = []
    try:
        with os.scandir(folder) as it:
            for entry in it:
                if entry.is_file() and os.path.splitext(entry.name)[1].lower() in IMAGE_EXTS:
                    found.append(Path(entry.path))
    except OSError:
        return []
    return sorted(found, key=lambda p: natural_key(p.name))
