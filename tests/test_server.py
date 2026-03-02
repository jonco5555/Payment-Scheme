import asyncio

import pytest
import pytest_asyncio

from payment.crypto.models import KeyShare
from payment.models import (
    MintRequest,
    RegistrationRequest,
    SignedMintRequest,
    SignedTransaction,
    Token,
    Transaction,
    UnregistrationRequest,
)
from payment.server.server import Server


@pytest.fixture
def fake_key_share(fake_pk, fake_sk):
    return KeyShare(id=1, share=fake_sk, public_key=fake_pk)


@pytest.fixture
def server(fake_key_share):
    return Server(key_share=fake_key_share, num_clients=1, initial_balance=10)


@pytest_asyncio.fixture
async def registered_server(server, fake_pk):
    await server.handle_register(RegistrationRequest(id="client-1", public_key=fake_pk))
    return server


@pytest.fixture
def signed_mint_request(fake_pk, fake_sig):
    mint_req = MintRequest(id="client-1", public_key=fake_pk)
    payload = mint_req.model_dump_json().encode()
    return SignedMintRequest(payload=payload, signature=fake_sig)


@pytest.fixture
def signed_transaction(fake_pk, fake_sig):
    token_payload = (
        MintRequest(id="client-1", public_key=fake_pk).model_dump_json().encode()
    )
    token = Token(payload=token_payload, signature=fake_sig)

    recipient_payload = (
        MintRequest(id="recipient", public_key=fake_pk).model_dump_json().encode()
    )
    tx = Transaction(token=token, recipient_payload=recipient_payload)
    return SignedTransaction(payload=tx.model_dump_json().encode(), signature=fake_sig)


@pytest.mark.asyncio
async def test_register(server, fake_pk):
    await server.handle_register(RegistrationRequest(id="client-1", public_key=fake_pk))

    assert "client-1" in server._clients
    assert server._clients["client-1"].balance == 10


@pytest.mark.asyncio
async def test_register_concurrent(fake_key_share, fake_pk):
    server = Server(key_share=fake_key_share, num_clients=3, initial_balance=10)

    requests = [
        RegistrationRequest(id=f"client-{i}", public_key=fake_pk) for i in range(3)
    ]
    await asyncio.gather(*[server.handle_register(r) for r in requests])

    assert len(server._clients) == 3


@pytest.mark.asyncio
async def test_register_duplicate_raises(registered_server, fake_pk):
    with pytest.raises(ValueError, match="Client already registered"):
        await registered_server.handle_register(
            RegistrationRequest(id="client-1", public_key=fake_pk)
        )


@pytest.mark.asyncio
async def test_unregister(registered_server):
    await registered_server.handle_unregister(UnregistrationRequest(id="client-1"))

    assert "client-1" not in registered_server._clients


@pytest.mark.asyncio
async def test_mint(registered_server, signed_mint_request, fake_partial_sig):
    result = await registered_server.handle_mint(signed_mint_request)

    assert result == fake_partial_sig
    assert registered_server._clients["client-1"].balance == 9


@pytest.mark.asyncio
async def test_mint_insufficient_balance_raises(registered_server, signed_mint_request):
    registered_server._clients["client-1"].balance = 0

    with pytest.raises(ValueError, match="Insufficient balance"):
        await registered_server.handle_mint(signed_mint_request)


@pytest.mark.asyncio
async def test_pay(registered_server, signed_transaction, fake_partial_sig):
    result = await registered_server.handle_pay(signed_transaction)

    token = Transaction.model_validate_json(signed_transaction.payload).token
    assert result == fake_partial_sig
    assert token in registered_server._token_nullifiers


@pytest.mark.asyncio
async def test_pay_duplicate_token_raises(registered_server, signed_transaction):
    await registered_server.handle_pay(signed_transaction)

    with pytest.raises(ValueError, match="Token already used"):
        await registered_server.handle_pay(signed_transaction)
