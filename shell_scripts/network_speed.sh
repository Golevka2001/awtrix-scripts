#!/bin/bash

# A script on my router to monitor network speed on specified interfaces
# crontab: * * * * * /path/to/this/script.sh

# Interface(s) to monitor
IF_LIST=(
	apcli0
	apclix0
)

# MQTT Configuration
MQTT_HOST="127.0.0.1"
MQTT_PORT=1883
MQTT_TOPIC="awtrix_8b9a64/custom/network_speed"
MQTT_USERNAME="<<<<< REPLACE_WITH_YOUR_MQTT_USERNAME >>>>>"
MQTT_PASSWORD="<<<<< REPLACE_WITH_YOUR_MQTT_PASSWORD >>>>>"

# Lock file to prevent overlapping runs
LOCK_FILE="/var/lock/network_speed.lock"

DOWNLOAD_ICON="60550"
UPLOAD_ICON="60553"

get_bytes() {
	if [ -e "/sys/class/net/$1/statistics/rx_bytes" ]; then
		cat "/sys/class/net/$1/statistics/rx_bytes"
		cat "/sys/class/net/$1/statistics/tx_bytes"
	else
		echo 0
		echo 0
	fi
}

measure_and_publish() {
	# Read twice with a 1 second interval
	R1_LIST=()
	T1_LIST=()
	for IF in "${IF_LIST[@]}"; do
		set -- $(get_bytes $IF)
		R1_LIST+=("$1")
		T1_LIST+=("$2")
	done

	sleep 1

	R2_LIST=()
	T2_LIST=()
	for IF in "${IF_LIST[@]}"; do
		set -- $(get_bytes $IF)
		R2_LIST+=("$1")
		T2_LIST+=("$2")
	done

	# Calculate differences and sum them up
	RX_DIFF=0
	TX_DIFF=0
	for i in "${!IF_LIST[@]}"; do
		RX_DIFF=$((RX_DIFF + (${R2_LIST[$i]} - ${R1_LIST[$i]})))
		TX_DIFF=$((TX_DIFF + (${T2_LIST[$i]} - ${T1_LIST[$i]})))
	done

	# Send MQTT messages (or just print if DRY_RUN=1)
	MSG_PAYLOAD="[
		{icon: ${DOWNLOAD_ICON}, text: \"$(format_bytes $RX_DIFF)\"},
		{icon: ${UPLOAD_ICON}, text: \"$(format_bytes $TX_DIFF)\"}
	]"

	if [ "${DRY_RUN:-0}" = "1" ]; then
		echo "DRY_RUN payload: $MSG_PAYLOAD"
	else
		mosquitto_pub -h "$MQTT_HOST" \
			-p "$MQTT_PORT" \
			-u "$MQTT_USERNAME" \
			-P "$MQTT_PASSWORD" \
			-t "$MQTT_TOPIC" \
			-m "$MSG_PAYLOAD"
	fi
}

format_bytes() {
	local bytes=$1
	local units=("B" "KB" "MB" "GB" "TB")
	local divisor=1024
	local unit_index=0
	local original_bytes=$bytes

	while { [ "$bytes" -ge $divisor ] || [ "$bytes" -ge 1000 ]; } && [ $unit_index -lt $((${#units[@]} - 1)) ]; do
		bytes=$((bytes / divisor))
		((unit_index++))
	done

	local unit=${units[$unit_index]}

	if [ $unit_index -eq 0 ]; then
		printf "%d %s" "$bytes" "$unit"
	elif [ "$bytes" -lt 10 ]; then
		printf "%.1f %s" "$(echo "$original_bytes $unit_index" | awk '{print $1 / (1024 ^ $2)}')" "$unit"
	else
		printf "%.0f %s" "$(echo "$original_bytes $unit_index" | awk '{print $1 / (1024 ^ $2)}')" "$unit"
	fi
}

# Acquire lock (non-blocking). If already running, exit immediately to avoid overlap
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
	# couldn't acquire lock; another instance is running
	exit 0
fi

for ((i = 1; i <= 59; i++)); do
	measure_and_publish
	if [ "$i" -lt 59 ]; then
		sleep 1
	fi
done

# Lock (fd 200) will be released when the script exits (and FD closes)
