from config import config_data
from helpers import requests_get

from .base import BaseTask

ICON = "63850"
ERROR_ICON = ICON

API_URL = "https://apis.tianapi.com/oilprice/index"

APP_NAME = "gas_price"
DEFAULT_INTERVAL = 1200


class GasPriceTask(BaseTask):
    """Gas price"""

    def __init__(self):
        super().__init__(APP_NAME, default_interval=DEFAULT_INTERVAL)

    def fetch_data(self):
        """Fetch gas price data"""
        task_config = config_data.get("tasks", {}).get(APP_NAME, {})
        api_key = task_config.get("api_key")
        province = task_config.get("province", "北京")
        self.display_type = task_config.get("display_type", "92")

        if not api_key:
            raise Exception("API key not configured")

        params = {"key": api_key, "prov": province}
        response = requests_get(API_URL, params=params)
        response.raise_for_status()

        data = response.json()
        if data.get("code") != 200:
            raise Exception(f"API Error: {data.get('msg')} (code: {data.get('code')})")

        return data["result"]

    def create_mqtt_message(self, data):
        """Create MQTT message from gas price data"""
        if not data:
            raise Exception("Missing gas price data in API response")

        # Map gas prices
        price_map = {
            "0": data.get("p0"),
            "89": data.get("p89"),
            "92": data.get("p92"),
            "95": data.get("p95"),
            "98": data.get("p98"),
        }

        price = price_map.get(str(self.display_type))
        if not price:
            raise Exception(f"Invalid gas price display type: {self.display_type}")

        # Ensure price is a valid number
        try:
            float(price)
        except (ValueError, TypeError) as e:
            raise Exception(f"Invalid price data: {e}")

        return {
            "icon": ICON,
            "textCase": 2,
            "text": f"¥ {price}",
        }

    def get_error_message(self):
        return {
            "icon": ERROR_ICON,
            "textCase": 2,
            "text": "Error",
            "color": "#666666",
        }

if __name__ == "__main__":
    # uv run -m tasks.task_gas_price
    import json
    import sys

    from mqtt_sender import send_message

    task = GasPriceTask()

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