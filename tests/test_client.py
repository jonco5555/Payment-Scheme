from unittest.mock import patch

import httpx
import pytest

from payment.client.client import Client
from payment.crypto.models import PartialSignature
from payment.models import Payment

SERVER_URLS = ["http://s1:8000", "http://s2:8000", "http://s3:8000"]
F = 1  # threshold = f + 1 = 2

pytestmark = pytest.mark.usefixtures("_mock_crypto")


@pytest.fixture
def client(respx_mock, fake_pk):
    return Client(
        id="test-client",
        system_public_key=fake_pk,
        servers=SERVER_URLS,
        f=F,
        initial_balance=10,
        timeout=10.0,
    )


@pytest.mark.asyncio
async def test_register(client, respx_mock):
    for url in SERVER_URLS:
        respx_mock.post(f"{url}/register").mock(return_value=httpx.Response(200))

    await client.register()


@pytest.mark.asyncio
async def test_mint_stores_token(client, respx_mock, fake_sig):
    for i, url in enumerate(SERVER_URLS):
        respx_mock.post(f"{url}/mint").mock(
            return_value=httpx.Response(
                200,
                json=PartialSignature(id=i + 1, signature=fake_sig).model_dump(
                    mode="json"
                ),
            )
        )

    await client.mint_request()

    assert len(client._tokens) == 1


@pytest.mark.asyncio
async def test_broadcast_raises_without_quorum(client, respx_mock):
    respx_mock.post(f"{SERVER_URLS[0]}/register").mock(return_value=httpx.Response(200))
    respx_mock.post(f"{SERVER_URLS[1]}/register").mock(return_value=httpx.Response(500))
    respx_mock.post(f"{SERVER_URLS[2]}/register").mock(return_value=httpx.Response(500))

    with pytest.raises(RuntimeError, match="need at least"):
        await client.register()


@pytest.mark.asyncio
async def test_pay_raises_with_no_tokens(client, respx_mock, fake_sig):
    respx_mock.get("http://recipient:9000/payment-key").mock(
        return_value=httpx.Response(200, json=fake_sig.model_dump(mode="json"))
    )

    with pytest.raises(ValueError, match="No tokens to pay"):
        await client.pay_request("recipient", "http://recipient:9000")


@pytest.mark.asyncio
async def test_receive_payment_stores_token(client, fake_sig):
    blinded_payload = client.generate_payment_key()
    payment = Payment(blinded_payload=blinded_payload, blinded_signature=fake_sig)

    await client.receive_payment(payment)

    assert len(client._tokens) == 1
    assert blinded_payload not in client._pending_keys


@pytest.mark.asyncio
async def test_receive_payment_rejects_invalid_signature(client, fake_sig):
    with patch("payment.client.client.verify_signature", return_value=False):
        blinded_payload = client.generate_payment_key()
        payment = Payment(blinded_payload=blinded_payload, blinded_signature=fake_sig)

        with pytest.raises(ValueError, match="invalid payment signature"):
            await client.receive_payment(payment)
