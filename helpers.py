import base64
import json
import os
from pathlib import Path

import cv2
import numpy as np
import pykakasi
import requests
from korean_romanizer.romanizer import Romanizer as KoreanRomanizer
from pypinyin import Style, lazy_pinyin

from config import STORE_DIR

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
REQUEST_TIMEOUT = 10
IMAGE_CACHE_PATH = str(Path(STORE_DIR) / "image_cache.json")

KKS = pykakasi.kakasi()


def format_number(num):
    """Format number with unit suffix (k, M, etc.)"""
    units = ["", "k", "M", "B", "T"]
    divisor = 1000
    unit_index = 0
    original_num = num

    # 找到合适的单位
    while num >= divisor and unit_index < len(units) - 1:
        num = num // divisor
        unit_index += 1

    unit = units[unit_index]

    if unit_index > 0:  # 有单位的情况
        # 计算实际值
        actual_value = original_num / (divisor**unit_index)

        if actual_value < 10:
            # 1.00 k
            return f"{actual_value:.2f}{unit}"
        elif actual_value < 100:
            # 10.0 k
            return f"{actual_value:.1f}{unit}"
        else:
            # 100 k
            return f"{int(actual_value)}{unit}"
    else:
        # 无单位，直接返回数字
        return str(int(original_num))


def requests_get(url, **kwargs):
    headers = kwargs.pop("headers", {}) or {}
    headers.setdefault("User-Agent", USER_AGENT)
    return requests.get(url, headers=headers, **kwargs, timeout=REQUEST_TIMEOUT)


def requests_post(url, **kwargs):
    headers = kwargs.pop("headers", {}) or {}
    headers.setdefault("User-Agent", USER_AGENT)
    headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    return requests.post(url, headers=headers, **kwargs, timeout=REQUEST_TIMEOUT)


def cjk_to_initials(text: str, separator: str = "") -> str:
    """
    Convert each CJK character to its pinyin/romanized initial. Others unchanged.
    Args:
        text (str): Input string, may contain CJK characters
        separator (str): Separator between characters
    Returns:
        str: Converted string
    """

    def char_to_initial(char: str) -> str:
        # Convert one character to initial (CJK supported)
        if not char:
            return ""
        codepoint = ord(char)
        # Chinese
        if 0x4E00 <= codepoint <= 0x9FFF:
            try:
                pinyin = lazy_pinyin(char, style=Style.FIRST_LETTER)
                return pinyin[0].upper() if pinyin else char
            except Exception:
                return char
        # Japanese
        if 0x3040 <= codepoint <= 0x30FF:
            try:
                result = KKS.convert(char)
                romaji = "".join(item.get("hepburn", "") for item in result)
                return romaji[0].upper() if romaji else char
            except Exception:
                return char
        # Korean
        if 0xAC00 <= codepoint <= 0xD7A3:
            try:
                romaji = KoreanRomanizer(char).romanize()
                return romaji[0].upper() if romaji else char
            except Exception:
                return char
        return char

    if not isinstance(text, str) or not text:
        return ""
    return separator.join(char_to_initial(c) for c in text)


def fetch_image_and_convert_to_packed_rgb(url, target_size):
    """
    Fetch image from URL, resize, convert to packed RGB format
    Args:
        url (str): Image URL
        target_size (tuple): (width, height)
    Returns:
        list: List of packed RGB integers
    """
    try:
        response = requests_get(url)
        response.raise_for_status()

        image_array = np.frombuffer(response.content, np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        resized_image = cv2.resize(image_rgb, target_size)
        height, width = resized_image.shape[:2]
        packed_pixels = []

        for y in range(height):
            for x in range(width):
                r, g, b = map(int, resized_image[y, x])
                packed = (r << 16) | (g << 8) | b
                packed_pixels.append(packed)

        return packed_pixels
    except Exception as e:
        print(f"Error fetching or processing image from {url}: {e}")
        return None


def fetch_image_and_convert_to_base64(url, target_size, image_format="JPG"):
    """
    Fetch image from URL, resize, convert to base64 string. Uses persistent cache.
    Args:
        url (str): Image URL
        target_size (tuple): (width, height)
        image_format (str): Output format, default JPG
    Returns:
        str: Base64-encoded image (no prefix)
    """
    key = f"{url}|{target_size[0]}x{target_size[1]}|{image_format.upper()}"

    global _image_cache_dict
    if "_image_cache_dict" not in globals():
        # Load persistent cache from disk
        if os.path.exists(IMAGE_CACHE_PATH):
            try:
                with open(IMAGE_CACHE_PATH, "r", encoding="utf-8") as f:
                    _image_cache_dict = json.load(f)
            except Exception:
                _image_cache_dict = {}
        else:
            _image_cache_dict = {}

    cache = _image_cache_dict

    if key in cache:
        return cache[key]

    # Cache miss, process the image
    try:
        response = requests_get(url)
        response.raise_for_status()

        image_array = np.frombuffer(response.content, np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Failed to decode image")
        resized_image = cv2.resize(image, target_size)

        # Encode to specified format
        success, buffer = cv2.imencode(f".{image_format.lower()}", resized_image)
        if not success:
            raise ValueError("Failed to encode image")
        base64_str = base64.b64encode(buffer).decode("utf-8")

        # Write to cache (update both memory and disk)
        cache[key] = base64_str
        try:
            with open(IMAGE_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
        except Exception as e:
            print(f"Error writing image cache: {e}")

        return base64_str
    except Exception as e:
        print(f"Error fetching or processing image from {url}: {e}")
        return None
