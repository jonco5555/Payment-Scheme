from fastapi import FastAPI

from payment.client.client import Client
from payment.crypto.models import G1_Point
from payment.models import Token


def create_app(client: Client) -> FastAPI:
    app = FastAPI()

    @app.post("/payment-key", response_model=G1_Point)
    async def payment_key():
        return client.generate_payment_key()

    @app.post("/pay")
    async def pay(token: Token):
        return await client.receive_payment(token)

    return app
