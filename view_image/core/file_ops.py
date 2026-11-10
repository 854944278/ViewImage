# -*- coding: utf-8 -*-
"""
文件安全拷贝与剪切（移动）操作模块
支持目标重名智能检测、多策略冲突提示（递增重命名/覆盖/跳过）及批量处理
"""

import os
import shutil
from pathlib import Path

POLICY_RENAME = "rename"        # 自动递增重命名 (追加 _1, _2 等)
POLICY_OVERWRITE = "overwrite"  # 覆盖已存在的目标文件
POLICY_SKIP = "skip"            # 跳过已存在的文件


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


def check_conflicts(source_paths, dest_dir):
    """
    预检源文件在目标输出目录中是否存在重名冲突。
    返回已存在的重名文件名列表 [filename1, filename2, ...]
    """
    if not dest_dir or not os.path.isdir(dest_dir):
        return []
    conflicts = []
    for src in source_paths:
        name = os.path.basename(str(src))
        target = os.path.join(dest_dir, name)
        if os.path.exists(target):
            conflicts.append(name)
    return conflicts


def copy_file_safe(source_path, dest_dir, policy=POLICY_RENAME):
    """
    安全复制文件至目标目录，支持冲突处理策略：
      - rename: 自动递增加 _1, _2 后缀
      - overwrite: 直接覆盖目标同名文件
      - skip: 若已存在则跳过复制
    返回 (状态 "copied"|"skipped", 最终目标路径)
    """
    source = str(source_path)
    if not os.path.isfile(source):
        raise FileNotFoundError("源文件不存在：%s" % source)
    if not dest_dir or not os.path.isdir(dest_dir):
        raise ValueError("目标输出目录无效或不存在：%s" % dest_dir)

    name = os.path.basename(source)
    exact_target = os.path.join(dest_dir, name)

    if os.path.exists(exact_target):
        if policy == POLICY_SKIP:
            return "skipped", exact_target
        elif policy == POLICY_OVERWRITE:
            target = exact_target
        else:  # rename
            target = get_unique_target_path(source, dest_dir)
    else:
        target = exact_target

    shutil.copy2(source, target)
    return "copied", target


def move_file_safe(source_path, dest_dir, policy=POLICY_RENAME):
    """
    安全剪切（移动）文件至目标目录，支持冲突处理策略：
      - rename: 自动递增加 _1, _2 后缀
      - overwrite: 直接覆盖目标同名文件
      - skip: 若已存在则跳过剪切（保留原文件不动）
    返回 (状态 "moved"|"skipped", 最终目标路径)
    """
    source = str(source_path)
    if not os.path.isfile(source):
        raise FileNotFoundError("源文件不存在：%s" % source)
    if not dest_dir or not os.path.isdir(dest_dir):
        raise ValueError("目标输出目录无效或不存在：%s" % dest_dir)

    name = os.path.basename(source)
    exact_target = os.path.join(dest_dir, name)

    if os.path.exists(exact_target):
        if policy == POLICY_SKIP:
            return "skipped", exact_target
        elif policy == POLICY_OVERWRITE:
            if os.path.abspath(source) != os.path.abspath(exact_target):
                os.remove(exact_target)
            target = exact_target
        else:  # rename
            target = get_unique_target_path(source, dest_dir)
    else:
        target = exact_target

    shutil.move(source, target)
    return "moved", target


def batch_copy_files(source_paths, dest_dir, policy=POLICY_RENAME, progress_callback=None):
    """
    批量拷贝文件至 dest_dir。
    返回 (成功列表 [(src, target), ...], 跳过列表 [src, ...], 失败列表 [(src, err_msg), ...])
    """
    successes, skipped, failures = [], [], []
    total = len(source_paths)

    for idx, src in enumerate(source_paths):
        try:
            status, target = copy_file_safe(src, dest_dir, policy=policy)
            if status == "skipped":
                skipped.append(src)
            else:
                successes.append((src, target))
        except Exception as exc:
            failures.append((src, str(exc)))
        if progress_callback:
            progress_callback(idx + 1, total)

    return successes, skipped, failures


def batch_move_files(source_paths, dest_dir, policy=POLICY_RENAME, progress_callback=None):
    """
    批量剪切（移动）文件至 dest_dir。
    返回 (成功列表 [(src, target), ...], 跳过列表 [src, ...], 失败列表 [(src, err_msg), ...])
    """
    successes, skipped, failures = [], [], []
    total = len(source_paths)

    for idx, src in enumerate(source_paths):
        try:
            status, target = move_file_safe(src, dest_dir, policy=policy)
            if status == "skipped":
                skipped.append(src)
            else:
                successes.append((src, target))
        except Exception as exc:
            failures.append((src, str(exc)))
        if progress_callback:
            progress_callback(idx + 1, total)

    return successes, skipped, failures
