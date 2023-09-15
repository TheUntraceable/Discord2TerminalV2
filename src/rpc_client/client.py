import asyncio
import os
from typing import Optional
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


class Client:
    def __init__(self, client_id: int):
        self.client_id = client_id
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    async def read_output(self):
        if not self._reader:
            raise RuntimeError("Not connected to IPC")
        preamble = await self._reader.read(8)
        _, length = struct.unpack("<II", preamble[:8])
        data = await self._reader.read(length)
        payload = json.loads(data.decode("utf-8"))
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
            OpCode.HANDSHAKE, {"v": 1, "client_id": str(self.client_id)}
        )
        data = await self.read_output()
        print(data)
