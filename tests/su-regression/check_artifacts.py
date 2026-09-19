#!/usr/bin/env python3
"""Check the native build produced each requested ABI; no runtime claims."""
import hashlib
import json
from pathlib import Path
import struct
import sys

root, report = map(Path, sys.argv[1:])
expected = {"arm64-v8a": (2, 183), "armeabi-v7a": (1, 40), "x86": (1, 3), "x86_64": (2, 62)}
rows = []
for abi, (elf_class, machine) in expected.items():
    path = root / abi / "magisk"
    data = path.read_bytes()
    assert data[:4] == b"\x7fELF", str(path)
    assert data[4] == elf_class and data[5] == 1, str(path)
    assert struct.unpack_from("<H", data, 18)[0] == machine, str(path)
    rows.append(dict(abi=abi, size=len(data), sha256=hashlib.sha256(data).hexdigest(), path=str(path)))
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text(json.dumps(rows, indent=2) + "\n")
print(report.read_text())
