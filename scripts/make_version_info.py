"""Write a PyInstaller version-info file from pyproject.toml's version.

Embedding a full VERSIONINFO resource (company, product, description,
version) makes the .exe look like an ordinary application in Explorer's
Properties dialog, and executables without one are a common heuristic
flag for antivirus scanners.

Usage: python scripts/make_version_info.py <output-path>
"""
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TEMPLATE = """\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={vtuple},
    prodvers={vtuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'arp-Trosh'),
        StringStruct('FileDescription', 'Pegs and Jokers'),
        StringStruct('FileVersion', '{vstr}'),
        StringStruct('InternalName', 'PegsAndJokers'),
        StringStruct('LegalCopyright', 'Copyright (c) arp-Trosh'),
        StringStruct('OriginalFilename', 'PegsAndJokers.exe'),
        StringStruct('ProductName', 'Pegs and Jokers'),
        StringStruct('ProductVersion', '{vstr}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def main() -> None:
    with open(ROOT / "pyproject.toml", "rb") as f:
        version = tomllib.load(f)["project"]["version"]
    parts = [int(p) for p in version.split(".")[:4]]
    parts += [0] * (4 - len(parts))
    vtuple = "(" + ", ".join(str(p) for p in parts) + ")"
    vstr = ".".join(str(p) for p in parts)
    Path(sys.argv[1]).write_text(TEMPLATE.format(vtuple=vtuple, vstr=vstr))
    print(f"Wrote version info {vstr} to {sys.argv[1]}")


if __name__ == "__main__":
    main()
