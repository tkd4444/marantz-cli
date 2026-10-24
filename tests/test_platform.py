"""Cache conventions and interface discovery, without external network traffic."""
import ctypes
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

from test_discovery import discovery


class CachePathTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.environment = mock.patch.dict(os.environ, {"HOME": str(self.home)}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_macos_ignores_xdg(self):
        with mock.patch.object(sys, "platform", "darwin"), mock.patch.dict(os.environ, {"XDG_CACHE_HOME": "/tmp/unused"}):
            self.assertEqual(discovery.cache_path(), self.home / "Library/Caches/marantz/device.json")

    def test_linux_default(self):
        with mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(discovery.cache_path(), self.home / ".cache/marantz/device.json")

    def test_linux_xdg_absolute_with_spaces(self):
        base = self.home / "cache with spaces"
        with mock.patch.object(sys, "platform", "linux"), mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(base)}):
            self.assertEqual(discovery.cache_path(), base / "marantz/device.json")

    def test_linux_invalid_xdg(self):
        for value in ("", "relative", "~/.cache", "/tmp/bad\ncache", "/tmp/bad\x7fcache"):
            with self.subTest(value=repr(value)), mock.patch.object(sys, "platform", "linux"), \
                    mock.patch.dict(os.environ, {"XDG_CACHE_HOME": value}):
                self.assertEqual(discovery.cache_path(), self.home / ".cache/marantz/device.json")

    def test_invalid_or_missing_home_uses_account_directory(self):
        with mock.patch.object(discovery.pwd, "getpwuid", return_value=types.SimpleNamespace(pw_dir=str(self.home))), \
                mock.patch.object(sys, "platform", "linux"):
            for value in (None, "", "relative", "/tmp/bad\npath"):
                if value is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = value
                self.assertEqual(discovery.cache_path(), self.home / ".cache/marantz/device.json")

    def test_unwritable_cache_is_nonfatal(self):
        blocker = self.home / "not-a-directory"
        blocker.write_text("keep")
        discovery.write_cache(blocker / "device.json", {"udn": "uuid:test", "location": "http://127.0.0.1/xml"}, 23, False)
        self.assertEqual(blocker.read_text(), "keep")


class InterfaceTests(unittest.TestCase):
    def test_native_enumeration_returns_valid_unique_ipv4(self):
        # Enumeration reads local interface metadata; it sends no packets.
        addresses = discovery.interface_addresses()
        self.assertEqual(addresses, sorted(set(addresses)))
        self.assertLessEqual(len(addresses), 32)
        for address in addresses:
            self.assertEqual(socket.inet_ntoa(socket.inet_aton(address)), address)
            self.assertFalse(address.startswith("127."))

    def test_both_sockaddr_layouts_filter_and_deduplicate(self):
        for platform in ("darwin", "linux"):
            buffers, nodes = [], []
            for address, flags in (("192.0.2.1", 1), ("192.0.2.2", 1), ("192.0.2.1", 1),
                                   ("127.0.0.1", 1), ("192.0.2.3", 0), ("0.0.0.0", 1)):
                header = bytes([16, socket.AF_INET]) if platform == "darwin" else socket.AF_INET.to_bytes(2, sys.byteorder)
                buffer = ctypes.create_string_buffer(header + b"\0\0" + socket.inet_aton(address) + b"\0" * 8)
                node = discovery.Interface()
                node.flags, node.address = flags, ctypes.addressof(buffer)
                buffers.append(buffer)
                nodes.append(node)
            for previous, following in zip(nodes, nodes[1:]):
                previous.next = ctypes.pointer(following)
            libc = mock.Mock()
            def get_addresses(pointer):
                ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(discovery.Interface)))[0] = ctypes.pointer(nodes[0])
                return 0
            libc.getifaddrs.side_effect = get_addresses
            with mock.patch.object(sys, "platform", platform), mock.patch.object(discovery.ctypes, "CDLL", return_value=libc):
                self.assertEqual(discovery.interface_addresses(), ["192.0.2.1", "192.0.2.2"])
            libc.freeifaddrs.assert_called_once()

    def test_enumeration_failure(self):
        libc = mock.Mock()
        libc.getifaddrs.return_value = -1
        with mock.patch.object(discovery.ctypes, "CDLL", return_value=libc):
            with self.assertRaises(OSError):
                discovery.interface_addresses()
        libc.freeifaddrs.assert_not_called()

    def test_search_each_interface_and_continue_after_failure(self):
        sock = mock.Mock()
        sock.setsockopt.side_effect = [OSError("unavailable"), None, None]
        discovery.search_interfaces(sock, discovery.DESTINATION, ["192.0.2.1", "192.0.2.2", "192.0.2.3"], False)
        self.assertEqual(sock.setsockopt.call_count, 3)
        self.assertEqual(sock.sendto.call_args_list, [mock.call(packet, discovery.DESTINATION)
                         for _ in range(2) for packet in (discovery.REQUEST, discovery.ROOT_REQUEST)])

    def test_no_usable_interface_fails(self):
        sock = mock.Mock()
        sock.sendto.side_effect = OSError("unreachable")
        with self.assertRaises(OSError):
            discovery.search_interfaces(sock, discovery.DESTINATION, ["192.0.2.1"], False)

    def test_send_deadline_prevents_late_transmissions(self):
        sock = mock.Mock()
        with self.assertRaises(OSError):
            discovery.search_interfaces(sock, discovery.DESTINATION, ["192.0.2.1", "192.0.2.2"],
                                        False, time.monotonic() - 1)
        sock.sendto.assert_not_called()

    def test_discover_uses_all_interfaces_with_one_shared_deadline(self):
        sock = mock.MagicMock()
        sock.__enter__.return_value = sock
        sock.recvfrom.side_effect = socket.timeout
        with mock.patch.object(discovery.socket, "socket", return_value=sock), \
                mock.patch.object(discovery, "interface_addresses", return_value=["192.0.2.1", "192.0.2.2"]):
            self.assertEqual(discovery.discover(0.01), [])
        self.assertEqual(sock.sendto.call_count, 4)
        interfaces = [call.args[2] for call in sock.setsockopt.call_args_list
                      if call.args[1] == socket.IP_MULTICAST_IF]
        self.assertEqual(interfaces, [socket.inet_aton("192.0.2.1"), socket.inet_aton("192.0.2.2")])

    def test_failed_enumeration_uses_default_route(self):
        sock = mock.MagicMock()
        sock.__enter__.return_value = sock
        sock.recvfrom.side_effect = socket.timeout
        with mock.patch.object(discovery.socket, "socket", return_value=sock), \
                mock.patch.object(discovery, "interface_addresses", side_effect=OSError("unavailable")):
            self.assertEqual(discovery.discover(0.01), [])
        sock.setsockopt.assert_any_call(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton("0.0.0.0"))
        self.assertEqual(sock.sendto.call_count, 2)
