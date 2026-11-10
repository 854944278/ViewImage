# -*- coding: utf-8 -*-
"""
ViewImage 全面自动化测试套件
涵盖：Qt 兼容层、规则引擎、扫描器、配置读写、滤镜变换、面板及主窗口功能一致性验证
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

# 确保无头环境
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import dual_image_viewer
from dual_image_viewer import (
    ConfigManager,
    ImageView,
    MainWindow,
    PairRule,
    RuleError,
    SidePanel,
    batch_copy_files,
    batch_move_files,
    build_pairs,
    common_prefix_len,
    common_suffix_len,
    copy_file_safe,
    infer_rules,
    move_file_safe,
    natural_key,
    scan_images,
)
from view_image.core.qt_compat import QtGui, QtWidgets


class TestScannerAndSorting(unittest.TestCase):
    def test_natural_key(self):
        files = ["img10.png", "img2.png", "img1.png", "img20.png"]
        sorted_files = sorted(files, key=natural_key)
        self.assertEqual(sorted_files, ["img1.png", "img2.png", "img10.png", "img20.png"])

    def test_scan_images(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建若干测试文件
            p1 = Path(tmpdir) / "test2.jpg"
            p2 = Path(tmpdir) / "test10.png"
            p3 = Path(tmpdir) / "test1.bmp"
            p4 = Path(tmpdir) / "readme.txt"
            for p in (p1, p2, p3, p4):
                p.write_bytes(b"dummy")

            scanned = scan_images(tmpdir)
            names = [p.name for p in scanned]
            self.assertEqual(names, ["test1.bmp", "test2.jpg", "test10.png"])

            # 测试不存在路径
            self.assertEqual(scan_images("/non/existent/path"), [])
            self.assertEqual(scan_images(""), [])


class TestPairRules(unittest.TestCase):
    def test_same_and_same_ext(self):
        r_same = PairRule("same")
        self.assertEqual(r_same.key("abc.png", "L"), "abc")
        self.assertEqual(r_same.key("abc.jpg", "R"), "abc")

        r_same_ext = PairRule("same_ext")
        self.assertEqual(r_same_ext.key("abc.png", "L"), "abc.png")
        self.assertNotEqual(r_same_ext.key("abc.png", "L"), r_same_ext.key("abc.jpg", "R"))

    def test_prefix_and_suffix(self):
        r_pre = PairRule("prefix:4")
        self.assertEqual(r_pre.key("1234_abc.png", "L"), "1234")
        self.assertIsNone(r_pre.key("12.png", "L"))

        r_suf = PairRule("suffix:3")
        self.assertEqual(r_suf.key("image_007.png", "L"), "007")
        self.assertIsNone(r_suf.key("0.png", "L"))

        with self.assertRaises(RuleError):
            PairRule("prefix:0")
        with self.assertRaises(RuleError):
            PairRule("prefix:-5")
        with self.assertRaises(RuleError):
            PairRule("prefix:abc")

    def test_number_rule(self):
        r_num = PairRule("number")
        self.assertEqual(r_num.key("batch_01_wire_99.png", "L"), "01|99")
        self.assertEqual(r_num.key("camB_01_99_crop.jpg", "R"), "01|99")
        self.assertIsNone(r_num.key("no_digits_here.png", "L"))

    def test_strip_rule(self):
        r_strip = PairRule("strip:left_|_ok|right_|_ng")
        self.assertEqual(r_strip.key("left_0042_ok.png", "L"), "0042")
        self.assertEqual(r_strip.key("right_0042_ng.png", "R"), "0042")
        self.assertIsNone(r_strip.key("left_0042_other.png", "L"))
        self.assertIsNone(r_strip.key("other_0042_ng.png", "R"))

        with self.assertRaises(RuleError):
            PairRule("strip:only|two|parts")

    def test_regex_rule(self):
        r_re = PairRule(r"regex:sample_(\d+)")
        self.assertEqual(r_re.key("sample_055_left.png", "L"), "055")
        self.assertIsNone(r_re.key("test_055.png", "L"))

        with self.assertRaises(RuleError):
            PairRule("regex:(")

    def test_build_pairs(self):
        lefts = [Path("sample_01_A.png"), Path("sample_02_A.png"), Path("sample_03_A.png")]
        rights = [Path("sample_02_B.png"), Path("sample_01_B.png"), Path("sample_04_B.png")]

        pairs, ul, ur = build_pairs(lefts, rights, "prefix:9")
        self.assertEqual(len(pairs), 2)
        # 保持左侧顺序
        self.assertEqual(pairs[0][0].name, "sample_01_A.png")
        self.assertEqual(pairs[0][1].name, "sample_01_B.png")
        self.assertEqual(pairs[1][0].name, "sample_02_A.png")
        self.assertEqual(pairs[1][1].name, "sample_02_B.png")
        self.assertEqual([p.name for p in ul], ["sample_03_A.png"])
        self.assertEqual([p.name for p in ur], ["sample_04_B.png"])

    def test_infer_rules(self):
        samples = [("cam1_#001_raw.png", "cam2_#001_proc.png"),
                   ("cam1_#002_raw.png", "cam2_#002_proc.png")]
        lefts = [Path(f"cam1_#{i:03d}_raw.png") for i in range(1, 10)]
        rights = [Path(f"cam2_#{i:03d}_proc.png") for i in range(1, 10)]

        candidates = infer_rules(samples, lefts, rights)
        self.assertTrue(len(candidates) > 0)
        # 验证数字提取规则或 strip 规则能否匹配全部 9 对
        texts = [c["text"] for c in candidates]
        self.assertTrue("number" in texts or any(t.startswith("strip:") for t in texts))


class TestConfigManager(unittest.TestCase):
    def test_config_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_file = os.path.join(tmpdir, "test_config.json")
            mgr = ConfigManager(cfg_file)

            # 初始加载默认值
            cfg = mgr.load()
            self.assertEqual(cfg["mode"], "A")
            self.assertTrue(cfg["link_views"])

            # 修改并保存
            cfg["left_dir"] = "/path/left"
            cfg["right_dir"] = "/path/right"
            cfg["mode"] = "B"
            cfg["pair_index"] = 42
            mgr.save(cfg)

            # 再次加载验证
            loaded = mgr.load()
            self.assertEqual(loaded["left_dir"], "/path/left")
            self.assertEqual(loaded["right_dir"], "/path/right")
            self.assertEqual(loaded["mode"], "B")
            self.assertEqual(loaded["pair_index"], 42)


class TestGUIAndFunctionality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cfg_path = os.path.join(self.tmpdir, "test_cfg.json")

        # 生成两组测试图片
        self.dir_l = os.path.join(self.tmpdir, "left")
        self.dir_r = os.path.join(self.tmpdir, "right")
        self.dir_out = os.path.join(self.tmpdir, "output")
        os.makedirs(self.dir_l, exist_ok=True)
        os.makedirs(self.dir_r, exist_ok=True)
        os.makedirs(self.dir_out, exist_ok=True)

        # 产生真实小图片 (64x64)
        fmt = getattr(QtGui.QImage.Format, "Format_RGB32", None) or getattr(QtGui.QImage, "Format_RGB32", None)
        for i in range(1, 6):
            img = QtGui.QImage(64, 64, fmt)
            img.fill(QtGui.QColor(i * 30, 100, 200))
            img.save(os.path.join(self.dir_l, f"item_{i:02d}_L.png"))

            img_r = QtGui.QImage(64, 64, fmt)
            img_r.fill(QtGui.QColor(200, i * 30, 100))
            img_r.save(os.path.join(self.dir_r, f"item_{i:02d}_R.png"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_image_view_operations(self):
        view = ImageView()
        test_img_path = os.path.join(self.dir_l, "item_01_L.png")
        loaded = view.load_path(test_img_path)
        self.assertTrue(loaded)
        self.assertTrue(view.is_loaded())
        self.assertEqual(view.image_size(), (64, 64))

        # 像素探针
        pixel = view.pixel_at(view.width() // 2, view.height() // 2)
        self.assertIsNotNone(pixel)
        x, y, gray, r, g, b = pixel
        self.assertTrue(0 <= x < 64)
        self.assertTrue(0 <= y < 64)
        self.assertTrue(0 <= gray <= 255)

        # 缩放与适应
        view.fit()
        self.assertTrue(view._fit_mode)
        view.zoom_by(2.0)
        self.assertFalse(view._fit_mode)
        view.set_one_to_one()
        self.assertAlmostEqual(view._scale, 1.0)

        # 亮度/对比度调节
        view.set_brightness(20)
        view.set_contrast(10)
        view.set_gray(True)
        view.reset_display()
        self.assertEqual(view._brightness, 0)
        self.assertEqual(view._contrast, 0)
        self.assertFalse(view._gray)

    def test_main_window_mode_a_and_b(self):
        win = MainWindow(config_path=self.cfg_path)
        win.edt_left.setText(self.dir_l)
        win.edt_right.setText(self.dir_r)
        win.edt_output.setText(self.dir_out)
        win.rule_text = "prefix:7"
        win.mode = "A"
        win._on_dirs_changed()

        # 模式 A：配对同步
        self.assertEqual(len(win.pairs), 5)
        self.assertEqual(win.pair_index, 0)
        win._turn_pair(1)
        self.assertEqual(win.pair_index, 1)

        # 模式 B：独立翻页
        win._on_mode_clicked("B")
        self.assertEqual(win.mode, "B")
        win._turn_side("L", 1)
        self.assertEqual(win.left_index, 1)
        self.assertEqual(win.right_index, 0)
        win._turn_side("R", 2)
        self.assertEqual(win.right_index, 2)

        # 左右互换测试
        win._swap_dirs()
        self.assertEqual(win.edt_left.text(), self.dir_r)
        self.assertEqual(win.edt_right.text(), self.dir_l)

        # 保存当前图像至输出目录
        win._save_current("L")
        out_files = os.listdir(self.dir_out)
        self.assertEqual(len(out_files), 1)

        # 再次保存：自动追加后缀不覆盖
        win._save_current("L")
        out_files_2 = os.listdir(self.dir_out)
        self.assertEqual(len(out_files_2), 2)
        self.assertTrue(any("_1" in f for f in out_files_2))

        # 文件列表展开/收起
        win._toggle_file_lists()
        self.assertFalse(win._show_file_list)
        win._toggle_file_lists()
        self.assertTrue(win._show_file_list)

    def test_search_filter_in_side_panel(self):
        panel = SidePanel("测试面板", is_left=True)
        paths = [(Path(f"prefix_{i:02d}_typeA.png"), None) for i in range(10)]
        paths += [(Path(f"special_{i:02d}_typeB.png"), None) for i in range(5)]
        panel.fill_list(paths, mark_unmatched=False)

        self.assertEqual(panel.list_widget.count(), 15)

        # 过滤 "special"
        panel.edt_filter.setText("special")
        self.assertEqual(panel.list_widget.count(), 5)

        # 清除过滤
        panel.btn_clear_filter.click()
        self.assertEqual(panel.list_widget.count(), 15)

    def test_corrupt_config_graceful_recovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_file = os.path.join(tmpdir, "bad_cfg.json")
            with open(cfg_file, "w") as f:
                f.write("{invalid json content!!!")

            mgr = ConfigManager(cfg_file)
            cfg = mgr.load()
            # 应该优雅降级回默认值，而不是崩溃
            self.assertEqual(cfg["mode"], "A")
            self.assertEqual(cfg["pair_index"], 0)

    def test_safe_file_ops_copy_and_cut(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = os.path.join(tmpdir, "src")
            out_dir = os.path.join(tmpdir, "out")
            os.makedirs(src_dir, exist_ok=True)
            os.makedirs(out_dir, exist_ok=True)

            f1 = Path(src_dir) / "test_img.png"
            f1.write_bytes(b"content_1")

            # 首次拷贝
            t1 = copy_file_safe(f1, out_dir)
            self.assertTrue(os.path.isfile(t1))
            self.assertEqual(os.path.basename(t1), "test_img.png")
            self.assertTrue(f1.exists())  # 拷贝不删除源文件

            # 重名再次拷贝：自动递增 _1
            t2 = copy_file_safe(f1, out_dir)
            self.assertEqual(os.path.basename(t2), "test_img_1.png")

            # 剪切（移动）
            t3 = move_file_safe(f1, out_dir)
            self.assertEqual(os.path.basename(t3), "test_img_2.png")
            self.assertFalse(f1.exists())  # 源文件已被移走

    def test_batch_copy_and_cut(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = os.path.join(tmpdir, "src")
            out_dir = os.path.join(tmpdir, "out")
            os.makedirs(src_dir, exist_ok=True)
            os.makedirs(out_dir, exist_ok=True)

            files = []
            for i in range(5):
                p = Path(src_dir) / f"photo_{i:02d}.jpg"
                p.write_bytes(b"data")
                files.append(p)

            # 批量拷贝
            successes, failures = batch_copy_files(files, out_dir)
            self.assertEqual(len(successes), 5)
            self.assertEqual(len(failures), 0)
            self.assertEqual(len(os.listdir(out_dir)), 5)
            self.assertEqual(len(os.listdir(src_dir)), 5)

            # 批量剪切剩余文件
            successes_cut, failures_cut = batch_move_files(files, out_dir)
            self.assertEqual(len(successes_cut), 5)
            self.assertEqual(len(failures_cut), 0)
            self.assertEqual(len(os.listdir(src_dir)), 0)  # 源文件全部移出
            self.assertEqual(len(os.listdir(out_dir)), 10)  # 重名追加了 _1

    def test_gui_single_cut_and_advance(self):
        win = MainWindow(config_path=self.cfg_path)
        win.edt_left.setText(self.dir_l)
        win.edt_right.setText(self.dir_r)
        win.edt_output.setText(self.dir_out)
        win.rule_text = "prefix:7"
        win.mode = "A"
        win._on_dirs_changed()

        self.assertEqual(len(win.pairs), 5)
        first_left_file = win.pairs[0][0]

        # 剪切当前左侧图片
        win._cut_current("L")

        # 验证文件已从左目录移走并进入输出目录
        self.assertFalse(first_left_file.exists())
        self.assertEqual(len(os.listdir(self.dir_out)), 1)
        # 验证列表自动刷新并就绪下一对
        self.assertEqual(len(win.pairs), 4)

    def test_gui_batch_check_and_sync(self):
        win = MainWindow(config_path=self.cfg_path)
        win.edt_left.setText(self.dir_l)
        win.edt_right.setText(self.dir_r)
        win.edt_output.setText(self.dir_out)
        win.rule_text = "prefix:7"
        win.mode = "A"
        win._on_dirs_changed()

        # 测试全选
        win.left_panel.select_all()
        checked_l = win.left_panel.get_checked_paths()
        self.assertEqual(len(checked_l), 5)

        # 验证成对联动勾选到右侧
        checked_r = win.right_panel.get_checked_paths()
        self.assertEqual(len(checked_r), 5)

        # 清空全选
        win.left_panel.unselect_all()
        self.assertEqual(len(win.left_panel.get_checked_paths()), 0)
        self.assertEqual(len(win.right_panel.get_checked_paths()), 0)


if __name__ == "__main__":
    unittest.main()
