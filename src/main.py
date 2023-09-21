import asyncio
import json
from logging import getLogger, FileHandler, Formatter
from typing import Any
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from rpc_client import Client

logger = getLogger("rpc.client")

handler = FileHandler(filename="rpc.log", encoding="utf-8", mode="w")
handler.setFormatter(Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s"))
logger.addHandler(handler)
logger.setLevel(-100)


with open("config.json", "r") as f:
    config = json.load(f)

client = Client(config)
messages: dict[str, Any] = {}


@client.event("MESSAGE_CREATE")
async def on_message(data):
    message = data["message"]
    message["channel_id"] = data["channel_id"]
    messages[message["id"]] = {
        "current_message": message,  # The current message
        "deleted": False,
        "edits": [],  # A list of edited messages
    }


@client.event("MESSAGE_UPDATE")
async def on_message_update(data):
    message = data["message"]
    message["channel_id"] = data["channel_id"]
    stored_message = messages.get(message["id"])

    if not stored_message:
        messages[message["id"]] = {
            "current_message": message,
            "deleted": False,
            "edits": [],
        }
        return

    stored_message["edits"].append(stored_message["current_message"])
    stored_message["current_message"] = message


@client.event("MESSAGE_DELETE")
async def on_message_delete(data):
    stored_message = messages.get(data['message']["id"])

    if not stored_message:
        return

    stored_message["deleted"] = True


async def get_commands():
    session = PromptSession("> ")
    while True:
        try:
            message = await session.prompt_async()
            print(message)
        except (EOFError, KeyboardInterrupt):
            break


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
    with patch_stdout():
        try:
            await get_commands()
        except (EOFError, KeyboardInterrupt):
            exit(0)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.run_forever()
