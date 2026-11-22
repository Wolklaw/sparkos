"""The public websites, checked straight from this PC: one GET, 5 second timeout, a plain user
agent, no cookies, nothing about the owner in the request."""

import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from . import SITE_TIMEOUT_S, VERSION
from .config import Site

USER_AGENT = f"SparkConnect/{VERSION}"


@dataclass
class SiteResult:
    name: str
    url: str
    status: Optional[int] = None
    ms: Optional[float] = None
    error: str = ''
    at: float = field(default_factory=time.time)

    @property
    def ok(self) -> bool:
        return not self.error and self.status is not None and self.status < 400


def check(site: Site, timeout: float = SITE_TIMEOUT_S) -> SiteResult:
    request = urllib.request.Request(site.url, headers={'User-Agent': USER_AGENT,
                                                        'Accept': '*/*'})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read(1024)
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
    except (urllib.error.URLError, socket.timeout, ssl.SSLError, ConnectionError,
            OSError) as exc:
        reason = getattr(exc, 'reason', exc)
        text = 'timed out' if isinstance(reason, socket.timeout) or 'timed out' in str(reason) \
            else str(reason)
        return SiteResult(site.name, site.url, error=text[:120])
    return SiteResult(site.name, site.url, status=status,
                      ms=(time.monotonic() - started) * 1000)
