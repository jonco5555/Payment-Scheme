from payment.client.client import Client
from payment.crypto.models import G1_Point
from payment.utils import wait_for_signal


async def main(id: str, system_public_key: G1_Point, servers: list[str]) -> None:
    client = Client(
        id=id,
        system_public_key=system_public_key,
        servers=servers,
    )

    await client.start()
    await wait_for_signal()
    await client.stop()
