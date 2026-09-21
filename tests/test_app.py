import ipaddress
import os
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import app


class WakeboardTests(unittest.TestCase):
    def test_magic_packet_has_exact_wol_format(self):
        mac = bytes.fromhex("A0B1C2D3E4F5")
        self.assertEqual(app.magic_packet("a0-b1-c2-d3-e4-f5"), b"\xff" * 6 + mac * 16)

    def test_rejects_multicast_mac(self):
        with self.assertRaises(app.AppError):
            app.normalize_mac("A1:B2:C3:D4:E5:F6")

    def test_add_offline_device_with_mac_does_not_query_network(self):
        value = {"name": "Wyłączony PC", "ip": "192.168.1.44", "mac": "A0:B1:C2:D3:E4:F5"}
        with patch.object(app, "network_from_request") as select_network, patch.object(
            app.devices, "add", side_effect=lambda item: item
        ) as save:
            self.assertEqual(app.add_device(value), value)
            select_network.assert_not_called()
            save.assert_called_once_with(value)

    def test_state_keeps_saved_devices_when_network_is_unavailable(self):
        saved = [{"name": "Wyłączony PC", "ip": "", "mac": "A0:B1:C2:D3:E4:F5"}]
        with patch.object(app, "available_networks", side_effect=app.AppError("Brak sieci")), patch.object(
            app.devices, "read", return_value=saved
        ):
            self.assertEqual(app.state_payload(), {
                "network": None, "networks": [], "network_error": "Brak sieci", "devices": saved,
            })

    def test_storage_permission_error_is_not_reported_as_network_failure(self):
        devices = app.Devices(Path("data/devices.json"))
        with patch.object(Path, "mkdir", side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(app.AppError, "Brak prawa zapisu w katalogu data") as error:
                devices._write([])
        self.assertEqual(error.exception.status, 500)

    def test_large_network_scan_stays_within_local_24(self):
        routes = [{"dev": "eth0"}]
        addresses = [{
            "ifname": "eth0",
            "addr_info": [{"family": "inet", "scope": "global", "local": "192.168.14.27", "prefixlen": 16}],
        }]
        with patch.object(app, "run_ip", side_effect=[routes, addresses]):
            network = app.choose_network()
        self.assertEqual(network.scan_network, ipaddress.ip_network("192.168.14.0/24"))
        self.assertEqual(network.broadcast, "192.168.255.255")

    def test_manual_subnet_selects_matching_interface_and_limits_scan(self):
        networks = [
            app.Network("eth0", "192.168.0.20", "192.168.0.0/24", "192.168.0.255", ipaddress.ip_network("192.168.0.0/24")),
            app.Network("eth1", "10.0.4.12", "10.0.0.0/16", "10.0.255.255", ipaddress.ip_network("10.0.4.0/24")),
        ]
        selected = app.choose_network("10.0.5.19/28", networks=networks)
        self.assertEqual(selected.interface, "eth1")
        self.assertEqual(selected.scan_network, ipaddress.ip_network("10.0.5.16/28"))
        self.assertEqual(selected.broadcast, "10.0.255.255")
        with self.assertRaises(app.AppError):
            app.choose_network("10.0.5.16/28", interface="eth0", networks=networks)

    def test_manual_subnet_rejects_remote_or_oversized_range(self):
        network = app.Network(
            "eth0", "192.168.0.20", "192.168.0.0/24", "192.168.0.255",
            ipaddress.ip_network("192.168.0.0/24"),
        )
        for subnet in ("192.168.1.0/24", "192.168.0.0/23", "192.168.0.0", "fd00::/64"):
            with self.subTest(subnet=subnet), self.assertRaises(app.AppError):
                app.choose_network(subnet, networks=[network])

    @unittest.skipIf(os.name == "nt", "Test uprawnień plików wymaga Linuksa")
    def test_saved_devices_are_private_and_duplicate_mac_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data" / "devices.json"
            devices = app.Devices(path)
            item = devices.add({"name": "PC", "ip": "192.168.1.4", "mac": "A0:B1:C2:D3:E4:F5"})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(devices.read(), [item])
            with self.assertRaises(app.AppError):
                devices.add({"name": "PC 2", "ip": "", "mac": item["mac"]})
            devices.remove(item["id"])
            self.assertEqual(devices.read(), [])

    def test_hostname_uses_reverse_dns_result(self):
        result = CompletedProcess(
            ["getent", "hosts", "192.168.1.4"], 0, "192.168.1.4 pc.local.\n", ""
        )
        with patch.object(app.shutil, "which", return_value="/usr/bin/getent"), patch.object(
            app.subprocess, "run", return_value=result
        ):
            self.assertEqual(app.hostname_for("192.168.1.4"), "pc.local")

    def test_scan_includes_hostname_when_available(self):
        network = app.Network(
            "eth0", "192.168.1.2", "192.168.1.0/30", "192.168.1.3",
            ipaddress.ip_network("192.168.1.0/30"),
        )
        with patch.object(app.shutil, "which", side_effect=lambda name: "/usr/bin/ping" if name == "ping" else None), patch.object(
            app, "probe"
        ), patch.object(app, "neighbors", return_value=[
            {"ip": "192.168.1.1", "mac": "A0:B1:C2:D3:E4:F5"}
        ]), patch.object(app, "hostname_for", return_value="pc.local"):
            self.assertEqual(app.scan(network)[0]["hostname"], "pc.local")

    def test_scan_keeps_ping_reply_without_neighbor_mac(self):
        network = app.Network(
            "eth0", "192.168.1.2", "192.168.1.0/30", "192.168.1.3",
            ipaddress.ip_network("192.168.1.0/30"),
        )
        with patch.object(app.shutil, "which", side_effect=lambda name: "/usr/bin/ping" if name == "ping" else None), patch.object(
            app, "probe", return_value=True
        ), patch.object(app, "neighbors", return_value=[]), patch.object(
            app, "hostname_for", return_value="sensor.local"
        ):
            self.assertEqual(app.scan(network), [{"ip": "192.168.1.1", "hostname": "sensor.local"}])

    def test_arp_scan_finds_hosts_without_ping_or_neighbor_entry(self):
        network = app.Network(
            "eth0", "192.168.1.2", "192.168.1.0/29", "192.168.1.7",
            ipaddress.ip_network("192.168.1.0/29"),
        )
        output = (
            "192.168.1.4\ta0:b1:c2:d3:e4:f5\n"
            "192.168.1.4\ta0:b1:c2:d3:e4:f5\n"
            "192.168.1.2\ta0:b1:c2:d3:e4:f6\n"
            "192.168.2.1\ta0:b1:c2:d3:e4:f7\n"
        )
        result = CompletedProcess(["arp-scan"], 0, output, "")
        with patch.object(app.shutil, "which", return_value="/usr/bin/arp-scan"), patch.object(
            app.subprocess, "run", return_value=result
        ) as command, patch.object(app, "probe") as probe, patch.object(
            app, "neighbors"
        ) as neighbors, patch.object(app, "hostname_for", return_value=None):
            self.assertEqual(app.scan(network), [{"ip": "192.168.1.4", "mac": "A0:B1:C2:D3:E4:F5"}])
            self.assertIn("--interface=eth0", command.call_args.args[0])
            self.assertEqual(command.call_args.args[0][-1], "192.168.1.0/29")
            probe.assert_not_called()
            neighbors.assert_not_called()

    def test_resolve_mac_queries_only_requested_ip_with_arp(self):
        network = app.Network(
            "eth0", "192.168.1.2", "192.168.1.0/29", "192.168.1.7",
            ipaddress.ip_network("192.168.1.0/29"),
        )
        result = CompletedProcess(["arp-scan"], 0, "192.168.1.4\ta0:b1:c2:d3:e4:f5\n", "")
        with patch.object(app.shutil, "which", return_value="/usr/bin/arp-scan"), patch.object(
            app.subprocess, "run", return_value=result
        ) as command:
            self.assertEqual(app.resolve_mac("192.168.1.4", network), "A0:B1:C2:D3:E4:F5")
            self.assertEqual(command.call_args.args[0][-1], "192.168.1.4")

    def test_arp_scan_reports_permission_failure(self):
        network = app.Network(
            "eth0", "192.168.1.2", "192.168.1.0/29", "192.168.1.7",
            ipaddress.ip_network("192.168.1.0/29"),
        )
        result = CompletedProcess(["arp-scan"], 1, "", "Operation not permitted")
        with patch.object(app.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(app.AppError, "NET_RAW"):
                app.arp_scan(network)


if __name__ == "__main__":
    unittest.main()
