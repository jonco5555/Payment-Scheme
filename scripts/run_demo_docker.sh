#!/usr/bin/env bash
set -euo pipefail  # Exit on error, exit when undefined variables, exit if any step in pipe fails

CONFIG_PATH="config/config.docker.yaml"
NUM_SERVERS=5
NUM_CLIENTS=5
CLIENT_BASE_PORT=9000
DEMO_SENDER_INDEX=0
DEMO_RECIPIENT_INDEX=1
DEMO_THIRD_INDEX=2

DEMO_SENDER_ID="client-${DEMO_SENDER_INDEX}"
DEMO_RECIPIENT_ID="client-${DEMO_RECIPIENT_INDEX}"
DEMO_THIRD_ID="client-${DEMO_THIRD_INDEX}"

cleanup() {
    echo ""
    echo "Shutting down docker compose..."
    docker compose down --remove-orphans >/dev/null 2>&1 || true
    echo "All containers stopped."
}

trap cleanup EXIT INT TERM

echo "Building payment image..."
docker compose build

echo "Generating system public key and key shares (into ./config)..."
docker run --rm \
    -v "$(pwd)/config:/app/config" \
    payment:latest \
    payment setup --config-path "/app/config/config.docker.yaml"
echo "Key shares generated."

echo "Starting demo servers and clients with docker compose..."
docker compose up -d

SENDER_PORT=$((CLIENT_BASE_PORT + DEMO_SENDER_INDEX))
RECIPIENT_PORT=$((CLIENT_BASE_PORT + DEMO_RECIPIENT_INDEX))
THIRD_PORT=$((CLIENT_BASE_PORT + DEMO_THIRD_INDEX))

SENDER_URL="http://localhost:${SENDER_PORT}"
RECIPIENT_URL="http://localhost:${RECIPIENT_PORT}"
THIRD_URL="http://localhost:${THIRD_PORT}"

RECIPIENT_SERVICE="client-${DEMO_RECIPIENT_INDEX}"
THIRD_SERVICE="client-${DEMO_THIRD_INDEX}"

RECIPIENT_ADDRESS_URL="http://${RECIPIENT_SERVICE}:${RECIPIENT_PORT}"
THIRD_ADDRESS_URL="http://${THIRD_SERVICE}:${THIRD_PORT}"

# Extract f from config
FAILURES=$(awk '/^[[:space:]]*failures:[[:space:]]*/ {print $2}' "$CONFIG_PATH" || echo 0)

echo "Waiting for demo clients to become ready..."
for attempt in {1..60}; do
    if curl -sSf "${SENDER_URL}/payment-key" >/dev/null 2>&1 && \
       curl -sSf "${RECIPIENT_URL}/payment-key" >/dev/null 2>&1 && \
       curl -sSf "${THIRD_URL}/payment-key" >/dev/null 2>&1; then
        echo "Clients are ready."
        break
    fi
    echo "Clients not ready yet (attempt ${attempt}/60), retrying..."
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
    -d "{\"recipient_id\":\"${DEMO_RECIPIENT_ID}\",\"recipient_address\":\"${RECIPIENT_ADDRESS_URL}\"}" \
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
        echo "Stopping server-${index}..."
        docker compose stop "server-${index}" >/dev/null
    done

    echo "Waiting briefly for server shutdown..."
    sleep 2

    echo ""
    echo "Running demo workflow under simulated omission failures..."

    echo "Recipient client ${DEMO_RECIPIENT_ID} will now pay client ${DEMO_THIRD_ID} using its received token..."
    curl -sSf -X POST "${RECIPIENT_URL}/demo/pay" \
        -H "Content-Type: application/json" \
        -d "{\"recipient_id\":\"${DEMO_THIRD_ID}\",\"recipient_address\":\"${THIRD_ADDRESS_URL}\"}" \
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
echo "Press Ctrl+C to stop all containers."

while true; do
    sleep 3600
done
