import json
import random

import httpx
import pytest

from payment.client.client import Client
from payment.crypto.shares import generate_shares, verify_signature
from payment.models import (
    MintRequest,
    Payment,
    RegistrationRequest,
    SignedMintRequest,
    SignedTransaction,
    Transaction,
)
from payment.server.server import Server

SERVER_URLS = ["http://s1:8000", "http://s2:8000", "http://s3:8000"]


def _create_client_and_servers():
    n = len(SERVER_URLS)
    f = 1
    _, shares = generate_shares(n, f)
    system_public_key = shares[0].public_key

    client = Client(
        id="real-client",
        system_public_key=system_public_key,
        servers=SERVER_URLS,
        f=f,
        initial_balance=10,
        timeout=10.0,
    )

    servers = [
        Server(id=f"server-{i}", key_share=share, num_clients=1, initial_balance=10)
        for i, share in enumerate(shares)
    ]

    return client, system_public_key, servers


def _setup_server_routes(
    respx_mock, servers, mint_transcripts=None, pay_transcripts=None
):
    for url, server in zip(SERVER_URLS, servers):

        async def register_handler(request, server=server):
            body = json.loads(request.content)
            reg = RegistrationRequest.model_validate(body)
            await server.handle_register(reg)
            return httpx.Response(200)

        async def mint_handler(request, server=server):
            body = json.loads(request.content)
            signed = SignedMintRequest.model_validate(body)
            if mint_transcripts is not None:
                mint_transcripts.append(signed)
            partial = await server.handle_mint(signed)
            return httpx.Response(200, json=partial.model_dump(mode="json"))

        async def pay_handler(request, server=server):
            body = json.loads(request.content)
            signed = SignedTransaction.model_validate(body)
            if pay_transcripts is not None:
                pay_transcripts.append(signed)
            partial = await server.handle_pay(signed)
            return httpx.Response(200, json=partial.model_dump(mode="json"))

        respx_mock.post(f"{url}/register").mock(side_effect=register_handler)
        respx_mock.post(f"{url}/mint").mock(side_effect=mint_handler)
        respx_mock.post(f"{url}/pay").mock(side_effect=pay_handler)


def _create_recipient_client(system_public_key: bytes) -> Client:
    return Client(
        id="recipient",
        system_public_key=system_public_key,
        servers=SERVER_URLS,
        f=1,
        initial_balance=0,
        timeout=10.0,
    )


def _setup_recipient_routes(
    respx_mock, recipient_client, recipient_address="http://recipient:9000"
):
    async def payment_key_handler(request):
        pk = recipient_client.generate_payment_key()
        return httpx.Response(200, json=pk.model_dump(mode="json"))

    async def receive_payment_handler(request):
        body = json.loads(request.content)
        payment = Payment.model_validate(body)
        await recipient_client.receive_payment(payment)
        return httpx.Response(200)

    respx_mock.get(f"{recipient_address}/payment-key").mock(
        side_effect=payment_key_handler
    )
    respx_mock.post(f"{recipient_address}/pay").mock(
        side_effect=receive_payment_handler
    )

    return recipient_address


@pytest.fixture
def setup_env(respx_mock):
    client, system_public_key, servers = _create_client_and_servers()
    _setup_server_routes(respx_mock, servers)
    return client, system_public_key, servers


@pytest.fixture
def transcript_env(respx_mock):
    client, system_public_key, servers = _create_client_and_servers()

    mint_transcripts: list[SignedMintRequest] = []
    pay_transcripts: list[SignedTransaction] = []

    _setup_server_routes(
        respx_mock,
        servers,
        mint_transcripts=mint_transcripts,
        pay_transcripts=pay_transcripts,
    )

    return client, system_public_key, servers, mint_transcripts, pay_transcripts


@pytest.mark.asyncio
async def test_mint_end_to_end(setup_env):
    """Test minting a single token end-to-end.

    The client registers with the servers, submits a mint request, and we then
    assert that exactly one token is created, balances are debited accordingly
    on both the client and all servers, and that the minted token verifies
    under the shared system public key.
    """
    client, system_public_key, servers = setup_env

    await client.register()
    starting_balance = client._balance

    await client.mint_request()

    assert len(client._tokens) == 1
    assert client._balance == starting_balance - 1
    token = client._tokens[0].token

    assert verify_signature(token.payload, token.signature, system_public_key)

    for server in servers:
        entry = server._clients["real-client"]
        assert entry.balance == starting_balance - 1


@pytest.mark.asyncio
async def test_pay_end_to_end(setup_env, respx_mock):
    """Test making a payment end-to-end between two clients.

    The sender client registers and mints a token, the recipient exposes HTTP
    endpoints for obtaining a payment key and receiving a payment, and the
    sender uses `pay_request` so that the token is transferred, its signature
    verifies under the system public key, and local token inventories are
    updated as expected.
    """
    client, system_public_key, _ = setup_env

    recipient_client = _create_recipient_client(system_public_key)
    recipient_address = _setup_recipient_routes(respx_mock, recipient_client)

    await client.register()
    await client.mint_request()
    assert len(client._tokens) == 1

    await client.pay_request("recipient", recipient_address)

    assert len(client._tokens) == 0
    assert len(recipient_client._tokens) == 1

    received_token = recipient_client._tokens[0].token
    assert verify_signature(
        received_token.payload, received_token.signature, system_public_key
    )


@pytest.mark.asyncio
async def test_pay_unlinkability(setup_env, respx_mock):
    """Test that payments are unlinkable at the token and server state level.

    The client mints a token and spends it once, we verify that the recipient
    receives a fresh, different token that also verifies under the same system
    public key, and that servers only record the spent token in their
    nullifier sets, ensuring they cannot link the recipient's token back to
    the original mint.
    """
    client, system_public_key, servers = setup_env

    recipient_client = _create_recipient_client(system_public_key)
    recipient_address = _setup_recipient_routes(respx_mock, recipient_client)

    await client.register()
    await client.mint_request()
    assert len(client._tokens) == 1
    original_token = client._tokens[0].token

    await client.pay_request("recipient", recipient_address)

    # Sender spent their token, recipient obtained a fresh one.
    assert len(client._tokens) == 0
    assert len(recipient_client._tokens) == 1

    received_token = recipient_client._tokens[0].token

    # Both tokens are valid under the same system public key.
    assert verify_signature(
        original_token.payload, original_token.signature, system_public_key
    )
    assert verify_signature(
        received_token.payload, received_token.signature, system_public_key
    )

    # Unlinkability: the token held by the recipient is a different,
    # freshly minted token, and servers only record the spent token.
    assert original_token.payload != received_token.payload

    for server in servers:
        assert original_token in server._token_nullifiers
        assert received_token not in server._token_nullifiers


@pytest.mark.asyncio
async def test_end_to_end_with_omission_failures(setup_env, respx_mock):
    """Test that the protocol tolerates omission failures at one server.

    One server is configured to time out on all endpoints, while the client
    still performs registration, minting, and a payment to a recipient; the
    test confirms that, despite one non-responding server, threshold-based
    communication allows all operations to succeed end-to-end.
    """
    client, system_public_key, servers = setup_env

    # Override one server to simulate an omission failure: it accepts the request but
    # never replies within the client's timeout window, which httpx reports as a ReadTimeout
    for index, (url, _server) in enumerate(zip(SERVER_URLS, servers)):
        if index == len(servers) - 1:
            respx_mock.post(f"{url}/register").mock(
                side_effect=httpx.ReadTimeout("server did not respond")
            )
            respx_mock.post(f"{url}/mint").mock(
                side_effect=httpx.ReadTimeout("server did not respond")
            )
            respx_mock.post(f"{url}/pay").mock(
                side_effect=httpx.ReadTimeout("server did not respond")
            )

    await client.register()
    starting_balance = client._balance

    await client.mint_request()

    assert len(client._tokens) == 1
    assert client._balance == starting_balance - 1

    # Now perform a payment to a recipient, still tolerating one omitted server.
    recipient_client = _create_recipient_client(system_public_key)
    recipient_address = _setup_recipient_routes(respx_mock, recipient_client)

    await client.pay_request("recipient", recipient_address)

    assert len(client._tokens) == 0
    assert len(recipient_client._tokens) == 1


@pytest.mark.asyncio
async def test_double_spend_rejected(setup_env):
    """Test that double-spending the same signed transaction is rejected.

    After minting a token, the client prepares a single signed transaction and
    broadcasts it once successfully, then attempts to broadcast the exact same
    signed transaction again; the second broadcast must raise an error and all
    servers must record the spent token exactly once in their nullifier sets.
    """
    client, system_public_key, servers = setup_env

    await client.register()
    await client.mint_request()
    assert len(client._tokens) == 1

    # Set up a recipient but use the lower-level client API to replay the same
    # signed transaction twice against servers
    recipient_client = _create_recipient_client(system_public_key)

    async with httpx.AsyncClient(timeout=10.0) as local_client:
        recipient_client._client = local_client

        # Generate a payment key and build a signed transaction once
        recipient_blinded_pk = recipient_client.generate_payment_key()
        spent_client_token, signed_tx = await client._prepare_pay(
            "recipient", recipient_blinded_pk
        )

        # First broadcast succeeds
        responses = await client._broadcast("pay", signed_tx.model_dump(mode="json"))
        assert len(responses) >= client._threshold

        # Second broadcast with the exact same signed transaction must fail,
        # because all servers have already nullified the token
        with pytest.raises(RuntimeError):
            await client._broadcast("pay", signed_tx.model_dump(mode="json"))

        # Every server has recorded the spent token exactly once
        for server in servers:
            assert spent_client_token.token in server._token_nullifiers


@pytest.mark.asyncio
async def test_multi_token_random_pay_unlinkability(transcript_env, respx_mock):
    """Test unlinkability when spending a random token among many and inspecting transcripts.

    The client mints multiple tokens, shuffles them, and spends one at random
    to a recipient. We then verify that all remaining and received tokens
    validate under the system key, that each server saw the expected number
    of mint and pay transcripts, and that blinded messages used in minting do
    not reappear verbatim in any pay transaction fields, demonstrating
    unlinkability at the transcript level.
    """
    client, system_public_key, servers, mint_tx, pay_tx = transcript_env

    recipient_client = _create_recipient_client(system_public_key)
    recipient_address = _setup_recipient_routes(respx_mock, recipient_client)

    await client.register()

    num_tokens = 5
    for _ in range(num_tokens):
        await client.mint_request()

    assert len(client._tokens) == num_tokens

    # Shuffle tokens so that the one spent is effectively random among those minted.
    random.shuffle(client._tokens)

    await client.pay_request("recipient", recipient_address)

    assert len(client._tokens) == num_tokens - 1
    assert len(recipient_client._tokens) == 1

    # Correctness: all minted tokens and the received token verify under the same system public key
    for client_token in client._tokens:
        assert verify_signature(
            client_token.token.payload, client_token.token.signature, system_public_key
        )
    received_token = recipient_client._tokens[0].token
    assert verify_signature(
        received_token.payload, received_token.signature, system_public_key
    )

    # Collect server-side transcripts
    mint_requests = [
        MintRequest.model_validate_json(signed.payload) for signed in mint_tx
    ]
    pay_transactions = [
        Transaction.model_validate_json(signed.payload) for signed in pay_tx
    ]

    # There should be num_tokens mint requests per server and exactly one pay transaction per server
    assert len(mint_requests) == num_tokens * len(servers)
    assert len(pay_transactions) == len(servers)

    # Unlinkability check (at transcript level): values that appear in mint
    # requests (blinded messages) never reappear verbatim in pay transactions
    mint_blinded = {mr.blinded_message.model_dump_json() for mr in mint_requests}
    pay_fields = set()
    for tx in pay_transactions:
        pay_fields.add(tx.recipient_blinded_payload.model_dump_json())
        pay_fields.add(tx.token.payload.decode())
        pay_fields.add(tx.token.signature.model_dump_json())

    assert mint_blinded.isdisjoint(pay_fields)
