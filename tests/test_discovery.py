#!/usr/bin/env python3
"""Loopback UDP/HTTP/TCP integration plus deterministic multi-device fixtures."""
import contextlib
from html import escape
import http.server
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from fake_receiver import Receiver

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("discovery", ROOT / "libexec" / "marantz-discovery.py")
discovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discovery)


def device(address="127.0.0.1", preferred=True, name="Marantz MODEL 40n", udn="uuid:test"):
    return {"address": address, "preferred": preferred, "name": name, "udn": udn,
            "location": "http://{}/device.xml".format(address), "model": "MODEL 40n",
            "manufacturer": "Marantz", "usn": udn}


class XMLHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.requests += 1
        payload = ('''<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0"><device>
<deviceType>{target}</deviceType><friendlyName>{friendly}</friendlyName>
<manufacturer>{manufacturer}</manufacturer><modelName>{model}</modelName>
<UDN>{udn}</UDN></device></root>'''.format(
            target=self.server.target, friendly=escape(self.server.friendly), udn=self.server.udn,
            manufacturer=escape(self.server.manufacturer), model=escape(self.server.model))).encode()
        payload = self.server.raw_xml if self.server.raw_xml is not None else payload
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        pass


class FakeSSDP:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.1)
        self.port = self.sock.getsockname()[1]
        self.http = http.server.ThreadingHTTPServer(("127.0.0.1", 0), XMLHandler)
        self.http.requests = 0
        self.http.friendly = "MODEL 40n"
        self.http.udn = "uuid:test-receiver"
        self.http.target = discovery.TARGET
        self.http.model = "MODEL 40n"
        self.http.manufacturer = "Marantz"
        self.http.raw_xml = None
        self.searches = []
        self.active = True
        self.respond = True
        self.drop_first = False
        self.only_root = False
        self.location = "http://127.0.0.1:{}/device.xml".format(self.http.server_address[1])
        self.threads = [threading.Thread(target=self.serve, daemon=True),
                        threading.Thread(target=self.http.serve_forever, daemon=True)]
        for thread in self.threads:
            thread.start()

    def serve(self):
        while self.active:
            try:
                request, peer = self.sock.recvfrom(16384)
                self.searches.append(request)
                if self.only_root and b"ST: upnp:rootdevice\r\n" not in request:
                    continue
                if self.respond and not (self.drop_first and len(self.searches) <= 2):
                    target = discovery.ROOT_TARGET if b"ST: upnp:rootdevice\r\n" in request else discovery.TARGET
                    response = ("HTTP/1.1 200 OK\r\nST: {}\r\nLOCATION: {}\r\nUSN: {}::{}\r\n\r\n".format(
                        target, self.location, self.http.udn, target)).encode()
                    self.sock.sendto(response, peer)
                    self.sock.sendto(response, peer)  # repeated announcements must deduplicate
            except socket.timeout:
                pass
            except OSError:
                break

    def close(self):
        self.active = False
        self.sock.close()
        self.http.shutdown()
        self.http.server_close()
        for thread in self.threads:
            thread.join(timeout=2)


class DiscoveryCLITests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.server = Receiver()
        self.server.__enter__()
        self.ssdp = FakeSSDP()
        # Redirect only the test helper's UDP destination to the loopback fake.
        # The installed production code has no configurable SSDP endpoint.
        wrapper_dir = Path(self.home.name) / "test-bin"
        wrapper_dir.mkdir()
        wrapper = wrapper_dir / "python3"
        wrapper.write_text('''#!{python}
import importlib.util, runpy, socket, sys
script = sys.argv[1]
sys.argv = sys.argv[1:]
if script.endswith('marantz-discovery.py'):
    spec = importlib.util.spec_from_file_location('discovery', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = module.discover
    module.discover = lambda timeout, debug=False: original(timeout, debug, destination=('127.0.0.1', {port}))
    sys.exit(module.main())
else:
    original = socket.create_connection
    def connect(address, *args, **kwargs):
        if address[0] == 'test-receiver.local':
            address = ('127.0.0.1', address[1])
        return original(address, *args, **kwargs)
    socket.create_connection = connect
    runpy.run_path(script, run_name='__main__')
'''.format(python=sys.executable, port=self.ssdp.port))
        wrapper.chmod(0o755)
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("MARANTZ_")}
        self.env.pop("XDG_CACHE_HOME", None)
        self.env.update(HOME=self.home.name, PATH=str(wrapper_dir) + os.pathsep + self.env["PATH"],
                        PYTHONDONTWRITEBYTECODE="1",
                        MARANTZ_PORT=str(self.server.server_address[1]), MARANTZ_DISCOVERY_TIMEOUT="0.1",
                        MARANTZ_VERIFY_TIMEOUT="0.3", MARANTZ_CONNECT_TIMEOUT="0.2",
                        MARANTZ_RESPONSE_TIMEOUT="0.2", MARANTZ_STABILIZE_DELAY="0")
        self.cache_base = Path(self.home.name) / ("Library/Caches" if sys.platform == "darwin" else ".cache")
        self.cache = self.cache_base / "marantz" / "device.json"

    def tearDown(self):
        self.ssdp.close()
        self.server.__exit__()
        self.home.cleanup()

    def cli(self, *args):
        return subprocess.run([str(ROOT / "bin" / "marantz"), *args], env=self.env,
                              text=True, capture_output=True, timeout=5)

    def good(self, *args):
        result = self.cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_discover_lists_and_deduplicates(self):
        result = self.good("discover")
        self.assertEqual(result.stdout.split(), ["Marantz", "MODEL", "40n", "127.0.0.1"])
        self.assertEqual(self.server.commands, [])
        self.assertEqual(self.ssdp.searches, [discovery.REQUEST, discovery.ROOT_REQUEST])
        self.assertFalse(self.cache.exists())

    def test_devices_alias(self):
        result = self.good("devices")
        self.assertIn("127.0.0.1", result.stdout)
        self.assertEqual(self.server.commands, [])
        self.assertFalse(self.cache.exists())

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux XDG integration")
    def test_linux_xdg_cache_integration(self):
        self.env["XDG_CACHE_HOME"] = str(Path(self.home.name) / "custom cache")
        self.good("volume")
        path = Path(self.env["XDG_CACHE_HOME"]) / "marantz" / "device.json"
        self.assertTrue(path.is_file())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertFalse(self.cache.exists())
        self.ssdp.respond = False
        self.good("volume")
        self.assertEqual(len(self.ssdp.searches), 2)

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux XDG integration")
    def test_linux_relative_xdg_falls_back(self):
        self.env["XDG_CACHE_HOME"] = "relative-cache"
        self.good("volume")
        self.assertTrue(self.cache.exists())

    def test_automatic_then_validated_cache(self):
        result = self.good("--debug", "volume")
        self.assertEqual(result.stdout, "10\n")
        self.assertIn("Discovery: SSDP\nDevice: Marantz MODEL 40n\nAddress: 127.0.0.1", result.stderr)
        self.assertEqual(self.server.commands, ["PW?", "MV?"])
        self.assertTrue(self.cache.exists())
        result = self.good("--debug", "power")
        self.assertEqual(result.stdout, "On\n")
        self.assertIn("Discovery: cached", result.stderr)
        self.assertEqual(len(self.ssdp.searches), 2)
        self.assertEqual(self.ssdp.http.requests, 2)  # description identity checked every time
        self.assertEqual(self.server.commands, ["PW?", "MV?", "PW?", "PW?"])

    def test_explicit_environment_bypasses_discovery_and_cache(self):
        self.env["MARANTZ_HOST"] = "127.0.0.1"
        self.good("status")
        self.assertEqual(self.ssdp.searches, [])
        self.assertEqual(self.server.commands, ["PW?", "MV?", "MU?", "SI?"])
        self.assertFalse(self.cache.exists())

    def test_environment_host_overrides_cached_address(self):
        self.good("volume")
        record = json.loads(self.cache.read_text())
        record["device"]["address"] = "192.0.2.1"
        self.cache.write_text(json.dumps(record))
        self.ssdp.respond = False
        self.env["MARANTZ_HOST"] = "127.0.0.1"
        self.assertIn("Discovery: environment", self.good("--debug", "volume").stderr)
        self.assertEqual(len(self.ssdp.searches), 2)
        self.assertEqual(self.server.commands, ["PW?", "MV?", "MV?"])
        self.assertEqual(json.loads(self.cache.read_text())["device"]["address"], "192.0.2.1")

    def test_zero_setup_with_only_disposable_cache_created(self):
        # An isolated HOME starts with only the test interpreter wrapper. No
        # user setup files or directories exist for the CLI to depend on.
        home = Path(self.home.name)
        self.assertEqual({entry.name for entry in home.iterdir()}, {"test-bin"})
        self.assertFalse(self.cache.parent.exists())
        # Initialize interpreter/shell caches before measuring application writes.
        # Docker Desktop's AMD64 translator can create its own XDG cache even
        # for a no-op Python process; that is independent of Marantz discovery.
        subprocess.run([sys.executable, "-c", "pass"], env=self.env, check=True,
                       capture_output=True, timeout=5)
        self.good("--help")
        before = set(home.rglob("*"))
        self.assertFalse(self.cache.parent.exists())
        self.assertFalse((home / ".config").exists())
        result = self.good("status")
        self.assertIn("Marantz MODEL 40n", result.stdout)
        self.assertTrue(self.cache.is_file())
        expected = {self.cache}
        for parent in self.cache.parents:
            if parent == home:
                break
            expected.add(parent)
        self.assertEqual(set(home.rglob("*")) - before, expected - before)

    def test_deleted_cache_directory_is_recreated_automatically(self):
        self.good("volume")
        self.cache.unlink()
        self.cache.parent.rmdir()
        self.good("volume")
        self.assertTrue(self.cache.is_file())
        self.assertEqual(len(self.ssdp.searches), 4)

    def test_local_hostname_preserved(self):
        self.env["MARANTZ_HOST"] = "test-receiver.local"
        result = self.good("--debug", "volume")
        self.assertIn("Address: test-receiver.local", result.stderr)
        self.assertEqual(result.stdout, "10\n")
        self.assertEqual(self.ssdp.searches, [])

    def test_discover_searches_even_when_explicit_host_exists(self):
        self.env["MARANTZ_HOST"] = "127.0.0.1"
        self.good("discover")
        self.assertEqual(len(self.ssdp.searches), 2)

    def test_expired_cache_rediscovered(self):
        self.good("volume")
        record = json.loads(self.cache.read_text())
        record["saved"] -= 301
        self.cache.write_text(json.dumps(record))
        self.good("volume")
        self.assertEqual(len(self.ssdp.searches), 4)

    def test_unreachable_cached_address_replaced(self):
        self.good("volume")
        record = json.loads(self.cache.read_text())
        record["device"]["address"] = "127.0.0.1"
        # A bound, non-listening description port models a stale DHCP endpoint.
        with socket.socket() as unavailable:
            unavailable.bind(("127.0.0.1", 0))
            record["device"]["location"] = "http://127.0.0.1:{}/device.xml".format(unavailable.getsockname()[1])
            self.cache.write_text(json.dumps(record))
            self.good("volume")
        self.assertEqual(len(self.ssdp.searches), 4)
        self.assertEqual(json.loads(self.cache.read_text())["device"]["location"], self.ssdp.location)

    def test_changed_identity_rediscovered(self):
        self.good("volume")
        self.ssdp.http.udn = "uuid:new-receiver"
        result = self.good("--debug", "volume")
        self.assertIn("changed identity", result.stderr)
        self.assertEqual(len(self.ssdp.searches), 4)
        self.assertEqual(json.loads(self.cache.read_text())["device"]["udn"], "uuid:new-receiver")

    def test_corrupt_cache_ignored(self):
        self.cache.parent.mkdir(parents=True)
        for contents in ("invalid JSON", json.dumps({"version": 1, "port": int(self.env["MARANTZ_PORT"]),
                            "saved": time.time(), "device": {"location": 123, "name": [], "udn": "uuid:x"}})):
            self.cache.write_text(contents)
            self.good("volume")
        self.assertEqual(len(self.ssdp.searches), 4)

    def test_no_results_does_not_use_default_ip(self):
        self.ssdp.respond = False
        result = self.cli("volume")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no compatible devices", result.stderr)
        self.assertEqual(self.server.commands, [])

    def test_invalid_cli_does_not_discover(self):
        for args in (("v", "-1"), ("discover", "extra"), ("raw", "MV?\rPWON"), ("unknown",)):
            self.assertEqual(self.cli(*args).returncode, 2)
        self.assertEqual(self.ssdp.searches, [])

    def test_power_change_resolves_once_before_setter(self):
        self.server.power = "PWSTANDBY"
        result = self.good("v", "up")
        self.assertEqual(result.stdout, "11\n")
        self.assertEqual(self.server.commands, ["PW?", "MV?", "PW?", "PWON", "PW?", "MVUP", "MV?"])
        self.assertEqual(len(self.ssdp.searches), 2)

    def test_named_device_list(self):
        self.ssdp.http.friendly = "Living room"
        result = self.good("discover")
        self.assertIn("Marantz MODEL 40n (Living room)", result.stdout)

    def test_dropped_first_search_is_retried_within_deadline(self):
        self.env["MARANTZ_DISCOVERY_TIMEOUT"] = "0.3"
        self.ssdp.drop_first = True
        started = time.monotonic()
        result = self.good("discover")
        self.assertIn("Marantz MODEL 40n", result.stdout)
        self.assertEqual(len(self.ssdp.searches), 4)
        self.assertLess(time.monotonic() - started, 1.5)

    def test_simulated_non_heos_sr_receiver_via_root_discovery(self):
        self.ssdp.only_root = True
        self.ssdp.http.target = "urn:schemas-upnp-org:device:MediaRenderer:1"
        self.ssdp.http.model = "SR7009 (simulation)"
        self.ssdp.http.friendly = "SR7009 (simulation)"
        result = self.good("status")
        self.assertTrue(result.stdout.startswith("Marantz SR7009 (simulation)\n"))
        self.assertNotIn("40n", result.stdout)

    def test_root_discovery_filters_unrelated_manufacturers(self):
        self.ssdp.only_root = True
        self.ssdp.http.manufacturer = "Unrelated printer vendor"
        self.assertNotEqual(self.cli("volume").returncode, 0)
        self.assertEqual(self.server.commands, [])

    def test_identity_report_is_metadata_not_hardware_certification(self):
        result = self.good("identify")
        self.assertIn("Device:  Marantz MODEL 40n", result.stdout)
        self.assertEqual(self.server.commands, ["PW?", "PW?"])

    def test_cache_expiry_with_vpn_multicast_failure_revalidates_direct_lan(self):
        self.good("volume")
        record = json.loads(self.cache.read_text())
        record["saved"] -= 301
        self.cache.write_text(json.dumps(record))
        self.ssdp.respond = False
        result = self.good("--debug", "volume")
        self.assertIn("expired; discovery unavailable; identity revalidated", result.stderr)
        self.assertEqual(result.stdout, "10\n")
        self.assertEqual(json.loads(self.cache.read_text())["saved"], record["saved"])

    def test_vpn_fallback_rejects_changed_cached_identity(self):
        self.good("volume")
        record = json.loads(self.cache.read_text())
        record["saved"] -= 301
        self.cache.write_text(json.dumps(record))
        self.ssdp.respond = False
        self.ssdp.http.udn = "uuid:different-device"
        result = self.cli("volume")
        self.assertEqual(result.returncode, 1)
        self.assertNotEqual(result.stdout, "10\n")

    def test_device_identity_selector_and_cache_mismatch(self):
        self.env["MARANTZ_DEVICE"] = "uuid:test-receiver"
        self.good("volume")
        self.env["MARANTZ_DEVICE"] = "uuid:another-receiver"
        result = self.cli("volume")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no device matches", result.stderr)

    def test_cache_disabled_is_never_written(self):
        self.env["MARANTZ_CACHE_TTL"] = "0"
        self.good("volume")
        self.assertFalse(self.cache.exists())

    def test_untrusted_xml_declarations_and_binary_encodings_are_rejected(self):
        candidate = device()
        candidate["location"] = self.ssdp.location
        for payload in (b'<!DOCTYPE r [<!ENTITY x "expanded">]><root>&x;</root>',
                        '<root/>'.encode("utf-16"), b"x" * 131073):
            self.ssdp.http.raw_xml = payload
            with self.assertRaises(ValueError):
                discovery.description(candidate, .3)


class DiscoveryUnitTests(unittest.TestCase):
    def test_models_are_never_silently_preferred(self):
        other = device("192.0.2.2", False, "Denon AVR")
        target = device("192.0.2.1")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(ValueError):
            discovery.choose([other, target])

    def test_two_model40n_or_unidentified_devices_are_ambiguous(self):
        for candidates in ([device("192.0.2.1"), device("192.0.2.2")],
                           [device("192.0.2.1", False, "HEOS A"), device("192.0.2.2", False, "HEOS B")]):
            with self.subTest(candidates=candidates), contextlib.redirect_stderr(io.StringIO()) as errors:
                with self.assertRaisesRegex(ValueError, "set MARANTZ_HOST"):
                    discovery.choose(candidates)
                for candidate in candidates:
                    self.assertIn(candidate["address"], errors.getvalue())

    def test_single_compatible_or_none(self):
        candidate = device(preferred=False, name="Denon AVR")
        self.assertEqual(discovery.choose([candidate]), candidate)
        self.assertIsNone(discovery.choose([]))

    def test_multiple_models_and_duplicate_names_require_exact_selection(self):
        a, b = device("192.0.2.1", name="Living room", udn="uuid:a"), device("192.0.2.2", name="Living room", udn="uuid:b")
        self.assertEqual(discovery.choose([a, b], "uuid:b"), b)
        self.assertEqual(discovery.choose([a, b], "192.0.2.1"), a)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(ValueError):
            discovery.choose([a, b], "Living room")
        with self.assertRaisesRegex(ValueError, "no device matches"):
            discovery.choose([a, b], "uuid:missing")

    def test_expired_cache_fallback_when_vpn_socket_is_blocked(self):
        with tempfile.TemporaryDirectory() as home:
            path = Path(home) / "device.json"
            candidate = device()
            discovery.write_cache(path, candidate, 23, False)
            record = json.loads(path.read_text())
            record["saved"] -= 400
            path.write_text(json.dumps(record))
            with mock.patch.object(discovery, "discover", side_effect=OSError("multicast blocked by VPN")), mock.patch.object(discovery, "validate_cached", return_value=candidate):
                self.assertEqual(discovery.resolve(path, 23, .1, .1, 300, False), candidate["address"])

    def test_stale_cache_never_masks_fresh_ambiguity(self):
        with tempfile.TemporaryDirectory() as home:
            path = Path(home) / "device.json"
            discovery.write_cache(path, device(), 23, False)
            record = json.loads(path.read_text())
            record["saved"] -= 400
            path.write_text(json.dumps(record))
            with mock.patch.object(discovery, "discover", return_value=[device("192.0.2.1"), device("192.0.2.2")]), mock.patch.object(discovery, "validate_cached") as validate, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(ValueError):
                discovery.resolve(path, 23, .1, .1, 300, False)
            validate.assert_not_called()

    def test_ambiguity_never_probes_or_selects_a_device(self):
        with tempfile.TemporaryDirectory() as home, mock.patch.object(discovery, "discover", return_value=[device("192.0.2.1"), device("192.0.2.2")]), mock.patch.object(discovery, "probe") as probe, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(ValueError):
                discovery.resolve(Path(home) / "cache", 23, .1, .1, 300, False)
            probe.assert_not_called()

    def test_parse_headers_case_insensitive(self):
        packet = ("HTTP/1.1 200 OK\r\nsT: {}\r\nLoCaTiOn: http://192.0.2.1/device.xml\r\n\r\n".format(discovery.TARGET)).encode()
        candidate = discovery.parse_response(packet, "192.0.2.1")
        self.assertEqual(candidate["address"], "192.0.2.1")
        self.assertEqual(candidate["location"], "http://192.0.2.1/device.xml")

    def test_irrelevant_malformed_or_conflicting_packets_ignored(self):
        for packet in (b"not HTTP", b"HTTP/1.1 404 Not Found\r\n", b"HTTP/1.1 200 OK\r\nST: ssdp:all\r\n\r\n",
                       ("HTTP/1.1 200 OK\r\nST: {}\r\nST: invalid\r\n\r\n".format(discovery.TARGET)).encode(), b"x" * 17000):
            self.assertIsNone(discovery.parse_response(packet, "192.0.2.1"))

    def test_description_url_cannot_redirect_to_another_host(self):
        for location in ("http://192.0.2.2/device.xml", "http://example.com/device.xml",
                         "file:///etc/passwd", "http://user:pass@192.0.2.1/device.xml"):
            candidate = device("192.0.2.1")
            candidate["location"] = location
            with mock.patch.object(discovery.http.client, "HTTPConnection") as connection:
                with self.assertRaises(ValueError):
                    discovery.description(candidate, .1)
                connection.assert_not_called()

    def test_cache_validation_failure_rediscovers_new_address(self):
        with tempfile.TemporaryDirectory() as home:
            path = Path(home) / "device.json"
            cached, fresh = device("192.0.2.1"), device("192.0.2.2", udn="uuid:new")
            discovery.write_cache(path, cached, 23, False)
            with mock.patch.object(discovery, "description", return_value=cached), mock.patch.object(discovery, "probe", side_effect=[False, True]) as probe, mock.patch.object(discovery, "discover", return_value=[fresh]):
                self.assertEqual(discovery.resolve(path, 23, .1, .1, 300, False), "192.0.2.2")
                self.assertEqual([call.args[0] for call in probe.call_args_list], ["192.0.2.1", "192.0.2.2"])
                self.assertEqual(json.loads(path.read_text())["device"]["address"], "192.0.2.2")

    def test_failed_probe_never_caches(self):
        with tempfile.TemporaryDirectory() as home:
            path = Path(home) / "device.json"
            with mock.patch.object(discovery, "discover", return_value=[device()]), mock.patch.object(discovery, "probe", return_value=False):
                with self.assertRaisesRegex(ValueError, "did not answer"):
                    discovery.resolve(path, 23, .1, .1, 300, False)
            self.assertFalse(path.exists())

    def test_no_identity_metadata_not_cached(self):
        with tempfile.TemporaryDirectory() as home:
            candidate = device(udn="")
            path = Path(home) / "device.json"
            discovery.write_cache(path, candidate, 23, False)
            self.assertFalse(path.exists())


class PortEnvironmentTests(unittest.TestCase):
    def test_port_defaults_to_23_and_accepts_environment_override(self):
        # Inspect the actual transport invocation instead of binding privileged
        # port 23. TCP communication with overridden ports is covered above.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            wrapper = path / "python3"
            log = path / "port.txt"
            wrapper.write_text('''#!{python}
from pathlib import Path
import sys
assert sys.argv[1].endswith('marantz-transport.py')
Path({log!r}).write_text(sys.argv[3])
assert sys.argv[4] == 'PW?'
print('PWON')
'''.format(python=sys.executable, log=str(log)))
            wrapper.chmod(0o755)
            env = {key: value for key, value in os.environ.items() if not key.startswith("MARANTZ_")}
            env.update(MARANTZ_HOST="127.0.0.1", PATH=str(path) + os.pathsep + env["PATH"], HOME=directory)
            for port, expected in ((None, "23"), ("2323", "2323")):
                if port is not None:
                    env["MARANTZ_PORT"] = port
                result = subprocess.run([str(ROOT / "bin" / "marantz"), "power"], env=env,
                                        text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "On\n")
                self.assertEqual(log.read_text(), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
