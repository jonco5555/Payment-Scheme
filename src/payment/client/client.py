import asyncio
import logging

import httpx

from payment.client.models import ClientToken
from payment.crypto.models import G1_Point, PartialSignature
from payment.crypto.shares import (
    combine_partial_signatures,
    create_fresh_key_pair,
    sign_message,
    verify_signature,
)
from payment.models import (
    MintRequest,
    RegistrationRequest,
    SignedMintRequest,
    SignedTransaction,
    Token,
    Transaction,
    UnregistrationRequest,
)


class Client:
    def __init__(
        self, id: str, system_public_key: G1_Point, servers: list[str]
    ) -> None:
        self._logger = logging.getLogger(__name__)
        self._id = id
        self._system_public_key = system_public_key
        self._public_key, self._private_key = create_fresh_key_pair()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(None, connect=5.0))
        self._server_urls = servers
        self._tokens: list[ClientToken] = []
        self._pending_keys: dict[G1_Point, int] = {}

    async def start(self) -> None:
        await self.register()

    async def stop(self) -> None:
        await self.unregister()
        await self._client.aclose()

    async def register(self) -> None:
        """Register this client's public key with all servers."""
        self._logger.info(
            f"{self._id} registering with {len(self._server_urls)} servers"
        )
        request = RegistrationRequest(id=self._id, public_key=self._public_key)
        tasks = [
            self._client.post(f"{url}/register", json=request.model_dump(mode="json"))
            for url in self._server_urls
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        failures = [
            r for r in responses if isinstance(r, Exception) or r.status_code != 200
        ]
        if failures:
            self._logger.error(f"Failures: {failures}")
            self._logger.error(
                f"{self._id} failed to register with {len(failures)} servers"
            )
            raise RuntimeError(
                f"Registration failed on {len(failures)}/{len(self._server_urls)} servers"
            )
        self._logger.info(f"{self._id} registered successfully with all servers")

    async def unregister(self) -> None:
        """Unregister this client from all servers."""
        self._logger.info(
            f"{self._id} unregistering from {len(self._server_urls)} servers"
        )
        request = UnregistrationRequest(id=self._id)
        tasks = [
            self._client.post(f"{url}/unregister", json=request.model_dump(mode="json"))
            for url in self._server_urls
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        failures = [
            r for r in responses if isinstance(r, Exception) or r.status_code != 200
        ]
        if failures:
            self._logger.error(f"Failures: {failures}")
            self._logger.error(
                f"{self._id} failed to unregister from {len(failures)} servers"
            )
            raise RuntimeError(
                f"Unregistration failed on {len(failures)}/{len(self._server_urls)} servers"
            )
        self._logger.info(f"{self._id} unregistered successfully from all servers")

    async def wait_for_servers_ready(self) -> None:
        """Poll all servers until they report all clients have registered."""
        self._logger.info(f"{self._id} waiting for all servers to be ready")
        while True:
            tasks = [self._client.get(f"{url}/ready") for url in self._server_urls]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            all_ready = all(
                not isinstance(r, Exception)
                and r.status_code == 200
                and r.json().get("ready")
                for r in responses
            )
            if all_ready:
                break
            await asyncio.sleep(1)
        self._logger.info(f"{self._id} all servers are ready")

    def generate_payment_key(self) -> G1_Point:
        pk, sk = create_fresh_key_pair()
        self._pending_keys[pk] = sk
        return pk

    async def mint_request(self) -> None:
        self._logger.info(f"{self._id} issuing a mint request")

        sk, payload, signed_mint_request = await self.prepare_mint()

        tasks = [
            self._client.post(f"{url}/mint", json=signed_mint_request.model_dump_json())
            for url in self._server_urls
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        self._logger.info(
            f"{self._id} received {len(responses)} responses for mint request"
        )

        # TODO: Check if we have enough non-error responses
        # TODO: Handle client balance here

        await self.process_mint_responses(sk, payload, responses)

        self._logger.info(f"{self._id} mint request completed")

    async def pay_request(self, recipient_id: str, recipient_address: str) -> None:
        self._logger.info(f"{self._id} issuing a pay request to {recipient_id}")

        async with self._client.post(
            f"{recipient_address}/payment-key"
        ) as key_response:
            if key_response.status_code != httpx.codes.OK:
                self._logger.error(
                    f"{self._id} failed to get payment key from {recipient_address}"
                )
                raise ValueError()
            recipient_public_key = G1_Point.model_validate_json(key_response.content)
            self._logger.info(
                f"{self._id} received payment key from {recipient_address}"
            )

        client_token, recipient_payload, signed_tx = await self.prepare_pay(
            recipient_id, recipient_public_key
        )

        tasks = [
            self._client.post(f"{url}/pay", json=signed_tx.model_dump_json())
            for url in self._server_urls
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        self._logger.info(
            f"{self._id} received {len(responses)} responses for pay request"
        )

        # TODO: Check if we have enough non-error responses
        # TODO: if not enough responses, return the token to the list

        await self.process_pay_responses(
            recipient_payload, recipient_address, responses
        )

        self._logger.info(f"{self._id} pay request to {recipient_id} completed")

    async def prepare_mint(self) -> tuple[int, bytes, SignedMintRequest]:
        pk, sk = create_fresh_key_pair()
        mint_request = MintRequest(id=self._id, public_key=pk)
        payload = mint_request.model_dump_json().encode()
        signature = sign_message(payload, self._private_key)
        signed_mint_request = SignedMintRequest(payload=payload, signature=signature)
        return sk, payload, signed_mint_request

    async def process_mint_responses(
        self, sk: int, payload: bytes, responses: list[httpx.Response]
    ) -> None:
        partial_signatures = [
            PartialSignature.model_validate_json(response.content)
            for response in responses
        ]
        signature = combine_partial_signatures(partial_signatures)
        self._tokens.append(
            ClientToken(
                token=Token(payload=payload, signature=signature), secret_key=sk
            )
        )

    async def prepare_pay(
        self, recipient_id: str, recipient_public_key: G1_Point
    ) -> tuple[ClientToken, bytes, SignedTransaction]:
        if not self._tokens:
            raise ValueError("No tokens to pay")
        client_token = self._tokens.pop(0)
        recipient_mint_request = MintRequest(
            id=recipient_id, public_key=recipient_public_key
        )
        recipient_payload = recipient_mint_request.model_dump_json().encode()
        tx = Transaction(
            token=client_token.token,
            recipient_payload=recipient_payload,
        )
        payload = tx.model_dump_json().encode()
        signature = sign_message(payload, client_token.secret_key)
        signed_tx = SignedTransaction(payload=payload, signature=signature)
        return client_token, recipient_payload, signed_tx

    async def process_pay_responses(
        self,
        recipient_payload: bytes,
        recipient_address: str,
        responses: list[httpx.Response],
    ) -> None:
        partial_signatures = [
            PartialSignature.model_validate_json(response.content)
            for response in responses
        ]
        signature = combine_partial_signatures(partial_signatures)
        token = Token(payload=recipient_payload, signature=signature)
        async with self._client.post(
            f"{recipient_address}/pay", json=token.model_dump_json()
        ) as response:
            if response.status_code != httpx.codes.OK:
                self._logger.error(
                    f"{self._id} failed to send payment to {recipient_address}"
                )
                raise ValueError()
            self._logger.info(
                f"{self._id} payment sent successfully to {recipient_address}"
            )

    async def receive_payment(self, token: Token) -> None:
        if not verify_signature(
            token.payload, token.signature, self._system_public_key
        ):
            self._logger.error(f"{self._id} invalid token signature")
            raise ValueError()

        mint_request = MintRequest.model_validate_json(token.payload)
        if mint_request.public_key not in self._pending_keys:
            self._logger.error(f"{self._id} no pending key for this payment")
            raise ValueError()

        sk = self._pending_keys.pop(mint_request.public_key)
        self._tokens.append(ClientToken(token=token, secret_key=sk))
