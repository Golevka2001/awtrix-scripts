from datetime import datetime

from .base import BaseTask

ICON = "12111"
PROGRESS_COLOR = "#ffffff"
PROGRESS_BG_COLOR = "#666666"

ERROR_ICON = ICON

APP_NAME = "year_progress"
DEFAULT_INTERVAL = 3600


class YearProgressTask(BaseTask):
    """Year progress"""

    def __init__(self):
        super().__init__(APP_NAME, default_interval=DEFAULT_INTERVAL)

    def fetch_data(self):
        """Calculate year progress data"""
        # Get current time
        now = datetime.now()

        # Calculate start and end of year
        year_start = datetime(now.year, 1, 1)
        year_end = datetime(now.year, 12, 31, 23, 59, 59)

        # Calculate total and elapsed seconds
        total_seconds = (year_end - year_start).total_seconds()
        elapsed_seconds = (now - year_start).total_seconds()

        # Calculate progress percentage
        progress_percentage = (elapsed_seconds / total_seconds) * 100

        return {"progress_percentage": progress_percentage, "year": now.year}

    def create_mqtt_message(self, data):
        """Create MQTT message from year progress data"""
        if not data:
            raise Exception("Missing year progress data")

        # Ensure progress data is a valid number
        try:
            progress_percentage = float(data["progress_percentage"])
        except (KeyError, ValueError, TypeError) as e:
            raise Exception(f"Invalid progress data: {e}")

        # Clamp progress between 0 and 100
        progress_percentage = max(0, min(100, progress_percentage))

        # Format display text, keep 2 decimals
        if progress_percentage >= 100:
            progress_text = "100 %"
            progress_int = 100
        else:
            progress_text = f"{progress_percentage:.2f} %"
            progress_int = int(round(progress_percentage))

        return {
            "icon": ICON,
            "textCase": 2,
            "text": progress_text,
            "progress": progress_int,
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
    # uv run -m tasks.task_year_progress
    import json
    import sys

    from mqtt_sender import send_message

    task = YearProgressTask()

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
