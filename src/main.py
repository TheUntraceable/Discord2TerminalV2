import asyncio
import json
from logging import getLogger, FileHandler, Formatter
from time import time
from typing import Any
import rich
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import FuzzyWordCompleter
from halo import Halo
from prompt_toolkit.patch_stdout import patch_stdout
from progressbar import ProgressBar, PercentageLabelBar, AdaptiveETA, Timer
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
    print_message([message])


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
    if stored_message := messages.get(data["message"]["id"]):
        stored_message["deleted"] = True
    else:
        return


async def get_commands(session: PromptSession):
    while True:
        try:
            message = await session.prompt_async()
            command, *args = message.split(" ")
            if command not in client.terminal_commands:
                print("Invalid command")
                continue
            await client.terminal_commands[command](*args)
        except (EOFError, KeyboardInterrupt):
            break


def print_message(messages: list):
    previous_author_id: int | None = None
    for message in messages:
        if previous_author_id != message["author"]["id"]:
            previous_author_id = message["author"]["id"]
            # formatted_text = f"[{hex_color}]{text}[/{hex_color}]"
            rich.print(
                f"[{message.get('author_color', '#99AAB5')}]{message['author']['username']}[/{message.get('author_color', '#99AAB5')}]: {message['content']}"
            )
        else:
            print(message["content"])


@client.terminal_command("echo")
async def echo(*args):
    print(" ".join(args))


async def main():
    await client.connect()
    if (
        not client.access_token
        or client.config.get("access_token", {}).get("expires_at", 0) < time()
    ):
        await client.authorize()
    else:
        await client.authenticate(client.access_token)

    fetch_guilds_spinner = Halo(text="Fetching guilds...", spinner="dots")
    fetching_channels_spinner = Halo(text="Fetching channels...", spinner="dots")
    fetched_channels = []

    fetch_guilds_spinner.start()
    guilds = await client.get_guilds()
    fetch_guilds_spinner.succeed(f"Fetched {len(guilds)} guilds")

    fetching_channels_spinner.start()
    for guild in guilds:
        channels = await client.get_channels(guild["id"])
        fetched_channels.extend(partial_channel["id"] for partial_channel in channels)
    fetching_channels_spinner.succeed(f"Fetched {len(fetched_channels)}")

    subscribing_bar = ProgressBar(
        widgets=[
            "Subscribing to events: ",
            PercentageLabelBar(),
            " ",
            AdaptiveETA(),
            " ",
            Timer(),
        ],
        max_value=len(fetched_channels),
    )
    for channel in fetched_channels:
        await client.subscribe("MESSAGE_CREATE", {"channel_id": channel})
        await client.subscribe("MESSAGE_UPDATE", {"channel_id": channel})
        await client.subscribe("MESSAGE_DELETE", {"channel_id": channel})
        subscribing_bar.update(subscribing_bar.value + 1)
    fetching_channels_spinner.succeed("Subscribed to all events!")

    word_completer = FuzzyWordCompleter(list(client.terminal_commands.keys()))
    session = PromptSession("> ", completer=word_completer, complete_while_typing=True)
    with patch_stdout(raw=True):
        try:
            await get_commands(session)
        except (EOFError, KeyboardInterrupt):
            exit(0)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.run_forever()
