from contextlib import suppress

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

SYSTEM_TASK_SCHEDULER_LOCK_KEY = 817263542


class SchedulerLeaderLease:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._connection: AsyncConnection | None = None

    async def try_acquire(self) -> bool:
        if self._connection is not None:
            try:
                await self._connection.execute(text("SELECT 1"))
                return True
            except Exception:
                await self._close_connection()

        connection = await self._engine.connect()
        try:
            acquired = bool(
                await connection.scalar(
                    text("SELECT pg_try_advisory_lock(:lock_key)"),
                    {"lock_key": SYSTEM_TASK_SCHEDULER_LOCK_KEY},
                )
            )
            if acquired:
                self._connection = connection
                return True
        except BaseException:
            await connection.close()
            raise
        await connection.close()
        return False

    async def release(self) -> None:
        if self._connection is None:
            return
        connection, self._connection = self._connection, None
        try:
            await connection.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": SYSTEM_TASK_SCHEDULER_LOCK_KEY},
            )
        finally:
            await connection.close()

    async def _close_connection(self) -> None:
        if self._connection is None:
            return
        connection, self._connection = self._connection, None
        with suppress(Exception):
            await connection.close()
