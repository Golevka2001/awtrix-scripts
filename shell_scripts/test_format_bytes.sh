#!/bin/bash

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

# Example usage:
echo "$(format_bytes 0)"            # 0.0 B
echo "$(format_bytes 9)"            # 9.0 B
echo "$(format_bytes 10)"           # 10 B
echo "$(format_bytes 999)"          # 999 B
echo "$(format_bytes 1000)"         # 1.0 KB
echo "$(format_bytes 1023)"         # 1.0 KB
echo "$(format_bytes 1024)"         # 1.0 KB
echo "$(format_bytes 1025)"         # 1.0 KB
echo "$(format_bytes 1500)"         # 1.4 KB
echo "$(format_bytes $((1 << 20)))" # 1.0 MB
echo "$(format_bytes $((1 << 29)))" # 512 MB
echo "$(format_bytes $((1 << 31)))" # 2.0 GB
