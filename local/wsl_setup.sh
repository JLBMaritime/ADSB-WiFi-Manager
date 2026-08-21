#!/usr/bin/env bash
# Sync the repo working copy into ~/adsb-test inside WSL and install a test
# config. Run INSIDE WSL:  bash /mnt/c/dev/ADSB-WiFi-Manager/local/wsl_setup.sh
#
# Everything runs from ~/adsb-test so the Windows working copy is never
# touched by the feeder (config autocreation, logs/ writes).
set -euo pipefail

SRC="${1:-/mnt/c/dev/ADSB-WiFi-Manager}"
DEST="$HOME/adsb-test"

mkdir -p "$DEST"
rsync -a --delete --exclude .git --exclude logs --exclude __pycache__ \
    "$SRC/" "$DEST/"
mkdir -p "$DEST/config" "$DEST/logs"

# Test config: local fakes as source and endpoints, short stale threshold
# (source_stale_after is a patched-code knob; unpatched code ignores it).
cat > "$DEST/config/adsb_server_config.conf" <<'EOF'
[Dump1090]
host = 127.0.0.1
sbs1_port = 30003
json_port = 8080
source_stale_after = 20

[Output]
format = sbs1

[Filter]
mode = all
icao_list =
altitude_filter_enabled = false
max_altitude = 10000

[Endpoints]
count = 2
endpoint_0_name = local-sink-1
endpoint_0_ip = 127.0.0.1
endpoint_0_port = 40001
endpoint_1_name = local-sink-2
endpoint_1_ip = 127.0.0.1
endpoint_1_port = 40002
EOF

# psutil is the feeder's only non-stdlib import
python3 -c 'import psutil' 2>/dev/null || {
    echo "installing python3-psutil..."
    sudo apt-get install -y python3-psutil >/dev/null
}

echo "ready: $DEST"
echo "  source:    python3 $DEST/local/fake_dump1090.py"
echo "  endpoints: python3 $DEST/local/fake_endpoint.py --port 40001 (and 40002)"
echo "  feeder:    python3 $DEST/adsb_server/adsb_server.py"
