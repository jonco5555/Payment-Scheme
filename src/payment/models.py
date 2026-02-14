from pydantic import BaseModel

from payment.crypto.models import G1_Point, G2_Point


class MintRequest(BaseModel):
    id: str
    public_key: G1_Point


class SignedMintRequest(BaseModel):
    payload: bytes  # MintRequest
    signature: G2_Point


class Token(BaseModel):
    payload: bytes  # MintRequest
    signature: G2_Point
