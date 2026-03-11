# Running the System

## Prerequisites

- **Python 3.12+**
- [**uv**](https://docs.astral.sh/uv/) (package manager / build tool)
- **Docker** and **Docker Compose** (for the containerized demo)

## Installation

```bash
# Clone the repository
git clone https://github.com/jonco5555/Payment-Scheme.git
cd Payment-Scheme

# Install all dependencies
uv sync
```

## Starting the System

### Option A: Local processes

Start all five servers and five clients in the foreground:

```bash
bash scripts/run_local.sh
```

This script:

1. Creates one key share per server and the system public key.
2. Starts servers 0–4 on ports `8000`–`8004`.
3. Waits 3 seconds for servers to bind.
4. Starts clients 0–4 on ports `9000`–`9004`.

Press `Ctrl+C` to shut everything down.

### Option B: Full local demo

Run the demo script that also performs mint and pay operations:

```bash
bash scripts/run_demo.sh
```

This script:

1. Creates one key share per server and the system public key.
2. Runs `payment setup` to generate fresh keys.
3. Starts all servers and clients.
4. Waits for clients to become ready (health-checks `/payment-key`).
5. Mints two tokens on `client-0`.
6. Sends a payment from `client-0` to `client-1`.
7. Prints balances.
8. Simulates omission failures by killing `f` servers.
9. Performs another payment (`client-1` → `client-2`) under degraded conditions.
10. Prints final balances.

### Option C: Docker Compose demo

```bash
bash scripts/run_demo_docker.sh
```

This builds the Docker image, generates keys inside a container, starts all services via `docker-compose up -d`, and then runs the same demo workflow using `curl` against the exposed client ports (`9000`–`9004`).

Omission failures are simulated by running `docker compose stop server-3` and `docker compose stop server-4`.

## Environment Variables

| Variable | Used by | Description |
|----------|---------|-------------|
| `CONFIG_PATH` | server, client | Path to the YAML config file |
| `SERVER_ID` | server | Server identifier (must match `servers[i].id` in config) |
| `KEY_SHARE_PATH` | server | Path to the server's key share `.bin` file |
| `CLIENT_ID` | client | Client identifier |
| `PORT` | client | Port for the client's FastAPI server |
| `LOG_LEVEL` | all | Logging level (`DEBUG`, `INFO`, `WARNING`, etc.) |
