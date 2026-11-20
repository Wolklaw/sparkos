"""What Spark Run downloads, from whom, and the SHA-256 each file must have.

Nothing here is fetched unless someone runs a Windows program (Wine, Wine Mono) or turns DXVK
on for one app. A file whose SHA-256 differs from the one written here is deleted, not used,
whatever the server says: the fingerprints below are the trust, reviewed in this repository.

To move to a newer Wine: build it first (files/spark-run/wine-build/build.sh: WINE_VERSION,
WINE_SHA256, BUILD; the wine-build workflow builds it twice and publishes the release), then
change the version, URL, size, SHA-256 and folder below together (compare the SHA-256 with the
release's sha256sums.txt and GitHub's asset digest), set MONO to the version that Wine's
dlls/appwiz.cpl/addons.c names in MONO_VERSION, and let CI run the test programs.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Download:
    key: str            # 'wine', 'mono', 'dxvk'
    name: str           # for people: "Wine 11.22"
    version: str
    url: str
    sha256: str
    size: int           # bytes, to show before downloading and to stop a runaway download
    whose: str          # who builds it, said plainly before downloading
    page: str           # where to read about it
    folder: str         # top folder inside the archive

    @property
    def filename(self) -> str:
        return self.url.rsplit('/', 1)[-1]


# Vanilla Wine (the WineHQ source, no patches), built by SparkOS itself: this repository's
# wine-build workflow builds it from WineHQ's signed source tarball in a pinned Fedora 45
# container, twice, and publishes it only if both builds are byte for byte the same. The "wow64"
# build runs 32-bit and 64-bit Windows programs without any 32-bit Linux libraries.
WINE = Download(
    key='wine',
    name="Wine 11.22",
    version="11.22",
    url="https://github.com/Wolklaw/sparkos/releases/download/wine-11.22-2/"
        "wine-11.22-2-amd64-wow64.tar.xz",
    sha256="f45dd527f528160c7d35ddb7bb3ebe402c65194c29d81bf60ef38eb81976007c",
    size=77024200,
    whose="WineHQ's source, built by SparkOS (github.com/Wolklaw/sparkos)",
    page="https://github.com/Wolklaw/sparkos/releases/tag/wine-11.22-2",
    folder="wine-11.22-2-amd64-wow64",
)

# Wine Mono: Wine's own .NET Framework replacement, from WineHQ. Unpacked once next to Wine and
# shared by every app, instead of a copy in each prefix. 11.3.0 is what Wine 11.22 asks for.
MONO = Download(
    key='mono',
    name="Wine Mono 11.3.0",
    version="11.3.0",
    url="https://dl.winehq.org/wine/wine-mono/11.3.0/wine-mono-11.3.0-x86.tar.xz",
    sha256="54a1b0111c3fe4b785eae688af94d27e64995707ad648b6fee8000381b80d298",
    size=39412620,
    whose="WineHQ (dl.winehq.org)",
    page="https://gitlab.winehq.org/wine/wine/-/wikis/Wine-Mono",
    folder="wine-mono-11.3.0",
)

# DXVK: Direct3D 9, 10 and 11 over Vulkan. Only fetched when someone turns it on for an app.
DXVK = Download(
    key='dxvk',
    name="DXVK 3.1.1",
    version="3.1.1",
    url="https://github.com/doitsujin/dxvk/releases/download/v3.1.1/dxvk-3.1.1.tar.gz",
    sha256="40565b4a724aadc4433fa4e010b4b23916d9b1f1baeee64e17186db94f54e608",
    size=18041512,
    whose="the DXVK project (github.com/doitsujin/dxvk)",
    page="https://github.com/doitsujin/dxvk/releases/tag/v3.1.1",
    folder="dxvk-3.1.1",
)

ALL = (WINE, MONO, DXVK)


def by_key(key: str) -> Optional[Download]:
    return next((d for d in ALL if d.key == key), None)
