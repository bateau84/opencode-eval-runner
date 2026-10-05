from __future__ import annotations

import os
import socket
import stat
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .protocol import ProtocolError, require


@dataclass(frozen=True)
class PeerCredentials:
    pid: int
    uid: int
    gid: int


def peer_credentials(sock: socket.socket) -> PeerCredentials | None:
    if not hasattr(socket, "SO_PEERCRED"):
        return None
    raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    pid, uid, gid = struct.unpack("3i", raw)
    return PeerCredentials(pid=pid, uid=uid, gid=gid)


class OneShotUnixListener:
    """Private one-accept AF_UNIX listener.

    The socket pathname is unlinked immediately after the first accepted peer.
    Python sockets are non-inheritable by default; this class asserts that
    property for both listener and accepted descriptor.
    """

    def __init__(self, parent: Path | None = None, *, name: str = "channel.sock") -> None:
        root = Path(tempfile.mkdtemp(prefix="trust001-", dir=parent))
        root.chmod(0o700)
        self.root = root
        self.path = root / name
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        require(not self.socket.get_inheritable(), "listener_inheritable")
        self.socket.bind(str(self.path))
        self.path.chmod(0o600)
        self.socket.listen(1)
        self.accepted = False
        self.closed = False

    def accept_once(
        self,
        *,
        expected_uid: int | None = None,
        expected_gid: int | None = None,
        expected_pid: int | None = None,
        timeout: float = 5.0,
    ) -> tuple[socket.socket, PeerCredentials | None]:
        require(not self.accepted and not self.closed, "listener_not_available")
        self.socket.settimeout(timeout)
        conn, _ = self.socket.accept()
        conn.set_inheritable(False)
        if conn.get_inheritable():
            conn.close()
            raise ProtocolError("accepted_descriptor_inheritable")
        credentials = peer_credentials(conn)
        if credentials is not None:
            if expected_uid is not None and credentials.uid != expected_uid:
                conn.close()
                raise ProtocolError("unexpected_peer_uid")
            if expected_gid is not None and credentials.gid != expected_gid:
                conn.close()
                raise ProtocolError("unexpected_peer_gid")
            if expected_pid is not None and credentials.pid != expected_pid:
                conn.close()
                raise ProtocolError("unexpected_peer_pid")
        elif any(value is not None for value in (expected_uid, expected_gid, expected_pid)):
            conn.close()
            raise ProtocolError("peer_credentials_unavailable")
        self.accepted = True
        try:
            self.path.unlink()
        finally:
            self.socket.close()
            self.closed = True
        return conn, credentials

    def close(self) -> None:
        if not self.closed:
            self.socket.close()
            self.closed = True
        self.path.unlink(missing_ok=True)

    def cleanup(self) -> None:
        self.close()
        try:
            self.root.rmdir()
        except OSError:
            pass

    def __enter__(self) -> "OneShotUnixListener":
        return self

    def __exit__(self, *_: object) -> None:
        self.cleanup()


def private_socket_path(listener: OneShotUnixListener) -> None:
    info = listener.root.stat()
    require(stat.S_IMODE(info.st_mode) == 0o700, "socket_dir_mode")
    info = listener.path.stat()
    require(stat.S_ISSOCK(info.st_mode), "not_socket")
    require(stat.S_IMODE(info.st_mode) == 0o600, "socket_mode")
