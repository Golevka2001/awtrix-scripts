import abc

from config import BEHAVIOR_ON_FAILURE, config_data
from storage import load, save


class BaseTask(abc.ABC):
    """Base class for all tasks. All specific tasks should inherit this."""

    def __init__(
        self, name: str, default_interval: int = 60, default_priority: int = 100
    ):
        self.name = name

        # Read interval and priority from config
        task_config = config_data.get("tasks", {}).get(name, {})
        self.enabled = task_config.get("enabled", True)
        self.interval = task_config.get("interval", default_interval)
        self.priority = task_config.get("priority", default_priority)

    @abc.abstractmethod
    def fetch_data(self):
        """Fetch data. Must be implemented by subclasses."""
        pass

    def run(self):
        """Run task: fetch data -> process -> store -> return MQTT message"""
        if not self.enabled:
            return {}

        try:
            # Fetch data
            data = self.fetch_data()

            # Process data and generate MQTT message
            mqtt_message = self.create_mqtt_message(data)

            # Store data (for timeout fallback)
            save(self.name, mqtt_message)

            # Return MQTT message
            return mqtt_message

        except Exception as e:
            print(f"Task {self.name} failed: {e}")
            match BEHAVIOR_ON_FAILURE:
                case 0:
                    # Remove app, return empty message
                    return {}
                case 1:
                    # Use last result
                    return load(self.name)
                case 2:
                    # Show error message
                    return self.get_error_message()
                case _:
                    raise e

    def get_error_message(self):
        """Get error message. Subclasses can override to customize error display."""
        return {
            "textCase": 2,
            "text": "Error",
            "color": "#666666",
        }

    @abc.abstractmethod
    def create_mqtt_message(self, data):
        """Create MQTT message from data. Must be implemented by subclasses."""
        pass
