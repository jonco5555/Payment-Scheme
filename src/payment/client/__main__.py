import uvicorn

from payment.client.app import create_app
from payment.client.client import Client
from payment.crypto.models import G1_Point


async def main(
    id: str, system_public_key: G1_Point, servers: list[str], f: int, port: int
) -> None:
    client = Client(
        id=id,
        system_public_key=system_public_key,
        servers=servers,
        f=f,
    )
    fastapi_app = create_app(client)
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=port)
    client_server = uvicorn.Server(config)
    await client.start()
    await client_server.serve()
    # await wait_for_signal()
    await client.stop()


async def interactive_main(
    id: str, system_public_key: G1_Point, servers: list[str], f: int
) -> None:
    client = Client(
        id=id,
        system_public_key=system_public_key,
        servers=servers,
        f=f,
    )
    # fastapi_app = create_app(client)
    # config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=port)
    # client_server = uvicorn.Server(config)

    await client.start()
    await client.mint_request()
    await client.pay_request("0", "http://localhost:9000")
    await client.stop()
