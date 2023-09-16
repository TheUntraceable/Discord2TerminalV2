import asyncio
import json
from logging import getLogger, FileHandler, Formatter
from rpc_client import Client

logger = getLogger("rpc.client")

handler = FileHandler(filename="rpc.log", encoding="utf-8", mode="w")
handler.setFormatter(Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s"))
logger.addHandler(handler)
logger.setLevel(-100)


with open("config.json", "r") as f:
    config = json.load(f)

client = Client(config)


async def prompt():
    while True:
        message = input("> ")


@client.event("MESSAGE_CREATE")
async def on_message(data):
    message = data["message"]
    message["channel_id"] = data["channel_id"]
    await client.messages.insert_one({
        "message": message,
        "deleted": False,
        "edits": [],
    })


@client.event("MESSAGE_UPDATE")
async def on_message_update(data):
    message = data["message"]
    message["channel_id"] = data["channel_id"]
    stored_message = await client.messages.find_one({
        "message.id": message["id"],
    })
    if not stored_message:
        return

    await client.messages.update_one({
        "message.id": message["id"],
    }, {
        "$push": {
            "edits": message,
        }
    })


@client.event("MESSAGE_DELETE")
async def on_message_delete(data):
    await client.messages.update_one({
        "message.id": data["message"]["id"],
    }, {
        "$set": {
            "deleted": True,
        }
    })


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
            await client.subscribe(
                "MESSAGE_CREATE", {"channel_id": partial_channel["id"]}
            )
            await client.subscribe(
                "MESSAGE_UPDATE", {"channel_id": partial_channel["id"]}
            )
            await client.subscribe(
                "MESSAGE_DELETE", {"channel_id": partial_channel["id"]}
            )
    asyncio.create_task(prompt())


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.run_forever()
