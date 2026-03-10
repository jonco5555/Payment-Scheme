import json

import httpx
import pytest

from payment.client.client import Client
from payment.crypto.shares import generate_shares, verify_signature
from payment.models import (
    Payment,
    RegistrationRequest,
    SignedMintRequest,
    SignedTransaction,
)
from payment.server.server import Server

SERVER_URLS = ["http://s1:8000", "http://s2:8000", "http://s3:8000"]


@pytest.fixture
def real_crypto_env(respx_mock):
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

    for url, server in zip(SERVER_URLS, servers):

        async def register_handler(request, server=server):
            body = json.loads(request.content)
            reg = RegistrationRequest.model_validate(body)
            await server.handle_register(reg)
            return httpx.Response(200)

        async def mint_handler(request, server=server):
            body = json.loads(request.content)
            signed = SignedMintRequest.model_validate(body)
            partial = await server.handle_mint(signed)
            return httpx.Response(200, json=partial.model_dump(mode="json"))

        async def pay_handler(request, server=server):
            body = json.loads(request.content)
            signed = SignedTransaction.model_validate(body)
            partial = await server.handle_pay(signed)
            return httpx.Response(200, json=partial.model_dump(mode="json"))

        respx_mock.post(f"{url}/register").mock(side_effect=register_handler)
        respx_mock.post(f"{url}/mint").mock(side_effect=mint_handler)
        respx_mock.post(f"{url}/pay").mock(side_effect=pay_handler)

    return client, system_public_key, servers


@pytest.mark.asyncio
async def test_mint_end_to_end_real_crypto(real_crypto_env):
    client, system_public_key, servers = real_crypto_env

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
async def test_pay_end_to_end_real_crypto(real_crypto_env, respx_mock):
    client, system_public_key, _ = real_crypto_env

    recipient_client = Client(
        id="recipient",
        system_public_key=system_public_key,
        servers=SERVER_URLS,
        f=1,
        initial_balance=0,
        timeout=10.0,
    )

    recipient_address = "http://recipient:9000"

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
async def test_pay_unlinkability_real_crypto(real_crypto_env, respx_mock):
    client, system_public_key, servers = real_crypto_env

    recipient_client = Client(
        id="recipient",
        system_public_key=system_public_key,
        servers=SERVER_URLS,
        f=1,
        initial_balance=0,
        timeout=10.0,
    )

    recipient_address = "http://recipient:9000"

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
async def test_end_to_end_with_omission_failures(respx_mock):
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

    # Two servers respond normally; one simulates an omission failure
    # by never successfully responding (modeled as timeouts).
    for index, (url, server) in enumerate(zip(SERVER_URLS, servers)):
        if index < 2:

            async def register_handler(request, server=server):
                body = json.loads(request.content)
                reg = RegistrationRequest.model_validate(body)
                await server.handle_register(reg)
                return httpx.Response(200)

            async def mint_handler(request, server=server):
                body = json.loads(request.content)
                signed = SignedMintRequest.model_validate(body)
                partial = await server.handle_mint(signed)
                return httpx.Response(200, json=partial.model_dump(mode="json"))

            async def pay_handler(request, server=server):
                body = json.loads(request.content)
                signed = SignedTransaction.model_validate(body)
                partial = await server.handle_pay(signed)
                return httpx.Response(200, json=partial.model_dump(mode="json"))

            respx_mock.post(f"{url}/register").mock(side_effect=register_handler)
            respx_mock.post(f"{url}/mint").mock(side_effect=mint_handler)
            respx_mock.post(f"{url}/pay").mock(side_effect=pay_handler)
        else:
            # Simulate an omission/timeout-style failure: the server accepts
            # the request but never replies within the client's timeout
            # window, which httpx reports as a ReadTimeout.
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
    recipient_client = Client(
        id="recipient",
        system_public_key=system_public_key,
        servers=SERVER_URLS,
        f=f,
        initial_balance=0,
        timeout=10.0,
    )

    recipient_address = "http://recipient:9000"

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

    await client.pay_request("recipient", recipient_address)

    assert len(client._tokens) == 0
    assert len(recipient_client._tokens) == 1
