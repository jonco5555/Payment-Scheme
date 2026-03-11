#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="config/config.yaml"
NUM_SERVERS=5
NUM_CLIENTS=5

PIDS=()

cleanup() {
    echo ""
    echo "Shutting down all processes..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null
    echo "All processes stopped."
}

trap cleanup EXIT INT TERM

echo "Generating system public key and key shares..."
payment setup --config-path "$CONFIG_PATH"
echo "Key shares generated."

for i in $(seq 0 $((NUM_SERVERS - 1))); do
    server_id="server-${i}"
    echo "Starting ${server_id}..."
    payment server --id "${server_id}" --config-path "$CONFIG_PATH" --key-share-path "config/share_${i}.bin" &
    PIDS+=($!)
done

echo "Waiting for servers to start..."
sleep 3

for i in $(seq 0 $((NUM_CLIENTS - 1))); do
    client_id="client-${i}"
    echo "Starting client ${client_id}..."
    payment client --id "${client_id}" --config-path "$CONFIG_PATH" --port $((9000 + i)) &
    PIDS+=($!)
done

echo ""
echo "All servers and clients are running. Press Ctrl+C to stop."
wait
