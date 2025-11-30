from mqtt_sender import send_message
from tasks import load_tasks


def cleanup():
    tasks = load_tasks()
    for task in tasks:
        send_message(task.name, "")
    print("Cleanup done.")


if __name__ == "__main__":
    cleanup()
