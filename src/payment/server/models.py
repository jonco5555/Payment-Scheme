from pydantic import BaseModel, Field

from payment.crypto.models import G1_Point, G2_Point


class ClientEntry(BaseModel):
    balance: int
    public_key: G1_Point
    public_key_nullifiers: set[G2_Point] = Field(default_factory=set)
