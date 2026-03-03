from fastapi import FastAPI

from payment.crypto.models import PartialSignature
from payment.models import (
    RegistrationRequest,
    SignedMintRequest,
    SignedTransaction,
    UnregistrationRequest,
)
from payment.server.server import Server


def create_app(server: Server) -> FastAPI:
    app = FastAPI()

    @app.post("/register")
    async def register(request: RegistrationRequest):
        return await server.handle_register(request)

    @app.post("/unregister")
    async def unregister(request: UnregistrationRequest):
        return await server.handle_unregister(request)

    @app.post("/mint", response_model=PartialSignature)
    async def mint(request: SignedMintRequest):
        return await server.handle_mint(request)

    @app.post("/pay", response_model=PartialSignature)
    async def pay(request: SignedTransaction):
        return await server.handle_pay(request)

    return app
