#!/usr/bin/env bash
# Full local verification matrix for the patched adsb_server.py.
# Run INSIDE WSL as root:  bash ~/adsb-test/local/wsl_test_matrix.sh [scenarios]
# e.g. `... wsl_test_matrix.sh B C D P` or no args for all (~15 min).
# Assumes wsl_setup.sh has synced the PATCHED working copy to ~/adsb-test.
set -u
cd "$HOME/adsb-test"
mkdir -p testlogs
PASS=0; FAIL=0
CONF=config/adsb_server_config.conf
SEL="${*:-B C D A P E}"
want() { case " $SEL " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }

say()  { echo; echo "########## $*"; }
ok()   { echo "PASS: $*"; PASS=$((PASS+1)); }
bad()  { echo "FAIL: $*"; FAIL=$((FAIL+1)); }

cleanup_procs() {
    pkill -f fake_dump1090.py 2>/dev/null
    pkill -f fake_endpoint.py 2>/dev/null
    pkill -f adsb_server/adsb_server.py 2>/dev/null
    iptables -D INPUT -p tcp --sport 30003 -j DROP 2>/dev/null
    sleep 1
}

start_stack() {  # $1 = source_stale_after value
    cleanup_procs
    sed -i "s/^source_stale_after = .*/source_stale_after = $1/" "$CONF"
    rm -f logs/adsb_server.log
    nohup python3 local/fake_endpoint.py --port 40001 > testlogs/ep1.log 2>&1 &
    nohup python3 local/fake_endpoint.py --port 40002 > testlogs/ep2.log 2>&1 &
    nohup python3 local/fake_dump1090.py --interval 0.5 > testlogs/dump.log 2>&1 &
    sleep 2
    nohup python3 adsb_server/adsb_server.py > testlogs/feeder.log 2>&1 &
    sleep 6
}

# Wait until pattern appears in feeder log (args: pattern, timeout_s)
wait_log() {
    local end=$(( $(date +%s) + $2 ))
    while [ "$(date +%s)" -lt "$end" ]; do
        grep -qE "$1" testlogs/feeder.log && return 0
        sleep 2
    done
    return 1
}

ep_count() { grep 'stats:' "testlogs/$1.log" | tail -1 | sed 's/.*lines=\([0-9]*\).*/\1/'; }

if want B; then
say "Scenario B: silent-but-connected source -> stale backstop (threshold 20s)"
start_stack 20
grep -q "Connected to dump1090-fa" testlogs/feeder.log || bad "B: no initial connect"
echo wedge | nc -q1 127.0.0.1 30099
if wait_log "No SBS1 data for [0-9]+s" 70; then ok "B: stale backstop fired"; else bad "B: backstop never fired"; fi
echo resume | nc -q1 127.0.0.1 30099
B1=$(ep_count ep1); sleep 12; B2=$(ep_count ep1)
if [ "${B2:-0}" -gt "${B1:-0}" ]; then ok "B: data resumed after redial"; else bad "B: no data after resume (${B1:-?}->${B2:-?})"; fi
fi

if want C; then
say "Scenario C: clean drop (FIN) -> immediate reconnect"
start_stack 300
echo close | nc -q1 127.0.0.1 30099
if wait_log "dump1090-fa connection lost" 40; then ok "C: clean drop detected"; else bad "C: clean drop not detected"; fi
sleep 8
C=$(grep -c "Connected to dump1090-fa" testlogs/feeder.log)
if [ "$C" -ge 2 ]; then ok "C: reconnected ($C connects)"; else bad "C: no reconnect"; fi
fi

if want D; then
say "Scenario D: endpoint death -> backoff retries -> recovery; cold start with endpoint down"
start_stack 300
pkill -f 'fake_endpoint.py --port 40002'
sleep 3
if wait_log "Failed to send to 127.0.0.1:40002" 30; then ok "D: send failure detected"; else bad "D: send failure not detected"; fi
sleep 10   # let backoff climb a little
nohup python3 local/fake_endpoint.py --port 40002 > testlogs/ep2b.log 2>&1 &
if wait_log "Reconnected to endpoint 127.0.0.1:40002" 45; then ok "D: endpoint reconnected after restart"; else bad "D: endpoint never reconnected"; fi
D1=$(ep_count ep2b); sleep 12; D2=$(ep_count ep2b)
if [ "${D2:-0}" -gt "${D1:-0}" ]; then ok "D: data flowing to revived endpoint"; else bad "D: no data to revived endpoint"; fi
# Cold start: feeder starts while 40002 is down
pkill -f 'fake_endpoint.py --port 40002'; sleep 2
pkill -f adsb_server/adsb_server.py; sleep 1
nohup python3 adsb_server/adsb_server.py > testlogs/feeder.log 2>&1 &
sleep 6
nohup python3 local/fake_endpoint.py --port 40002 > testlogs/ep2c.log 2>&1 &
if wait_log "(Connected|Reconnected) to endpoint 127.0.0.1:40002" 60; then
    ok "D: cold-start endpoint picked up once available"
else bad "D: cold-start endpoint never connected"; fi
fi

if want A; then
say "Scenario A: TRUE half-open source -> kernel keepalive detects (~160s)"
start_stack 600   # stale backstop out of the way; keepalive must catch it
iptables -A INPUT -p tcp --sport 30003 -j DROP
pkill -f fake_dump1090.py
sleep 1
nohup python3 local/fake_dump1090.py --interval 0.5 > testlogs/dump2.log 2>&1 &
if wait_log "Error receiving data" 260; then ok "A: keepalive killed dead socket"; else bad "A: keepalive never fired"; fi
iptables -D INPUT -p tcp --sport 30003 -j DROP
REC=no
END=$(( $(date +%s) + 60 ))
while [ "$(date +%s)" -lt "$END" ]; do
    [ "$(grep -c 'Connected to dump1090-fa' testlogs/feeder.log)" -ge 2 ] && REC=yes && break
    sleep 3
done
if [ "$REC" = yes ]; then ok "A: reconnected after network restored"; else bad "A: no reconnect after restore"; fi
A1=$(ep_count ep1); sleep 12; A2=$(ep_count ep1)
if [ "${A2:-0}" -gt "${A1:-0}" ]; then ok "A: end-to-end data resumed"; else bad "A: data did not resume"; fi
fi

if want P; then
say "Pinger gate unit test"
cleanup_procs
if python3 local/test_pinger_gate.py; then ok "pinger gate"; else bad "pinger gate"; fi
fi

if want E; then
say "Scenario E: systemd watchdog end-to-end (Type=notify, WatchdogSec=90)"
start_stack 300
pkill -f adsb_server/adsb_server.py; sleep 1
sed "s|%HOME%|$HOME|g" local/adsb-server-local.service > /etc/systemd/system/adsb-server-local.service
systemctl daemon-reload
systemctl restart adsb-server-local
sleep 5
if [ "$(systemctl is-active adsb-server-local)" = "active" ]; then
    ok "E: unit active (READY=1 accepted)"
else bad "E: unit not active: $(systemctl is-active adsb-server-local)"; fi
MAIN=$(systemctl show -p MainPID --value adsb-server-local)
kill -STOP "$MAIN"
STOPPED_AT=$(date +%s)
RECOVERED=no
while [ $(( $(date +%s) - STOPPED_AT )) -lt 200 ]; do
    NEW=$(systemctl show -p MainPID --value adsb-server-local)
    if [ -n "$NEW" ] && [ "$NEW" != "$MAIN" ] && [ "$NEW" != "0" ]; then RECOVERED=yes; break; fi
    sleep 5
done
if [ "$RECOVERED" = yes ]; then ok "E: watchdog killed and restarted wedged process (pid $MAIN -> $NEW)"; else bad "E: no watchdog restart in 200s"; fi
journalctl -u adsb-server-local --since "-5 min" --no-pager | grep -i "watchdog" | tail -2
systemctl stop adsb-server-local
systemctl disable adsb-server-local 2>/dev/null
rm -f /etc/systemd/system/adsb-server-local.service
systemctl daemon-reload
fi
cleanup_procs

echo
echo "=============================="
echo "RESULTS: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
