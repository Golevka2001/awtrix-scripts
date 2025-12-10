import json
import os
from pathlib import Path

from config import get_app_config


def get_store_dir():
    """Get store directory from current config"""
    app_config = get_app_config()
    store_dir = app_config["store_dir"]
    return str((Path(__file__).parent / store_dir).resolve())


def _ensure_store_dir():
    store_dir = get_store_dir()
    if not os.path.exists(store_dir):
        os.makedirs(store_dir)


def save(task_name, data):
    _ensure_store_dir()
    store_dir = get_store_dir()
    path = str(Path(store_dir) / f"{task_name}.json")
    with open(path, "w") as f:
        json.dump(data, f)


def load(task_name):
    store_dir = get_store_dir()
    path = str(Path(store_dir) / f"{task_name}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)
