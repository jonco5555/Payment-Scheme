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


class Transaction(BaseModel):
    token: Token
    recipient_payload: bytes  # MintRequest


class SignedTransaction(BaseModel):
    payload: bytes  # Transaction
    signature: G2_Point


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


class ServerConfig(BaseModel):
    id: int
    address: str


class Config(BaseModel):
    system: SystemConfig
    servers: list[ServerConfig]
