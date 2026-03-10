# Testing

The test suite lives in `tests/` and is organized into four modules, ordered from low-level crypto primitives up to full end-to-end integration.

## Running Tests

```bash
uv run pytest tests          # all tests
uv run pytest tests -v       # verbose output
uv run pytest tests -k mint  # only tests matching "mint"
```

## Test Modules

### `test_shares.py` — Cryptographic primitives

Unit tests for every function in `payment.crypto.shares`:

| Test | What it verifies |
|------|-----------------|
| `test_generate_polynomial_length` | Polynomial has `degree + 1` coefficients |
| `test_generate_polynomial_randomness` | Two polynomials are distinct (randomness) |
| `test_evaluate_polynomial_constant` | Constant polynomial evaluates correctly |
| `test_evaluate_polynomial_linear` | Linear polynomial `5 + 3x` at several points |
| `test_lagrange_coefficient_sum` | Lagrange coefficients for 3 points sum to 1 |
| `test_lagrange_reconstruction` | Reconstruct secret from polynomial evaluations |
| `test_generate_shares_count` | Correct number of shares generated |
| `test_generate_shares_ids` | Share IDs are `1, 2, …, n` |
| `test_reconstruct_with_threshold` | Reconstruct secret with exactly `f+1` shares |
| `test_reconstruct_with_all_shares` | Reconstruct with all `n` shares |
| `test_insufficient_shares_fails` | Fewer than `f+1` shares yield wrong result |
| `test_partial_sign_blinded_message_deterministic` | Same input → same partial signature |
| `test_combine_and_verify` | Combine partials, unblind, verify against PK |
| `test_different_subsets_same_signature` | Two different `f+1` subsets produce the same combined signature |
| `test_signature_invalid_for_different_message` | Signature on message A fails verification for message B |
| `test_signature_invalid_for_wrong_key` | Signature under one key fails verification under another |
| `test_end_to_end_blind_signing_flow` | Full blind sign flow: create key pair → blind → partial sign → combine → unblind → verify |

### `test_server.py` — Server logic

Unit tests for `payment.server.server.Server` with **mocked crypto** (no real elliptic-curve math, making tests fast):

| Test | What it verifies |
|------|-----------------|
| `test_register` | Client appears in server state with correct balance |
| `test_register_concurrent` | Three concurrent registrations all succeed |
| `test_register_duplicate_raises` | Re-registering the same client raises `ValueError` |
| `test_unregister` | Client removed from server state |
| `test_mint` | Returns partial signature; balance decremented |
| `test_mint_insufficient_balance_raises` | Zero-balance client cannot mint |
| `test_pay` | Returns partial signature; token added to nullifiers |
| `test_pay_duplicate_token_raises` | Replaying the same transaction raises `ValueError` (double-spend) |

### `test_client.py` — Client logic

Unit tests for `payment.client.client.Client` with mocked crypto and mocked HTTP (via `respx`):

| Test | What it verifies |
|------|-----------------|
| `test_register` | Registration broadcast succeeds |
| `test_mint_stores_token` | After minting, client has exactly one token |
| `test_broadcast_raises_without_quorum` | If fewer than `f+1` servers respond, `RuntimeError` is raised |
| `test_pay_raises_with_no_tokens` | Cannot pay when wallet is empty |
| `test_receive_payment_stores_token` | Accepting a payment stores the token and removes the pending key |
| `test_receive_payment_rejects_invalid_signature` | Payment with bad signature is rejected |

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

### Fixtures (`conftest.py`)

- `fake_pk`, `fake_sk`, `fake_sig`, `fake_partial_sig` — Lightweight stand-ins for crypto objects.
- `_mock_crypto` — Patches all crypto functions in both client and server modules so unit tests run instantly without elliptic-curve computation.

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
