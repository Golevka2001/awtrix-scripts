#!/bin/bash
#
# Publish per-second network throughput to an AWTRIX NG panel over MQTT.
# Runs as a resident daemon (while true loop) that publishes once per second.
# The cron entry only acts as a watchdog: it re-launches this script if it has
# exited. The per-second rhythm is entirely internal, so it can never drift out
# of phase with a cron interval.
#
# Usage:
#   ./awtrix-network-speed.sh      # resident daemon loop
#
# crontab watchdog (same pattern as seu-wlan-login):
#   * * * * * [ -f /tmp/.awtrix-network-speed.lock ] && kill -0 $(cat /tmp/.awtrix-network-speed.lock) 2>/dev/null || nohup /root/awtrix-network-speed.sh >>/tmp/awtrix-network-speed.log 2>&1 &

# ---------------------------------------------------------------- configuration

# Interface(s) to monitor. Their counters are summed.
IF_LIST=(
    apcli0
    apclix0
)

# MQTT_PREFIX must match the device's mqttPrefix.
MQTT_HOST="localhost"
MQTT_PORT=1883
MQTT_PREFIX="awtrix"
MQTT_USERNAME=""
MQTT_PASSWORD=""

# An array payload creates APP_NAME0 (download) and APP_NAME1 (upload).
APP_NAME="network-speed"
MQTT_TOPIC="${MQTT_PREFIX}/cmd/apps/pushed/${APP_NAME}"

# Mark the app if updates stop. Keep this above the longest expected update gap.
LIFETIME_MS=15000
LIFETIME_EXPIRY="mark"

DOWNLOAD_ICON="60550"
UPLOAD_ICON="60553"

# Sample interval (seconds) between publishes.
INTERVAL_SECONDS=1

# Lock file used by the cron watchdog.
LOCK_FILE="/tmp/.awtrix-network-speed.lock"

# Override for tests with a fake counter tree.
SYS_NET="${SYS_NET:-/sys/class/net}"

# -------------------------------------------------------------------- functions

# Read one interface's byte counters into RX_NOW / TX_NOW. Missing interfaces read
# as zero.
read_counters() {
    local base="$SYS_NET/$1/statistics"

    RX_NOW=0
    TX_NOW=0

    [ -r "$base/rx_bytes" ] || return 0
    read -r RX_NOW <"$base/rx_bytes"
    read -r TX_NOW <"$base/tx_bytes"
}

# Format a byte count for the panel into FMT_OUT. Keep this in sync with the test.
format_bytes() {
    local bytes=$1
    local units=("B" "KB" "MB" "GB" "TB")
    local scaled=$bytes
    local divisor=1
    local unit_index=0

    # Promote 1000..1023 to the next unit so the value fits the panel.
    while { [ "$scaled" -ge 1024 ] || [ "$scaled" -ge 1000 ]; } &&
            [ "$unit_index" -lt $((${#units[@]} - 1)) ]; do
        scaled=$((scaled / 1024))
        divisor=$((divisor * 1024))
        unit_index=$((unit_index + 1))
    done

    if [ "$unit_index" -eq 0 ]; then
        printf -v FMT_OUT '%d %s' "$bytes" "${units[0]}"
        return 0
    fi

    # Use one decimal below 10 units; whole numbers are narrower on the panel.
    local tenths=$(((bytes * 10 + divisor / 2) / divisor))
    if [ "$tenths" -lt 100 ]; then
        printf -v FMT_OUT '%d.%d %s' "$((tenths / 10))" "$((tenths % 10))" "${units[$unit_index]}"
    else
        printf -v FMT_OUT '%d %s' "$(((bytes + divisor / 2) / divisor))" "${units[$unit_index]}"
    fi
}

# ------------------------------------------------------------------------- main

# Single-instance guard using the same watchdog-lock pattern as seu-wlan-login.
if [ -f "$LOCK_FILE" ] && kill -0 "$(cat "$LOCK_FILE")" 2>/dev/null; then
    # Another resident instance is already running.
    exit 0
fi
echo $$ >"$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"; exit 0' INT TERM EXIT

# Send one-line payloads through a long-lived publisher. DRY_RUN writes to stdout.
if [ "${DRY_RUN:-0}" = "1" ]; then
    exec 3>&1
else
    exec 3> >(mosquitto_pub -h "$MQTT_HOST" \
        -p "$MQTT_PORT" \
        -u "$MQTT_USERNAME" \
        -P "$MQTT_PASSWORD" \
        -t "$MQTT_TOPIC" \
        -l)
fi

# Establish a baseline, then calculate each sample's delta.
declare -a RX_PREV TX_PREV
for idx in "${!IF_LIST[@]}"; do
    read_counters "${IF_LIST[$idx]}"
    RX_PREV[$idx]=$RX_NOW
    TX_PREV[$idx]=$TX_NOW
done

while true; do
    sleep "$INTERVAL_SECONDS"

    rx_diff=0
    tx_diff=0
    for idx in "${!IF_LIST[@]}"; do
        read_counters "${IF_LIST[$idx]}"

        # Counter resets should not produce negative speeds.
        d=$((RX_NOW - ${RX_PREV[$idx]}))
        [ "$d" -lt 0 ] && d=0
        rx_diff=$((rx_diff + d))

        d=$((TX_NOW - ${TX_PREV[$idx]}))
        [ "$d" -lt 0 ] && d=0
        tx_diff=$((tx_diff + d))

        RX_PREV[$idx]=$RX_NOW
        TX_PREV[$idx]=$TX_NOW
    done

    format_bytes "$rx_diff"
    rx_text=$FMT_OUT
    format_bytes "$tx_diff"
    tx_text=$FMT_OUT

    # Each array element is an independent app, so each needs its own lifetime.
    printf -v payload '[{"icon":"%s","text":"%s","lifetimeMs":%d,"lifetimeExpiry":"%s"},{"icon":"%s","text":"%s","lifetimeMs":%d,"lifetimeExpiry":"%s"}]' \
        "$DOWNLOAD_ICON" "$rx_text" "$LIFETIME_MS" "$LIFETIME_EXPIRY" \
        "$UPLOAD_ICON" "$tx_text" "$LIFETIME_MS" "$LIFETIME_EXPIRY"

    printf '%s\n' "$payload" >&3
done
