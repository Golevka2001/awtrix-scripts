import paho.mqtt.client as mqtt

from config import MQTT_HOST, MQTT_PASSWORD, MQTT_PORT, MQTT_TOPIC_PREFIX, MQTT_USERNAME


def send_message(app_name, payload):
    """Send MQTT message"""
    client = mqtt.Client()

    # Authenticate if username and password are set
    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    # Build topic
    prefix = MQTT_TOPIC_PREFIX.rstrip("/")
    app_name = app_name.strip("/")
    topic = f"{prefix}/{app_name}"

    # Connect and publish message
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.publish(topic, payload)
    client.disconnect()
