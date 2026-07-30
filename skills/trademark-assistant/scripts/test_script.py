#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""商品清单输入校验的最小回归测试。"""

import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("script.py")
SPEC = importlib.util.spec_from_file_location("trademark_goods_script", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NormalizeItemTests(unittest.TestCase):
    def test_valid_item_is_normalized(self):
        item, errors = MODULE.normalize_item(
            1,
            {"类别": "09", "类似群": "0901", "商品名称": " 计算机软件（已录制） "},
        )
        self.assertEqual(errors, [])
        self.assertEqual(
            item,
            {"类别": 9, "类似群": "0901", "商品名称": "计算机软件（已录制）"},
        )

    def test_fractional_category_is_rejected(self):
        item, errors = MODULE.normalize_item(
            1, {"类别": 9.5, "类似群": "0901", "商品名称": "计算机软件"}
        )
        self.assertIsNone(item)
        self.assertTrue(any("不是 1-45 的整数" in error for error in errors))

    def test_boolean_category_is_rejected(self):
        item, errors = MODULE.normalize_item(
            1, {"类别": True, "类似群": "0101", "商品名称": "化学制剂"}
        )
        self.assertIsNone(item)
        self.assertTrue(any("不是 1-45 的整数" in error for error in errors))

    def test_group_must_match_category(self):
        item, errors = MODULE.normalize_item(
            1, {"类别": 9, "类似群": "1001", "商品名称": "计算机软件"}
        )
        self.assertIsNone(item)
        self.assertTrue(any("与类别 9 不一致" in error for error in errors))

    def test_group_must_preserve_leading_zero(self):
        item, errors = MODULE.normalize_item(
            1, {"类别": 9, "类似群": 901, "商品名称": "计算机软件"}
        )
        self.assertIsNone(item)
        self.assertTrue(any("必须是 4 位数字字符串" in error for error in errors))

    def test_product_name_must_be_string(self):
        item, errors = MODULE.normalize_item(
            1, {"类别": 9, "类似群": "0901", "商品名称": {"name": "计算机软件"}}
        )
        self.assertIsNone(item)
        self.assertTrue(any("商品名称必须是字符串" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
