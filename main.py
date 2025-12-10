import datetime
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from cleanup import cleanup
from config import get_app_config, get_config
from mqtt_sender import send_message
from storage import load
from tasks import load_tasks


def get_store_dir():
    """Get store directory from current config"""
    app_config = get_app_config()
    store_dir = app_config["store_dir"]
    return str((Path(__file__).parent / store_dir).resolve())


LAST_RUN_PATH_BASE = "last_run.json"
ENABLED_TASKS_FILE = "enabled_tasks.json"


def get_last_run_path():
    """Get last_run.json path from current config"""
    return str(Path(get_store_dir()) / LAST_RUN_PATH_BASE)


def get_enabled_tasks_path():
    """Get enabled_tasks.json path from current config"""
    return str(Path(get_store_dir()) / ENABLED_TASKS_FILE)


def is_allowed_time():
    app_config = get_app_config()
    allowed_hours = app_config["allowed_hours"]
    now = datetime.datetime.now()
    hour = now.hour
    for start, end in allowed_hours:
        if start <= hour < end:
            return True
    return False


def load_last_run():
    last_run_path = get_last_run_path()
    if os.path.exists(last_run_path):
        with open(last_run_path, "r") as f:
            return json.load(f)
    return {}


def save_last_run(last_run):
    last_run_path = get_last_run_path()
    with open(last_run_path, "w") as f:
        json.dump(last_run, f)


def load_enabled_tasks():
    """Load previously enabled tasks state"""
    enabled_tasks_path = get_enabled_tasks_path()
    if os.path.exists(enabled_tasks_path):
        with open(enabled_tasks_path, "r") as f:
            return json.load(f)
    return {}


def save_enabled_tasks(enabled_tasks):
    """Save enabled tasks state"""
    enabled_tasks_path = get_enabled_tasks_path()
    with open(enabled_tasks_path, "w") as f:
        json.dump(enabled_tasks, f)


def sort_results_by_priority(tasks, results):
    """Sort results by task priority"""
    # Map task name to priority
    task_priority_map = {task.name: task.priority for task in tasks}

    # Sort by priority (lower value = higher priority)
    sorted_items = sorted(
        results.items(), key=lambda x: task_priority_map.get(x[0], 999)
    )

    # Return ordered dict
    from collections import OrderedDict

    return OrderedDict(sorted_items)


def run_single_task(task):
    """Run a single task with timeout"""
    app_config = get_app_config()
    task_timeout = app_config["task_timeout"]
    finished = [False]
    output = [None]

    def worker():
        try:
            output[0] = task.run()
        except Exception as e:
            print(task.name, "error:", e)
        finally:
            finished[0] = True

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(task_timeout)

    if finished[0]:
        return task.name, output[0]
    else:
        print(task.name, "timeout using old data")
        return task.name, load(task.name)


def main_loop():
    tasks = load_tasks()
    # Load last_run time from persistent storage
    last_run = load_last_run()
    # Load previously enabled tasks state
    enabled_tasks = load_enabled_tasks()
    config_check_interval = 10  # Check config every 10 seconds
    last_config_check = time.time()

    try:
        while True:
            # Reload config periodically
            current_time = time.time()
            if current_time - last_config_check >= config_check_interval:
                config = get_app_config()
                last_config_check = current_time

            if not is_allowed_time():
                print("Sleeping...")
                cleanup()
                time.sleep(1800)  # Sleep for 30 minutes
                continue

            now = time.time()
            results = {}
            tasks_to_run = []
            disabled_tasks = []
            current_enabled_state = {}

            for task in tasks:
                # Get current enabled state from config
                config = get_config()
                task_config = config.get("tasks", {}).get(task.name, {})
                enabled = task_config.get("enabled", True)
                current_enabled_state[task.name] = enabled

                # Check if task was previously enabled but now disabled
                if not enabled:
                    if enabled_tasks.get(task.name, True):
                        # Task was enabled before, now disabled -> send empty message
                        results[task.name] = {}
                        print(f"Task {task.name} disabled, sending empty message")
                    disabled_tasks.append(task)
                    continue

                last_time = last_run.get(task.name, 0)
                if now - last_time >= task.interval:
                    tasks_to_run.append(task)
                else:
                    # Use old data
                    prev = load(task.name)
                    results[task.name] = prev

            # Run all tasks that need to be executed in parallel
            if tasks_to_run:
                with ThreadPoolExecutor(max_workers=len(tasks_to_run)) as executor:
                    future_to_task = {
                        executor.submit(run_single_task, task): task
                        for task in tasks_to_run
                    }
                    for future in as_completed(future_to_task):
                        task_name, result = future.result()
                        results[task_name] = result
                        # Update last_run time
                        last_run[task_name] = now
                save_last_run(last_run)

            # Update enabled tasks state
            enabled_tasks = current_enabled_state
            save_enabled_tasks(enabled_tasks)

            # Sort results by priority and send one by one
            sorted_results = sort_results_by_priority(tasks, results)

            app_config = get_app_config()
            send_interval = app_config["send_interval"]

            for task_name, result in sorted_results.items():
                payload = json.dumps(result, ensure_ascii=False)
                print(f"sending {task_name}:", payload)
                send_message(task_name, payload)
                time.sleep(send_interval)

            app_config = get_app_config()
            main_loop_interval = app_config["main_loop_interval"]
            time.sleep(main_loop_interval)
    except KeyboardInterrupt:
        print("Program interrupted. Cleaning up...")
        cleanup()


if __name__ == "__main__":
    main_loop()
