# Payment Scheme

A replicated, threshold-signed digital payment system with **unlinkable tokens**, built on BLS blind signatures over the BLS12-381 curve.

## Overview

This project implements System Project 2 from [EX4 RDS 2026](tasks/ex4_2026.pdf), extending the payment scheme defined in [EX3 RDS 2026](tasks/ex3_2026.pdf) with an explicit **unlinkability** property.  The system consists of `n` servers tolerating `f` omission failures where `n = 2f + 1`, and an arbitrary number of clients.  Every token has a fixed denomination of **1**.

## Key Properties

| Property                     | How it is achieved                                                                 |
|------------------------------|------------------------------------------------------------------------------------|
| **Unforgeability**           | Tokens carry a BLS signature under the system-wide public key, only the server quorum can produce one. |
| **Authorization Unforgeability** | Every mint/pay request is signed by the client's key, servers verify before acting.   |
| **No Double Spend**          | Servers maintain a **token nullifier set**, a token can be spent at most once.       |
| **Liveness**                 | Clients broadcast to all servers and require only `f + 1` responses (quorum).        |
| **Conservation of Value**    | Minting deducts from un-minted balance, paying atomically spends one token and mints one for the recipient. |
| **Unlinkability**            | Blind signatures ensure servers never see the plaintext token payload they sign, breaking the link between Mint and Pay |

## Quick Links

| Page | Description |
|------|-------------|
| [Architecture](architecture.md) | System components, roles, and deployment topology |
| [Cryptographic Primitives](crypto.md) | BLS12-381, Shamir sharing, blind signatures |
| [Protocols](protocols.md) | Registration, Mint, and Pay step-by-step |
| [Unlinkability & Threat Model](threat-model.md) | Formal adversary model and unlinkability argument |
| [Running the System](running.md) | Setup, local run, Docker demo |
| [Testing](testing.md) | Test suite overview and what each test verifies |
| [Code Guide](code-guide.md) | Recommended reading order to understand the codebase |
| [Reference](reference/payment/index.md) | Auto-generated API docs from source docstrings |
