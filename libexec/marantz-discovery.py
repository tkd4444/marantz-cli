#!/usr/bin/env python3
"""Bounded SSDP discovery and validated cache; no subnet scanning or setters."""
import contextlib
import ctypes
import http.client
import ipaddress
import json
import os
from pathlib import Path
import pwd
import re
import signal
import socket
import sys
import tempfile
import time
import urllib.parse
import xml.etree.ElementTree as ET

TARGET = "urn:schemas-denon-com:device:ACT-Denon:1"
ROOT_TARGET = "upnp:rootdevice"
DESTINATION = ("239.255.255.250", 1900)
REQUEST = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
           'MAN: "ssdp:discover"\r\nMX: 1\r\nST: ' + TARGET + "\r\n\r\n").encode("ascii")
ROOT_REQUEST = REQUEST.replace(TARGET.encode("ascii"), ROOT_TARGET.encode("ascii"))


def alarm(_signum, _frame):
    raise TimeoutError("deadline exceeded")


@contextlib.contextmanager
def bounded(seconds):
    previous = signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def clean(text):
    """Keep untrusted metadata on a single printable line, never shell code."""
    return re.sub(r"\s+", " ", "".join(c for c in text if 32 <= ord(c) <= 126)).strip()[:160]


def parse_response(packet, address):
    if len(packet) > 16384:
        return None
    lines = packet.decode("iso-8859-1").split("\r\n")
    if not re.fullmatch(r"HTTP/1\.[01] 200(?: .*)?", lines[0]):
        return None
    headers = {}
    for line in lines[1:]:
        if not line:
            break
        key, separator, value = line.partition(":")
        if separator:
            key = key.strip().lower()
            if key in headers and headers[key] != value.strip():
                return None
            headers[key] = value.strip()
    target = headers.get("st", "").lower()
    if target not in (TARGET.lower(), ROOT_TARGET):
        return None
    try:
        ip = ipaddress.IPv4Address(address)
    except ValueError:
        return None
    if ip.is_unspecified or ip.is_multicast or str(ip) == "255.255.255.255":
        return None
    return {"address": str(ip), "location": headers.get("location", ""),
            "usn": clean(headers.get("usn", "")), "name": "HEOS / Denon / Marantz",
            "model": "", "manufacturer": "", "udn": "", "preferred": False,
            "search_target": target}


def description(candidate, timeout):
    """Only GET the responding address. No redirects, proxies or external URLs."""
    url = urllib.parse.urlsplit(candidate["location"])
    if (url.scheme != "http" or url.hostname != candidate["address"]
            or url.username or url.password or url.fragment):
        raise ValueError("description URL must point to the SSDP sender")
    port = url.port or 80
    path = urllib.parse.urlunsplit(("", "", url.path or "/", url.query, ""))
    with bounded(timeout):
        connection = http.client.HTTPConnection(candidate["address"], port, timeout=timeout)
        try:
            connection.request("GET", path, headers={"Connection": "close"})
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError("description HTTP status {}".format(response.status))
            data = response.read(131073)
            if (len(data) > 131072 or b"\x00" in data or b"<!DOCTYPE" in data.upper()
                    or b"<!ENTITY" in data.upper()):
                raise ValueError("description XML exceeds limits or contains declarations")
            root = ET.fromstring(data)
        finally:
            connection.close()
    devices = [element for element in root.iter() if element.tag.split("}")[-1] == "device"]
    if not devices:
        raise ValueError("description has no device metadata")
    # Prefer the ACT-Denon device; some descriptions contain nested renderers.
    fields = []
    for device in devices:
        fields.append({child.tag.split("}")[-1]: clean(child.text or "") for child in device})
    metadata = next((item for item in fields if item.get("deviceType", "").lower() == TARGET.lower()),
                    next((item for item in fields if any(brand in item.get("manufacturer", "").lower()
                                                        for brand in ("marantz", "denon"))), fields[0]))
    model = metadata.get("modelName", "")
    model_number = metadata.get("modelNumber", "")
    manufacturer = metadata.get("manufacturer", "")
    model = model or model_number
    name = clean((manufacturer + " " + model).strip()) or candidate["name"]
    friendly = metadata.get("friendlyName", "")
    if friendly and friendly.lower() not in (name.lower(), model.lower()):
        name = clean("{} ({})".format(name, friendly))
    return dict(candidate, model=model, manufacturer=manufacturer,
                udn=metadata.get("UDN", ""), name=name, preferred=False)


class Interface(ctypes.Structure):
    """getifaddrs layout shared by Darwin and Linux; sockaddr differs below."""


Interface._fields_ = [("next", ctypes.POINTER(Interface)), ("name", ctypes.c_char_p),
                     ("flags", ctypes.c_uint), ("address", ctypes.c_void_p),
                     ("netmask", ctypes.c_void_p), ("destination", ctypes.c_void_p),
                     ("data", ctypes.c_void_p)]


def interface_addresses():
    """Enumerate active IPv4 addresses without shell tools or interface names."""
    libc = ctypes.CDLL(None, use_errno=True)
    libc.getifaddrs.argtypes = [ctypes.POINTER(ctypes.POINTER(Interface))]
    libc.getifaddrs.restype = ctypes.c_int
    libc.freeifaddrs.argtypes = [ctypes.POINTER(Interface)]
    libc.freeifaddrs.restype = None
    head = ctypes.POINTER(Interface)()
    if libc.getifaddrs(ctypes.byref(head)) != 0:
        raise OSError(ctypes.get_errno(), "getifaddrs failed")
    addresses = set()
    try:
        node = head
        while node:
            item = node.contents
            if item.flags & 1 and item.address:  # IFF_UP on both platforms
                header = ctypes.string_at(item.address, 2)
                # Darwin sockaddr starts with length/family bytes; Linux with
                # native-endian sa_family_t. IPv4 address starts at byte four.
                family = header[1] if sys.platform == "darwin" else int.from_bytes(header, sys.byteorder)
                if family == socket.AF_INET:
                    address = ipaddress.IPv4Address(ctypes.string_at(item.address + 4, 4))
                    if not (address.is_loopback or address.is_unspecified or address.is_multicast):
                        addresses.add(str(address))
            node = item.next
    finally:
        libc.freeifaddrs(head)
    return sorted(addresses)[:32]


def search_interfaces(sock, destination, addresses, debug, deadline=None):
    sent = False
    for address in addresses:
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(address))
            for packet in (REQUEST, ROOT_REQUEST):
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        if sent:
                            return
                        raise TimeoutError("SSDP send deadline exceeded")
                    sock.settimeout(remaining)
                sock.sendto(packet, destination)
                sent = True
        except OSError as error:
            # A VPN/down interface must not prevent discovery on another link.
            if debug:
                print("SSDP interface: " + clean(str(error)), file=sys.stderr)
    if not sent:
        raise OSError("no usable multicast interface; use MARANTZ_HOST for direct access")


def discover(timeout, debug=False, destination=DESTINATION):
    candidates = {}
    deadline = time.monotonic() + timeout
    if debug:
        print("SSDP: searching 239.255.255.250:1900 for HEOS and UPnP root devices", file=sys.stderr)
    addresses = ["0.0.0.0"]
    if destination == DESTINATION:
        try:
            addresses = interface_addresses() or addresses
        except (OSError, AttributeError):
            # Retain OS routing if enumeration is unavailable.
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.bind(("", 0))
        search_interfaces(sock, destination, addresses, debug, deadline)
        # UDP can drop a search or response. Retry only this read-only discovery
        # request pair, within the same budget and at most three transmissions.
        retry_interval = min(1.0, timeout / 2)
        next_search = time.monotonic() + retry_interval if timeout >= 0.25 else deadline
        searches = 1
        packets = 0
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_search and searches < 3:
                search_interfaces(sock, destination, addresses, debug, deadline)
                searches += 1
                next_search = now + retry_interval if searches < 3 else deadline
            sock.settimeout(max(0.001, min(deadline, next_search) - time.monotonic()))
            try:
                packet, peer = sock.recvfrom(16385)
            except socket.timeout:
                continue
            packets += 1
            if packets > 4096:
                raise ValueError("too many SSDP responses; configure MARANTZ_HOST explicitly")
            candidate = parse_response(packet, peer[0])
            if candidate is not None:
                address = candidate["address"]
                if address not in candidates or not candidates[address]["location"]:
                    candidates[address] = candidate
                if len(candidates) > 32:
                    raise ValueError("too many devices; configure MARANTZ_HOST explicitly")
    # A separate overall metadata budget prevents N responders multiplying waits.
    deadline = time.monotonic() + timeout
    result = []
    for candidate in candidates.values():
        remaining = deadline - time.monotonic()
        if candidate["location"] and remaining > 0:
            try:
                candidate = description(candidate, min(0.75, remaining))
            except (OSError, ValueError, ET.ParseError, http.client.HTTPException) as error:
                if debug:
                    print("Discovery metadata: {}: {}".format(candidate["address"], clean(str(error))), file=sys.stderr)
        # Broad UPnP searches also find printers, routers and unrelated renderers.
        # Retain them only with vendor metadata; HEOS remains a candidate signal,
        # not proof of port-23 control support.
        if candidate.get("search_target") == ROOT_TARGET and not any(
                brand in candidate.get("manufacturer", "").lower() for brand in ("marantz", "denon")):
            continue
        result.append(candidate)
    return sorted(result, key=lambda item: (item["name"], item["address"]))


def print_candidates(candidates, stream=sys.stdout):
    for candidate in candidates:
        print("{:<36} {}".format(candidate["name"], candidate["address"]), file=stream)


def matches(candidate, selector):
    return not selector or selector.casefold() in (
        candidate.get(key, "").casefold() for key in ("address", "udn", "name", "model"))


def choose(candidates, selector=""):
    options = [item for item in candidates if matches(item, selector)]
    if len(options) == 1:
        return options[0]
    if options:
        print("marantz: Multiple discovery candidates found (TCP capabilities unverified):", file=sys.stderr)
        print_candidates(candidates, sys.stderr)
        raise ValueError("set MARANTZ_HOST or an exact MARANTZ_DEVICE identity to select a device")
    if selector:
        raise ValueError("no device matches MARANTZ_DEVICE; run marantz discover")
    return None


def probe(host, port, timeout):
    """Check receiver protocol with PW? only, not just an open TCP port."""
    try:
        with bounded(timeout), socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(b"PW?\r")
            data = bytearray()
            while len(data) <= 8192:
                chunk = sock.recv(1024)
                if not chunk:
                    return False
                data.extend(chunk)
                while b"\r" in data:
                    line, _, tail = data.partition(b"\r")
                    data = bytearray(tail)
                    if line.lstrip(b"\n") in (b"PWON", b"PWSTANDBY"):
                        return True
    except OSError:
        pass
    return False


def read_cache(path, port, ttl):
    try:
        if path.stat().st_size > 8192:
            return None
        record = json.loads(path.read_text())
        candidate = record["device"]
        age = time.time() - record["saved"]
        if (record["version"] != 1 or record["port"] != port or age < 0
                or (ttl is not None and age > ttl)
                or not isinstance(candidate, dict)
                or any(not isinstance(candidate.get(key), str) or not candidate[key]
                       for key in ("address", "udn", "location", "name"))
                or len(candidate["location"]) > 2048):
            return None
        if any(not isinstance(candidate.get(key, ""), str) for key in ("model", "manufacturer")):
            return None
        if any(clean(candidate[key]) != candidate[key] for key in ("udn", "name")):
            return None
        ipaddress.IPv4Address(candidate["address"])
        return candidate
    except (OSError, ValueError, KeyError, TypeError):
        return None


def write_cache(path, candidate, port, debug):
    # Without identity metadata we cannot safely revalidate an address reassigned
    # by DHCP. Such devices can be used, but require discovery again next time.
    if not candidate["udn"] or not candidate["location"]:
        return
    temporary = None
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=str(path.parent), delete=False) as file:
            temporary = file.name
            json.dump({"version": 1, "port": port, "saved": time.time(), "device": candidate}, file)
        os.replace(temporary, str(path))
    except OSError as error:
        if debug:
            print("Cache: cannot save: " + clean(str(error)), file=sys.stderr)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def debug_device(method, candidate, debug):
    if debug:
        print("Discovery: {}\nDevice: {}\nAddress: {}".format(
            method, clean(candidate["name"]), candidate["address"]), file=sys.stderr)


def validate_cached(cached, port, verify_timeout):
    started = time.monotonic()
    current = description(cached, verify_timeout / 2)
    remaining = verify_timeout - (time.monotonic() - started)
    if current["udn"] == cached["udn"] and remaining > 0 and probe(cached["address"], port, remaining):
        return current
    return None


def resolve(cache_path, port, timeout, verify_timeout, ttl, debug, selector="", include_identity=False):
    cached = read_cache(cache_path, port, ttl) if ttl else None
    stale = read_cache(cache_path, port, None) if ttl and cached is None else None
    if cached is not None and not matches(cached, selector):
        cached = None
    if stale is not None and not matches(stale, selector):
        stale = None
    if cached is not None:
        try:
            current = validate_cached(cached, port, verify_timeout)
            if current:
                debug_device("cached", current, debug)
                return current if include_identity else current["address"]
        except (OSError, ValueError, ET.ParseError, http.client.HTTPException):
            pass
    if debug and cached is not None:
        print("Cache: stale, unreachable or changed identity; rediscovering", file=sys.stderr)
    discovery_error = None
    try:
        candidates = discover(timeout, debug)
    except (OSError, ValueError) as error:
        candidates, discovery_error = [], error
    # Never use a cached selection to hide a fresh ambiguous result or a changed
    # identity. Expiry alone may fall back when a VPN blocks multicast, provided
    # the HTTP identity and PW? are both freshly validated on the LAN.
    if not candidates and stale is not None:
        try:
            current = validate_cached(stale, port, verify_timeout)
            if current:
                debug_device("cached (expired; discovery unavailable; identity revalidated)", current, debug)
                return current if include_identity else current["address"]
        except (OSError, ValueError, ET.ParseError, http.client.HTTPException):
            pass
    if discovery_error:
        raise ValueError("discovery unavailable; use MARANTZ_HOST for direct LAN access: " + clean(str(discovery_error)))
    candidate = choose(candidates, selector)
    if candidate is not None:
        if not probe(candidate["address"], port, verify_timeout):
            raise ValueError("discovered device at {} did not answer PW? on port {}".format(candidate["address"], port))
        if ttl:
            write_cache(cache_path, candidate, port, debug)
        debug_device("SSDP", candidate, debug)
        return candidate if include_identity else candidate["address"]
    raise ValueError("no compatible devices found; run marantz discover or set MARANTZ_HOST in the environment")


def cache_path():
    value = os.environ.get("HOME", "")
    home = Path(value) if valid_absolute_path(value) else Path(pwd.getpwuid(os.getuid()).pw_dir)
    if sys.platform == "darwin":
        base = home / "Library" / "Caches"
    else:
        value = os.environ.get("XDG_CACHE_HOME", "")
        # XDG requires absolute paths. Empty, relative and control-containing
        # values fall back without making configuration mandatory.
        base = Path(value) if valid_absolute_path(value) else home / ".cache"
    return base / "marantz" / "device.json"


def valid_absolute_path(value):
    return value.startswith("/") and not any(ord(c) < 32 or ord(c) == 127 for c in value)


def main():
    mode, port, timeout, verify_timeout, ttl, debug = sys.argv[1:7]
    selector = sys.argv[7] if len(sys.argv) > 7 else ""
    port, timeout, verify_timeout, ttl = int(port), float(timeout), float(verify_timeout), int(ttl)
    debug = debug == "1"
    try:
        if mode == "discover":
            candidates = discover(timeout, debug)
            if not candidates:
                raise ValueError("no compatible devices found via SSDP")
            print_candidates(candidates)
            return 0
        path = cache_path()
        candidate = resolve(path, port, timeout, verify_timeout, ttl, debug, selector, include_identity=True)
        print(candidate["address"])
        if mode == "resolve-info":
            print(clean(candidate["name"]))
        return 0
    except (OSError, ValueError, http.client.HTTPException) as error:
        print("marantz: discovery failed: {}.".format(clean(str(error))), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
