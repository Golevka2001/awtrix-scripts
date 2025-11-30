import datetime
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from cleanup import cleanup
from config import (
    ALLOWED_HOURS,
    MAIN_LOOP_INTERVAL,
    SEND_INTERVAL,
    STORE_DIR,
    TASK_TIMEOUT,
)
from mqtt_sender import send_message
from storage import load
from tasks import load_tasks

LAST_RUN_PATH = str(Path(STORE_DIR) / "last_run.json")


def is_allowed_time():
    now = datetime.datetime.now()
    hour = now.hour
    for start, end in ALLOWED_HOURS:
        if start <= hour < end:
            return True
    return False


def load_last_run():
    if os.path.exists(LAST_RUN_PATH):
        with open(LAST_RUN_PATH, "r") as f:
            return json.load(f)
    return {}


def save_last_run(last_run):
    with open(LAST_RUN_PATH, "w") as f:
        json.dump(last_run, f)


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
    thread.join(TASK_TIMEOUT)

    if finished[0]:
        return task.name, output[0]
    else:
        print(task.name, "timeout using old data")
        return task.name, load(task.name)


def main_loop():
    tasks = load_tasks()
    # Load last_run time from persistent storage
    last_run = load_last_run()

    try:
        while True:
            if not is_allowed_time():
                print("Sleeping...")
                cleanup()
                time.sleep(1800)  # Sleep for 30 minutes
                continue

            now = time.time()
            results = {}
            tasks_to_run = []
            disabled_tasks = []

            for task in tasks:
                # Check if task is enabled
                enabled = getattr(task, "enabled", True)
                if not enabled:
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

            # Send empty message for disabled tasks
            for task in disabled_tasks:
                results[task.name] = {}

            # Sort results by priority and send one by one
            sorted_results = sort_results_by_priority(tasks, results)

            for task_name, result in sorted_results.items():
                payload = json.dumps(result, ensure_ascii=False)
                print(f"sending {task_name}:", payload)
                send_message(task_name, payload)
                time.sleep(SEND_INTERVAL)

            time.sleep(MAIN_LOOP_INTERVAL)
    except KeyboardInterrupt:
        print("Program interrupted. Cleaning up...")
        cleanup()


if __name__ == "__main__":
    main_loop()
