import asyncio
import os
from typing import Annotated

import typer

from payment.crypto.models import G1_Point, KeyShare
from payment.crypto.shares import generate_shares_to_files
from payment.utils import load_config

app = typer.Typer()


@app.command()
def setup(
    config_path: Annotated[str, typer.Option(envvar="CONFIG_PATH")],
) -> None:
    config = load_config(config_path)
    shares_dir = os.path.dirname(config_path)
    generate_shares_to_files(
        n=config.system.servers,
        f=config.system.failures,
        shares_dir=shares_dir,
    )
    typer.echo(f"Generated {config.system.servers} key shares in {shares_dir}/")


@app.command()
def client(
    id: Annotated[str, typer.Option(envvar="CLIENT_ID")],
    config_path: Annotated[str, typer.Option(envvar="CONFIG_PATH")],
    port: Annotated[int, typer.Option(envvar="PORT")],
) -> None:
    from payment.client.__main__ import main

    config = load_config(config_path)

    with open(config.system.public_key_path, "rb") as f:
        system_public_key = G1_Point.model_validate_json(f.read())

    servers = [server.address for server in config.servers]
    asyncio.run(
        main(
            id=id,
            system_public_key=system_public_key,
            servers=servers,
            f=config.system.failures,
            port=port,
            initial_balance=config.system.initial_balance,
            timeout=2 * config.system.delta,
            demo_enabled=config.system.demo_enabled,
        )
    )


@app.command()
def server(
    id: Annotated[str, typer.Option(envvar="SERVER_ID")],
    config_path: Annotated[str, typer.Option(envvar="CONFIG_PATH")],
    key_share_path: Annotated[str, typer.Option(envvar="KEY_SHARE_PATH")],
) -> None:
    from payment.server.__main__ import main

    config = load_config(config_path)

    with open(key_share_path, "rb") as f:
        key_share = KeyShare.model_validate_json(f.read())

    num_clients = config.system.clients
    initial_balance = config.system.initial_balance
    port = int(
        next(server for server in config.servers if server.id == id).address.split(":")[
            -1
        ]
    )
    asyncio.run(
        main(
            id=id,
            key_share=key_share,
            num_clients=num_clients,
            initial_balance=initial_balance,
            port=port,
        )
    )


if __name__ == "__main__":
    app()
