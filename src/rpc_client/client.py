import asyncio
from collections import defaultdict
import os
from time import time
from typing import (
    DefaultDict,
    Dict,
    List,
    NotRequired,
    Optional,
    Callable,
    Coroutine,
    Any,
    TypedDict,
)
from logging import getLogger
import json
import aiohttp
import struct
from enum import IntEnum

from discord_typings import ApplicationData, UserData


logger = getLogger("rpc.client")


class OpCode(IntEnum):
    HANDSHAKE = 0
    FRAME = 1
    CLOSE = 2
    PING = 3
    PONG = 4


class AccessTokenData(TypedDict):
    access_token: str
    expires_at: int
    refresh_token: str


class Config(TypedDict):
    access_token: NotRequired[AccessTokenData]
    client_id: int
    client_secret: str
    client_token: str


class Client:
    def __init__(self, config: Config):
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._expected: Dict[str, asyncio.Future] = {}
        self.events: DefaultDict[
            str, List[Callable[..., Coroutine[Any, Any, Any]]]
        ] = defaultdict(list)
        self.config = config
        self.application: Optional[ApplicationData] = None
        self.user: Optional[UserData] = None
        self.access_token: Optional[str] = config.get("access_token", {}).get(
            "access_token"
        )

    def event(self, name: str):
        def decorator(func):
            self.events[name.lower()].append(func)
            logger.info(f"Registered event {name}")
            return func

        return decorator

    async def authorize(self):
        data = await self.command(
            "AUTHORIZE",
            {
                "client_id": str(self.config["client_id"]),
                "client_secret": self.config["client_secret"],
                "prompt": "none",
                "scopes": [
                    "rpc",
                    "messages.read",
                    "rpc.notifications.read",
                    "rpc.voice.read",
                    "identify",
                ],
            },
        )
        code = data["data"]["code"]

        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field("client_id", str(self.config["client_id"]))
            form.add_field("client_secret", self.config["client_secret"])
            form.add_field("grant_type", "authorization_code")
            form.add_field("code", code)
            form.add_field("redirect_uri", "https://discord.com")
            async with session.post(
                "https://discord.com/api/v10/oauth2/token", data=form
            ) as response:
                data = await response.json()
                if response.status != 200:
                    raise RuntimeError(data.get("message"))
                expires_at = int(time()) + data["expires_in"]
                self.config["access_token"] = {
                    "access_token": data["access_token"],
                    "expires_at": expires_at,
                    "refresh_token": data["refresh_token"],
                }
                with open("config.json", "w") as f:
                    json.dump(self.config, f, indent=4)
                logger.info(f"Wrote {self.config} to config.json")
                self.access_token = data["access_token"]
        await self.authenticate(data["access_token"])

    async def authenticate(self, access_token: str):
        data = await self.command("AUTHENTICATE", {"access_token": access_token})
        if data.get("evt") == "ERROR":
            raise RuntimeError(data.get("data").get("message"))
        self.application = data["data"]["application"]
        self.user = data["data"]["user"]
        logger.info(f"Authenticated as {self.user['username']}")

    def on_event(self, data):
        data = data[8:]
        payload = json.loads(data.decode("utf-8"))
        logger.debug(f"Received payload: {payload}")
        if payload.get("evt") == "DISPATCH":
            if self.events.get(payload["evt"].lower()):
                for func in self.events[payload["evt"].lower()]:
                    asyncio.create_task(func(payload["data"]))
        if self._expected.get(payload.get("nonce")):
            self._expected[payload["nonce"]].set_result(payload)
            del self._expected[payload["nonce"]]

    async def read_output(self):
        if not self._reader:
            raise RuntimeError("Not connected to IPC")
        preamble = await self._reader.read(8)
        _, length = struct.unpack("<II", preamble[:8])
        data = await self._reader.read(length)
        payload = json.loads(data.decode("utf-8"))

        if self.events.get(payload["evt"].lower()):
            for func in self.events[payload["evt"].lower()]:
                asyncio.create_task(func(payload["data"]))
        if self._expected.get(payload.get("nonce")):
            self._expected[payload["nonce"]].set_result(payload)
            del self._expected[payload["nonce"]]

        return payload

    async def send_data(self, op: int, payload):
        if not self._writer:
            raise RuntimeError("Not connected to IPC")
        payload = json.dumps(payload)
        self._writer.write(
            struct.pack("<II", op, len(payload)) + payload.encode("utf-8")
        )
        await self._writer.drain()
        logger.debug(f"Sent payload: {payload}")

    async def command(self, cmd: str, args: Dict[str, Any]):
        if not self._writer:
            raise RuntimeError("Not connected to IPC")
        nonce = os.urandom(32).hex()
        await self.send_data(OpCode.FRAME, {"cmd": cmd, "args": args, "nonce": nonce})
        future = asyncio.Future()
        self._expected[nonce] = future
        return await future

    def get_ipc_path(self, id: int):
        prefix = (
            os.environ.get("XDG_RUNTIME_DIR")
            or os.environ.get("TMPDIR")
            or os.environ.get("TMP")
            or os.environ.get("TEMP")
            or "/tmp"
        )
        return f"{prefix.rstrip('/')}/discord-ipc-{id}"

    async def connect(self):
        for i in range(10):
            path = self.get_ipc_path(i)
            try:
                self._reader, self._writer = await asyncio.open_unix_connection(path)
            except (FileNotFoundError, ConnectionRefusedError):
                continue
            else:
                break
        if not self._writer or not self._reader:
            raise ConnectionError("Failed to connect to IPC")
        await self.handshake()

    async def subscribe(self, event_name: str, args: Dict[str, Any]):
        nonce = os.urandom(32).hex()
        await self.send_data(
            OpCode.FRAME,
            {
                "cmd": "SUBSCRIBE",
                "args": args,
                "evt": event_name.upper(),
                "nonce": nonce,
            },
        )
        # Not using self.command because we won't be able to specify the evt key
        # because it is top level, not in the args dict
        future = asyncio.Future()
        self._expected[nonce] = future
        data = await future

        # Yes we could just read_output but that risks a clash with another event being
        # sent at the same time and unlike some people I don't take stupid risks
        # that could ruin the entire application
        logger.debug(f"Subscribed to {event_name} with args {args}. Response: {data}")

    async def handshake(self):
        if not self._writer or not self._reader:
            raise RuntimeError("Not connected to IPC")

        await self.send_data(
            OpCode.HANDSHAKE, {"v": 1, "client_id": str(self.config["client_id"])}
        )
        data = await self.read_output()
        if data.get("message") == "Invalid Client ID":
            raise RuntimeError("Invalid client ID")

        self._reader.feed_data = self.on_event
