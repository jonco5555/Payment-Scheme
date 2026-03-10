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

# Install all dependencies (runtime + dev + docs)
uv sync --all-groups
```

## Step 1: Generate Key Shares

Before starting servers, generate the Shamir key shares and system public key:

```bash
payment setup --config-path config/config.yaml
```

This creates:

- `config/share_0.bin` … `config/share_4.bin` — one key share per server
- `config/system_public_key.bin` — the shared public key `PK`

## Step 2: Start Servers and Clients

### Option A: Local processes

Start all five servers and five clients in the foreground:

```bash
bash scripts/run_local.sh
```

This script:

1. Starts servers 0–4 on ports `8000`–`8004`.
2. Waits 3 seconds for servers to bind.
3. Starts clients 0–4 on ports `9000`–`9004`.

Press `Ctrl+C` to shut everything down.

### Option B: Full local demo

Run the demo script that also performs mint and pay operations:

```bash
bash scripts/run_demo.sh
```

This script:

1. Runs `payment setup` to generate fresh keys.
2. Starts all servers and clients.
3. Waits for clients to become ready (health-checks `/payment-key`).
4. Mints two tokens on `client-0`.
5. Sends a payment from `client-0` to `client-1`.
6. Prints balances.
7. Simulates omission failures by killing `f` servers.
8. Performs another payment (`client-1` → `client-2`) under degraded conditions.
9. Prints final balances.

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

## CI Pipeline

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push and PR to `main`:

1. **Run tests** — `uv run pytest tests`
2. **Build docs** — `uv run --group docs mkdocs build` (on PRs)
3. **Deploy docs** — `uv run --group docs mkdocs gh-deploy --force` (on push to `main`)
