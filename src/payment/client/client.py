import asyncio
import logging

import httpx

from payment.client.models import ClientToken
from payment.crypto.models import G1_Point, PartialSignature
from payment.crypto.shares import (
    blind_point,
    combine_partial_signatures,
    create_fresh_key_pair,
    sign_message,
    unblind_signature,
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
        self,
        id: str,
        system_public_key: G1_Point,
        servers: list[str],
        f: int,
        initial_balance: int,
    ) -> None:
        """Initialize a payment client.

        Generates a fresh key pair on creation.

        Args:
            id: Unique client identifier.
            system_public_key: System-wide BLS public key for verifying tokens.
            servers: List of server base URLs.
            f: Max number of faulty servers (threshold = f + 1).
            initial_balance: Starting balance for minting tokens.
        """
        self._logger = logging.getLogger(__name__)
        self._id = id
        self._system_public_key = system_public_key
        self._public_key, self._private_key = create_fresh_key_pair()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(None, connect=5.0))
        self._server_urls = servers
        self._tokens: list[ClientToken] = []
        self._pending_keys: dict[G1_Point, tuple[int, int]] = {}
        self._threshold = f + 1
        self._balance = initial_balance

    async def start(self) -> None:
        await self.register()

    async def stop(self) -> None:
        await self.unregister()
        await self._client.aclose()

    async def _broadcast(
        self,
        endpoint: str,
        data: dict | str,
    ) -> list[httpx.Response]:
        """Send a request to all servers and collect a quorum of successful responses.

        Returns as soon as f+1 servers have replied with HTTP 200,
        cancelling any still-pending requests.

        Args:
            endpoint: Server API endpoint to call.
            data: JSON-serializable request body.

        Returns:
            List of at least f+1 successful responses.

        Raises:
            RuntimeError: If a quorum cannot be reached.
        """

        tasks = [
            asyncio.create_task(self._client.post(f"{url}/{endpoint}", json=data))
            for url in self._server_urls
        ]

        successes: list[httpx.Response] = []
        pending = set(tasks)

        while pending:
            done, pending = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                try:
                    response = task.result()
                    if response.status_code == httpx.codes.OK:
                        successes.append(response)
                    else:
                        self._logger.warning(
                            f"{self._id} {endpoint}: server returned {response.status_code}"
                        )
                except Exception as e:
                    self._logger.warning(
                        f"{self._id} {endpoint}: server request failed: {e}"
                    )

            if len(successes) >= self._threshold:
                break  # enough responses

            if len(successes) + len(pending) < self._threshold:
                break  # won't get enough valid responses

        for task in pending:
            task.cancel()  # cancel any still-pending requests (may be omission errors)

        if len(successes) < self._threshold:
            raise RuntimeError(
                f"{self._id} {endpoint}: got {len(successes)} successful responses, need at least {self._threshold}"
            )

        return successes

    async def register(self) -> None:
        """Broadcast a registration request to all servers."""

        self._logger.info(f"{self._id} registering")

        request = RegistrationRequest(id=self._id, public_key=self._public_key)
        await self._broadcast("register", request.model_dump(mode="json"))

        self._logger.info(f"{self._id} registered successfully")

    async def unregister(self) -> None:
        """Broadcast an unregistration request to all servers."""

        self._logger.info(f"{self._id} unregistering")

        request = UnregistrationRequest(id=self._id)
        await self._broadcast("unregister", request.model_dump(mode="json"))

        self._logger.info(f"{self._id} unregistered successfully")

    def generate_payment_key(self) -> G1_Point:
        """Create a one-time key pair for receiving a payment.

        The secret key is stored internally; the public key is returned
        so it can be shared with the payer.

        Returns:
            Public key to give to the sender.
        """

        pk, sk = create_fresh_key_pair()
        pk, r = blind_point(pk)
        self._pending_keys[pk] = (sk, r)
        return pk

    async def mint_request(self) -> None:
        """Mint a new token by collecting partial signatures from servers.

        Raises:
            ValueError: If balance is insufficient.
        """

        self._logger.info(f"{self._id} issuing a mint request")

        if self._balance < 1:
            raise ValueError(f"{self._id} insufficient balance")

        sk, payload, signed_mint_request, blinding_factor = await self._prepare_mint()

        responses = await self._broadcast(
            "mint", signed_mint_request.model_dump(mode="json")
        )

        self._balance -= 1
        await self._process_mint_responses(sk, payload, responses, blinding_factor)

        self._logger.info(f"{self._id} mint request completed")

    async def pay_request(self, recipient_id: str, recipient_address: str) -> None:
        """Send a token to another client, re-minting it under their key.

        Fetches a one-time payment key from the recipient, then broadcasts
        the transaction to servers for threshold signing.

        Args:
            recipient_id: The recipient's client identifier.
            recipient_address: Base URL of the recipient's HTTP server.

        Raises:
            ValueError: If no tokens are available or recipient is unreachable.
        """

        self._logger.info(f"{self._id} issuing a pay request to {recipient_id}")

        key_response = await self._client.post(f"{recipient_address}/payment-key")
        if key_response.status_code != httpx.codes.OK:
            raise ValueError(
                f"{self._id} failed to get payment key from {recipient_address}"
            )

        recipient_public_key = G1_Point.model_validate_json(key_response.content)
        self._logger.info(f"{self._id} received payment key from {recipient_address}")

        client_token, recipient_payload, signed_tx = await self._prepare_pay(
            recipient_id, recipient_public_key
        )

        try:
            responses = await self._broadcast("pay", signed_tx.model_dump(mode="json"))
        except RuntimeError:
            self._tokens.insert(0, client_token)
            raise

        await self._process_pay_responses(
            recipient_payload, recipient_address, responses
        )

        self._logger.info(f"{self._id} pay request to {recipient_id} completed")

    async def _prepare_mint(self) -> tuple[int, bytes, SignedMintRequest, int]:
        """Build and sign a mint request with a fresh key pair.

        Returns:
            Tuple of (secret_key, raw_payload, signed_request, blinding_factor).
        """

        pk, sk = create_fresh_key_pair()
        pk, r = blind_point(pk)
        mint_request = MintRequest(id=self._id, public_key=pk)
        payload = mint_request.model_dump_json().encode()
        signature = sign_message(payload, self._private_key)
        signed_mint_request = SignedMintRequest(payload=payload, signature=signature)
        return sk, payload, signed_mint_request, r

    async def _process_mint_responses(
        self,
        sk: int,
        payload: bytes,
        responses: list[httpx.Response],
        blinding_factor: int,
    ) -> None:
        """Combine server partial signatures into a token and store it.

        Args:
            sk: Secret key corresponding to the token's public key.
            payload: Raw mint request payload that was signed.
            responses: Successful HTTP responses containing partial signatures.
            blinding_factor: Blinding factor used to blind the public key.
        """

        partial_signatures = [
            PartialSignature.model_validate_json(response.content)
            for response in responses
        ]
        signature = combine_partial_signatures(partial_signatures)
        signature = unblind_signature(signature, blinding_factor)
        self._tokens.append(
            ClientToken(
                token=Token(payload=payload, signature=signature), secret_key=sk
            )
        )

    async def _prepare_pay(
        self, recipient_id: str, recipient_public_key: G1_Point
    ) -> tuple[ClientToken, bytes, SignedTransaction]:
        """Build and sign a pay transaction using the oldest available token.

        Args:
            recipient_id: Recipient's client identifier.
            recipient_public_key: One-time public key provided by the recipient.

        Returns:
            Tuple of (spent_token, recipient_payload, signed_transaction).

        Raises:
            ValueError: If there are no tokens to spend.
        """

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

    async def _process_pay_responses(
        self,
        recipient_payload: bytes,
        recipient_address: str,
        responses: list[httpx.Response],
    ) -> None:
        """Combine partial signatures into a new token and deliver it to the recipient.

        Args:
            recipient_payload: Serialized mint request for the recipient.
            recipient_address: Base URL of the recipient's HTTP server.
            responses: Successful HTTP responses containing partial signatures.

        Raises:
            ValueError: If the recipient rejects the payment.
        """

        partial_signatures = [
            PartialSignature.model_validate_json(response.content)
            for response in responses
        ]
        signature = combine_partial_signatures(partial_signatures)
        token = Token(payload=recipient_payload, signature=signature)
        response = await self._client.post(
            f"{recipient_address}/pay", json=token.model_dump(mode="json")
        )
        if response.status_code != httpx.codes.OK:
            raise ValueError(
                f"{self._id} failed to send payment to {recipient_address}"
            )
        self._logger.info(
            f"{self._id} payment sent successfully to {recipient_address}"
        )

    async def receive_payment(self, token: Token) -> None:
        """Verify and accept an incoming payment token.

        Checks the system signature and matches the token's public key
        against a pending one-time key issued by `generate_payment_key`.

        Args:
            token: The payment token to accept.

        Raises:
            ValueError: If the signature is invalid or the key is unknown.
        """

        if not verify_signature(
            token.payload, token.signature, self._system_public_key
        ):
            raise ValueError(f"{self._id} invalid token signature")

        mint_request = MintRequest.model_validate_json(token.payload)
        if mint_request.public_key not in self._pending_keys:
            raise ValueError(f"{self._id} no pending key for this payment")

        sk, r = self._pending_keys.pop(mint_request.public_key)
        token = Token(
            payload=token.payload, signature=unblind_signature(token.signature, r)
        )
        self._tokens.append(ClientToken(token=token, secret_key=sk))
