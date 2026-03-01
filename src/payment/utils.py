import asyncio
import signal

import yaml

from payment.models import Config


def load_config(config_path: str) -> Config:
    with open(config_path) as f:
        return Config(**yaml.safe_load(f))


async def wait_for_signal(signals=(signal.SIGINT, signal.SIGTERM)):
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def handler(sig):
        print(f"Received signal: {sig!s}", flush=True)
        stop_event.set()

    # Register signal handlers
    for sig in signals:
        loop.add_signal_handler(sig, handler, sig)

    print("Running until a signal is received", flush=True)
    await stop_event.wait()
    print("Got a termination signal, cleaning up and exiting gracefully", flush=True)

    # Cleanup handlers
    for sig in signals:
        loop.remove_signal_handler(sig)
