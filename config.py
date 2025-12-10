from pathlib import Path

import yaml

CONFIG_FILE = "config.yaml"
_config_cache = None


def load_config(config_path=CONFIG_FILE):
    """Load configuration from YAML file"""
    config = {}

    if Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    return config


def get_config():
    """Get current configuration (with hot reload support)"""
    global _config_cache
    _config_cache = load_config(CONFIG_FILE)
    return _config_cache


def get_mqtt_config():
    """Get MQTT configuration"""
    config = get_config()
    return {
        "host": config.get("mqtt", {}).get("host", "localhost"),
        "port": config.get("mqtt", {}).get("port", 1883),
        "topic_prefix": config.get("mqtt", {}).get("topic_prefix", "awtrix/custom/"),
        "username": config.get("mqtt", {}).get("username", ""),
        "password": config.get("mqtt", {}).get("password", ""),
    }


def get_app_config():
    """Get app configuration"""
    config = get_config()
    app_config = config.get("app", {})
    return {
        "allowed_hours": app_config.get("allowed_hours", [[0, 1], [8, 24]]),
        "main_loop_interval": app_config.get("main_loop_interval", 20),
        "task_timeout": app_config.get("task_timeout", 5),
        "send_interval": app_config.get("send_interval", 0.5),
        "behavior_on_failure": app_config.get("behavior_on_failure", 0),
        "store_dir": app_config.get("store_dir", "data"),
    }


# Legacy global variables for backward compatibility (loaded on module init)
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
