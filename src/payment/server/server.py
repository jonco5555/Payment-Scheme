import logging

from payment.crypto.models import KeyShare, PartialSignature
from payment.crypto.shares import partial_sign, verify_signature
from payment.models import ClientEntry, MintRequest, SignedMintRequest

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


class Server:
    def __init__(
        self,
        key_share: KeyShare,
        clients: dict[str, ClientEntry],
    ) -> None:
        self._logger = logging.getLogger(__name__)
        self._key_share = key_share
        self._clients = clients

    async def handle_mint(self, request: SignedMintRequest) -> PartialSignature:
        mint_request = MintRequest.model_validate_json(request.payload)
        if mint_request.id not in self._clients:
            raise ValueError(f"Unknown client: {mint_request.id}")

        if (
            mint_request.public_key
            in self._clients[mint_request.id].public_key_nullifiers
        ):
            raise ValueError(
                f"Public key already used for {mint_request.id}: {mint_request.public_key}"
            )

        if self._clients[mint_request.id].balance < 1:
            raise ValueError(f"Insufficient balance for {mint_request.id}")

        if not verify_signature(
            request.payload,
            request.signature,
            self._clients[mint_request.id].public_key,
        ):
            raise ValueError("Invalid signature")

        self._clients[mint_request.id].balance -= 1
        self._clients[mint_request.id].public_key_nullifiers.add(
            mint_request.public_key
        )
        return partial_sign(request.payload, self._key_share)
