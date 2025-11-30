from pathlib import Path

import yaml


def load_config(config_path="config.yaml"):
    config = {}

    if Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    return config


config_data = load_config()

# MQTT Settings
MQTT_HOST = config_data.get("mqtt", {}).get("host", "localhost")
MQTT_PORT = config_data.get("mqtt", {}).get("port", 1883)
MQTT_TOPIC_PREFIX = config_data.get("mqtt", {}).get("topic_prefix", "awtrix/custom/")
MQTT_USERNAME = config_data.get("mqtt", {}).get("username", "")
MQTT_PASSWORD = config_data.get("mqtt", {}).get("password", "")

# App Settings
ALLOWED_HOURS = config_data.get("app", {}).get("allowed_hours", [[0, 1], [8, 24]])
MAIN_LOOP_INTERVAL = config_data.get("app", {}).get("main_loop_interval", 20)
TASK_TIMEOUT = config_data.get("app", {}).get("task_timeout", 5)
SEND_INTERVAL = config_data.get("app", {}).get("send_interval", 0.5)
BEHAVIOR_ON_FAILURE = config_data.get("app", {}).get("behavior_on_failure", 0)
STORE_DIR = str(
    (
        Path(__file__).parent / config_data.get("app", {}).get("store_dir", "data")
    ).resolve()
)
