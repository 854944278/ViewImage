# -*- coding: utf-8 -*-
"""
配对规则引擎与推断算法
"""

import os
import re
from collections import defaultdict


class RuleError(ValueError):
    """配对规则解析或执行错误"""
    pass


def _positive_int(raw, label):
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        raise RuleError("%s必须是正整数" % label)
    if value <= 0:
        raise RuleError("%s必须是正整数" % label)
    return value


class PairRule:
    """
    规则表达式（单行文本，可直接编辑）：
        same                              文件名（不含扩展名）完全相同
        same_ext                          含扩展名的完整文件名相同
        prefix:N                          文件名前 N 位相同
        suffix:N                          文件名后 N 位相同
        number                            文件名中所有数字串按顺序相同
        strip:L前|L后|R前|R后             左右各自去掉固定前后缀后，中间部分相同
        regex:PATTERN                     正则提取：优先取 group(1)，否则 group(0)
    """

    def __init__(self, text):
        self.text = (text or "").strip()
        self.kind, self.params = self._parse(self.text)

    @staticmethod
    def _parse(text):
        if not text:
            raise RuleError("规则为空")
        if text in ("same", "same_ext", "number"):
            return text, {}
        if text.startswith("prefix:"):
            return "prefix", {"n": _positive_int(text[7:], "前 N 位的 N")}
        if text.startswith("suffix:"):
            return "suffix", {"n": _positive_int(text[7:], "后 N 位的 N")}
        if text.startswith("strip:"):
            parts = text[6:].split("|")
            if len(parts) != 4:
                raise RuleError("strip 规则需要 4 段：左前缀|左后缀|右前缀|右后缀")
            return "strip", {"lp": parts[0], "ls": parts[1],
                             "rp": parts[2], "rs": parts[3]}
        if text.startswith("regex:"):
            pattern = text[6:]
            if not pattern:
                raise RuleError("正则不能为空")
            try:
                re.compile(pattern)
            except re.error as exc:
                raise RuleError("正则无效：%s" % exc)
            return "regex", {"pattern": pattern}
        raise RuleError("无法识别的规则表达式：%s" % text)

    def key(self, filename, side):
        """把文件名映射成配对用的键；不适用该规则时返回 None。"""
        stem = os.path.splitext(filename)[0]
        kind = self.kind
        if kind == "same_ext":
            return filename
        if kind == "same":
            return stem
        if kind == "prefix":
            n = self.params["n"]
            return stem[:n] if len(stem) >= n else None
        if kind == "suffix":
            n = self.params["n"]
            return stem[-n:] if len(stem) >= n else None
        if kind == "number":
            nums = re.findall(r"\d+", stem)
            return "|".join(nums) if nums else None
        if kind == "strip":
            pre = self.params["lp"] if side == "L" else self.params["rp"]
            suf = self.params["ls"] if side == "L" else self.params["rs"]
            if not stem.startswith(pre):
                return None
            if suf and not stem.endswith(suf):
                return None
            end = len(stem) - len(suf) if suf else len(stem)
            if end < len(pre):
                return None
            core = stem[len(pre):end]
            return core or None
        if kind == "regex":
            match = re.search(self.params["pattern"], stem)
            if match is None:
                return None
            index = 1 if (match.lastindex or 0) >= 1 else 0
            try:
                return match.group(index)
            except IndexError:
                return match.group(0)
        return None

    def describe(self):
        kind = self.kind
        if kind == "same_ext":
            return "完整文件名相同"
        if kind == "same":
            return "文件名相同（忽略扩展名）"
        if kind == "prefix":
            return "文件名前 %d 位相同" % self.params["n"]
        if kind == "suffix":
            return "文件名后 %d 位相同" % self.params["n"]
        if kind == "number":
            return "文件名中的编号相同（忽略前后缀）"
        if kind == "strip":
            p = self.params
            return "去前后缀后相同：左[%s…%s] / 右[%s…%s]" % (
                p["lp"], p["ls"], p["rp"], p["rs"])
        if kind == "regex":
            return "正则提取：%s" % self.params["pattern"]
        return self.text


def build_pairs(left_files, right_files, rule_text):
    """
    按规则配对。返回 (pairs, 左未匹配, 右未匹配)，pairs 保持左列表顺序。
    pairs: [(left_path, right_path), ...]
    unmatched_left: [left_path, ...]
    unmatched_right: [right_path, ...]
    """
    rule = PairRule(rule_text)
    buckets = defaultdict(list)
    for path in right_files:
        key = rule.key(path.name, "R")
        if key is not None:
            buckets[key].append(path)

    cursor = defaultdict(int)
    pairs, unmatched_left, used_right = [], [], set()
    for left in left_files:
        key = rule.key(left.name, "L")
        bucket = buckets.get(key) if key is not None else None
        index = cursor.get(key, 0) if key is not None else 0
        if bucket and index < len(bucket):
            right = bucket[index]
            cursor[key] = index + 1
            pairs.append((left, right))
            used_right.add(str(right))
        else:
            unmatched_left.append(left)
    unmatched_right = [p for p in right_files if str(p) not in used_right]
    return pairs, unmatched_left, unmatched_right


def common_prefix_len(a, b):
    count = 0
    for x, y in zip(a, b):
        if x != y:
            break
        count += 1
    return count


def common_suffix_len(a, b):
    return common_prefix_len(a[::-1], b[::-1])


def longest_common_substring(a, b):
    if not a or not b:
        return ""
    prev = [0] * (len(b) + 1)
    best_len, best_end = 0, 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        char = a[i - 1]
        for j in range(1, len(b) + 1):
            if char == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best_len:
                    best_len, best_end = cur[j], i
        prev = cur
    return a[best_end - best_len:best_end]


def strip_core(stem, pre, suf):
    if not stem.startswith(pre):
        return None
    if suf and not stem.endswith(suf):
        return None
    end = len(stem) - len(suf) if suf else len(stem)
    if end < len(pre):
        return None
    return stem[len(pre):end]


def infer_rules(sample_pairs, left_files, right_files):
    """
    从 2 对样本推断候选规则。要求规则能同时解释两对样本，且两对样本产生
    不同的键（避免 prefix:1 这类无区分度的宽泛规则）。
    返回按「匹配对数多、未匹配少、键更具体」排序的候选列表。
    """
    (l1, r1), (l2, r2) = sample_pairs
    s1, t1 = os.path.splitext(l1)[0], os.path.splitext(r1)[0]
    s2, t2 = os.path.splitext(l2)[0], os.path.splitext(r2)[0]

    texts = []
    if l1 == r1 and l2 == r2:
        texts.append("same_ext")
    if s1 == t1 and s2 == t2:
        texts.append("same")
    n_pre = min(common_prefix_len(s1, t1), common_prefix_len(s2, t2))
    if n_pre > 0:
        texts.append("prefix:%d" % n_pre)
    n_suf = min(common_suffix_len(s1, t1), common_suffix_len(s2, t2))
    if n_suf > 0:
        texts.append("suffix:%d" % n_suf)
    nums1 = re.findall(r"\d+", s1)
    nums2 = re.findall(r"\d+", s2)
    if nums1 and nums1 == re.findall(r"\d+", t1) and nums2 == re.findall(r"\d+", t2):
        texts.append("number")

    # strip 候选：以最长公共子串或数字串作为「core」锚点，反推左右各自的前后缀
    anchors = set()
    lcs = longest_common_substring(s1, t1)
    if lcs:
        anchors.add(lcs)
    for num in re.findall(r"\d+", s1):
        if num in t1:
            anchors.add(num)
    for core in anchors:
        if "|" in core:
            continue
        i1, j1 = s1.find(core), t1.find(core)
        if i1 < 0 or j1 < 0:
            continue
        lp, ls = s1[:i1], s1[i1 + len(core):]
        rp, rs = t1[:j1], t1[j1 + len(core):]
        c2l, c2r = strip_core(s2, lp, ls), strip_core(t2, rp, rs)
        if c2l is None or c2r is None or c2l != c2r:
            continue
        if any("|" in x for x in (lp, ls, rp, rs)):
            continue
        texts.append("strip:%s|%s|%s|%s" % (lp, ls, rp, rs))

    results, seen = [], set()
    for text in texts:
        if text in seen:
            continue
        seen.add(text)
        try:
            rule = PairRule(text)
        except RuleError:
            continue
        k1l, k1r = rule.key(l1, "L"), rule.key(r1, "R")
        k2l, k2r = rule.key(l2, "L"), rule.key(r2, "R")
        if k1l is None or k1l != k1r or k2l is None or k2l != k2r:
            continue
        if k1l == k2l:  # 两对样本落到同一个键，规则过于宽泛
            continue
        try:
            pairs, ul, ur = build_pairs(left_files, right_files, text)
        except RuleError:
            continue
        results.append({
            "text": text,
            "describe": rule.describe(),
            "matched": len(pairs),
            "unmatched_l": len(ul),
            "unmatched_r": len(ur),
            "specificity": len(str(k1l)) + len(str(k2l)),
        })
    results.sort(key=lambda d: (-d["matched"],
                                d["unmatched_l"] + d["unmatched_r"],
                                -d["specificity"]))
    return results
