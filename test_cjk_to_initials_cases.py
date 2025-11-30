import unittest

from helpers import cjk_to_initials


class TestCjkrToInitials(unittest.TestCase):
    def test_chinese(self):
        self.assertEqual(cjk_to_initials("中文测试"), "ZWCS")
        self.assertEqual(cjk_to_initials("汉字"), "HZ")

    def test_japanese(self):
        self.assertEqual(cjk_to_initials("かなカナ"), "KNKN")  # かな=kana, カナ=kana
        self.assertEqual(
            cjk_to_initials("こんにちは"), "KNNCH"
        )  # こんにちは=konnichiwa

    def test_korean(self):
        self.assertEqual(cjk_to_initials("한글"), "HG")  # 한글=hangul
        self.assertEqual(cjk_to_initials("가나다"), "GND")  # 가나다=ganada

    def test_mixed(self):
        self.assertEqual(cjk_to_initials("中A文B한글C日D"), "ZAWBHGCRD")
        self.assertEqual(cjk_to_initials("123中文abc"), "123ZWabc")

    def test_english_and_digits(self):
        self.assertEqual(cjk_to_initials("abcXYZ"), "abcXYZ")
        self.assertEqual(cjk_to_initials("123456"), "123456")

    def test_symbols_and_emoji(self):
        self.assertEqual(cjk_to_initials("!@#￥%……&*"), "!@#￥%……&*")
        self.assertEqual(cjk_to_initials("😀中日한A"), "😀ZRHA")

    def test_separator(self):
        self.assertEqual(cjk_to_initials("中文测试", "-"), "Z-W-C-S")
        self.assertEqual(cjk_to_initials("한글", ","), "H,G")

    def test_empty_and_none(self):
        self.assertEqual(cjk_to_initials(""), "")
        self.assertEqual(cjk_to_initials(None), "")


if __name__ == "__main__":
    unittest.main()
