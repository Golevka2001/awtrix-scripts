import json
import os
from pathlib import Path

from config import STORE_DIR

if not os.path.exists(STORE_DIR):
    os.makedirs(STORE_DIR)


def save(task_name, data):
    path = str(Path(STORE_DIR) / f"{task_name}.json")
    with open(path, "w") as f:
        json.dump(data, f)


def load(task_name):
    path = str(Path(STORE_DIR) / f"{task_name}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)
