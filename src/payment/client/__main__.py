import signal

import uvicorn

from payment.client.app import create_app
from payment.client.client import Client
from payment.crypto.models import G1_Point
from payment.utils import configure_logging


def handler(sig, frame):
    print(f"Received signal: {sig!s}", flush=True)


async def main(
    id: str,
    system_public_key: G1_Point,
    servers: list[str],
    f: int,
    port: int,
    initial_balance: int,
    timeout: float,
) -> None:
    configure_logging()
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    client = Client(
        id=id,
        system_public_key=system_public_key,
        servers=servers,
        f=f,
        initial_balance=initial_balance,
        timeout=timeout,
    )
    fastapi_app = create_app(client)
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=port)
    client_server = uvicorn.Server(config)
    await client.start()
    await client_server.serve()
    await client.stop()


async def interactive_main(
    id: str,
    system_public_key: G1_Point,
    servers: list[str],
    f: int,
    initial_balance: int,
) -> None:
    configure_logging()
    client = Client(
        id=id,
        system_public_key=system_public_key,
        servers=servers,
        f=f,
        initial_balance=initial_balance,
    )
    # fastapi_app = create_app(client)
    # config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=port)
    # client_server = uvicorn.Server(config)

    await client.start()
    await client.mint_request()
    await client.pay_request("0", "http://localhost:9000")
    await client.stop()
