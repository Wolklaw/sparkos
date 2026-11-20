"""Frames and messages (docs/spark-link-protocol.md, Connection): a 4-byte big-endian length,
then up to 1 MiB of UTF-8 JSON, or of raw bytes for the one binary frame that follows each
file.chunk."""

import asyncio
import json
import struct
from typing import Any, Dict, Optional

from . import MAX_CHUNK, MAX_FRAME


class ProtocolError(Exception):
    """The other side broke the framing or sent something that isn't a message: close."""


def pack(payload: bytes) -> bytes:
    if len(payload) > MAX_FRAME:
        raise ProtocolError(f'frame of {len(payload)} bytes is over the limit')
    return struct.pack('>I', len(payload)) + payload


def encode(msg: Dict[str, Any]) -> bytes:
    return json.dumps(msg, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def decode(payload: bytes) -> Dict[str, Any]:
    try:
        msg = json.loads(payload.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ProtocolError(f'not JSON: {exc}') from None
    if not isinstance(msg, dict) or not isinstance(msg.get('type'), str):
        raise ProtocolError('not a message object')
    return msg


async def read_frame(reader: asyncio.StreamReader) -> bytes:
    head = await reader.readexactly(4)
    (length,) = struct.unpack('>I', head)
    if length > MAX_FRAME:
        raise ProtocolError(f'frame of {length} bytes is over the limit')
    return await reader.readexactly(length) if length else b''


class Link:
    """One TLS connection: numbered messages out (writes never interleave), and messages in,
    with a file.chunk's binary frame attached to it as msg['_data']."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader, self.writer = reader, writer
        self.next_id = 0
        self.lock = asyncio.Lock()
        self.closed = False

    def new_id(self) -> int:
        """The next message id; take one ahead of send() when the reply must find its record."""
        mid = self.next_id
        self.next_id += 1
        return mid

    async def send(self, msg: Dict[str, Any], binary: Optional[bytes] = None) -> int:
        if 'id' not in msg:
            msg = dict(msg, id=self.new_id())
        async with self.lock:
            data = pack(encode(msg))
            if binary is not None:
                data += pack(binary)
            self.writer.write(data)
            await self.writer.drain()
            return msg['id']

    async def recv(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        msg = decode(await asyncio.wait_for(read_frame(self.reader), timeout))
        if msg['type'] == 'file.chunk':
            data = await asyncio.wait_for(read_frame(self.reader), timeout)
            if len(data) > MAX_CHUNK:
                raise ProtocolError(f'file chunk of {len(data)} bytes is over the limit')
            msg['_data'] = data
        return msg

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.writer.close()
            await asyncio.wait_for(self.writer.wait_closed(), 2.0)
        except (OSError, asyncio.TimeoutError, ConnectionError, RuntimeError):
            pass
        except Exception:                         # ssl errors while closing don't matter
            pass
