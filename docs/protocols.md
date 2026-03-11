# Protocols

This page walks through each operation in the payment scheme step by step.

## Registration

Before any minting or paying, every client must register with all servers.

```mermaid
sequenceDiagram
    participant C as Client
    participant S0 as Server 0
    participant S1 as Server 1
    participant S2 as …
    participant S4 as Server 4

    C->>S0: POST /register {id, public_key}
    C->>S1: POST /register {id, public_key}
    C->>S2: POST /register {id, public_key}
    C->>S4: POST /register {id, public_key}

    Note over S0,S4: Each server stores the client entry<br/>with initial balance and waits until<br/>all expected clients have registered.

    S0-->>C: 200 OK
    S1-->>C: 200 OK
    S2-->>C: 200 OK
    S4-->>C: 200 OK
```

The server blocks the response until all `num_clients` have registered (using `asyncio.Event`), ensuring a synchronized start.
The client uses a timeout that equals `2 · Δ`, where `Δ` is the network synchronization delay.

## Mint

Minting creates a new token of value 1, consuming 1 unit of the client's un-minted balance.

```mermaid
sequenceDiagram
    participant C as Client
    participant S as Server Quorum (f+1)

    Note over C: 1. Generate fresh key pair (pk, sk)
    Note over C: 2. Build TokenPayload = {public_key: pk}
    Note over C: 3. Blind: (H', r) = blind(TokenPayload)
    Note over C: 4. Build MintRequest = {id, blinded_message: H'}
    Note over C: 5. Sign MintRequest with long-term sk

    C->>S: POST /mint { payload, signature }

    Note over S: Verify client identity
    Note over S: Check blinded_message not reused (nullifier)
    Note over S: Check balance ≥ 1
    Note over S: Verify signature against client's public key
    Note over S: Deduct balance by 1
    Note over S: Compute σ'ᵢ = H'^{sᵢ}

    S-->>C: PartialSignature {id, σ'ᵢ}

    Note over C: 6. Collect f+1 partial signatures
    Note over C: 7. Combine: σ' = Σ λᵢ·σ'ᵢ
    Note over C: 8. Unblind: σ = r⁻¹·σ'
    Note over C: 9. Store Token = {payload: TokenPayload, signature: σ}
    Note over C: 10. Store sk alongside the token
```

### What the server sees vs. what the token contains

| Server sees | Token contains |
|---|---|
| Client identity (`id`) | Not stored — token is anonymous |
| `H' = r·H(TokenPayload)` (blinded) | `TokenPayload` (plaintext public key) |
| `σ'ᵢ` (partial blind signature) | `σ = H(TokenPayload)^{SK}` (unblinded full signature) |

Because `r` is secret and random, the server **cannot** derive `H(TokenPayload)` from `H'`, nor link `σ` back to `σ'ᵢ`.

## Pay

Payment transfers a token from one client (sender) to another (recipient).

```mermaid
sequenceDiagram
    participant Sender as Sender Client
    participant Recipient as Recipient Client
    participant S as Server Quorum (f+1)

    Sender->>Recipient: GET /payment-key

    Note over Recipient: 1. Generate fresh key pair (pk_r, sk_r)
    Note over Recipient: 2. Build TokenPayload_r = {public_key: pk_r}
    Note over Recipient: 3. Blind: (H'_r, r_r) = blind(TokenPayload_r)
    Note over Recipient: 4. Store (sk_r, r_r, payload_bytes) in pending_keys

    Recipient-->>Sender: H'_r (blinded one-time key)

    Note over Sender: 5. Pick a token from wallet
    Note over Sender: 6. Build Transaction = {token, recipient_blinded_payload: H'_r}
    Note over Sender: 7. Sign Transaction with the token's one-time sk

    Sender->>S: POST /pay { payload, signature }

    Note over S: Verify token signature against system PK
    Note over S: Check token not in nullifier set
    Note over S: Verify transaction signature against token's pk
    Note over S: Add token to nullifier set
    Note over S: Compute σ'ᵢ = H'_r^{sᵢ}

    S-->>Sender: PartialSignature {id, σ'ᵢ}

    Note over Sender: 8. Combine: σ'_r = Σ λᵢ·σ'ᵢ
    Note over Sender: 9. Build Payment = {blinded_payload: H'_r, blinded_signature: σ'_r}

    Sender->>Recipient: POST /pay {blinded_payload, blinded_signature}

    Note over Recipient: 10. Look up (sk_r, r_r, payload_bytes) by blinded_payload
    Note over Recipient: 11. Unblind: σ_r = r_r⁻¹·σ'_r
    Note over Recipient: 12. Verify: verify(payload_bytes, σ_r, system_PK) ✓
    Note over Recipient: 13. Store Token = {payload: payload_bytes, signature: σ_r}
```

### Value flow

- The sender's token is **consumed** (added to every server's nullifier set).
- The recipient receives a **fresh token** — independently signed, with a new one-time key pair.
- Total value is conserved: 1 token spent → 1 token created.

## Broadcast and Quorum

The client broadcasts every request to **all n servers** concurrently using `asyncio.gather`.  It collects responses and considers the operation successful once **f + 1** servers respond with HTTP 200.

```mermaid
graph LR
    C[Client] --> |POST| S0[Server 0]
    C --> |POST| S1[Server 1]
    C --> |POST| S2[Server 2]
    C --> |POST| S3[Server 3]
    C --> |POST| S4[Server 4]

    S0 --> |200 ✓| C
    S1 --> |200 ✓| C
    S2 --> |200 ✓| C
    S3 --> |timeout ✗| C
    S4 --> |timeout ✗| C

    style S3 stroke:#f66,stroke-width:2px
    style S4 stroke:#f66,stroke-width:2px
```

If fewer than `f + 1` servers respond successfully, the client raises a `RuntimeError`.  This provides **liveness** as long as at most `f` servers suffer omission failures.

## Communication Protocol Summary

All communication uses **HTTP/JSON** over FastAPI:

| From | To | Transport | Serialization |
|------|----|-----------|---------------|
| Client → Server | `/register`, `/mint`, `/pay` | HTTP POST | Pydantic JSON |
| Server → Client | Response body | HTTP 200 | Pydantic JSON (`PartialSignature`) |
| Sender → Recipient | `/payment-key` (GET), `/pay` (POST) | HTTP | Pydantic JSON |
