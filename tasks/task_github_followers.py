from urllib.parse import urljoin

from config import config_data
from helpers import fetch_image_and_convert_to_base64, format_number, requests_get

from .base import BaseTask

ICON = "71442"
ERROR_ICON = ICON

API_URL_WITH_TOKEN = "https://api.github.com/user"  # https://docs.github.com/en/rest/users/users?apiVersion=2022-11-28#get-the-authenticated-user
API_URL_WITH_USERNAME = "https://api.github.com/users"  # https://docs.github.com/en/rest/users/users?apiVersion=2022-11-28#get-a-user

APP_NAME = "github_followers"
DEFAULT_INTERVAL = 3600


class GithubFollowersTask(BaseTask):
    """GitHub followers count"""

    def __init__(self):
        super().__init__(APP_NAME, default_interval=DEFAULT_INTERVAL)

    def fetch_data(self):
        """Fetch GitHub followers data"""
        task_config = config_data.get("tasks", {}).get(APP_NAME, {})
        token = task_config.get("token")
        username = task_config.get("username")
        self.draw_avatar = task_config.get("draw_avatar", False)

        if not token and not username:
            raise Exception("GitHub token or username not configured")

        # Choose API endpoint and authentication based on config
        if token:
            url = API_URL_WITH_TOKEN
            headers = {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        else:
            url = urljoin(API_URL_WITH_USERNAME + "/", username)
            headers = {}

        response = requests_get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data

    def create_mqtt_message(self, data):
        """Create MQTT message from followers data"""
        if not data:
            raise Exception("Missing followers data in API response")

        # Ensure followers count is a valid number
        try:
            followers = int(data["followers"])
        except (KeyError, ValueError, TypeError) as e:
            raise Exception(f"Invalid followers data: {e}")

        followers_display = format_number(followers)

        # Use avatar as icon if enabled
        icon = ICON
        if self.draw_avatar:
            avatar_url = data.get("avatar_url", "")
            if avatar_url:
                icon = (
                    fetch_image_and_convert_to_base64(
                        avatar_url, (8, 8), image_format="JPG"
                    )
                    or ICON
                )

        return {
            "icon": icon,
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
    # uv run -m tasks.task_github_followers
    import json
    import sys

    from mqtt_sender import send_message

    task = GithubFollowersTask()

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
