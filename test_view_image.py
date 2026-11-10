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
    check_conflicts,
    common_prefix_len,
    common_suffix_len,
    copy_file_safe,
    infer_rules,
    move_file_safe,
    natural_key,
    scan_images,
)
from view_image.core.qt_compat import DIALOG_ACCEPTED, DIALOG_REJECTED, QtGui, QtWidgets
from view_image.widgets.path_dialog import PathSettingsDialog
from unittest.mock import patch


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
            self.assertEqual(cfg["layout_orientation"], "horizontal")

            # 修改并保存
            cfg["left_dir"] = "/path/left"
            cfg["right_dir"] = "/path/right"
            cfg["mode"] = "B"
            cfg["pair_index"] = 42
            cfg["layout_orientation"] = "vertical"
            mgr.save(cfg)

            # 再次加载验证
            loaded = mgr.load()
            self.assertEqual(loaded["left_dir"], "/path/left")
            self.assertEqual(loaded["right_dir"], "/path/right")
            self.assertEqual(loaded["mode"], "B")
            self.assertEqual(loaded["pair_index"], 42)
            self.assertEqual(loaded["layout_orientation"], "vertical")


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
        win._save_current("L", policy="rename")
        out_files = os.listdir(self.dir_out)
        self.assertEqual(len(out_files), 1)

        # 再次保存：自动追加后缀不覆盖
        win._save_current("L", policy="rename")
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
            status1, t1 = copy_file_safe(f1, out_dir)
            self.assertEqual(status1, "copied")
            self.assertTrue(os.path.isfile(t1))
            self.assertEqual(os.path.basename(t1), "test_img.png")
            self.assertTrue(f1.exists())  # 拷贝不删除源文件

            # 重名再次拷贝：自动递增 _1
            status2, t2 = copy_file_safe(f1, out_dir)
            self.assertEqual(status2, "copied")
            self.assertEqual(os.path.basename(t2), "test_img_1.png")

            # 剪切（移动）
            status3, t3 = move_file_safe(f1, out_dir)
            self.assertEqual(status3, "moved")
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
            successes, skipped, failures = batch_copy_files(files, out_dir)
            self.assertEqual(len(successes), 5)
            self.assertEqual(len(failures), 0)
            self.assertEqual(len(os.listdir(out_dir)), 5)
            self.assertEqual(len(os.listdir(src_dir)), 5)

            # 批量剪切剩余文件
            successes_cut, skipped_cut, failures_cut = batch_move_files(files, out_dir)
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

        # 剪切当前左侧图片（指定 policy 避免弹窗阻塞无头测试）
        win._cut_current("L", policy="rename")

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

        # 测试侧边抽屉列表全选（模式 A 下 5 对包含左右共 10 个文件）
        win.sidebar.select_all()
        checked = win.sidebar.get_checked_paths()
        self.assertEqual(len(checked), 10)

        # 清空全选
        win.sidebar.unselect_all()
        self.assertEqual(len(win.sidebar.get_checked_paths()), 0)

        # 针对冲突检测函数进行单元测试
        conflicts = check_conflicts([self.pairs_sample_file if hasattr(self, 'pairs_sample_file') else win.pairs[0][0]], self.dir_out)
        self.assertIsInstance(conflicts, list)

    def test_conflict_policies(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "image.png"
            src.write_bytes(b"source_content")
            out = Path(tmpdir) / "output"
            out.mkdir(parents=True, exist_ok=True)

            # 首次复制
            copy_file_safe(src, str(out))
            existing_target = out / "image.png"
            self.assertTrue(existing_target.exists())

            # 冲突检测
            conflicts = check_conflicts([src], str(out))
            self.assertEqual(conflicts, ["image.png"])

            # 策略 1: SKIP 跳过
            status, target = copy_file_safe(src, str(out), policy="skip")
            self.assertEqual(status, "skipped")

            # 策略 2: OVERWRITE 覆盖
            src.write_bytes(b"updated_content")
            status, target = copy_file_safe(src, str(out), policy="overwrite")
            self.assertEqual(status, "copied")
            self.assertEqual(existing_target.read_bytes(), b"updated_content")

            # 策略 3: RENAME 递增
            status, target = copy_file_safe(src, str(out), policy="rename")
            self.assertEqual(status, "copied")
            self.assertTrue(target.endswith("image_1.png"))

    def test_batch_cut_gui_mode_a_with_displayed_image(self):
        """测试模式 A 下批量剪切（含当前正在展示的图像），验证无锁、无闪退、自动刷新"""
        win = MainWindow(config_path=self.cfg_path)
        win.edt_left.setText(self.dir_l)
        win.edt_right.setText(self.dir_r)
        win.edt_output.setText(self.dir_out)
        win.rule_text = "prefix:7"
        win.mode = "A"
        win._on_dirs_changed()

        self.assertEqual(len(win.pairs), 5)
        # 初始状态第 0 对正在展示
        displayed_l, displayed_r = win.pairs[0]
        self.assertEqual(win.left_view.current_path(), str(displayed_l))

        # 勾选前 2 对（包含当前正显示的第 0 对）
        to_cut = [win.pairs[0][0], win.pairs[0][1], win.pairs[1][0], win.pairs[1][1]]
        win._batch_cut(to_cut, policy="rename", prompt=False)

        # 验证已成功剪切移入输出目录
        self.assertFalse(displayed_l.exists())
        self.assertFalse(displayed_r.exists())
        self.assertEqual(len(os.listdir(self.dir_out)), 4)
        # 验证配对自动刷新为剩余 3 对，当前展示顺延为新的第 0 对
        self.assertEqual(len(win.pairs), 3)
        self.assertTrue(win.left_view.is_loaded())

    def test_batch_cut_gui_cut_all_files(self):
        """测试批量剪切所有文件（清空整个目录），验证无崩溃并优雅清空视口"""
        win = MainWindow(config_path=self.cfg_path)
        win.edt_left.setText(self.dir_l)
        win.edt_right.setText(self.dir_r)
        win.edt_output.setText(self.dir_out)
        win.rule_text = "prefix:7"
        win.mode = "A"
        win._on_dirs_changed()

        win.sidebar.select_all()
        all_paths = win.sidebar.get_checked_paths()
        self.assertEqual(len(all_paths), 10)

        # 批量剪切全部文件
        win._batch_cut(all_paths, policy="rename", prompt=False)

        self.assertEqual(len(win.pairs), 0)
        self.assertEqual(len(win.left_files), 0)
        self.assertEqual(len(win.right_files), 0)
        self.assertFalse(win.left_view.is_loaded())
        self.assertFalse(win.right_view.is_loaded())
        self.assertEqual(win.lbl_pos.text(), "0 / 0")

    def test_batch_cut_gui_mode_b_and_legacy_signature(self):
        """测试模式 B 独立翻页下的批量剪切与旧版签名 (side, paths) 兼容调用"""
        win = MainWindow(config_path=self.cfg_path)
        win.edt_left.setText(self.dir_l)
        win.edt_right.setText(self.dir_r)
        win.edt_output.setText(self.dir_out)
        win._on_mode_clicked("B")

        self.assertEqual(len(win.left_files), 5)
        # 兼容旧代码调用签名：win._batch_cut("L", paths, policy="rename", prompt=False)
        left_to_cut = win.left_files[:2]
        win._batch_cut("L", left_to_cut, policy="rename", prompt=False)

        self.assertEqual(len(win.left_files), 3)
        self.assertEqual(len(win.right_files), 5)

    def test_image_view_unlocked_memory_loading_and_unload(self):
        """测试 ImageView 内存无锁读取：图片正在查看时，磁盘文件可直接删除/移动，且 unload 安全释放"""
        with tempfile.TemporaryDirectory() as tmp:
            img_file = Path(tmp) / "lock_test.png"
            fmt = getattr(QtGui.QImage.Format, "Format_RGB32", None) or getattr(QtGui.QImage, "Format_RGB32", None)
            img = QtGui.QImage(32, 32, fmt)
            img.fill(QtGui.QColor(128, 64, 32))
            img.save(str(img_file))

            view = ImageView()
            self.assertTrue(view.load_path(img_file))
            self.assertTrue(view.is_loaded())

            # 磁盘上直接移动文件（模拟剪切），验证 Python 进程内绝无 OS 文件句柄锁定
            dest = Path(tmp) / "moved_test.png"
            shutil.move(str(img_file), str(dest))
            self.assertTrue(dest.exists())
            self.assertFalse(img_file.exists())

            # 测试安全释放
            view.unload()
            self.assertFalse(view.is_loaded())
            self.assertIsNone(view.current_path())

    def test_same_file_safe_move_and_copy(self):
        """测试源与目标同目录自身的安全移动与拷贝（不抛 SameFileError）"""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "self.png"
            f.write_bytes(b"content")

            # 移动至自身所在目录且同名：安全跳过
            status, target = move_file_safe(f, tmp, policy="overwrite")
            self.assertEqual(status, "skipped")
            self.assertTrue(f.exists())

            # 拷贝至自身所在目录且同名（非重命名策略）：安全跳过
            status, target = copy_file_safe(f, tmp, policy="overwrite")
            self.assertEqual(status, "skipped")

    def test_dialog_code_compatibility_and_path_dialog(self):
        """测试 QtWidgets.QDialog.Accepted/Rejected 兼容性与路径设置对话框交互"""
        self.assertTrue(hasattr(QtWidgets.QDialog, "Accepted"))
        self.assertTrue(hasattr(QtWidgets.QDialog, "Rejected"))
        self.assertEqual(QtWidgets.QDialog.Accepted, DIALOG_ACCEPTED)
        self.assertEqual(QtWidgets.QDialog.Rejected, DIALOG_REJECTED)
        self.assertTrue(hasattr(QtWidgets.QMessageBox, "Yes"))
        self.assertTrue(hasattr(QtWidgets.QMessageBox, "No"))

        win = MainWindow(config_path=self.cfg_path)

        # 1. 真实 PathSettingsDialog 交互验证
        dlg = PathSettingsDialog(win, left_dir="L_old", right_dir="R_old", output_dir="O_old")
        dlg.edt_left.setText("L_new")
        dlg.edt_right.setText("R_new")
        dlg.edt_output.setText("O_new")
        dlg._on_ok()
        self.assertEqual(dlg.result(), DIALOG_ACCEPTED)
        self.assertEqual(dlg.result_paths["left_dir"], "L_new")

        # 2. 模拟 _open_path_dialog 成功确认应用
        with patch("view_image.main_window.PathSettingsDialog") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.result_paths = {
                "left_dir": self.dir_l,
                "right_dir": self.dir_r,
                "output_dir": self.dir_out,
            }
            with patch("view_image.main_window._dialog_exec", return_value=DIALOG_ACCEPTED):
                win._open_path_dialog()
                self.assertEqual(win.edt_left.text(), self.dir_l)
                self.assertEqual(win.edt_right.text(), self.dir_r)
                self.assertEqual(win.edt_output.text(), self.dir_out)

        # 3. 模拟 _open_path_dialog 点击取消（DIALOG_REJECTED）
        with patch("view_image.main_window.PathSettingsDialog") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.result_paths = {
                "left_dir": "/should/not/apply",
                "right_dir": "/should/not/apply",
                "output_dir": "/should/not/apply",
            }
            with patch("view_image.main_window._dialog_exec", return_value=DIALOG_REJECTED):
                win._open_path_dialog()
                self.assertNotEqual(win.edt_left.text(), "/should/not/apply")

    def test_layout_orientation_and_menu_bar(self):
        """测试左右/上下分屏布局切换、菜单栏与设置持久化"""
        from view_image.core.qt_compat import HORIZONTAL, VERTICAL
        win = MainWindow(config_path=self.cfg_path)

        # 1. 验证菜单栏结构
        mb = win.menuBar()
        self.assertIsNotNone(mb)
        menus = [m.title() for m in mb.findChildren(QtWidgets.QMenu)]
        self.assertTrue(any("文件" in title for title in menus))
        self.assertTrue(any("视图" in title for title in menus))
        self.assertTrue(any("操作" in title for title in menus))
        self.assertTrue(any("帮助" in title for title in menus))

        # 2. 初始默认水平左右排列
        self.assertEqual(win.layout_orientation, "horizontal")
        self.assertEqual(win.canvas_splitter.orientation(), HORIZONTAL)
        self.assertEqual(win.left_view._panel_title, "🟦 左")
        self.assertEqual(win.right_view._panel_title, "🟩 右")
        self.assertIn("左右", win.btn_layout.text())
        self.assertTrue(win.act_layout_h.isChecked())
        self.assertFalse(win.act_layout_v.isChecked())

        # 3. 切换为上下排列
        win.set_layout_orientation("vertical")
        self.assertEqual(win.layout_orientation, "vertical")
        self.assertEqual(win.canvas_splitter.orientation(), VERTICAL)
        self.assertEqual(win.left_view._panel_title, "🟦 上")
        self.assertEqual(win.right_view._panel_title, "🟩 下")
        self.assertIn("上下", win.btn_layout.text())
        self.assertTrue(win.act_layout_v.isChecked())
        self.assertFalse(win.act_layout_h.isChecked())

        # 4. 快捷切换回左右排列
        win._toggle_layout_orientation()
        self.assertEqual(win.layout_orientation, "horizontal")
        self.assertEqual(win.canvas_splitter.orientation(), HORIZONTAL)
        self.assertEqual(win.left_view._panel_title, "🟦 左")
        self.assertEqual(win.right_view._panel_title, "🟩 右")
        self.assertIn("左右", win.btn_layout.text())
        self.assertTrue(win.act_layout_h.isChecked())

        # 5. 持久化验证：重新加载配置确保保存了当前状态
        win.set_layout_orientation("vertical")
        mgr = ConfigManager(self.cfg_path)
        cfg = mgr.load()
        self.assertEqual(cfg["layout_orientation"], "vertical")

    def test_single_folder_copy_and_cut(self):
        """测试单独拷贝/剪切单个文件夹图像（单张与批量单文件夹范围过滤）"""
        win = MainWindow(config_path=self.cfg_path)
        win.edt_left.setText(self.dir_l)
        win.edt_right.setText(self.dir_r)
        win.edt_output.setText(self.dir_out)
        win.rule_text = "prefix:7"
        win.mode = "A"
        win._on_dirs_changed()

        self.assertEqual(len(win.pairs), 5)

        # 1. 单张操作测试：单独拷贝左图与单独拷贝右图
        win._copy_left()
        out_files = os.listdir(self.dir_out)
        self.assertIn("item_01_L.png", out_files)
        self.assertNotIn("item_01_R.png", out_files)

        win._copy_right()
        out_files = os.listdir(self.dir_out)
        self.assertIn("item_01_R.png", out_files)

        # 2. 批量抽屉范围过滤测试
        win.sidebar.select_all()
        # 默认全部：应包含全部 10 张图 (5 左 + 5 右)
        all_paths = win.sidebar.get_checked_paths(scope="ALL")
        self.assertEqual(len(all_paths), 10)

        # 切换范围至仅左侧目录
        left_paths = win.sidebar.get_checked_paths(scope="L")
        self.assertEqual(len(left_paths), 5)
        self.assertTrue(all("_L.png" in p.name for p in left_paths))

        # 切换范围至仅右侧目录
        right_paths = win.sidebar.get_checked_paths(scope="R")
        self.assertEqual(len(right_paths), 5)
        self.assertTrue(all("_R.png" in p.name for p in right_paths))

        # 3. 模拟在「仅左侧」作用域下执行批量拷贝
        win.sidebar.cmb_scope.setCurrentIndex(1)  # 仅左侧
        win._batch_copy(paths=left_paths, policy="rename", prompt=False)
        out_files_after = os.listdir(self.dir_out)
        # 验证左侧全部 5 张均已在输出目录中，右侧其余未被批量拷贝
        for i in range(1, 6):
            self.assertTrue(any(f"item_{i:02d}_L" in name for name in out_files_after))

        # 4. 验证画板右键上下文菜单
        self.assertTrue(hasattr(win.left_view, "contextMenuEvent"))
        self.assertTrue(hasattr(win.right_view, "contextMenuEvent"))

    def test_top_ribbon_simplified(self):
        """测试顶栏精简化：低频重复按键从顶栏移除，核心功能由工具按钮下拉菜单与系统菜单承载"""
        win = MainWindow(config_path=self.cfg_path)
        top_ribbon = win.findChild(QtWidgets.QFrame, "TopRibbon")
        self.assertIsNotNone(top_ribbon)

        # 验证已升级的拷贝与剪切下拉工具按钮
        self.assertIsInstance(win.btn_copy, QtWidgets.QToolButton)
        self.assertIsInstance(win.btn_cut, QtWidgets.QToolButton)
        self.assertIsNotNone(win.btn_copy.menu())
        self.assertIsNotNone(win.btn_cut.menu())

        # 顶栏按钮文本集合
        btn_texts = [b.text() for b in top_ribbon.findChildren(QtWidgets.QAbstractButton)]
        # 低频重复按键（1:1、＋、－、帮助）已被精简出顶栏
        self.assertNotIn("1:1", btn_texts)
        self.assertNotIn("＋", btn_texts)
        self.assertNotIn("－", btn_texts)
        self.assertNotIn("❓ 帮助", btn_texts)

        # 核心高频按键依然完整保留
        self.assertIn(win.btn_paths, top_ribbon.findChildren(QtWidgets.QAbstractButton))
        self.assertIn("⇄", btn_texts)
        self.assertIn("适应", btn_texts)
        self.assertTrue(any("拷贝" in t for t in btn_texts))
        self.assertTrue(any("剪切" in t for t in btn_texts))
        self.assertTrue(any("调色" in t for t in btn_texts))
        self.assertTrue(any("列表" in t for t in btn_texts))


if __name__ == "__main__":
    unittest.main()
