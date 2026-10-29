import asyncio

import uvloop  # Comment it out if using on windows
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pyrogram import idle

from Powers import BDB_URI, TIME_ZONE
from Powers.bot_class import Gojo
from Powers.plugins.birthday import send_wishish
from Powers.plugins.clean_db import clean_my_db

scheduler = AsyncIOScheduler(timezone=TIME_ZONE)


def register_jobs(client):
    """Register the cron jobs against the already-started client."""
    scheduler.add_job(
        clean_my_db, "cron", [client], hour=3, minute=0, second=0,
        id="clean_my_db", replace_existing=True,
    )
    if BDB_URI:
        scheduler.add_job(
            send_wishish, "cron", [client], hour=0, minute=0, second=0,
            id="send_wishish", replace_existing=True,
        )


async def main():
    # The client MUST be constructed here, inside the coroutine that
    # asyncio.run() drives. Pyrogram captures the current event loop at
    # construction time (Client.loop) and its dispatcher spawns the
    # update/handler workers on that captured loop. Constructing Gojo()
    # at module level captured the import-time loop, which asyncio.run()
    # never drives — the bot started and connected, but no update was
    # ever dispatched. Jobs are registered against this same started
    # instance (previously they were registered after the blocking
    # Client.run() call, with fresh never-started clients, so they could
    # never fire either).
    app = Gojo()
    await app.start()
    register_jobs(app)
    scheduler.start()
    await idle()
    scheduler.shutdown(wait=False)
    await app.stop()


if __name__ == "__main__":
    uvloop.install()  # Comment it out if using on windows
    asyncio.run(main())
