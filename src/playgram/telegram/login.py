from __future__ import annotations

import asyncio

from playgram.telegram.client import build_client


async def _amain() -> None:
    client = build_client()
    await client.start()
    me = await client.get_me()
    print(f"Logged in as: {getattr(me, 'username', None) or getattr(me, 'first_name', None) or me.id}")
    await client.disconnect()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
