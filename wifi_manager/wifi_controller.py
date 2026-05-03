#!/usr/bin/env python3
"""
WiFi Controller — Manages WiFi connections on wlan0 via NetworkManager.
Part of JLBMaritime ADS-B & Wi-Fi Management System.

REWRITE NOTE (v2):
    The original v1 implementation drove wlan0 via the *legacy* wireless
    toolset:
        sudo iwlist scan          # to scan
        sudo wpa_cli list_networks # to list saved
        sudo wpa_cli add_network   # to connect
        sudo dhclient              # to get an IP
    On a Bookworm + NetworkManager Pi this fails for two unrelated
    reasons that combine to give silent empty lists:

      1.  Our `/etc/sudoers.d/adsb-wifi-manager` only whitelists
          `nmcli`, `iw`, `ip`, and a small `systemctl` allow-list.
          `iwlist` / `wpa_cli` / `dhclient` are NOT in there, so
          `sudo wpa_cli ...` hangs the subprocess waiting for a
          password it can never provide and returns rc!=0 with
          empty stdout.  The Python `try/except` catches the
          parse-of-empty-output silently and the API returns [].

      2.  Even if (1) were fixed, `wpa_cli` against an NM-managed
          interface returns nothing useful: NetworkManager owns the
          supplicant control socket and exposes its own profile
          system via `nmcli connection`, NOT via `wpa_supplicant.conf`.
          So an Imager-preconfigured profile (named `preconfigured`,
          containing the operator's SSID) is invisible to wpa_cli.

    This rewrite drives everything via `nmcli`, the same binary the
    rest of the project (install.sh, the AP, the watchdog) already
    uses.  It correctly surfaces the `preconfigured` profile (mapped
    to its real SSID for display), correctly scans (modern NM does
    its own background scans plus an on-demand `nmcli device wifi
    rescan`), and correctly de-duplicates by SSID, hides hidden /
    null-byte SSIDs, and reports a stable signal/security/frequency
    triple to the web UI.

    Public API (consumed by `web_interface/app.py`) is preserved
    exactly:
        scan_networks()      -> List[{ssid, signal, encrypted, security, freq}]
        get_saved_networks() -> List[{id, ssid}]
        get_current_network()-> {ssid, ip, signal} | None
        connect_to_network(ssid, password=None) -> bool
        forget_network(ssid) -> bool
        get_ip_address()     -> str | None
        ping_test(host, count) -> {success, output}
        get_diagnostics()    -> {...}
"""

import os
import re
import subprocess
import time

# nmcli's terse (-t) output uses ':' as a column separator.  Embedded
# colons in field values are escaped as '\:' -- so we MUST split on
# unescaped colons only, then unescape each cell.  This regex matches
# a ':' that is NOT preceded by a backslash.
_NMCLI_COLON = re.compile(r'(?<!\\):')


def _split_nmcli(line: str):
    """Split an `nmcli -t` row on unescaped colons and unescape each cell.

    nmcli's `-t` (terse) output uses ':' as the column separator and
    backslash-escapes any literal ':' or '\\' that appear inside a cell.
    Order matters: we MUST unescape '\\\\' (literal backslash) BEFORE
    '\\:' (escaped colon), otherwise '\\\\:' (a literal backslash next to
    a real separator) would round-trip through the wrong order and turn
    into '\\:' (an escaped colon) by accident.  In practice nmcli
    rarely emits literal backslashes in SSIDs, but the ordering bug
    has bitten parsers in adjacent projects -- belt and braces.
    """
    cells = _NMCLI_COLON.split(line)
    out = []
    for cell in cells:
        cell = cell.replace('\\\\', '\x00')   # placeholder
        cell = cell.replace('\\:', ':')
        cell = cell.replace('\x00', '\\')
        out.append(cell)
    return out



class WiFiController:
    def __init__(self, interface: str = 'wlan0'):
        self.interface = interface

    # ----------------------------------------------------------------
    # Internal helper
    # ----------------------------------------------------------------
    def _nmcli(self, *args, timeout: int = 15) -> subprocess.CompletedProcess:
        """
        Run `sudo nmcli ...` with sane defaults.  We always use sudo
        because the web UI runs as the unprivileged `adsb` user, and
        many `nmcli connection` / `nmcli device wifi connect` calls
        require root.  The sudoers drop-in installed by install.sh
        permits NOPASSWD for /usr/bin/nmcli.
        """
        cmd = ['sudo', '-n', 'nmcli'] + list(args)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    # ----------------------------------------------------------------
    # Scan
    # ----------------------------------------------------------------
    def scan_networks(self):
        """
        Scan wlan0 (NEVER wlan1 -- that's the AP and a master-mode
        radio cannot scan).  Returns the list deduped by SSID, sorted
        by signal strength descending, with hidden / null-byte SSIDs
        filtered out.
        """
        try:
            # Trigger a fresh scan (best-effort -- if the radio is
            # busy NM will return rc=10 'scan was rejected', that's
            # fine because it has cached results from its background
            # scans every 30-60 s).
            self._nmcli('device', 'wifi', 'rescan', 'ifname', self.interface, timeout=15)
            time.sleep(1.5)

            r = self._nmcli('-t', '-f', 'IN-USE,SSID,SIGNAL,SECURITY,FREQ',
                            'device', 'wifi', 'list', 'ifname', self.interface,
                            timeout=15)
            if r.returncode != 0:
                # Final fallback: list across all interfaces.  Better
                # to show the user *something* than to refuse to scan
                # because of a transient ifname race.
                r = self._nmcli('-t', '-f', 'IN-USE,SSID,SIGNAL,SECURITY,FREQ',
                                'device', 'wifi', 'list',
                                timeout=15)

            seen = set()
            results = []
            for raw in r.stdout.splitlines():
                if not raw.strip():
                    continue
                parts = _split_nmcli(raw)
                if len(parts) < 5:
                    continue
                in_use, ssid, signal_s, security, freq_s = parts[:5]
                ssid = ssid.strip()
                if not ssid:                        # hidden network
                    continue
                if '\x00' in ssid or '\\x00' in ssid:
                    continue
                if any(ord(c) < 32 and c not in '\t' for c in ssid):
                    continue
                # Hide our own AP from the wlan0 scan results -- it's
                # the broadcast on wlan1 leaking into wlan0's scan
                # because the two share the same airspace, and joining
                # ourselves would brick the AP.
                if ssid == 'JLBMaritime-ADSB':
                    continue
                if ssid in seen:
                    continue
                seen.add(ssid)

                try:
                    signal = int(signal_s)
                except ValueError:
                    signal = 0
                # Frequency: nmcli prints "5180 MHz" or just "2412"
                freq_match = re.search(r'(\d+)', freq_s)
                freq_mhz = int(freq_match.group(1)) if freq_match else 0
                band = '5GHz' if freq_mhz >= 5000 else ('2.4GHz' if freq_mhz else '?')

                results.append({
                    'ssid': ssid,
                    'signal': signal,
                    'encrypted': bool(security and security not in ('', '--')),
                    'security': security or '',
                    'frequency': freq_mhz,
                    'band': band,
                    'in_use': in_use == '*',
                })

            return sorted(results, key=lambda x: x['signal'], reverse=True)

        except subprocess.TimeoutExpired:
            print("scan_networks: nmcli timed out")
            return []
        except Exception as e:
            print(f"Error scanning networks: {e}")
            return []

    # ----------------------------------------------------------------
    # Saved profiles
    # ----------------------------------------------------------------
    def get_saved_networks(self):
        """
        Return every 802-11-wireless NM connection profile EXCEPT the
        AP (`adsb-hotspot`).  We expose the SSID stored INSIDE the
        profile, not the profile name -- so the Imager-preconfigured
        profile (named `preconfigured`) shows up as the real SSID
        (e.g. `Team L-B`) in the web UI.
        """
        try:
            r = self._nmcli('-t', '-f', 'NAME,TYPE', 'connection', 'show',
                            timeout=10)
            networks = []
            seen_ssid = set()
            for raw in r.stdout.splitlines():
                if not raw.strip():
                    continue
                parts = _split_nmcli(raw)
                if len(parts) < 2:
                    continue
                name, ctype = parts[0], parts[1]
                if ctype != '802-11-wireless':
                    continue
                if name == 'adsb-hotspot':
                    continue                    # never expose the AP
                ssid = self._get_profile_ssid(name) or name
                if ssid in seen_ssid:
                    # Two profiles with the same SSID is rare but
                    # possible (e.g. one explicit + one Imager
                    # preconfigured).  Only show the first.
                    continue
                seen_ssid.add(ssid)
                networks.append({'id': name, 'ssid': ssid})
            return networks
        except subprocess.TimeoutExpired:
            print("get_saved_networks: nmcli timed out")
            return []
        except Exception as e:
            print(f"Error getting saved networks: {e}")
            return []

    def _get_profile_ssid(self, profile_name: str) -> str:
        """Return the SSID stored inside an NM connection profile, or ''."""
        try:
            r = self._nmcli('-g', '802-11-wireless.ssid', 'connection', 'show',
                            profile_name, timeout=5)
            return r.stdout.strip()
        except Exception:
            return ''

    # ----------------------------------------------------------------
    # Current
    # ----------------------------------------------------------------
    def get_current_network(self):
        """Return what wlan0 is currently associated with (or None).

        Implementation note: an earlier version of this method used
            `nmcli -t -f GENERAL.CONNECTION,GENERAL.STATE,IP4.ADDRESS \
                  device show <iface>`
        which superficially looks fine but is fragile across NM
        versions: `IP4.ADDRESS` is a section *prefix* (the actual key
        is `IP4.ADDRESS[1]`), and on NM 1.42+ the `-f` filter against
        `device show` for that prefix sometimes produces an rc!=0 with
        empty stdout, which our error handler then maps to None ->
        the UI shows "Not connected" even when wlan0 is happily
        associated.

        The form below uses `nmcli -t -f DEVICE,STATE,CONNECTION
        device status` which has been stable since NM 1.10 and yields
        exactly one tabular row per interface.  We get the IP from
        `ip -4 addr show` (already used by get_ip_address) -- no
        nmcli ambiguity at all.
        """
        try:
            # 1) Identify the active connection name on our interface.
            r = self._nmcli('-t', '-f', 'DEVICE,STATE,CONNECTION',
                            'device', 'status', timeout=10)
            conn_name = None
            for raw in r.stdout.splitlines():
                parts = _split_nmcli(raw)
                if len(parts) < 3:
                    continue
                dev, state, name = parts[0], parts[1], parts[2]
                if dev != self.interface:
                    continue
                # State strings: 'connected', 'connecting', 'disconnected',
                # 'unavailable', 'unmanaged'.  Only 'connected' counts.
                if state != 'connected':
                    return None
                if name and name != '--':
                    conn_name = name
                break
            if not conn_name:
                return None

            # 2) IP from `ip -4 addr show wlan0` -- canonical and never
            #    ambiguous.
            ip = self.get_ip_address() or 'Unknown'

            # 3) SSID is what the operator actually cares about; the NM
            #    profile name might be 'preconfigured' (RPi imager) or
            #    something operator-set.  Resolve to the SSID stored
            #    inside the profile, falling back to the profile name.
            ssid = self._get_profile_ssid(conn_name) or conn_name

            # 4) Signal: pick the row marked '*' (in-use) from the scan
            #    list.  Best-effort -- if the scan call fails for any
            #    reason we just return signal=0 rather than failing the
            #    whole call.
            signal = 0
            try:
                s = self._nmcli('-t', '-f', 'IN-USE,SIGNAL', 'device', 'wifi',
                                'list', 'ifname', self.interface, timeout=10)
                if s.returncode == 0:
                    for raw in s.stdout.splitlines():
                        parts = _split_nmcli(raw)
                        if len(parts) >= 2 and parts[0] == '*':
                            try:
                                signal = int(parts[1])
                            except ValueError:
                                pass
                            break
            except Exception:
                pass

            return {
                'ssid': ssid,
                'ip': ip,
                'signal': signal,
            }
        except subprocess.TimeoutExpired:
            print("get_current_network: nmcli timed out")
            return None
        except Exception as e:
            print(f"Error getting current network: {e}")
            return None

    # ----------------------------------------------------------------
    # Connect
    # ----------------------------------------------------------------
    def connect_to_network(self, ssid: str, password: str = None) -> bool:
        """
        Idempotent connect.  `nmcli device wifi connect <SSID>` will:
          * activate an existing matching profile if one exists, OR
          * create a new profile with the given password and activate it.
        We do NOT delete any existing profile first -- so re-connecting
        to a saved network without re-typing the password works.

        If the operator passes a NEW password for an existing SSID
        we modify-in-place rather than create-duplicate, which avoids
        leaving two profiles fighting on autoconnect.
        """
        try:
            if not ssid or not ssid.strip():
                return False
            ssid = ssid.strip()

            # Find existing profile (if any) for this SSID
            existing_profile = None
            for net in self.get_saved_networks():
                if net['ssid'] == ssid:
                    existing_profile = net['id']
                    break

            # Caller passed a password and a profile already exists -- update it.
            if existing_profile and password:
                self._nmcli('connection', 'modify', existing_profile,
                            'wifi-sec.key-mgmt', 'wpa-psk',
                            'wifi-sec.psk', password, timeout=15)

            # Activate.
            if existing_profile:
                r = self._nmcli('connection', 'up', existing_profile,
                                'ifname', self.interface, timeout=45)
            else:
                cmd = ['device', 'wifi', 'connect', ssid,
                       'ifname', self.interface]
                if password:
                    cmd += ['password', password]
                r = self._nmcli(*cmd, timeout=45)

            if r.returncode != 0:
                print(f"connect_to_network: nmcli rc={r.returncode}: "
                      f"{r.stderr.strip() or r.stdout.strip()}")
                return False
            return True

        except subprocess.TimeoutExpired:
            print("connect_to_network: nmcli timed out")
            return False
        except Exception as e:
            print(f"Error connecting to network: {e}")
            return False

    # ----------------------------------------------------------------
    # Forget
    # ----------------------------------------------------------------
    def forget_network(self, ssid: str) -> bool:
        """Delete the NM profile that holds this SSID."""
        try:
            for net in self.get_saved_networks():
                if net['ssid'] == ssid:
                    r = self._nmcli('connection', 'delete', net['id'], timeout=10)
                    return r.returncode == 0
            return False
        except subprocess.TimeoutExpired:
            print("forget_network: nmcli timed out")
            return False
        except Exception as e:
            print(f"Error forgetting network: {e}")
            return False

    # ----------------------------------------------------------------
    # Helpers used by the web UI / diagnostics page
    # ----------------------------------------------------------------
    def get_ip_address(self):
        try:
            result = subprocess.run(['ip', '-4', 'addr', 'show', self.interface],
                                    capture_output=True, text=True, timeout=5)
            m = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', result.stdout)
            return m.group(1) if m else None
        except Exception as e:
            print(f"Error getting IP: {e}")
            return None

    def ping_test(self, host: str = '8.8.8.8', count: int = 4):
        try:
            result = subprocess.run(
                ['ping', '-c', str(count), '-W', '2', host],
                capture_output=True, text=True, timeout=count * 3 + 5)
            return {'success': result.returncode == 0, 'output': result.stdout}
        except Exception as e:
            return {'success': False, 'output': f"Error: {e}"}

    def get_diagnostics(self):
        try:
            d = {}
            r = subprocess.run(['ip', 'link', 'show', self.interface],
                               capture_output=True, text=True, timeout=5)
            d['interface_up'] = 'UP' in r.stdout

            r = subprocess.run(['ip', 'addr', 'show', self.interface],
                               capture_output=True, text=True, timeout=5)
            d['ip_config'] = r.stdout

            r = subprocess.run(['ip', 'route', 'show', 'default'],
                               capture_output=True, text=True, timeout=5)
            m = re.search(r'default via (\d+\.\d+\.\d+\.\d+)', r.stdout)
            d['gateway'] = m.group(1) if m else 'None'

            d['dns'] = []
            if os.path.exists('/etc/resolv.conf'):
                with open('/etc/resolv.conf', 'r') as f:
                    for line in f:
                        if line.startswith('nameserver'):
                            d['dns'].append(line.split()[1])
            return d
        except Exception as e:
            return {'error': str(e)}
