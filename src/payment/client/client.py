import asyncio

import httpx

from payment.client.models import ClientToken
from payment.crypto.models import PartialSignature
from payment.crypto.shares import (
    combine_partial_signatures,
    create_fresh_key_pair,
    sign_message,
)
from payment.models import MintRequest, SignedMintRequest, Token


class Client:
    def __init__(self, id: str, servers: list[str]) -> None:
        self._id = id
        self._public_key, self._private_key = create_fresh_key_pair()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(5.0))
        self._server_urls = servers
        self._tokens: list[ClientToken] = []

    async def mint_request(self) -> None:
        pk, sk = create_fresh_key_pair()
        mint_request = MintRequest(id=self._id, public_key=pk)
        payload = mint_request.model_dump_json().encode()
        signature = sign_message(payload, self._private_key)
        signed_mint_request = SignedMintRequest(payload=payload, signature=signature)

        tasks = [
            self._client.post(url, json=signed_mint_request.model_dump_json())
            for url in self._server_urls
        ]

        responses = await asyncio.gather(*tasks)
        partial_signatures = [
            PartialSignature.model_validate_json(response.content)
            for response in responses
        ]
        # TODO: Check if we have enough partial signatures
        signature = combine_partial_signatures(partial_signatures)
        self._tokens.append(
            ClientToken(
                token=Token(payload=payload, signature=signature),
                secret_key=sk,
            )
        )
