# -*- coding: utf-8 -*-
"""
应用配置持久化管理模块
"""

import json
import os

DEFAULT_CONFIG_NAME = "viewer_config.json"


class ConfigManager:
    """管理 viewer_config.json 的读写与默认值"""

    def __init__(self, config_path=None):
        if config_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            config_path = os.path.join(base_dir, DEFAULT_CONFIG_NAME)
        self.config_path = config_path

    def load(self):
        """读取配置，若文件不存在或格式损坏则返回默认字典。"""
        defaults = {
            "left_dir": "",
            "right_dir": "",
            "output_dir": "",
            "mode": "A",
            "rule_text": "",
            "link_views": True,
            "pair_index": 0,
            "left_index": 0,
            "right_index": 0,
            "show_file_list": True,
        }
        if not os.path.isfile(self.config_path):
            return defaults
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return defaults
            # 合并默认值
            for k, v in defaults.items():
                if k not in data:
                    data[k] = v
            # 校验枚举与整型
            if data["mode"] not in ("A", "B"):
                data["mode"] = "A"
            for idx_key in ("pair_index", "left_index", "right_index"):
                try:
                    data[idx_key] = max(0, int(data.get(idx_key, 0) or 0))
                except (ValueError, TypeError):
                    data[idx_key] = 0
            data["link_views"] = bool(data.get("link_views", True))
            data["show_file_list"] = bool(data.get("show_file_list", True))
            return data
        except Exception:
            return defaults

    def save(self, data):
        """保存配置字典至 json 文件。"""
        try:
            payload = {
                "left_dir": str(data.get("left_dir", "") or "").strip(),
                "right_dir": str(data.get("right_dir", "") or "").strip(),
                "output_dir": str(data.get("output_dir", "") or "").strip(),
                "mode": "B" if data.get("mode") == "B" else "A",
                "rule_text": str(data.get("rule_text", "") or "").strip(),
                "link_views": bool(data.get("link_views", True)),
                "pair_index": int(data.get("pair_index", 0) or 0),
                "left_index": int(data.get("left_index", 0) or 0),
                "right_index": int(data.get("right_index", 0) or 0),
                "show_file_list": bool(data.get("show_file_list", True)),
            }
            tmp_path = self.config_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.config_path)
            return True
        except OSError:
            return False
