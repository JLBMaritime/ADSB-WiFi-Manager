# Local test environment (Windows PC + WSL2)

The production Pi is remote and operational, so feeder changes are verified
here first. WSL2 Ubuntu runs real systemd, which lets us test everything
except the RTL-SDR/dump1090-fa hardware itself: TCP keepalive behaviour,
the stale-source backstop, endpoint backoff, and the `Type=notify` +
`WatchdogSec` watchdog integration.

## Pieces

| File | Purpose |
|---|---|
| `fake_dump1090.py` | SBS1 emitter on :30003 with a control port (:30099) to trigger failure modes: `wedge` (silent, connection kept open), `close` (clean FIN), `resume`, `status`, `quit` |
| `fake_endpoint.py` | TCP sink standing in for FlightAware/ADSB.lol; logs line counts so data flow is assertable |
| `wsl_setup.sh` | rsyncs the repo into `~/adsb-test` inside WSL and writes a test config (short `source_stale_after`, endpoints :40001/:40002) |
| `adsb-server-local.service` | WSL-only unit mirroring production `Type=notify`/`NotifyAccess=main`/`WatchdogSec=90` |

## Setup (inside WSL)

```bash
bash /mnt/c/dev/ADSB-WiFi-Manager/local/wsl_setup.sh
cd ~/adsb-test
python3 local/fake_endpoint.py --port 40001 &
python3 local/fake_endpoint.py --port 40002 &
python3 local/fake_dump1090.py &
python3 adsb_server/adsb_server.py        # or via the local systemd unit
```

## Scenarios

1. **Half-open source drop** (the original bug — silent wedge forever before
   the 2026-08 fix). Black-hole the source, then kill it so no FIN ever
   arrives:

   ```bash
   sudo iptables -A INPUT -p tcp --sport 30003 -j DROP
   pkill -f fake_dump1090; sleep 2
   sudo iptables -D INPUT -p tcp --sport 30003 -j DROP
   python3 local/fake_dump1090.py &
   ```

   Expected (fixed code): within ~160 s the kernel keepalive kills the dead
   socket, the feeder logs `Error receiving data: ... timed out` and
   reconnects. Set `source_stale_after` high (600) in the test config first
   if you want to prove keepalive alone catches it.

2. **Silent-but-healthy source** (dump1090 wedged, TCP fine):
   `echo wedge | nc -q1 127.0.0.1 30099` → after `source_stale_after`
   seconds the feeder logs `No SBS1 data for Ns -- reconnecting` and
   redials; `echo resume | ...` → data flows again.

3. **Clean drop:** `echo close | nc -q1 127.0.0.1 30099` → feeder logs
   `dump1090-fa connection lost` and reconnects within ~5 s.

4. **Endpoint backoff:** kill one `fake_endpoint` → feeder retries with
   1→30 s exponential backoff (no giving up); restart the endpoint → it
   reconnects without a feeder restart. Also works from cold: start the
   feeder with an endpoint down, bring it up later.

5. **systemd watchdog** (as root, unit installed per the comment in
   `adsb-server-local.service`):
   `kill -STOP $(systemctl show -p MainPID --value adsb-server-local)` →
   systemd logs `Watchdog timeout` and restarts the unit within ~165 s.
   `systemctl status` must show `active (running)` — proves READY=1.

Windows smoke test (no WSL): the same fakes and feeder run under Windows
Python — proves the code has no Linux-only assumptions (`tune_socket`
guards, `_sd_notify` no-op without `NOTIFY_SOCKET`).
