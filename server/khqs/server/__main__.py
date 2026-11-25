import asyncio
import logging
import signal

from .runner import serve
from .settings import Settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings = Settings.from_env()

    async def run():
        task = asyncio.create_task(serve(settings))
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, task.cancel)
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())


if __name__ == "__main__":
    main()
