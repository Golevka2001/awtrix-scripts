from config import config_data
from helpers import format_number, requests_get

from .base import BaseTask

ICON = "71441"
ERROR_ICON = ICON

API_URL = "https://api.bilibili.com/x/relation/stat"

APP_NAME = "bilibili_followers"
DEFAULT_INTERVAL = 3600


class BilibiliFollowersTask(BaseTask):
    """Bilibili followers count"""

    def __init__(self):
        super().__init__(APP_NAME, default_interval=DEFAULT_INTERVAL)

    def fetch_data(self):
        """Fetch Bilibili followers data"""
        task_config = config_data.get("tasks", {}).get(APP_NAME, {})
        uid = task_config.get("uid")

        if not uid:
            raise Exception("Bilibili UID not configured")

        params = {"vmid": uid, "jsonp": "jsonp"}
        response = requests_get(API_URL, params=params)
        response.raise_for_status()

        data = response.json()
        if data.get("code") != 0:
            raise Exception(f"Bilibili API Error: {data.get('message')}")

        return data["data"]

    def create_mqtt_message(self, data):
        """Create MQTT message from followers data"""
        if not data:
            raise Exception("Missing followers data in API response")

        # Ensure followers count is a valid number
        try:
            followers = int(data["follower"])
        except (KeyError, ValueError, TypeError) as e:
            raise Exception(f"Invalid followers data: {e}")

        followers_display = format_number(followers)

        return {
            "icon": ICON,
            "textCase": 2,
            "text": followers_display,
        }

    def get_error_message(self):
        return {
            "icon": ERROR_ICON,
            "textCase": 2,
            "text": "Error",
            "color": "#666666",
        }

if __name__ == "__main__":
    # uv run -m tasks.task_bilibili_followers
    import json
    import sys

    from mqtt_sender import send_message

    task = BilibiliFollowersTask()

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