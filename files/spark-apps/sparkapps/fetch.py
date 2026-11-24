"""Downloads: HTTPS only, a timeout on every read, a total deadline and a size cap.

Plain urllib, no shell, no curl. Redirects (GitHub sends release assets to its CDN) are followed
only to https. A test can pass allow_http=True to talk to a server on localhost; nothing in the
command line, the environment or the files reads can switch that on.
"""

import hashlib
import time
import urllib.error
import urllib.request
from typing import BinaryIO, Optional

from . import HTTP_DEADLINE, HTTP_TIMEOUT, VERSION


class FetchError(Exception):
    """A download failed. `offline` is true when the network is the likely reason, so a
    scheduled run can end quietly."""

    def __init__(self, message: str, offline: bool = False):
        super().__init__(message)
        self.offline = offline


def _opener(allow_http: bool):
    class OnlyHttps(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not allow_http and not newurl.lower().startswith('https://'):
                raise urllib.error.URLError(f"redirect to a non-https address refused: {newurl}")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return urllib.request.build_opener(OnlyHttps)


def fetch(url: str, max_bytes: int, out: Optional[BinaryIO] = None, *,
          allow_http: bool = False, timeout: float = HTTP_TIMEOUT,
          deadline: float = HTTP_DEADLINE) -> bytes:
    """Download url. With `out`, the bytes go there (and b'' is returned); otherwise they are
    returned. Raises FetchError past max_bytes, past the deadline, or on any network error."""
    scheme = url.split(':', 1)[0].lower()
    if scheme != 'https' and not (allow_http and scheme == 'http'):
        raise FetchError("only https addresses are used")
    request = urllib.request.Request(url, headers={'User-Agent': f'spark-apps-update/{VERSION}',
                                                   'Accept': '*/*'})
    started = time.monotonic()
    chunks = []
    total = 0
    try:
        with _opener(allow_http).open(request, timeout=timeout) as response:
            length = response.headers.get('Content-Length')
            if length and length.isdigit() and int(length) > max_bytes:
                raise FetchError("the download is bigger than the limit")
            while True:
                block = response.read(65536)
                if not block:
                    break
                total += len(block)
                if total > max_bytes:
                    raise FetchError("the download is bigger than the limit")
                if time.monotonic() - started > deadline:
                    raise FetchError("the download took too long", offline=True)
                if out is not None:
                    out.write(block)
                else:
                    chunks.append(block)
    except FetchError:
        raise
    except urllib.error.HTTPError as exc:
        raise FetchError(f"the server answered {exc.code}", offline=exc.code >= 500) from None
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
        raise FetchError(f"can't download: {getattr(exc, 'reason', exc)}", offline=True) from None
    return b''.join(chunks)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(65536), b''):
            digest.update(block)
    return digest.hexdigest()
