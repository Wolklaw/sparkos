"""Writes a Windows SYSTEM registry file whose MountedDevices maps drive letters to GPT partitions, for the sparkos-windows-drives
tests. Same layout Windows writes (the builder is Spark Welcome's test helper, files/spark-welcome/tests/test_spark_welcome.py).

    make_hive.py OUT LETTER=PARTUUID [LETTER=PARTUUID ...]
"""
import os
import struct
import sys
import uuid


def make_hive(path, key_path, values):
    cells = bytearray(b"hbin" + b"\0" * 28)

    def add(data):
        offset, size = len(cells), len(data) + 4
        size += (-size) % 8
        cells.extend(struct.pack("<i", -size) + data + b"\0" * (size - 4 - len(data)))
        return offset

    def nk(name, subkeys, value_list, n_values):
        raw = bytearray(0x4C)
        raw[0:2] = b"nk"
        struct.pack_into("<H", raw, 2, 0x20)
        struct.pack_into("<I", raw, 0x14, 1 if subkeys is not None else 0)
        struct.pack_into("<I", raw, 0x1C, subkeys if subkeys is not None else 0xFFFFFFFF)
        struct.pack_into("<I", raw, 0x24, n_values)
        struct.pack_into("<I", raw, 0x28, value_list if value_list is not None else 0xFFFFFFFF)
        struct.pack_into("<H", raw, 0x48, len(name))
        return add(bytes(raw) + name.encode("latin-1"))

    offsets = []
    for name, (vtype, data) in values.items():
        data_cell = add(data)
        offsets.append(add(b"vk" + struct.pack("<HIIIHH", len(name), len(data), data_cell, vtype, 1, 0) + name.encode("latin-1")))
    value_list = add(b"".join(struct.pack("<I", o) for o in offsets))
    parts = key_path.split("\\")
    child = nk(parts[-1], None, value_list, len(offsets))
    for name in reversed(["ROOT"] + parts[:-1]):
        sig = b"li" if len(name) % 2 else b"lh"
        entry = struct.pack("<I", child) + (b"" if sig == b"li" else b"\0" * 4)
        child = nk(name, add(sig + struct.pack("<H", 1) + entry), None, 0)
    header = bytearray(0x1000)
    header[0:4] = b"regf"
    struct.pack_into("<I", header, 0x24, child)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(bytes(header) + bytes(cells))


def mounted_devices(letters):
    """{'\\DosDevices\\C:': (REG_BINARY, b'DMIO:ID:' + GUID)} for {'C': partuuid}."""
    return {f"\\DosDevices\\{l.upper()}:": (3, b"DMIO:ID:" + uuid.UUID(g).bytes_le) for l, g in letters.items()}


if __name__ == "__main__":
    out, pairs = sys.argv[1], dict(a.split("=", 1) for a in sys.argv[2:])
    make_hive(out, "MountedDevices", mounted_devices(pairs))
