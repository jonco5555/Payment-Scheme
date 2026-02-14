from pydantic import BaseModel

from payment.crypto.models import G1_Point


class ClientEntry(BaseModel):
    balance: int
    public_key: G1_Point
    public_key_nullifiers: set[G1_Point]
    token_nullifiers: set[G1_Point]
