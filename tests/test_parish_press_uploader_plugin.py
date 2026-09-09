"""Guard the WordPress plugin so Settings / side menu cannot be stripped again."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "wordpress" / "parish-press-uploader" / "parish-press-uploader.php"


class TestParishPressUploaderPlugin(unittest.TestCase):
    def test_main_plugin_file_exists(self) -> None:
        self.assertTrue(PLUGIN.is_file(), f"missing {PLUGIN}")

    def test_plugin_header_and_version(self) -> None:
        text = PLUGIN.read_text(encoding="utf-8")
        self.assertIn("Plugin Name: Parish Press Uploader", text)
        self.assertIn("Version: 16.0.1", text)
        self.assertIn("define('PPU_VER', '16.0.1')", text)
        self.assertNotIn("malicious infection", text.lower())

    def test_settings_link_and_side_menu_are_registered(self) -> None:
        text = PLUGIN.read_text(encoding="utf-8")
        self.assertIn("plugin_action_links_", text)
        self.assertIn("add_menu_page", text)
        self.assertIn("ppu-dashboard", text)
        self.assertIn("Settings", text)

    def test_public_and_upload_routes_are_wired(self) -> None:
        text = PLUGIN.read_text(encoding="utf-8")
        self.assertIn("template_redirect", text)
        self.assertIn("register_rest_route", text)
        self.assertIn("ppu/v1", text)
        self.assertIn("function ppu_handle_redirect", text)

    def test_service_worker_does_not_own_wp_admin(self) -> None:
        text = PLUGIN.read_text(encoding="utf-8")
        self.assertIn("scope: '/bulletin-upload/'", text)
        self.assertIn("Service-Worker-Allowed: /bulletin-upload/", text)
        self.assertNotIn("scope: '/' })", text)

    def test_upload_does_not_wipe_options_on_activate(self) -> None:
        text = PLUGIN.read_text(encoding="utf-8")
        self.assertIn("function ppu_activate", text)
        self.assertNotIn("delete_option('ppu_parishes')", text)
        self.assertNotIn("delete_option('ppu_dioceses')", text)


if __name__ == "__main__":
    unittest.main()
