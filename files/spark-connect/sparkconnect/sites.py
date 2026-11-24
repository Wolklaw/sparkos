"""The public websites, checked straight from this PC: one GET, 5 second timeout, a plain user
agent, no cookies, nothing about the owner in the request. A GET that times out or can't connect
is tried once more over IPv4 only, so a home connection whose IPv6 route stalls for a minute
doesn't show a working site as down; the time shown then covers both tries."""

import http.client
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


def _ipv4(host: str, port: int) -> str:
    return socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]


class _V4HTTPConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.create_connection((_ipv4(self.host, self.port), self.port),
                                             self.timeout, self.source_address)


class _V4HTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        sock = socket.create_connection((_ipv4(self.host, self.port), self.port),
                                        self.timeout, self.source_address)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _V4HTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_V4HTTPConnection, req)


class _V4HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_V4HTTPSConnection, req, context=self._context)


_DEFAULT = urllib.request.build_opener()
_IPV4 = urllib.request.build_opener(_V4HTTPHandler, _V4HTTPSHandler)


class _NoAnswer(Exception):
    pass


def _get(opener, request, timeout: float) -> int:
    try:
        with opener.open(request, timeout=timeout) as response:
            response.read(1024)
            return response.status
    except urllib.error.HTTPError as exc:
        exc.close()
        return exc.code
    except (urllib.error.URLError, socket.timeout, ssl.SSLError, ConnectionError,
            OSError) as exc:
        reason = getattr(exc, 'reason', exc)
        text = 'timed out' if isinstance(reason, socket.timeout) or 'timed out' in str(reason) \
            else str(reason)
        raise _NoAnswer(text[:120]) from exc


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
        status = _get(_DEFAULT, request, timeout)
    except _NoAnswer as first:
        try:
            status = _get(_IPV4, request, timeout)
        except _NoAnswer:
            return SiteResult(site.name, site.url, error=str(first))
    return SiteResult(site.name, site.url, status=status,
                      ms=(time.monotonic() - started) * 1000)
