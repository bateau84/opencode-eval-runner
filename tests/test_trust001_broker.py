from __future__ import annotations

import unittest

from runner.trust001.broker import CapabilityRouter
from runner.trust001.protocol import ProtocolError, WIRE_VERSION


GEN = "a" * 64
HOST_REQ = "1" * 32
CALLBACK_REQ = "2" * 32


def message(kind: str, request_id: str, **extra):
    return {
        "version": WIRE_VERSION,
        "kind": kind,
        "generation": GEN,
        "request_id": request_id,
        **extra,
    }


class BrokerTests(unittest.TestCase):
    def test_loom_host_request_round_trip(self):
        router = CapabilityRouter(GEN)
        target, request = router.route("loom", message(
            "capability.host.request",
            HOST_REQ,
            operation="storage.get",
            payload={"key": "project/x"},
        ))
        self.assertEqual(target, "bridge")
        self.assertEqual(request["operation"], "storage.get")

        target, _ = router.route("bridge", message(
            "capability.host.response",
            HOST_REQ,
            ok=True,
            payload={"value": None},
        ))
        self.assertEqual(target, "loom")
        self.assertNotIn(HOST_REQ, router.host_calls.outstanding)

    def test_bridge_callback_round_trip(self):
        router = CapabilityRouter(GEN)
        target, request = router.route("bridge", message(
            "capability.callback.request",
            CALLBACK_REQ,
            operation="tool.execute.before",
            payload={"tool": "question"},
        ))
        self.assertEqual(target, "loom")
        self.assertEqual(request["operation"], "tool.execute.before")

        target, _ = router.route("loom", message(
            "capability.callback.response",
            CALLBACK_REQ,
            ok=True,
            payload={"input": {}},
        ))
        self.assertEqual(target, "bridge")

    def test_request_classes_cannot_cross_direction(self):
        cases = [
            ("loom", message(
                "capability.callback.request", CALLBACK_REQ,
                operation="tool.execute.before", payload={}
            )),
            ("bridge", message(
                "capability.host.request", HOST_REQ,
                operation="storage.get", payload={"key": "x"}
            )),
            ("loom", message(
                "capability.host.response", HOST_REQ,
                ok=True, payload={}
            )),
            ("bridge", message(
                "capability.callback.response", CALLBACK_REQ,
                ok=True, payload={}
            )),
        ]
        for origin, value in cases:
            with self.subTest(origin=origin, kind=value["kind"]):
                router = CapabilityRouter(GEN)
                with self.assertRaises(ProtocolError):
                    router.route(origin, value)
                self.assertTrue(router.failed)

    def test_duplicate_response_fails_router(self):
        router = CapabilityRouter(GEN)
        router.route("bridge", message(
            "capability.callback.request", CALLBACK_REQ,
            operation="trust001.preflight.ping", payload={}
        ))
        response = message(
            "capability.callback.response", CALLBACK_REQ,
            ok=True, payload={"pong": True}
        )
        router.route("loom", response)
        with self.assertRaises(ProtocolError):
            router.route("loom", response)
        self.assertTrue(router.failed)

    def test_stale_generation_fails_router(self):
        router = CapabilityRouter(GEN)
        stale = message(
            "capability.host.request", HOST_REQ,
            operation="storage.get", payload={"key": "x"}
        )
        stale["generation"] = "b" * 64
        with self.assertRaises(ProtocolError):
            router.route("loom", stale)
        self.assertTrue(router.failed)

    def test_class_specific_cancel_rejects_late_response(self):
        router = CapabilityRouter(GEN)
        router.route("bridge", message(
            "capability.callback.request", CALLBACK_REQ,
            operation="tool.execute", payload={}
        ))
        router.route("bridge", message(
            "capability.callback.cancel", CALLBACK_REQ,
            reason="interrupted"
        ))
        with self.assertRaises(ProtocolError):
            router.route("loom", message(
                "capability.callback.response", CALLBACK_REQ,
                ok=True, payload={}
            ))
        self.assertTrue(router.failed)

    def test_close_requires_both_namespaces_settled(self):
        router = CapabilityRouter(GEN)
        router.route("loom", message(
            "capability.host.request", HOST_REQ,
            operation="storage.get", payload={"key": "x"}
        ))
        router.close_admission()
        self.assertFalse(router.settled)
        router.route("bridge", message(
            "capability.host.response", HOST_REQ,
            ok=True, payload={"value": None}
        ))
        self.assertTrue(router.settled)


if __name__ == "__main__":
    unittest.main()
