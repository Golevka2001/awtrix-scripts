import colorsys
from collections import defaultdict
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from config import config_data
from helpers import color_to_packed_rgb, requests_get

from .base import BaseTask

CONTRIBUTION_LEVELS = [
    "#151b23",  # level 0 (no contributions)
    "#033b16",  # level 1
    "#1a6d2e",  # level 2
    "#2fa144",  # level 3
    "#56d365",  # level 4 (most contributions)
]
BG_COLOR = "#000000"
MONTH_MARKER_COLOR = "#666666"  # This will be ignored if `rainbow_months` is enabled

ERROR_ICON = "45205"

API_URL = "https://github.com/users/{username}/contributions"

APP_NAME = "github_contributions"
DEFAULT_INTERVAL = 3600  # 1 hour


def gen_rainbow_color_for_month(month):
    """Generate rainbow color based on month (1-12)"""
    hue = (month - 1) / 12.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.7, 0.7)
    return int(r * 255) << 16 | int(g * 255) << 8 | int(b * 255)


def generate_packed_pixels(
    contributions,
    cols=32,
    use_rainbow_months=True,
    split_by_month=False,
):
    bg_color = color_to_packed_rgb(BG_COLOR)
    month_marker_color = color_to_packed_rgb(MONTH_MARKER_COLOR)
    level_colors = [color_to_packed_rgb(c) for c in CONTRIBUTION_LEVELS]
    fallback_level_color = level_colors[4]

    matrix = [[bg_color] * cols for _ in range(8)]

    if not contributions:
        return [p for row in matrix for p in row]

    # Calculate anchor date, Saturday of this week (last_date) will be placed at the bottom right
    # Sun(6)->1, Mon(0)->2 ... Sat(5)->7
    last_date = contributions[-1]["date"]
    last_row = (last_date.weekday() + 1) % 7 + 1
    anchor_date = last_date + timedelta(days=7 - last_row)

    week_to_days = defaultdict(list)
    for item in contributions:
        date = item["date"]
        week_idx = (anchor_date - date).days // 7
        week_to_days[week_idx].append(item)

    def build_column(day_list):
        """Build a column of 8 pixels from a list of day contributions"""
        column = [bg_color] * 8
        marker_set = False
        for day in day_list:
            date = day["date"]
            row = (date.weekday() + 1) % 7 + 1
            lvl = day["level"]
            column[row] = (
                level_colors[lvl]
                if 0 <= lvl < len(level_colors)
                else fallback_level_color
            )
            if not marker_set and date.day == 1:
                column[0] = (
                    gen_rainbow_color_for_month(date.month)
                    if use_rainbow_months
                    else month_marker_color
                )
                marker_set = True
        return column

    columns = []
    max_week_idx = max(week_to_days.keys(), default=-1)
    for week_idx in range(max_week_idx + 1):
        days = week_to_days.get(week_idx)
        if not days:
            columns.append([bg_color] * 8)
            continue

        if split_by_month:
            # If days span multiple months, split them into separate columns
            month_groups = defaultdict(list)
            for day in days:
                date = day["date"]
                month_groups[(date.year, date.month)].append(day)

            if len(month_groups) > 1:
                grouped = sorted(
                    month_groups.values(),
                    key=lambda group: max(d["date"] for d in group),
                    reverse=True,
                )
                for group in grouped:
                    columns.append(build_column(group))
                continue

        columns.append(build_column(days))

    for idx, column in enumerate(columns[:cols]):
        target_col = cols - 1 - idx
        for row_idx, color in enumerate(column):
            matrix[row_idx][target_col] = color

    return [p for row in matrix for p in row]


class GitHubContributionsTask(BaseTask):
    """GitHub contributions heatmap display"""

    def __init__(self):
        super().__init__(APP_NAME, default_interval=DEFAULT_INTERVAL)

    def fetch_data(self):
        """Fetch GitHub contributions data"""
        task_config = config_data.get("tasks", {}).get(APP_NAME, {})
        token = task_config.get("token")
        username = task_config.get("username")

        if not username:
            raise Exception("GitHub username not configured")

        response = requests_get(API_URL.format(username=username))
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        contributions = []
        for day in soup.find_all("td", class_="ContributionCalendar-day"):
            date_str = day.get("data-date")
            level = day.get("data-level")
            if date_str:
                contributions.append(
                    {
                        "date": datetime.strptime(date_str, "%Y-%m-%d"),
                        "level": int(level) if level else 0,
                    }
                )
        contributions.sort(key=lambda x: x["date"])
        return contributions

    def create_mqtt_message(self, contributions):
        """Create MQTT message from GitHub contributions data"""
        if not contributions:
            raise Exception("No contributions data received")

        # Get configuration for rainbow months
        task_config = config_data.get("tasks", {}).get(APP_NAME, {})
        use_rainbow_months = task_config.get("rainbow_months", True)
        split_by_month = task_config.get("split_by_month", False)

        # Generate matrix from contributions
        packed_rgbs = generate_packed_pixels(
            contributions,
            cols=32,
            use_rainbow_months=use_rainbow_months,
            split_by_month=split_by_month,
        )

        return {
            "draw": [
                {"db": [0, 0, 32, 8, packed_rgbs]},
            ],
        }

    def get_error_message(self):
        return {
            "icon": ERROR_ICON,
            "textCase": 2,
            "text": "Error",
            "color": "#666666",
        }


if __name__ == "__main__":
    # uv run -m tasks.task_github_contributions
    import json
    import sys

    from mqtt_sender import send_message

    task = GitHubContributionsTask()

    if len(sys.argv) > 1 and sys.argv[1] == "del":
        print("Deleting app...")
        send_message(task.name, "{}")
        exit()

    try:
        msg = task.run()
    except Exception as e:
        print(f"Error: {e}")
        msg = task.get_error_message()

    msg = json.dumps(msg)
    print(msg)

    send_message(task.name, msg)
