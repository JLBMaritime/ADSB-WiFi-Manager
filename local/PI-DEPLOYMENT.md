# Deploying the reconnect fix to the operational Pi (remote, minimal-touch)

The production Pi is remote and cannot be recovered on-site, so this fix is
deployed by copying files — **do not re-run `install.sh` on it** (the
installer touches NetworkManager/hostapd, which is the remote-access risk).
`adsb-server.service` is independent of SSH, the web UI, and the hotspot:
the worst case at every stage below is a down *feed*, never a lost Pi.

All local tests in `wsl_test_matrix.sh` must pass before starting.

## Stage 1 — code only (unit file unchanged)

The new code is fully compatible with the old `Type=simple` unit
(`_sd_notify` no-ops when `NOTIFY_SOCKET` is unset).

```bash
ssh <pi>
sudo cp /opt/adsb-wifi-manager/adsb_server/adsb_server.py \
        /opt/adsb-wifi-manager/adsb_server/adsb_server.py.bak
# transfer the new adsb_server.py (scp/sftp), then:
sudo cp ~/adsb_server.py /opt/adsb-wifi-manager/adsb_server/adsb_server.py
sudo systemctl restart adsb-server
journalctl -u adsb-server -f     # expect normal startup + data flow
```

Rollback: `sudo cp .../adsb_server.py.bak .../adsb_server.py && sudo systemctl restart adsb-server`

**Soak ≥ 24 h** before Stage 2. What Stage 1 already fixes: TCP keepalive
(half-open source death self-heals in ~160 s), the 300 s stale-source
backstop, and endpoint reconnects with backoff that no longer give up.

## Stage 2 — enable the systemd watchdog

```bash
sudo systemctl edit --full adsb-server        # or edit the file directly
#   Type=simple            ->  Type=notify
#   (add) NotifyAccess=main
#   (add) WatchdogSec=90
sudo systemctl daemon-reload
sudo systemctl restart adsb-server
systemctl show adsb-server -p Type,WatchdogUSec,NotifyAccess
#   expect: Type=notify / WatchdogUSec=1min 30s / NotifyAccess=main
systemctl status adsb-server                  # must be 'active (running)'
```

Rollback: revert the three lines, `daemon-reload`, restart.

## Afterwards

- `sudo git -C /opt/adsb-wifi-manager pull --ff-only` to sync the tree with
  the committed fix (no scripts executed). Future fresh installs get the
  new unit from `install.sh` automatically.
- Optional on-Pi confidence checks (risk only the feed): black-hole test
  (`iptables -A INPUT -p tcp --sport 30003 -j DROP` + restart dump1090-fa,
  expect recovery within ~3 min, then remove the rule) and watchdog test
  (`sudo kill -STOP $(systemctl show -p MainPID --value adsb-server)`,
  expect auto-restart within ~3 min).
