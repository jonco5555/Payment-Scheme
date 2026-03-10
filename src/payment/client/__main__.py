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
    demo_enabled: bool = False,
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
        demo_enabled=demo_enabled,
    )
    fastapi_app = create_app(client)
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=port)
    client_server = uvicorn.Server(config)
    await client.start()
    await client_server.serve()
    await client.stop()
