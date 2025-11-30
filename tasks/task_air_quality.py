from config import config_data
from helpers import requests_get

from .base import BaseTask

ICON_COLOR_MAP = [
    (50, "47651", "#71d608"),  # 0-50：优，绿色
    (100, "47652", "#faff1b"),  # 51-100：良，黄色
    (150, "47653", "#f98718"),  # 101-150：轻度污染，橙色
    (200, "47654", "#f70017"),  # 151-200：中度污染，红色
    (300, "47655", "#8f00ff"),  # 201-300：重度污染，紫色
    (float("inf"), "47656", "#870089"),  # 301以上：严重污染，褐红色
]

ERROR_ICON = "47657"

API_URL = "https://apis.tianapi.com/aqi/index"

APP_NAME = "air_quality"
DEFAULT_INTERVAL = 1200


class AirQualityTask(BaseTask):
    """Air quality"""

    def __init__(self):
        super().__init__(APP_NAME, default_interval=DEFAULT_INTERVAL)

    def fetch_data(self):
        """Fetch air quality data"""
        task_config = config_data.get("tasks", {}).get(APP_NAME, {})
        api_key = task_config.get("api_key")
        area = task_config.get("area", "北京")

        if not api_key:
            raise Exception("API key not configured")

        params = {"key": api_key, "area": area}
        response = requests_get(API_URL, params=params)
        response.raise_for_status()

        data = response.json()
        if data.get("code") != 200:
            raise Exception(f"API Error: {data.get('msg')} (code: {data.get('code')})")

        return data["result"]

    def create_mqtt_message(self, data):
        """Create MQTT message from air quality data"""
        if not data:
            raise Exception("Missing AQI data in API response")

        # Ensure AQI value is a valid number
        try:
            aqi = int(data["aqi"])
        except (KeyError, ValueError, TypeError) as e:
            raise Exception(f"Invalid AQI data: {e}")

        # Select icon and color based on AQI level
        icon = color = None
        for threshold, level_icon, level_color in ICON_COLOR_MAP:
            if aqi <= threshold:
                icon, color = level_icon, level_color
                break

        return {
            "icon": icon,
            "textCase": 2,
            "text": str(aqi),
            "color": color,
        }

    def get_error_message(self):
        return {
            "icon": ERROR_ICON,
            "textCase": 2,
            "text": "Error",
            "color": "#666666",
        }


if __name__ == "__main__":
    # uv run -m tasks.task_air_quality
    import json
    import sys

    from mqtt_sender import send_message

    task = AirQualityTask()

    if len(sys.argv) > 1 and sys.argv[1] == "del":
        print("Deleting app...")
        send_message(task.name, "{}")
        exit()

    try:
        data = task.fetch_data()
        msg = task.create_mqtt_message(data)
    except Exception as e:
        print("Error:", e)
        msg = task.get_error_message()

    msg = json.dumps(msg)
    print(msg)

    send_message(task.name, msg)
