"""Routing tests: the desktop launcher must not start a browser in native mode."""

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location("launcher", Path(__file__).parents[1] / "launcher.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        config = types.ModuleType("app.config")
        config.Settings = lambda **kwargs: types.SimpleNamespace(backend_port=9876)
        self.modules = patch.dict(sys.modules, {"app.config": config})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.opener = MagicMock()
        self.opener.open.return_value.__enter__.return_value.status = 200

    def test_desktop_execs_native_python_without_browser(self):
        with (
            patch.dict(os.environ, {"DISPLAY": ":1"}, clear=True),
            patch.object(sys, "argv", ["linux-monitor"]),
            patch.object(launcher, "build_opener", return_value=self.opener),
            patch.object(launcher.os, "execv", side_effect=SystemExit) as execute,
            patch.object(launcher.webbrowser, "open") as browser,
        ):
            with self.assertRaises(SystemExit):
                launcher.main()
            argv = execute.call_args.args[1]
            self.assertEqual(argv[-2:], ["--url", "http://127.0.0.1:9876/"])
            self.assertTrue(argv[2].endswith("/native.py"))
            browser.assert_not_called()

    def test_explicit_browser_overrides_graphical_display(self):
        with (
            patch.dict(os.environ, {"DISPLAY": ":1"}, clear=True),
            patch.object(sys, "argv", ["linux-monitor", "--browser"]),
            patch.object(launcher, "build_opener", return_value=self.opener),
            patch.object(launcher.os, "execv") as execute,
            patch.object(launcher.webbrowser, "open", return_value=True) as browser,
        ):
            self.assertEqual(launcher.main(), 0)
            browser.assert_called_once_with("http://127.0.0.1:9876/")
            execute.assert_not_called()

    def test_wsl_without_linux_display_uses_windows_browser(self):
        with (
            patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}, clear=True),
            patch.object(sys, "argv", ["linux-monitor"]),
            patch.object(launcher, "build_opener", return_value=self.opener),
            patch.object(launcher.shutil, "which", return_value="/mnt/c/explorer.exe"),
            patch.object(launcher.subprocess, "Popen") as spawn,
        ):
            self.assertEqual(launcher.main(), 0)
            self.assertEqual(
                spawn.call_args.args[0], ["/mnt/c/explorer.exe", "http://127.0.0.1:9876/"]
            )

    def test_url_only_does_not_require_backend_or_display(self):
        with (
            patch.object(sys, "argv", ["linux-monitor", "--url"]),
            patch.object(launcher, "build_opener") as opener,
            patch("builtins.print") as output,
        ):
            self.assertEqual(launcher.main(), 0)
            output.assert_called_once_with("http://127.0.0.1:9876/")
            opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
