import asyncio
import logging

from payment.crypto.models import KeyShare, PartialSignature
from payment.crypto.shares import partial_sign, verify_signature
from payment.models import (
    MintRequest,
    RegistrationRequest,
    SignedMintRequest,
    SignedTransaction,
    Token,
    Transaction,
    UnregistrationRequest,
)
from payment.server.models import ClientEntry

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


class Server:
    def __init__(
        self,
        key_share: KeyShare,
        num_clients: int,
        initial_balance: int,
    ) -> None:
        self._logger = logging.getLogger(__name__)
        self._key_share = key_share
        self._id = self._key_share.id
        self._system_public_key = self._key_share.public_key
        self._num_clients = num_clients
        self._initial_balance = initial_balance
        self._clients: dict[str, ClientEntry] = {}
        self._token_nullifiers: set[Token] = set()
        self._all_registered = asyncio.Event()

    async def handle_register(self, request: RegistrationRequest) -> None:
        """Register a client and wait until all expected clients have joined.

        Args:
            request: Registration request with client id and public key.

        Raises:
            ValueError: If the client is already registered or max clients reached.
        """

        if request.id in self._clients:
            raise ValueError(f"Client already registered: {request.id}")
        if len(self._clients) >= self._num_clients:
            raise ValueError("Maximum number of clients reached")

        self._clients[request.id] = ClientEntry(
            balance=self._initial_balance, public_key=request.public_key
        )
        self._logger.info(
            f"Server {self._id} registered client {request.id} "
            f"({len(self._clients)}/{self._num_clients})"
        )

        if len(self._clients) == self._num_clients:
            self._all_registered.set()

        await self._all_registered.wait()

    async def handle_unregister(self, request: UnregistrationRequest) -> None:
        """Remove a client from the list of registered clients.

        Args:
            request: Unregistration request with client id.

        Raises:
            ValueError: If the client is not registered.
        """

        if request.id not in self._clients:
            raise ValueError(f"Client not registered: {request.id}")
        del self._clients[request.id]
        self._logger.info(
            f"Server {self._id} unregistered client {request.id} "
            f"({len(self._clients)} remaining)"
        )

    async def handle_mint(self, request: SignedMintRequest) -> PartialSignature:
        """Validate a mint request and return a partial signature on the payload.

        Checks client identity, balance, signature, and public-key uniqueness
        before issuing the partial signature.

        Args:
            request: Signed mint request from a client.

        Returns:
            Partial BLS signature on the mint payload.

        Raises:
            ValueError: If validation fails (unknown client, bad signature, etc.).
        """

        mint_request = MintRequest.model_validate_json(request.payload)
        if mint_request.id not in self._clients:
            raise ValueError(f"Unknown client: {mint_request.id}")

        client = self._clients[mint_request.id]

        self._logger.info(
            f"Server {self._id} handling mint request from {mint_request.id}"
        )

        if mint_request.public_key in client.public_key_nullifiers:
            raise ValueError(
                f"Public key already used for {mint_request.id}: {mint_request.public_key}"
            )

        if client.balance < 1:
            raise ValueError(f"Insufficient balance for {mint_request.id}")

        if not verify_signature(
            request.payload,
            request.signature,
            client.public_key,
        ):
            raise ValueError("Invalid signature")

        client.balance -= 1
        client.public_key_nullifiers.add(mint_request.public_key)
        return partial_sign(request.payload, self._key_share)

    async def handle_pay(self, request: SignedTransaction) -> PartialSignature:
        """Validate a pay transaction and return a partial signature for the recipient.

        Verifies the token signature, checks for double-spending, and verifies
        the transaction signature before issuing a partial signature on the
        recipient's mint payload.

        Args:
            request: Signed transaction from the paying client.

        Returns:
            Partial BLS signature on the recipient's mint payload.

        Raises:
            ValueError: If the token was already spent or signatures are invalid.
        """

        transaction = Transaction.model_validate_json(request.payload)
        mint_request = MintRequest.model_validate_json(transaction.token.payload)

        if mint_request.id not in self._clients:
            raise ValueError(f"Unknown client: {mint_request.id}")

        self._logger.info(
            f"Server {self._id} handling pay request from {mint_request.id}"
        )

        if transaction.token in self._token_nullifiers:
            raise ValueError(f"Token already used: {transaction.token}")

        if not verify_signature(
            transaction.token.payload,
            transaction.token.signature,
            self._system_public_key,
        ):
            raise ValueError("Invalid token signature")

        if not verify_signature(
            request.payload,
            request.signature,
            mint_request.public_key,
        ):
            raise ValueError("Invalid transaction signature")

        self._token_nullifiers.add(transaction.token)
        return partial_sign(transaction.recipient_payload, self._key_share)
