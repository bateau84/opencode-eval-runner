from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runner.trust001.protocol import ProtocolError
from runner.trust001.source_closure import build_source_closure, verify_source_closure


class SourceClosureTests(unittest.TestCase):
    def test_builds_read_only_bridge_only_closure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge = root / "bridge.ts"
            bridge.write_text("export default { id: 'trust001-bridge', async setup() {} }\n")
            destination = root / "config"
            manifest = build_source_closure(destination=destination, bridge_source=bridge)
            verify_source_closure(destination, manifest)
            self.assertEqual(manifest["expected_external_plugin_ids"], ["trust001-bridge"])
            self.assertTrue(manifest["project_config_disabled"])

    def test_product_config_cannot_declare_external_plugins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge = root / "bridge.ts"
            bridge.write_text("export default {}\n")
            for key in ("plugin", "plugins"):
                config = root / f"{key}.json"
                config.write_text(json.dumps({key: ["hostile"]}))
                with self.subTest(key=key):
                    with self.assertRaises(ProtocolError):
                        build_source_closure(
                            destination=root / f"out-{key}",
                            bridge_source=bridge,
                            product_config=config,
                        )

    def test_symlinked_bridge_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real.ts"
            real.write_text("export default {}\n")
            link = root / "link.ts"
            link.symlink_to(real)
            with self.assertRaises(ProtocolError):
                build_source_closure(destination=root / "out", bridge_source=link)

    def test_post_build_mutation_breaks_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge = root / "bridge.ts"
            bridge.write_text("export default {}\n")
            destination = root / "config"
            manifest = build_source_closure(destination=destination, bridge_source=bridge)
            plugin = destination / "plugins" / "trust001-bridge.mjs"
            plugin.chmod(0o644)
            plugin.write_text("export default { id: 'replacement' }\n")
            with self.assertRaises(ProtocolError):
                verify_source_closure(destination, manifest)


if __name__ == "__main__":
    unittest.main()
