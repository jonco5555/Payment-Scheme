from unittest.mock import patch

import pytest

from payment.crypto.models import FQ2_Point, G1_Point, G2_Point, PartialSignature


@pytest.fixture
def fake_pk():
    return G1_Point(x=1, y=2)


@pytest.fixture
def fake_sk():
    return 42


@pytest.fixture
def fake_sig():
    return G2_Point(x=FQ2_Point(c0=5, c1=6), y=FQ2_Point(c0=7, c1=8))


@pytest.fixture
def fake_partial_sig(fake_sig):
    return PartialSignature(id=1, signature=fake_sig)


@pytest.fixture(autouse=True)
def _mock_crypto(fake_sig, fake_pk, fake_sk, fake_partial_sig):
    """Mock all crypto ops to avoid expensive elliptic-curve math."""
    with (
        patch(
            "payment.client.client.create_fresh_key_pair",
            return_value=(fake_pk, fake_sk),
        ),
        patch("payment.client.client.sign_message", return_value=fake_sig),
        patch("payment.client.client.verify_signature", return_value=True),
        patch(
            "payment.client.client.combine_partial_signatures",
            return_value=fake_sig,
        ),
        patch("payment.server.server.verify_signature", return_value=True),
        patch(
            "payment.server.server.partial_sign",
            return_value=fake_partial_sig,
        ),
    ):
        yield
