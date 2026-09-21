"""Local network discovery and Wake-on-LAN server for the dashboard."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "devices.json"
MAC_RE = re.compile(r"^[0-9a-fA-F]{12}$")


class AppError(Exception):
    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = status


def run_ip(*args: str) -> Any:
    if not shutil.which("ip"):
        if os.name == "nt":
            raise AppError("Skanowanie sieci jest dostępne w systemie Linux.", 503)
        raise AppError("Brakuje polecenia ip. Zainstaluj pakiet iproute2.", 503)
    result = subprocess.run(
        ["ip", "-j", *args], capture_output=True, text=True, timeout=5, check=False
    )
    if result.returncode:
        raise AppError("Nie udało się odczytać ustawień sieci.", 503)
    return json.loads(result.stdout or "[]")


@dataclass(frozen=True)
class Network:
    interface: str
    address: str
    cidr: str
    broadcast: str
    scan_network: ipaddress.IPv4Network

    def public(self) -> dict[str, str]:
        return {
            "interface": self.interface,
            "address": self.address,
            "cidr": self.cidr,
            "scan_range": str(self.scan_network),
        }


def available_networks() -> list[Network]:
    routes = run_ip("-4", "route", "show", "default")
    preferred = next((route.get("dev") for route in routes if route.get("dev")), None)
    interfaces = run_ip("-4", "addr", "show")
    candidates: list[Network] = []
    for interface in interfaces:
        name = interface.get("ifname", "")
        if name == "lo":
            continue
        for address in interface.get("addr_info", []):
            if address.get("family") != "inet" or address.get("scope") != "global":
                continue
            ip = address.get("local")
            prefix = address.get("prefixlen")
            if not ip or not isinstance(prefix, int):
                continue
            subnet = ipaddress.ip_interface(f"{ip}/{prefix}").network
            # Limit discovery to 254 peers even on large LANs.
            scan_network = (
                ipaddress.ip_network(f"{ip}/24", strict=False)
                if subnet.num_addresses > 256
                else subnet
            )
            candidates.append(
                Network(
                    interface=name,
                    address=ip,
                    cidr=str(subnet),
                    broadcast=address.get("broadcast", str(subnet.broadcast_address)),
                    scan_network=scan_network,
                )
            )
    if not candidates:
        raise AppError("Nie znaleziono aktywnej sieci IPv4.", 503)
    return sorted(candidates, key=lambda item: item.interface != preferred)


def choose_network(subnet: str = "", interface: str = "", networks: list[Network] | None = None) -> Network:
    candidates = list(networks) if networks is not None else available_networks()
    if interface:
        candidates = [item for item in candidates if item.interface == interface]
        if not candidates:
            raise AppError("Wybrany interfejs sieciowy nie jest dostępny.")
    if subnet:
        if "/" not in subnet:
            raise AppError("Podaj podsieć w formacie CIDR, np. 192.168.0.0/24.")
        try:
            requested = ipaddress.ip_network(subnet.strip(), strict=False)
        except ValueError as exc:
            raise AppError("Podaj poprawną podsieć IPv4, np. 192.168.0.0/24.") from exc
        if not isinstance(requested, ipaddress.IPv4Network):
            raise AppError("Podaj podsieć IPv4.")
        if requested.num_addresses > 256:
            raise AppError("Zakres skanowania może obejmować najwyżej 256 adresów (/24).")
        candidates = [
            item for item in candidates
            if requested.subnet_of(ipaddress.IPv4Network(item.cidr))
        ]
        if not candidates:
            raise AppError("Podsieć musi należeć do lokalnej sieci wybranego interfejsu.")
        return replace(candidates[0], scan_network=requested)
    if not candidates:
        raise AppError("Nie znaleziono aktywnej sieci IPv4.", 503)
    return candidates[0]


def network_from_request(value: dict[str, Any]) -> Network:
    subnet = value.get("subnet", "")
    interface = value.get("interface", "")
    if not isinstance(subnet, str) or not isinstance(interface, str):
        raise AppError("Nieprawidłowy wybór sieci.")
    return choose_network(subnet, interface)


def normalize_mac(raw: str) -> str:
    compact = raw.replace(":", "").replace("-", "").replace(".", "").strip()
    if not MAC_RE.fullmatch(compact):
        raise AppError("Podaj poprawny adres MAC.")
    octets = bytes.fromhex(compact)
    if octets == b"\x00" * 6 or octets == b"\xff" * 6 or octets[0] & 1:
        raise AppError("Podaj adres MAC pojedynczego urządzenia.")
    return ":".join(f"{part:02X}" for part in octets)


def normalize_ip(raw: str) -> str:
    try:
        address = ipaddress.IPv4Address(raw.strip())
    except ipaddress.AddressValueError as exc:
        raise AppError("Podaj poprawny adres IPv4.") from exc
    if not address.is_private:
        raise AppError("Adres IP musi należeć do sieci prywatnej.")
    return str(address)


def neighbors(network: Network) -> list[dict[str, str]]:
    entries = run_ip("-4", "neigh", "show", "dev", network.interface)
    found: list[dict[str, str]] = []
    for entry in entries:
        ip = entry.get("dst", "")
        raw_mac = entry.get("lladdr", "")
        try:
            if (
                not raw_mac
                or ip == network.address
                or ipaddress.IPv4Address(ip) not in network.scan_network
            ):
                continue
            mac = normalize_mac(raw_mac)
        except (AppError, ipaddress.AddressValueError):
            continue
        found.append({"ip": ip, "mac": mac})
    return sorted(found, key=lambda item: ipaddress.IPv4Address(item["ip"]))


def arp_scan_executable() -> str | None:
    return shutil.which("arp-scan") or (
        "/usr/sbin/arp-scan" if Path("/usr/sbin/arp-scan").is_file() else None
    )


def arp_scan(network: Network, target: str | None = None) -> list[dict[str, str]]:
    command = [
        arp_scan_executable() or "arp-scan", f"--interface={network.interface}", "--quiet", "--plain",
        "--ignoredups", "--numeric", "--format=${ip}\t${mac}",
        target or str(network.scan_network),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    if result.returncode:
        raise AppError(
            "Skanowanie ARP nie powiodło się. Sprawdź uprawnienie NET_RAW i wybrany interfejs.",
            503,
        )
    found: dict[str, dict[str, str]] = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        ip, raw_mac = fields
        try:
            if ip == network.address or ipaddress.IPv4Address(ip) not in network.scan_network:
                continue
            found[ip] = {"ip": ip, "mac": normalize_mac(raw_mac)}
        except (AppError, ipaddress.AddressValueError):
            continue
    return sorted(found.values(), key=lambda item: ipaddress.IPv4Address(item["ip"]))


def probe(ip: str, interface: str, source: str) -> bool:
    # A UDP packet prompts ARP resolution even when ICMP is blocked.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.bind((source, 0))
            sender.sendto(b"\0", (ip, 65534))
    except OSError:
        pass
    result = subprocess.run(
        ["ping", "-n", "-c", "1", "-W", "1", "-I", interface, ip],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=2,
        check=False,
    )
    return result.returncode == 0


def hostname_for(ip: str) -> str | None:
    """Try system reverse DNS, then local mDNS, without delaying a scan indefinitely."""
    for command in (("getent", "hosts", ip), ("avahi-resolve-address", ip)):
        if not shutil.which(command[0]):
            continue
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=1.5, check=False
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode:
            continue
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2 or parts[0] != ip:
                continue
            hostname = parts[1].rstrip(".")[:253]
            if hostname and hostname != ip and all(ord(char) >= 32 for char in hostname):
                return hostname
    return None


def scan(network: Network) -> list[dict[str, str]]:
    if arp_scan_executable():
        found = arp_scan(network)
    else:
        if not shutil.which("ping"):
            raise AppError("Brakuje polecenia arp-scan lub ping.", 503)
        hosts = [
            str(ip)
            for ip in network.scan_network.hosts()
            if str(ip) != network.address
        ]
        with ThreadPoolExecutor(max_workers=32) as executor:
            replies = list(executor.map(lambda ip: probe(ip, network.interface, network.address), hosts))
        found_by_ip = {item["ip"]: item for item in neighbors(network)}
        for ip, replied in zip(hosts, replies):
            if replied and ip not in found_by_ip:
                found_by_ip[ip] = {"ip": ip}
        found = sorted(found_by_ip.values(), key=lambda item: ipaddress.IPv4Address(item["ip"]))
    if found:
        with ThreadPoolExecutor(max_workers=min(32, len(found))) as executor:
            hostnames = list(executor.map(hostname_for, (item["ip"] for item in found)))
        for item, hostname in zip(found, hostnames):
            if hostname:
                item["hostname"] = hostname
    return found


def resolve_mac(ip: str, network: Network) -> str | None:
    if ipaddress.IPv4Address(ip) not in network.scan_network:
        return None
    if arp_scan_executable():
        return next((item["mac"] for item in arp_scan(network, ip) if item["ip"] == ip), None)
    probe(ip, network.interface, network.address)
    return next((item["mac"] for item in neighbors(network) if item["ip"] == ip), None)


def magic_packet(mac: str) -> bytes:
    device = bytes.fromhex(normalize_mac(mac).replace(":", ""))
    return b"\xff" * 6 + device * 16


def wake(mac: str, network: Network) -> None:
    packet = magic_packet(mac)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sender.bind((network.address, 0))
            sender.sendto(packet, (network.broadcast, 9))
    except OSError as exc:
        raise AppError(f"Nie udało się wysłać pakietu: {exc}", 503) from exc


def add_device(value: dict[str, Any]) -> dict[str, str]:
    ip = normalize_ip(str(value.get("ip", ""))) if value.get("ip") else ""
    if value.get("mac"):
        mac = normalize_mac(str(value["mac"]))
    elif ip:
        mac = resolve_mac(ip, network_from_request(value))
    else:
        mac = None
    if not mac:
        raise AppError("Podaj adres MAC. Nie udało się go ustalić z podanego IP.")
    name = str(value.get("name", "")).strip()[:60] or ip or mac
    return devices.add({"name": name, "ip": ip, "mac": mac})


class Devices:
    def __init__(self, path: Path = DATA_FILE):
        self.path = path
        self.lock = threading.Lock()

    def _load(self) -> list[dict[str, str]]:
        try:
            if not self.path.exists():
                return []
            data = json.loads(self.path.read_text())
            if not isinstance(data, list):
                raise ValueError("invalid format")
            return data
        except PermissionError as exc:
            raise AppError("Brak dostępu do data/devices.json. Sprawdź uprawnienia katalogu data.", 500) from exc
        except (OSError, ValueError) as exc:
            raise AppError("Nie udało się odczytać zapisanych urządzeń.", 500) from exc

    def read(self) -> list[dict[str, str]]:
        with self.lock:
            return self._load()

    def _write(self, items: list[dict[str, str]]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n")
            temporary.chmod(0o600)
            temporary.replace(self.path)
        except PermissionError as exc:
            raise AppError("Brak prawa zapisu w katalogu data. Sprawdź jego uprawnienia.", 500) from exc
        except OSError as exc:
            raise AppError("Nie udało się zapisać urządzenia w katalogu data.", 500) from exc

    def add(self, item: dict[str, str]) -> dict[str, str]:
        with self.lock:
            items = self._load()
            if any(existing["mac"] == item["mac"] for existing in items):
                raise AppError("To urządzenie jest już zapisane.", 409)
            item = {"id": uuid.uuid4().hex, **item}
            items.append(item)
            self._write(items)
            return item

    def remove(self, device_id: str) -> None:
        with self.lock:
            items = self._load()
            remaining = [item for item in items if item["id"] != device_id]
            if len(remaining) == len(items):
                raise AppError("Nie znaleziono urządzenia.", 404)
            self._write(remaining)


devices = Devices()


def state_payload() -> dict[str, Any]:
    try:
        networks = available_networks()
        network_error = None
    except (AppError, OSError, subprocess.TimeoutExpired) as exc:
        networks = []
        network_error = str(exc) if isinstance(exc, AppError) else "Sieć jest niedostępna."
    return {
        "network": networks[0].public() if networks else None,
        "networks": [item.public() for item in networks],
        "network_error": network_error,
        "devices": devices.read(),
    }


class Handler(BaseHTTPRequestHandler):
    def send_json(self, value: Any, status: int = 200) -> None:
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_asset(self, name: str, content_type: str) -> None:
        body = (ROOT / "static" / name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict[str, Any]:
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise AppError("Nieprawidłowe żądanie.") from exc
        if size <= 0 or size > 8192:
            raise AppError("Nieprawidłowy rozmiar żądania.")
        try:
            value = json.loads(self.rfile.read(size))
        except (UnicodeDecodeError, ValueError) as exc:
            raise AppError("Nieprawidłowe dane JSON.") from exc
        if not isinstance(value, dict):
            raise AppError("Nieprawidłowe dane JSON.")
        return value

    def handle_api(self, action) -> None:
        try:
            action()
        except AppError as exc:
            self.send_json({"error": str(exc)}, exc.status)
        except (OSError, subprocess.TimeoutExpired):
            self.send_json({"error": "Nie udało się wykonać operacji sieciowej."}, 503)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            return self.send_asset("index.html", "text/html; charset=utf-8")
        if path == "/style.css":
            return self.send_asset("style.css", "text/css; charset=utf-8")
        if path == "/app.js":
            return self.send_asset("app.js", "text/javascript; charset=utf-8")
        if path == "/favicon.svg":
            return self.send_asset("favicon.svg", "image/svg+xml")
        if path == "/api/state":
            return self.handle_api(lambda: self.send_json(state_payload()))
        self.send_error(404)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]

        def action() -> None:
            if path == "/api/scan":
                value = self.read_json() if self.headers.get("Content-Length") else {}
                network = network_from_request(value)
                return self.send_json({"devices": scan(network), "network": network.public()})
            if path == "/api/devices":
                value = self.read_json()
                item = add_device(value)
                return self.send_json({"device": item}, 201)
            if path == "/api/wake":
                value = self.read_json()
                mac = normalize_mac(str(value.get("mac", "")))
                network = network_from_request(value)
                wake(mac, network)
                return self.send_json({"ok": True})
            raise AppError("Nie znaleziono endpointu.", 404)

        self.handle_api(action)

    def do_DELETE(self) -> None:
        def action() -> None:
            if not self.path.startswith("/api/devices/"):
                raise AppError("Nie znaleziono endpointu.", 404)
            device_id = self.path.removeprefix("/api/devices/")
            if not re.fullmatch(r"[0-9a-f]{32}", device_id):
                raise AppError("Nieprawidłowy identyfikator urządzenia.")
            devices.remove(device_id)
            self.send_json({"ok": True})

        self.handle_api(action)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lokalny panel Wake-on-LAN")
    parser.add_argument("--host", default="127.0.0.1", help="Adres nasłuchiwania")
    parser.add_argument("--port", type=int, default=8000, help="Port HTTP")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Panel dostępny pod adresem http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
