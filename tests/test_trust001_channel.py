from __future__ import annotations

import os
import socket
import threading
import unittest

from runner.trust001.channel import OneShotUnixListener, private_socket_path
from runner.trust001.protocol import ProtocolError


class ChannelTests(unittest.TestCase):
    def test_listener_is_private_noninheritable_and_one_shot(self):
        with OneShotUnixListener() as listener:
            private_socket_path(listener)
            self.assertFalse(listener.socket.get_inheritable())
            observed = {}

            def connect():
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                client.connect(str(listener.path))
                observed["client_inheritable"] = client.get_inheritable()
                client.sendall(b"x")
                client.close()

            thread = threading.Thread(target=connect)
            thread.start()
            conn, credentials = listener.accept_once(
                expected_uid=os.getuid() if hasattr(socket, "SO_PEERCRED") else None,
                expected_gid=os.getgid() if hasattr(socket, "SO_PEERCRED") else None,
            )
            try:
                self.assertFalse(conn.get_inheritable())
                self.assertEqual(conn.recv(1), b"x")
                if credentials is not None:
                    self.assertEqual(credentials.uid, os.getuid())
                    self.assertEqual(credentials.gid, os.getgid())
            finally:
                conn.close()
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertFalse(listener.path.exists())
            self.assertFalse(observed["client_inheritable"])

    def test_wrong_expected_peer_is_rejected(self):
        if not hasattr(socket, "SO_PEERCRED"):
            self.skipTest("SO_PEERCRED unavailable")
        with OneShotUnixListener() as listener:
            thread = threading.Thread(
                target=lambda: self._connect_and_close(str(listener.path))
            )
            thread.start()
            with self.assertRaises(ProtocolError):
                listener.accept_once(expected_uid=os.getuid() + 1)
            thread.join(2)

    @staticmethod
    def _connect_and_close(path: str) -> None:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            client.connect(path)
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
