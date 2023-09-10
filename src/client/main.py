import asyncio
from ..rpc_client import Client

client = Client(9)


async def main():
    await client.connect()


if __name__ == "__main__":
    asyncio.run(main())
