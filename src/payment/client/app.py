from fastapi import FastAPI
from pydantic import BaseModel

from payment.client.client import Client
from payment.crypto.models import G2_Point
from payment.models import Payment


def create_app(client: Client) -> FastAPI:
    app = FastAPI()

    @app.get("/payment-key", response_model=G2_Point)
    async def payment_key():
        return client.generate_payment_key()

    @app.post("/pay")
    async def pay(payment: Payment):
        return await client.receive_payment(payment)

    # These endpoints are for demo only, to control a running client from the outside.
    # Ideally, these endpoints are only exposed as a package-internal API
    if client._demo_enabled:

        class PayRequest(BaseModel):
            recipient_id: str
            recipient_address: str

        @app.post("/demo/mint")
        async def mint():
            await client.mint_request()
            return {"status": "ok"}

        @app.post("/demo/pay")
        async def pay(request: PayRequest):
            await client.pay_request(
                recipient_id=request.recipient_id,
                recipient_address=request.recipient_address,
            )
            return {"status": "ok"}

    return app
