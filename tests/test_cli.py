#!/usr/bin/env python3
"""End-to-end CLI tests use loopback only; never the physical amplifier."""
import os
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from fake_receiver import Receiver

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "marantz"


class CLITests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.server = Receiver()
        self.server.__enter__()
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("MARANTZ_")}
        self.env.update(HOME=self.home.name, MARANTZ_HOST="127.0.0.1",
                        MARANTZ_PORT=str(self.server.server_address[1]),
                        MARANTZ_CONNECT_TIMEOUT="0.2", MARANTZ_RESPONSE_TIMEOUT="0.2",
                        MARANTZ_POWER_TIMEOUT="2", MARANTZ_POLL_INTERVAL="0.02",
                        MARANTZ_STABILIZE_DELAY="0", MARANTZ_REBOOT_DELAY="0")

    def tearDown(self):
        self.server.__exit__()
        self.home.cleanup()

    def run_cli(self, *args, env=None):
        return subprocess.run([str(CLI), *args], env=self.env if env is None else env,
                              text=True, capture_output=True, timeout=8)

    def succeeds(self, args, output):
        result = self.run_cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, output)
        self.assertEqual(result.stderr, "")
        return result

    def fails(self, args, text=None):
        result = self.run_cli(*args)
        self.assertNotEqual(result.returncode, 0)
        if text:
            self.assertIn(text, result.stderr)
        return result

    def test_status(self):
        self.succeeds(["status"], "Marantz\nPower:   On\nVolume:  10\nMute:    Off\nInput:   NET\n")
        self.assertEqual(self.server.commands, ["PW?", "MV?", "MU?", "SI?"])

    def test_physical_model40n_and_documented_avr_simulation_fixtures(self):
        for name in ("model40n.json", "avr_simulated.json"):
            fixture = json.loads((ROOT / "tests" / "fixtures" / name).read_text())
            for case in fixture["cases"]:
                with self.subTest(fixture=name, response=case["response"]):
                    self.server.responses[case["query"]] = case["response"].encode() + b"\r"
                    self.succeeds([case["command"]], case["output"] + "\n")
                    del self.server.responses[case["query"]]

    def test_simulated_volume_namespace_advisory_is_not_current_volume(self):
        self.server.responses["MV?"] = b"MV MAX 98\rMV795\r"
        self.succeeds(["volume"], "79.5\n")

    def test_capabilities_are_observations_not_invented_control_support(self):
        result = self.run_cli("capabilities")
        self.assertEqual(result.returncode, 0, result.stderr)
        for label in ("Power query:", "Volume query:", "Mute query:", "Input query:"):
            self.assertIn(label, result.stdout)
        self.assertEqual(result.stdout.count("Observed"), 4)
        self.assertIn("Volume control: Unknown (not probed)", result.stdout)
        self.assertEqual(self.server.commands, ["PW?", "MV?", "MU?", "SI?"])

    def test_partial_unknown_capabilities_are_not_called_unsupported(self):
        self.server.responses["MV?"] = None
        result = self.run_cli("capabilities")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Volume query:   Unknown", result.stdout)
        self.assertNotIn("unsupported", result.stdout.lower())
        self.assertEqual(result.stdout.count("Observed"), 3)

    def test_no_observed_capabilities_returns_failure(self):
        for query in ("PW?", "MV?", "MU?", "SI?"):
            self.server.responses[query] = None
        result = self.run_cli("capabilities")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.count("Observed"), 0)

    def test_unknown_volume_capability_prevents_wake_and_volume_write(self):
        self.server.power = "PWSTANDBY"
        self.server.responses["MV?"] = None
        self.fails(["v", "up"], "response timeout")
        self.assertEqual(self.server.commands, ["MV?"])

    def test_unknown_mute_capability_prevents_mute_write(self):
        self.server.responses["MU?"] = None
        self.fails(["mute", "on"], "response timeout")
        self.assertEqual(self.server.commands, ["MU?"])

    def test_unknown_power_capability_prevents_power_write(self):
        self.server.responses["PW?"] = b"PWUNKNOWN\r"
        self.fails(["power", "on"], "Malformed")
        self.assertEqual(self.server.commands, ["PW?"])

    def test_failed_confirmation_is_not_reported_as_success_or_retried(self):
        # Simulate firmware that accepts a connection but ignores a setter.
        self.server.responses["MU?"] = b"MUOFF\r"
        self.fails(["mute", "on"], "did not confirm")
        self.assertEqual(self.server.commands.count("MUON"), 1)
        self.server.responses["MV?"] = b"MV10\r"
        self.fails(["v", "set", "20"], "did not confirm")
        self.assertEqual(self.server.commands.count("MV20"), 1)

    def test_direct_host_identity_is_unknown_not_a_guessed_model(self):
        result = self.run_cli("identify")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Device:  Unknown", result.stdout)
        self.assertNotIn("40n", result.stdout)

    def test_wake_delay_precedes_the_next_primitive_command(self):
        self.server.power = "PWSTANDBY"
        self.env["MARANTZ_STABILIZE_DELAY"] = "0.15"
        start = time.monotonic()
        self.succeeds(["power", "on"], "On\n")
        self.assertGreaterEqual(time.monotonic() - start, .15)
        self.assertEqual(self.server.commands, ["PW?", "PWON", "PW?"])

    def test_queries_and_aliases(self):
        for command, output in [("volume", "10\n"), ("vol", "10\n"), ("v", "10\n"),
                                ("power", "On\n"), ("mute", "Off\n"), ("input", "NET\n")]:
            for args in ([command], [command, "status"]):
                with self.subTest(args=args):
                    self.succeeds(args, output)

    def test_standby_query(self):
        self.server.power = "PWSTANDBY"
        self.succeeds(["power"], "Standby\n")

    def test_volume_up_on(self):
        self.succeeds(["v", "up"], "11\n")
        self.assertEqual(self.server.commands, ["MV?", "PW?", "MVUP", "MV?"])

    def test_volume_up_standby_and_poll_sequence(self):
        self.server.power = "PWSTANDBY"
        self.server.on_after_queries = 2
        self.succeeds(["vol", "up"], "11\n")
        self.assertEqual(self.server.commands, ["MV?", "PW?", "PWON", "PW?", "PW?", "PW?", "MVUP", "MV?"])

    def test_volume_down(self):
        self.succeeds(["volume", "down"], "9\n")
        self.assertEqual(self.server.commands, ["MV?", "PW?", "MVDOWN", "MV?"])

    def test_absolute_volume_and_padding(self):
        for args in (["volume", "set", "10"], ["volume", "10"], ["v", "10"], ["vol", "010"]):
            self.succeeds(args, "10\n")
        self.succeeds(["v", "7"], "7\n")
        self.assertIn("MV07", self.server.commands)

    def test_absolute_volume_wakes_receiver(self):
        self.server.power = "PWSTANDBY"
        self.succeeds(["volume", "set", "12"], "12\n")
        self.assertEqual(self.server.commands, ["MV?", "PW?", "PWON", "PW?", "MV12", "MV?"])

    def test_down_wakes_receiver(self):
        self.server.power = "PWSTANDBY"
        self.succeeds(["v", "down"], "9\n")
        self.assertEqual(self.server.commands, ["MV?", "PW?", "PWON", "PW?", "MVDOWN", "MV?"])

    def test_invalid_volume_never_connects(self):
        for level in ("-1", "99", "100", "10.5", "", "abc", "1e1", "1;pwd", "999999999999999999999", "0x10"):
            with self.subTest(level=level):
                self.assertEqual(self.fails(["volume", "set", level]).returncode, 2)
        self.assertEqual(self.server.commands, [])

    def test_configurable_volume_policy(self):
        self.env.update(MARANTZ_VOLUME_MIN="5", MARANTZ_VOLUME_MAX="20")
        self.fails(["volume", "4"], "5..20")
        self.succeeds(["volume", "20"], "20\n")

    def test_mute_on_off_and_toggle(self):
        self.succeeds(["mute", "on"], "On\n")
        self.succeeds(["mute", "off"], "Off\n")
        self.succeeds(["mute", "toggle"], "On\n")
        self.succeeds(["mute", "toggle"], "Off\n")
        self.assertEqual(self.server.commands, ["MU?", "MUON", "MU?", "MU?", "MUOFF", "MU?", "MU?", "MUON", "MU?", "MU?", "MUOFF", "MU?"])

    def test_power_actions(self):
        for action, output in (("off", "Standby\n"), ("standby", "Standby\n"), ("on", "On\n")):
            self.succeeds(["power", action], output)
        self.assertEqual(self.server.commands, ["PW?", "PWSTANDBY", "PW?", "PW?", "PWSTANDBY", "PW?", "PW?", "PWON", "PW?"])

    def test_reboot(self):
        self.succeeds(["reboot"], "Putting Marantz into standby...\nPowering Marantz back on...\nMarantz is online.\n")
        self.assertEqual(self.server.commands, ["PW?", "PWSTANDBY", "PW?", "PWON", "PW?"])

    def test_never_ready(self):
        self.server.power = "PWSTANDBY"
        self.server.never_on = True
        self.env["MARANTZ_POWER_TIMEOUT"] = "1"
        self.fails(["v", "up"], "Timed out waiting")
        self.assertEqual(self.server.commands.count("PWON"), 1)
        self.assertNotIn("MVUP", self.server.commands)

    def test_unreachable(self):
        with socket.socket() as unused:
            unused.bind(("127.0.0.1", 0))
            # Bound but not listening: guaranteed unused TCP port.
            self.env["MARANTZ_PORT"] = str(unused.getsockname()[1])
            result = self.fails(["status"], "is unreachable")
            self.assertEqual(result.stdout, "")

    def test_no_response_timeout(self):
        self.server.responses["PW?"] = None
        start = time.monotonic()
        self.fails(["power"], "response timeout")
        self.assertLess(time.monotonic() - start, 1.5)

    def test_absolute_deadline_despite_trickling(self):
        self.server.responses["PW?"] = "trickle"
        start = time.monotonic()
        self.fails(["power"], "response timeout")
        self.assertLess(time.monotonic() - start, 1.5)

    def test_malformed_response(self):
        for args, command, reply in [(["power"], "PW?", b"PWUNKNOWN\r"),
                                     (["volume"], "MV?", b"MVabc\r"),
                                     (["volume"], "MV?", b"MV106\r"),
                                     (["mute"], "MU?", b"MUBAD\r"),
                                     (["input"], "SI?", b"SI\r")]:
            with self.subTest(reply=reply):
                self.server.responses[command] = reply
                result = self.fails(args, "Malformed")
                self.assertEqual(result.stdout, "")

    def test_binary_incomplete_and_oversized_frames(self):
        for reply in (b"PWON\x00\r", b"PW\xff\r", b"PWON", b"P" * 9000):
            self.server.responses["PW?"] = reply
            self.fails(["power"])

    def test_fragmented_and_unsolicited_response(self):
        self.server.fragment = True
        self.server.responses["PW?"] = b"MUOFF\r\nPWON\r\n"
        self.succeeds(["power"], "On\n")

    def test_no_ack_setters(self):
        self.server.no_ack = True
        self.succeeds(["v", "up"], "11\n")
        self.succeeds(["mute", "on"], "On\n")

    def test_state_change_is_not_retried_after_reset(self):
        self.server.responses["MVUP"] = "reset"
        self.fails(["v", "up"], "may have taken effect")
        self.assertEqual(self.server.commands, ["MV?", "PW?", "MVUP"])

    def test_raw(self):
        for command, output in (("MV?", "MV10\n"), ("PW?", "PWON\n"), ("SI?", "SINET\n")):
            self.succeeds(["raw", command], output)

    def test_raw_is_never_executed(self):
        marker = Path(self.home.name) / "injected"
        for command in ("$(touch {})".format(marker), "`touch {}`".format(marker), "MV?; touch {}".format(marker)):
            self.succeeds(["raw", command], "UNKNOWN\n")
            self.assertEqual(self.server.commands[-1], command)
        self.assertFalse(marker.exists())

    def test_raw_injection_rejected(self):
        for command in ("MV?\rPWON", "MV?\nPWON", "", "MV?\t", "x" * 1025):
            self.fails(["raw", command])
        self.assertEqual(self.server.commands, [])

    def test_help(self):
        for args in (["-h"], ["--help"], ["help"], []):
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 0)
            for text in ("volume set LEVEL", "reboot", "raw COMMAND", "MARANTZ_HOST", "MARANTZ_PORT"):
                self.assertIn(text, result.stdout)
        self.assertEqual(self.server.commands, [])

    def test_bad_environment(self):
        for key, value in (("MARANTZ_PORT", "23-24"), ("MARANTZ_HOST", "-x"),
                           ("MARANTZ_RESPONSE_TIMEOUT", "0"), ("MARANTZ_CONNECT_TIMEOUT", "nan"),
                           ("MARANTZ_POWER_TIMEOUT", "0"), ("MARANTZ_VOLUME_MAX", "100"),
                           ("MARANTZ_POLL_INTERVAL", "-1"), ("MARANTZ_REBOOT_DELAY", "999")):
            with self.subTest(key=key):
                env = self.env.copy()
                env[key] = value
                result = self.run_cli("status", env=env)
                self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.server.commands, [])

    def test_bad_cli_arguments(self):
        for args in (["status", "extra"], ["input", "NET"], ["power", "reset"],
                     ["volume", "set"], ["volume", "up", "10"], ["mute", "on", "extra"],
                     ["raw"], ["reboot", "extra"], ["reset"], ["--other"]):
            self.assertEqual(self.fails(args).returncode, 2)
        self.assertEqual(self.server.commands, [])

    def test_debug_separates_output(self):
        result = self.run_cli("--debug", "v", "up")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "11\n")
        self.assertEqual(result.stderr, "Discovery: environment\nAddress: 127.0.0.1\nTX: MV?\nRX: MV10\nTX: PW?\nRX: PWON\nTX: MVUP\nRX: MV11\nTX: MV?\nRX: MV11\n")

    def test_one_command_per_connection_and_immediate_close(self):
        start = time.monotonic()
        self.succeeds(["status"], "Marantz\nPower:   On\nVolume:  10\nMute:    Off\nInput:   NET\n")
        self.assertLess(time.monotonic() - start, 1.5)
        time.sleep(0.03)
        self.assertEqual(len(self.server.transactions), 4)
        for transaction, command in zip(self.server.transactions, self.server.commands):
            self.assertEqual(transaction["wire"], command.encode() + b"\r")
            self.assertEqual(transaction["extra"], b"")
            self.assertTrue(transaction["closed"])

    def test_install_run_man_and_uninstall(self):
        # A prefix with spaces also checks installer/path quoting.
        prefix = Path(self.home.name) / "local prefix"
        result = subprocess.run([str(ROOT / "install.sh"), "--prefix", str(prefix)],
                                env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        files = [prefix / "bin" / "marantz", prefix / "libexec" / "marantz-transport.py",
                 prefix / "libexec" / "marantz-discovery.py",
                 prefix / "share" / "man" / "man1" / "marantz.1"]
        for path in files:
            self.assertTrue(path.is_file())
        result = subprocess.run([str(files[0]), "volume"], env=self.env,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "10\n")
        result = subprocess.run(["mandoc", "-T", "ascii", str(files[3])],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MARANTZ(1)", result.stdout)
        self.assertIn("standby to on", result.stdout)
        result = subprocess.run(["man", "-M", str(prefix / "share" / "man"), "marantz"],
                                env=dict(self.env, MANPAGER="cat", PAGER="cat", TERM="dumb"),
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MARANTZ", result.stdout)
        # Simulate an older install, upgrade, then repeat without corruption.
        files[1].write_text("old helper\n")
        for _ in range(2):
            result = subprocess.run([str(ROOT / "install.sh"), "--prefix", str(prefix)],
                                    env=self.env, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            for path, source in zip(files, ("bin/marantz", "libexec/marantz-transport.py",
                                           "libexec/marantz-discovery.py", "man/marantz.1")):
                self.assertEqual(path.read_bytes(), (ROOT / source).read_bytes())
                self.assertEqual(path.stat().st_mode & 0o777, 0o755 if path == files[0] else 0o644)
        unrelated = prefix / "bin" / "keep-me"
        unrelated.write_text("keep")
        user_file = Path(self.home.name) / "unrelated-user-data"
        user_file.write_text("keep user data")
        result = subprocess.run([str(ROOT / "uninstall.sh"), "--prefix", str(prefix)],
                                env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in files:
            self.assertFalse(path.exists())
        self.assertTrue(unrelated.is_file())
        self.assertEqual(user_file.read_text(), "keep user data")
        result = subprocess.run([str(ROOT / "uninstall.sh"), "--prefix", str(prefix)],
                                env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(unrelated.is_file())

    def test_info_alias(self):
        result = self.run_cli("info")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Unknown", result.stdout)
        self.assertEqual(self.server.commands, ["PW?"])

    def test_install_permission_failure_preserves_unrelated_file(self):
        if os.geteuid() == 0:
            self.skipTest("permission test requires an unprivileged user")
        prefix = Path(self.home.name) / "locked"
        prefix.mkdir()
        sentinel = prefix / "keep"
        sentinel.write_text("keep")
        prefix.chmod(0o555)
        try:
            result = subprocess.run([str(ROOT / "install.sh"), "--prefix", str(prefix)],
                                    capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(sentinel.read_text(), "keep")
            self.assertFalse((prefix / "bin").exists())
        finally:
            prefix.chmod(0o755)

    def test_installers_validate_prefix(self):
        for script in ("install.sh", "uninstall.sh"):
            for args in (["--prefix", "relative"], ["--prefix", "/"], ["--prefix", "/tmp/.."],
                         ["--bad"], ["--wrong", "/tmp/example"]):
                result = subprocess.run([str(ROOT / script), *args], capture_output=True, text=True, timeout=3)
                self.assertEqual(result.returncode, 2)


class TransportDeadlineTests(unittest.TestCase):
    def test_connection_timeout_including_resolution(self):
        # Deterministic stalled connect/resolution; no external black-hole IP.
        program = """
import runpy, socket, sys, time
socket.create_connection = lambda *args, **kwargs: time.sleep(10)
sys.argv = [sys.argv[1], '127.0.0.1', '23', 'PW?', 'query', 'PW', '0.15', '0.2']
runpy.run_path(sys.argv[0], run_name='__main__')
"""
        start = time.monotonic()
        result = subprocess.run([sys.executable, "-c", program, str(ROOT / "libexec" / "marantz-transport.py")],
                                text=True, capture_output=True, timeout=2)
        self.assertEqual(result.returncode, 1)
        self.assertIn("connection timeout", result.stderr)
        self.assertLess(time.monotonic() - start, 1.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
