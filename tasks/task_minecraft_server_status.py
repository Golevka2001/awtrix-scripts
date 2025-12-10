from mcstatus import BedrockServer, JavaServer

from config import config_data

from .base import BaseTask

OFFLINE_ICON = "23611"
OFFLINE_TEXT = "Off"
OFFLINE_TEXT_COLOR = "#666666"

ONLINE_ICON = "21699"
PROGRESS_COLOR = "#ffffff"
PROGRESS_BG_COLOR = "#666666"

ERROR_ICON = OFFLINE_ICON

APP_NAME = "minecraft_server_status"
DEFAULT_INTERVAL = 300


class MinecraftServerStatusTask(BaseTask):
    """Minecraft server status"""

    def __init__(self):
        super().__init__(APP_NAME, default_interval=DEFAULT_INTERVAL)

    def fetch_data(self):
        """Fetch Minecraft server data"""
        task_config = config_data.get("tasks", {}).get(APP_NAME, {})
        server_addr = task_config.get("server_addr")
        java_edition = task_config.get("java_edition", True)

        if not server_addr:
            raise Exception("Minecraft server address not configured")
        try:
            if java_edition:
                server = JavaServer.lookup(server_addr)
            else:
                server = BedrockServer.lookup(server_addr)
            status = server.status()
            online = status.players.online or 0
            maximum = status.players.max or 0

            return {"online": True, "players": {"online": online, "max": maximum}}
        except Exception:
            return {"online": False}

    def create_mqtt_message(self, data):
        """Create MQTT message from server status data"""
        # Server offline
        if not data.get("online"):
            return {
                "icon": OFFLINE_ICON,
                "textCase": 2,
                "text": OFFLINE_TEXT,
                "color": OFFLINE_TEXT_COLOR,
            }

        # Server online, get player info
        players = data.get("players", {})
        if not players:
            raise Exception("Missing players data in server response")

        # Ensure player counts are valid numbers
        try:
            online_count = int(players["online"])
            max_count = int(players["max"])
        except (KeyError, ValueError, TypeError) as e:
            raise Exception(f"Invalid player count data: {e}")

        # Calculate online player percentage
        progress = int(round(online_count * 100) / max_count) if max_count > 0 else 0

        return {
            "icon": ONLINE_ICON,
            "textCase": 2,
            "text": str(online_count),
            "progress": progress,
            "progressC": PROGRESS_COLOR,
            "progressBC": PROGRESS_BG_COLOR,
        }

    def get_error_message(self):
        return {
            "icon": ERROR_ICON,
            "textCase": 2,
            "text": "Error",
            "color": "#666666",
        }


if __name__ == "__main__":
    # uv run -m tasks.task_minecraft_server_status
    import json
    import sys

    from mqtt_sender import send_message

    task = MinecraftServerStatusTask()

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
