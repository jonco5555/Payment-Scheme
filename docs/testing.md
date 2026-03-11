# Testing

The test suite lives in `tests/` and is organized into four modules, ordered from low-level crypto primitives up to full end-to-end integration.

## Running Tests

```bash
uv run pytest tests
```

## Test Modules

### `test_shares.py` — Cryptographic primitives

Unit tests for every function in `payment.crypto.shares`.

### `test_server.py` — Server logic

Unit tests for `payment.server.server.Server` with **mocked crypto** (no real elliptic-curve math, making tests fast).

### `test_client.py` — Client logic

Unit tests for `payment.client.client.Client` with mocked crypto and mocked HTTP (via `respx`).

### `test_integration.py` — End-to-end integration

Full integration tests with **real cryptography** (BLS12-381 operations, no mocking), using `respx` to wire clients to in-process `Server` instances:

| Test | What it verifies |
|------|-----------------|
| `test_mint_end_to_end` | Mint a token, verify it under system PK, check balances on all servers |
| `test_pay_end_to_end` | Mint → pay → recipient holds a valid token, sender's wallet is empty |
| `test_pay_unlinkability` | After pay: original and received tokens are **different objects**, both valid under PK, and only the original appears in server nullifiers |
| `test_end_to_end_with_omission_failures` | One server times out on all endpoints; mint and pay still succeed (quorum = 2 out of 3) |
| `test_double_spend_rejected` | Replaying the exact same `SignedTransaction` a second time raises `RuntimeError`; token in nullifiers exactly once |
| `test_multi_token_random_pay_unlinkability` | Mints 5 tokens, shuffles, spends a random one; verifies all tokens valid; checks that **blinded messages from Mint never appear in Pay transcripts** (transcript-level unlinkability) |

### What the unlinkability tests specifically check

1. **Token-level**: The received token has a different `payload` and different `signature` than the original.
2. **Nullifier-level**: Only the spent token is in the nullifier set; the new token is not.
3. **Transcript-level**: The set of `blinded_message` values from all Mint transcripts is **disjoint** from all field values in Pay transcripts (recipient blinded payload, token payload, token signature).

## Test Infrastructure

### `respx` for HTTP mocking

Integration tests use `respx_mock` to intercept `httpx` requests.  Handler functions deserialize the request body and delegate to real `Server` instances, making the tests exercise the full protocol logic without starting actual HTTP servers.

## Docker Demo as a System Test

The `scripts/run_demo_docker.sh` script acts as a system-level smoke test:

1. Builds the Docker image.
2. Generates keys.
3. Starts 5 servers + 5 clients in containers.
4. Mints tokens, performs payments, and prints balances.
5. Stops `f` servers and performs a payment under omission failures.

This validates that the entire stack — Docker image, networking, CLI, FastAPI routing, crypto — works end to end in a realistic deployment.
