# -*- coding: utf-8 -*-
"""
文件安全拷贝与剪切（移动）操作模块
支持防覆盖递增自动重命名与批量并发/串行安全处理
"""

import os
import shutil
from pathlib import Path


def get_unique_target_path(source_path, dest_dir):
    """
    计算目标输出目录下的唯一文件名。
    若同名文件已存在，则自动添加 _1, _2 等后缀，绝对杜绝文件被意外覆盖。
    """
    name = os.path.basename(str(source_path))
    stem, ext = os.path.splitext(name)
    target = os.path.join(dest_dir, name)
    counter = 1
    while os.path.exists(target):
        target = os.path.join(dest_dir, "%s_%d%s" % (stem, counter, ext))
        counter += 1
    return target


def copy_file_safe(source_path, dest_dir):
    """
    将文件安全复制到 dest_dir，重名自动递增加后缀。
    返回复制后的目标路径字符串。
    """
    source = str(source_path)
    if not os.path.isfile(source):
        raise FileNotFoundError("源文件不存在：%s" % source)
    if not dest_dir or not os.path.isdir(dest_dir):
        raise ValueError("目标输出目录无效或不存在：%s" % dest_dir)

    target = get_unique_target_path(source, dest_dir)
    shutil.copy2(source, target)
    return target


def move_file_safe(source_path, dest_dir):
    """
    将文件安全剪切（移动）到 dest_dir，重名自动递增加后缀。
    返回移动后的目标路径字符串。
    """
    source = str(source_path)
    if not os.path.isfile(source):
        raise FileNotFoundError("源文件不存在：%s" % source)
    if not dest_dir or not os.path.isdir(dest_dir):
        raise ValueError("目标输出目录无效或不存在：%s" % dest_dir)

    target = get_unique_target_path(source, dest_dir)
    shutil.move(source, target)
    return target


def batch_copy_files(source_paths, dest_dir, progress_callback=None):
    """
    批量拷贝文件到 dest_dir。
    返回 (成功列表 [(src, target), ...], 失败列表 [(src, err_msg), ...])。
    """
    successes = []
    failures = []
    total = len(source_paths)

    for idx, src in enumerate(source_paths):
        try:
            target = copy_file_safe(src, dest_dir)
            successes.append((src, target))
        except Exception as exc:
            failures.append((src, str(exc)))
        if progress_callback:
            progress_callback(idx + 1, total)

    return successes, failures


def batch_move_files(source_paths, dest_dir, progress_callback=None):
    """
    批量剪切（移动）文件到 dest_dir。
    返回 (成功列表 [(src, target), ...], 失败列表 [(src, err_msg), ...])。
    """
    successes = []
    failures = []
    total = len(source_paths)

    for idx, src in enumerate(source_paths):
        try:
            target = move_file_safe(src, dest_dir)
            successes.append((src, target))
        except Exception as exc:
            failures.append((src, str(exc)))
        if progress_callback:
            progress_callback(idx + 1, total)

    return successes, failures
