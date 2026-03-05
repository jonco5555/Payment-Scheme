from typing import Optional

from pydantic import BaseModel, ConfigDict

from payment.crypto.models import G1_Point, G2_Point


class TokenPayload(BaseModel):
    public_key: G1_Point


class MintRequest(BaseModel):
    id: str
    blinded_message: G2_Point  # The blinded hash of the TokenPayload


class SignedMintRequest(BaseModel):
    payload: bytes  # MintRequest
    signature: G2_Point


class Token(BaseModel):
    model_config = ConfigDict(frozen=True)

    payload: bytes  # MintRequest
    signature: G2_Point


class Transaction(BaseModel):
    token: Token
    recipient_blinded_payload: G2_Point  # Blinded TokenPayload


class SignedTransaction(BaseModel):
    payload: bytes  # Transaction
    signature: G2_Point


class Payment(BaseModel):
    blinded_payload: G2_Point
    blinded_signature: G2_Point


class RegistrationRequest(BaseModel):
    id: str
    public_key: G1_Point


class UnregistrationRequest(BaseModel):
    id: str


class SystemConfig(BaseModel):
    public_key_path: str
    servers: int
    failures: int
    clients: int
    initial_balance: int
    delta: float
    demo_enabled: Optional[bool] = False


class ServerConfig(BaseModel):
    id: int
    address: str


class Config(BaseModel):
    system: SystemConfig
    servers: list[ServerConfig]
