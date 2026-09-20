import ipaddress
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
        with patch.object(app.shutil, "which", return_value="/usr/bin/ping"), patch.object(
            app, "probe"
        ), patch.object(app, "neighbors", return_value=[
            {"ip": "192.168.1.1", "mac": "A0:B1:C2:D3:E4:F5"}
        ]), patch.object(app, "hostname_for", return_value="pc.local"):
            self.assertEqual(app.scan(network)[0]["hostname"], "pc.local")


if __name__ == "__main__":
    unittest.main()
