import paho.mqtt.client as mqtt

from config import get_mqtt_config


def send_message(app_name, payload):
    """Send MQTT message"""
    mqtt_config = get_mqtt_config()
    client = mqtt.Client()

    # Authenticate if username and password are set
    if mqtt_config["username"] and mqtt_config["password"]:
        client.username_pw_set(mqtt_config["username"], mqtt_config["password"])

    # Build topic
    prefix = mqtt_config["topic_prefix"].rstrip("/")
    app_name = app_name.strip("/")
    topic = f"{prefix}/{app_name}"

    # Connect and publish message
    client.connect(mqtt_config["host"], mqtt_config["port"], 60)
    client.publish(topic, payload)
    client.disconnect()
