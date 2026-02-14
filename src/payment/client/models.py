from pydantic import BaseModel

from payment.models import Token


class ClientToken(BaseModel):
    token: Token
    secret_key: int
