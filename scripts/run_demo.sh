#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="config/config.yaml"
NUM_SERVERS=5
NUM_CLIENTS=5
CLIENT_BASE_PORT=9000
DEMO_SENDER_INDEX=0
DEMO_RECIPIENT_INDEX=1
DEMO_THIRD_INDEX=2

DEMO_SENDER_ID="client-${DEMO_SENDER_INDEX}"
DEMO_RECIPIENT_ID="client-${DEMO_RECIPIENT_INDEX}"
DEMO_THIRD_ID="client-${DEMO_THIRD_INDEX}"

PIDS=()
SERVER_PIDS=()

cleanup() {
    echo ""
    echo "Shutting down all processes..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    echo "All processes stopped."
}

trap cleanup EXIT INT TERM

echo "Generating system public key and key shares..."
payment setup --config-path "$CONFIG_PATH"
echo "Key shares generated."

echo "Starting demo servers..."
for i in $(seq 0 $((NUM_SERVERS - 1))); do
    server_id="server-${i}"
    echo "Starting ${server_id}..."
    payment server --id "${server_id}" --config-path "$CONFIG_PATH" --key-share-path "config/share_${i}.bin" &
    pid=$!
    PIDS+=("$pid")
    SERVER_PIDS+=("$pid")
done

echo "Waiting for servers to start..."
sleep 3

echo "Starting demo clients..."
for i in $(seq 0 $((NUM_CLIENTS - 1))); do
    client_id="client-${i}"
    echo "Starting client ${client_id}..."
    payment client --id "${client_id}" --config-path "$CONFIG_PATH" --port $((CLIENT_BASE_PORT + i)) &
    PIDS+=("$!")
done

SENDER_PORT=$((CLIENT_BASE_PORT + DEMO_SENDER_INDEX))
RECIPIENT_PORT=$((CLIENT_BASE_PORT + DEMO_RECIPIENT_INDEX))
THIRD_PORT=$((CLIENT_BASE_PORT + DEMO_THIRD_INDEX))
SENDER_URL="http://localhost:${SENDER_PORT}"
RECIPIENT_URL="http://localhost:${RECIPIENT_PORT}"
THIRD_URL="http://localhost:${THIRD_PORT}"

# Extract tolerated failures f from the config (system.failures).
FAILURES=$(awk '/^[[:space:]]*failures:[[:space:]]*/ {print $2}' "$CONFIG_PATH" || echo 0)

# Basic safety: never try to stop all servers.
if [ -z "${FAILURES}" ]; then
    FAILURES=0
fi
if [ "$FAILURES" -ge "$NUM_SERVERS" ]; then
    FAILURES=$((NUM_SERVERS - 1))
fi

echo "Waiting for demo clients to become ready..."
for attempt in {1..30}; do
    if curl -sSf "${SENDER_URL}/payment-key" >/dev/null 2>&1 && \
       curl -sSf "${RECIPIENT_URL}/payment-key" >/dev/null 2>&1 && \
       curl -sSf "${THIRD_URL}/payment-key" >/dev/null 2>&1; then
        echo "Clients are ready."
        break
    fi
    echo "Clients not ready yet (attempt ${attempt}/30), retrying..."
    sleep 1
done

echo ""
echo "Running demo workflow..."

echo "Minting a demo token on client ${DEMO_SENDER_ID}..."
curl -sSf -X POST "${SENDER_URL}/demo/mint" >/dev/null
echo "First mint completed."

echo "Minting a second demo token on client ${DEMO_SENDER_ID}..."
curl -sSf -X POST "${SENDER_URL}/demo/mint" >/dev/null
echo "Second mint completed."

echo "Sending a payment from client ${DEMO_SENDER_ID} to client ${DEMO_RECIPIENT_ID}..."
curl -sSf -X POST "${SENDER_URL}/demo/pay" \
    -H "Content-Type: application/json" \
    -d "{\"recipient_id\":\"${DEMO_RECIPIENT_ID}\",\"recipient_address\":\"${RECIPIENT_URL}\"}" \
    >/dev/null
echo "Demo payment completed successfully."

echo ""
echo "Current balances and token counts (after first payment):"
echo "  Sender (${DEMO_SENDER_ID}):"
curl -sSf "${SENDER_URL}/demo/balance"
echo ""
echo "  Recipient (${DEMO_RECIPIENT_ID}):"
curl -sSf "${RECIPIENT_URL}/demo/balance"
echo ""

if [ "$FAILURES" -gt 0 ]; then
    echo ""
    echo "Simulating up to ${FAILURES} omission failures by stopping servers..."

    # Stop up to f servers (highest indices) to simulate omission/timeout failures.
    for i in $(seq 1 "$FAILURES"); do
        index=$((NUM_SERVERS - i))
        pid="${SERVER_PIDS[$index]}"
        if [ -n "${pid:-}" ]; then
            echo "Stopping server with local index ${index} (PID ${pid})..."
            kill "$pid" 2>/dev/null || true
        fi
    done

    echo "Waiting briefly for server shutdown..."
    sleep 2

    echo ""
    echo "Running demo workflow under simulated omission failures..."

    echo "Recipient client ${DEMO_RECIPIENT_ID} will now pay client ${DEMO_THIRD_ID} using its received token..."
    curl -sSf -X POST "${RECIPIENT_URL}/demo/pay" \
        -H "Content-Type: application/json" \
        -d "{\"recipient_id\":\"${DEMO_THIRD_ID}\",\"recipient_address\":\"${THIRD_URL}\"}" \
        >/dev/null
    echo "Recipient-to-third-client payment under omissions completed successfully."

    echo ""
    echo "Balances and token counts after omission-failure run:"
    echo "  Sender (${DEMO_SENDER_ID}):"
    curl -sSf "${SENDER_URL}/demo/balance"
    echo ""
    echo "  Recipient (${DEMO_RECIPIENT_ID}):"
    curl -sSf "${RECIPIENT_URL}/demo/balance"
    echo ""
    echo "  Third client (${DEMO_THIRD_ID}):"
    curl -sSf "${THIRD_URL}/demo/balance"
    echo ""
fi

echo ""
echo "Demo complete. Some servers may have been stopped to simulate omission failures."
echo "You can send additional demo requests to:"
echo "  Sender:    ${SENDER_URL}"
echo "  Recipient: ${RECIPIENT_URL}"
echo "  Third:     ${THIRD_URL}"
echo ""
echo "Press Ctrl+C to stop all processes."

wait
