import asyncio
from collections import defaultdict
import os
from typing import (
    DefaultDict,
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
import struct
from enum import IntEnum


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


class Config(TypedDict):
    access_token: NotRequired[AccessTokenData]
    client_id: int
    client_secret: str
    client_token: str


class Client:
    def __init__(self, config: Config):
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self.events: DefaultDict[
            str, List[Callable[..., Coroutine[Any, Any, Any]]]
        ] = defaultdict(list)
        self.config = config

    def event(self, name: str):
        def decorator(func):
            self.events[name.lower()].append(func)
            return func

        return decorator

    async def read_output(self):
        if not self._reader:
            raise RuntimeError("Not connected to IPC")
        preamble = await self._reader.read(8)
        _, length = struct.unpack("<II", preamble[:8])
        data = await self._reader.read(length)
        payload = json.loads(data.decode("utf-8"))
        print(payload)

        if self.events.get(payload["evt"].lower()):
            for func in self.events[payload["evt"].lower()]:
                asyncio.create_task(func(payload["data"]))

        return payload

    async def send_data(self, op: int, payload):
        if not self._writer:
            raise RuntimeError("Not connected to IPC")
        payload = json.dumps(payload)

        self._writer.write(
            struct.pack("<II", op, len(payload)) + payload.encode("utf-8")
        )
        await self._writer.drain()

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

    async def handshake(self):
        if not self._writer:
            raise RuntimeError("Not connected to IPC")

        await self.send_data(
            OpCode.HANDSHAKE, {"v": 1, "client_id": str(self.config["client_id"])}
        )
        data = await self.read_output()
        if data.get("message") == "Invalid Client ID":
            raise RuntimeError("Invalid client ID")
