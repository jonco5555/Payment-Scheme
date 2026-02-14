from fastapi import FastAPI

from payment.models import SignedMintRequest
from payment.server.server import Server


def create_app(server: Server) -> FastAPI:
    app = FastAPI()

    @app.post("/mint")
    async def mint(request: SignedMintRequest):
        return await server.handle_mint(request)

    return app
