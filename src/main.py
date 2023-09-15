import asyncio
import json
from logging import getLogger, FileHandler, Formatter
from rpc_client import Client

logger = getLogger("rpc.client")

handler = FileHandler(filename="rpc.log", encoding="utf-8")
handler.setFormatter(Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s"))
logger.addHandler(handler)
logger.setLevel(-100)


with open("config.json", "r") as f:
    config = json.load(f)

client = Client(config)


async def main():
    await client.connect()
    if not client.access_token:
        await client.authorize()
    else:
        await client.authenticate(client.access_token)
    guilds = await client.get_guilds()
    for guild in guilds:
        guild = await client.get_guild(guild["id"])
        channels = await client.get_channels(guild["id"])
        for partial_channel in channels:
            channel = await client.get_channel(partial_channel["id"])
            print(channel)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.run_forever()
