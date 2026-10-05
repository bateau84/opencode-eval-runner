from __future__ import annotations

import os
import socket
import threading
import unittest

from runner.trust001.protocol import WIRE_VERSION
from runner.trust001.runtime import ChannelSet
from runner.trust001.transport import FramedSocket


GEN = "a" * 64


class RuntimeChannelTests(unittest.TestCase):
    def test_three_endpoints_are_distinct_and_unlinked_after_admission(self):
        with ChannelSet(generation=GEN) as channels:
            paths = channels.paths()
            roots = channels.mount_roots()
            self.assertEqual(len(set(paths.values())), 3)
            self.assertEqual(len(set(roots.values())), 3)

            clients = {}

            def connect(name, channel, role):
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(str(paths[name]))
                FramedSocket(sock, channel=channel).send({
                    "version": WIRE_VERSION,
                    "kind": f"{channel}.hello",
                    "generation": GEN,
                    "role": role,
                })
                clients[name] = sock

            # ChannelSet admits evidence, bridge capability, then Loom capability.
            threads = [
                threading.Thread(target=connect, args=("evidence", "evidence", "bridge")),
                threading.Thread(target=connect, args=("capability_bridge", "capability", "bridge")),
                threading.Thread(target=connect, args=("capability_loom", "capability", "loom")),
            ]
            for thread in threads:
                thread.start()

            admitted = channels.admit(
                bridge_uid=os.getuid() if hasattr(socket, "SO_PEERCRED") else None,
                bridge_gid=os.getgid() if hasattr(socket, "SO_PEERCRED") else None,
                loom_uid=os.getuid() if hasattr(socket, "SO_PEERCRED") else None,
                loom_gid=os.getgid() if hasattr(socket, "SO_PEERCRED") else None,
            )
            for thread in threads:
                thread.join(2)
                self.assertFalse(thread.is_alive())

            self.assertEqual(admitted.generation, GEN)
            self.assertTrue(all(not path.exists() for path in paths.values()))

            for sock in clients.values():
                sock.close()
            admitted.capability.bridge.sock.close()
            admitted.capability.loom.sock.close()
            admitted.evidence.channel.sock.close()


if __name__ == "__main__":
    unittest.main()
