import uvicorn

from payment.crypto.models import KeyShare
from payment.server.app import create_app
from payment.server.server import Server


async def main(
    key_share: KeyShare,
    num_clients: int,
    initial_balance: int,
    port: int,
) -> None:
    server = Server(
        key_share=key_share,
        num_clients=num_clients,
        initial_balance=initial_balance,
    )
    fastapi_app = create_app(server)
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    await server.serve()
