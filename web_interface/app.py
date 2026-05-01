#!/usr/bin/env python3
"""
Web Application - Flask-based management interface
Part of JLBMaritime ADS-B & Wi-Fi Management System
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response, make_response
import sys
import os
import secrets
import configparser
import socket
import subprocess
import json
from functools import wraps
from datetime import datetime, timedelta
from werkzeug.middleware.proxy_fix import ProxyFix

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from wifi_manager.wifi_controller import WiFiController

app = Flask(__name__)

# --------------------------------------------------------------------------
# Persistent SECRET_KEY
# Was: hard-coded string in source.  Anyone with the repo could forge any
# session cookie.  Persist a random key at /opt/adsb-wifi-manager/secret_key
# (mode 600), regenerate only if missing.  Same pattern as AIS-WiFi-Manager.
# --------------------------------------------------------------------------
_SECRET_KEY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'secret_key')
try:
    if not os.path.exists(_SECRET_KEY_PATH):
        with open(_SECRET_KEY_PATH, 'wb') as _f:
            _f.write(secrets.token_bytes(48))
        try:
            os.chmod(_SECRET_KEY_PATH, 0o600)
        except OSError:
            pass
    with open(_SECRET_KEY_PATH, 'rb') as _f:
        app.secret_key = _f.read()
except OSError:
    # Fall back to ephemeral (sessions invalidate every restart).
    app.secret_key = secrets.token_bytes(48)

# Production mode detection
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PRODUCTION_MODE = os.path.exists(os.path.join(BASE_DIR, '.production_mode'))

# Configure for production if behind reverse proxy
if PRODUCTION_MODE:
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1,
        x_port=1,
        x_prefix=1
    )
    
    # Enhanced session security for production
    app.config.update(
        SESSION_COOKIE_SECURE=True,  # HTTPS only
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12)
    )

# Configuration paths
ADSB_CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'adsb_server_config.conf')
WEB_CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'web_config.conf')
LOG_PATH = os.path.join(BASE_DIR, 'logs', 'adsb_server.log')


# Initialize WiFi controller
wifi = WiFiController('wlan0')

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Load credentials from config
        config = configparser.ConfigParser()
        if os.path.exists(WEB_CONFIG_PATH):
            config.read(WEB_CONFIG_PATH)
            stored_username = config.get('Auth', 'username', fallback='JLBMaritime')
            stored_password = config.get('Auth', 'password', fallback='Admin')
        else:
            stored_username = 'JLBMaritime'
            stored_password = 'Admin'
            
        if username == stored_username and password == stored_password:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid credentials')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout"""
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    """Main dashboard page"""
    return render_template('index.html')

@app.route('/health')
def health_check():
    """Health check endpoint for monitoring (no auth required)"""
    return jsonify({
        'status': 'healthy',
        'production_mode': PRODUCTION_MODE,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/healthz')
def healthz():
    """Liveness probe used by install.sh post-flight, by `adsb-cli doctor`,
    and by external uptime checkers (e.g. Uptime Kuma over Tailscale).
    Returns 200 when:
      * the dump1090-fa SBS1 socket is reachable on 127.0.0.1:30003, AND
      * the adsb-server unit is in `active` state.
    Otherwise 503 with a JSON body explaining which check failed.
    No @login_required by design.
    """
    checks = {}
    overall = True

    # 1) SBS1 socket reachable?
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(('127.0.0.1', 30003))
        checks['sbs1_30003'] = 'ok'
    except OSError as e:
        checks['sbs1_30003'] = f'fail: {e!s}'
        overall = False

    # 2) adsb-server unit active?
    try:
        rc = subprocess.run(['systemctl', 'is-active', 'adsb-server'],
                            capture_output=True, text=True, timeout=2)
        active = (rc.stdout.strip() == 'active')
        checks['adsb_server_unit'] = 'ok' if active else f'fail: {rc.stdout.strip()}'
        overall = overall and active
    except Exception as e:
        checks['adsb_server_unit'] = f'fail: {e!s}'
        overall = False

    body = {'status': 'ok' if overall else 'fail', 'checks': checks,
            'timestamp': datetime.now().isoformat()}
    return jsonify(body), (200 if overall else 503)


# ============================================================================
# CAPTIVE-PORTAL PROBE RESPONDERS
# ============================================================================
# DO NOT add @login_required to any route in this block.
#
# When a phone joins the AP it immediately fires probes at well-known
# URLs to decide whether the network has internet.  The matching
# /etc/NetworkManager/dnsmasq-shared.d/00-adsb-upstream.conf redirects
# those domains at 192.168.4.1 -- here we answer the HTTP probes with
# the magic byte sequence each OS expects.  Without these, phones mark
# the AP as "no internet, secured" and may refuse to keep traffic on
# it (Android 12+ / iOS 14+ are the worst offenders).
#
# The reference matrix (verified 2024-08, re-verified 2026-04):
#   Apple  /hotspot-detect.html         -> 200 + "<HTML>...Success...</HTML>"
#   Apple  /library/test/success.html   -> 200 + same body
#   Android  /generate_204               -> 204 No Content
#   Windows  /connecttest.txt            -> 200 + "Microsoft Connect Test"
#   Windows  /ncsi.txt                   -> 200 + "Microsoft NCSI"
#   GNOME   /check_network_status.txt   -> 200 + "NetworkManager is online"
# ============================================================================
_APPLE_OK_BODY = (
    '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">'
    '<HTML><HEAD><TITLE>Success</TITLE></HEAD>'
    '<BODY>Success</BODY></HTML>'
)


@app.route('/hotspot-detect.html')
@app.route('/library/test/success.html')
def _captive_apple():
    return Response(_APPLE_OK_BODY, mimetype='text/html')


@app.route('/generate_204')
@app.route('/gen_204')
def _captive_android():
    return ('', 204)


@app.route('/connecttest.txt')
def _captive_msft_connecttest():
    return Response('Microsoft Connect Test', mimetype='text/plain')


@app.route('/ncsi.txt')
def _captive_msft_ncsi():
    return Response('Microsoft NCSI', mimetype='text/plain')


@app.route('/check_network_status.txt')
def _captive_gnome():
    return Response('NetworkManager is online', mimetype='text/plain')


# Some Android builds probe the bare hostname over HTTP -- we want a
# 200 body, NOT a redirect to /login (which trips the captive sheet).
# We special-case the well-known probe User-Agents.
@app.before_request
def _captive_useragent_short_circuit():
    ua = (request.headers.get('User-Agent') or '').lower()
    path = request.path or '/'
    if path == '/' and any(t in ua for t in (
            'captiveportal', 'captivenetworksupport', 'dalvik', 'wisp',
            'connectivity', 'ncsi')):
        return ('', 204)
    return None


# ============= API ENDPOINTS =============

# Dashboard APIs
@app.route('/api/dashboard/status')
@login_required
def get_dashboard_status():
    """Get system status for dashboard"""
    try:
        # ADS-B Server status
        adsb_status = subprocess.run(['systemctl', 'is-active', 'adsb-server'],
                                    capture_output=True, text=True)
        adsb_running = adsb_status.stdout.strip() == 'active'
        
        # Get uptime
        if adsb_running:
            uptime_result = subprocess.run(['systemctl', 'show', 'adsb-server', 
                                          '--property=ActiveEnterTimestamp'],
                                         capture_output=True, text=True)
            uptime = uptime_result.stdout.strip().split('=')[1] if '=' in uptime_result.stdout else 'Unknown'
        else:
            uptime = 'N/A'
            
        # WiFi status
        current_wifi = wifi.get_current_network()
        
        # System info
        hostname_result = subprocess.run(['hostname'], capture_output=True, text=True)
        hostname = hostname_result.stdout.strip()
        
        return jsonify({
            'success': True,
            'adsb_server': {
                'running': adsb_running,
                'uptime': uptime
            },
            'wifi': current_wifi,
            'hostname': hostname
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# WiFi Manager APIs
@app.route('/api/wifi/scan')
@login_required
def wifi_scan():
    """Scan for available networks"""
    try:
        networks = wifi.scan_networks()
        return jsonify({'success': True, 'networks': networks})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/wifi/saved')
@login_required
def wifi_saved():
    """Get saved networks"""
    try:
        saved = wifi.get_saved_networks()
        current = wifi.get_current_network()
        current_ssid = current['ssid'] if current else None
        
        return jsonify({
            'success': True,
            'networks': saved,
            'current': current_ssid
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/wifi/current')
@login_required
def wifi_current():
    """Get current connection info"""
    try:
        current = wifi.get_current_network()
        return jsonify({'success': True, 'network': current})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/wifi/connect', methods=['POST'])
@login_required
def wifi_connect():
    """Connect to a network"""
    try:
        data = request.get_json()
        ssid = data.get('ssid')
        password = data.get('password')
        
        success = wifi.connect_to_network(ssid, password)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/wifi/forget', methods=['POST'])
@login_required
def wifi_forget():
    """Forget a network"""
    try:
        data = request.get_json()
        ssid = data.get('ssid')
        
        success = wifi.forget_network(ssid)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/wifi/ping', methods=['POST'])
@login_required
def wifi_ping():
    """Run ping test"""
    try:
        data = request.get_json()
        host = data.get('host', '8.8.8.8')
        
        result = wifi.ping_test(host)
        return jsonify({
            'success': True,
            'ping_success': result['success'],
            'output': result['output']
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/wifi/diagnostics')
@login_required
def wifi_diagnostics():
    """Get network diagnostics"""
    try:
        diag = wifi.get_diagnostics()
        return jsonify({'success': True, 'diagnostics': diag})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ADS-B Configuration APIs
@app.route('/api/adsb/config')
@login_required
def get_adsb_config():
    """Get ADS-B configuration"""
    try:
        config = configparser.ConfigParser()
        config.read(ADSB_CONFIG_PATH)
        
        # Get output format
        output_format = config.get('Output', 'format', fallback='sbs1')
        
        filter_mode = config.get('Filter', 'mode', fallback='all')
        icao_list = config.get('Filter', 'icao_list', fallback='').split(',')
        icao_list = [icao.strip() for icao in icao_list if icao.strip()]
        
        # Get altitude filter settings
        altitude_filter_enabled = config.getboolean('Filter', 'altitude_filter_enabled', fallback=False)
        max_altitude = config.getint('Filter', 'max_altitude', fallback=10000)
        
        endpoints = []
        endpoint_count = config.getint('Endpoints', 'count', fallback=0)
        for i in range(endpoint_count):
            name = config.get('Endpoints', f'endpoint_{i}_name', fallback='')
            ip = config.get('Endpoints', f'endpoint_{i}_ip', fallback='')
            port = config.get('Endpoints', f'endpoint_{i}_port', fallback='')
            if ip and port:
                endpoints.append({'name': name, 'ip': ip, 'port': port})
                
        return jsonify({
            'success': True,
            'output_format': output_format,
            'filter_mode': filter_mode,
            'icao_list': icao_list,
            'altitude_filter_enabled': altitude_filter_enabled,
            'max_altitude': max_altitude,
            'endpoints': endpoints
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/adsb/config', methods=['POST'])
@login_required
def update_adsb_config():
    """Update ADS-B configuration"""
    try:
        data = request.get_json()
        
        config = configparser.ConfigParser()
        config.read(ADSB_CONFIG_PATH)
        
        # Ensure sections exist
        if not config.has_section('Output'):
            config.add_section('Output')
        if not config.has_section('Filter'):
            config.add_section('Filter')
        if not config.has_section('Endpoints'):
            config.add_section('Endpoints')
        
        # Update output format
        if 'output_format' in data:
            config.set('Output', 'format', data['output_format'])
        
        # Update filter
        if 'filter_mode' in data:
            config.set('Filter', 'mode', data['filter_mode'])
            
        if 'icao_list' in data:
            icao_string = ','.join(data['icao_list'])
            config.set('Filter', 'icao_list', icao_string)
        
        # Update altitude filter
        if 'altitude_filter_enabled' in data:
            config.set('Filter', 'altitude_filter_enabled', str(data['altitude_filter_enabled']).lower())
            
        if 'max_altitude' in data:
            config.set('Filter', 'max_altitude', str(data['max_altitude']))
            
        # Update endpoints
        if 'endpoints' in data:
            config.set('Endpoints', 'count', str(len(data['endpoints'])))
            for i, endpoint in enumerate(data['endpoints']):
                config.set('Endpoints', f'endpoint_{i}_name', endpoint.get('name', ''))
                config.set('Endpoints', f'endpoint_{i}_ip', endpoint['ip'])
                config.set('Endpoints', f'endpoint_{i}_port', str(endpoint['port']))
                
        # Save configuration
        with open(ADSB_CONFIG_PATH, 'w') as f:
            config.write(f)
            
        # Restart ADS-B service
        subprocess.run(['sudo', 'systemctl', 'restart', 'adsb-server'])
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/adsb/service/<action>', methods=['POST'])
@login_required
def adsb_service_control(action):
    """Control ADS-B service"""
    try:
        if action in ['start', 'stop', 'restart']:
            subprocess.run(['sudo', 'systemctl', action, 'adsb-server'], check=True)
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Invalid action'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/adsb/test-endpoint', methods=['POST'])
@login_required
def test_endpoint():
    """Test connection to an endpoint"""
    try:
        data = request.get_json()
        import socket
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((data['ip'], int(data['port'])))
        sock.close()
        
        return jsonify({'success': result == 0})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Logs & Troubleshooting APIs
@app.route('/api/logs/view')
@login_required
def view_logs():
    """View log file contents"""
    try:
        filter_level = request.args.get('level', 'all')
        
        if not os.path.exists(LOG_PATH):
            return jsonify({'success': True, 'logs': []})
            
        with open(LOG_PATH, 'r') as f:
            lines = f.readlines()
            
        # Filter by level if specified
        if filter_level != 'all':
            lines = [line for line in lines if filter_level.upper() in line]
            
        # Return last 500 lines
        logs = lines[-500:]
        
        return jsonify({'success': True, 'logs': logs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/logs/download')
@login_required
def download_logs():
    """Download log file"""
    try:
        from flask import send_file
        return send_file(LOG_PATH, as_attachment=True, download_name='adsb_server.log')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/logs/clear', methods=['POST'])
@login_required
def clear_logs():
    """Clear log file"""
    try:
        with open(LOG_PATH, 'w') as f:
            f.write('')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Settings APIs
@app.route('/api/settings/password', methods=['POST'])
@login_required
def change_password():
    """Change web interface password"""
    try:
        data = request.get_json()
        new_password = data.get('password')
        
        config = configparser.ConfigParser()
        if os.path.exists(WEB_CONFIG_PATH):
            config.read(WEB_CONFIG_PATH)
        else:
            config['Auth'] = {}
            config['Auth']['username'] = 'JLBMaritime'
            
        config.set('Auth', 'password', new_password)
        
        with open(WEB_CONFIG_PATH, 'w') as f:
            config.write(f)
            
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/settings/system-info')
@login_required
def get_system_info():
    """Get system information"""
    try:
        # Hostname
        hostname = subprocess.run(['hostname'], capture_output=True, text=True).stdout.strip()
        
        # OS version
        with open('/etc/os-release', 'r') as f:
            os_info = f.read()
        
        # Uptime
        uptime = subprocess.run(['uptime', '-p'], capture_output=True, text=True).stdout.strip()
        
        return jsonify({
            'success': True,
            'hostname': hostname,
            'os_info': os_info,
            'uptime': uptime
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/settings/backup')
@login_required
def backup_config():
    """Backup configuration"""
    try:
        from flask import send_file
        import zipfile
        import tempfile
        
        # Create temporary zip file
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        
        with zipfile.ZipFile(temp_zip.name, 'w') as zf:
            zf.write(ADSB_CONFIG_PATH, 'adsb_server_config.conf')
            if os.path.exists(WEB_CONFIG_PATH):
                zf.write(WEB_CONFIG_PATH, 'web_config.conf')
                
        return send_file(temp_zip.name, as_attachment=True, 
                        download_name=f'adsb_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    # Ensure config directory exists
    os.makedirs(os.path.join(BASE_DIR, 'config'), exist_ok=True)

    # Create default config if it doesn't exist
    # NB: json_port is 8080, NOT 30047.  v1 of this file wrote 30047
    # (which is piaware's status JSON, not dump1090-fa's aircraft.json),
    # while adsb_server.py defaulted to 8080 -- result: aircraft counts
    # always read 0 on a fresh install.  This is the canonical port now.
    if not os.path.exists(ADSB_CONFIG_PATH):
        config = configparser.ConfigParser()
        config['Dump1090'] = {'host': '127.0.0.1', 'sbs1_port': '30003', 'json_port': '8080'}
        config['Output'] = {'format': 'sbs1'}
        config['Filter'] = {'mode': 'specific', 'icao_list': 'A92F2D,A932E4,A9369B,A93A52',
                           'altitude_filter_enabled': 'false', 'max_altitude': '10000'}
        config['Endpoints'] = {'count': '0'}
        with open(ADSB_CONFIG_PATH, 'w') as f:
            config.write(f)
    else:
        # Migrate the 30047 bug on existing installs.
        _mig = configparser.ConfigParser()
        _mig.read(ADSB_CONFIG_PATH)
        if _mig.has_section('Dump1090') and _mig.get('Dump1090', 'json_port', fallback='') == '30047':
            _mig.set('Dump1090', 'json_port', '8080')
            with open(ADSB_CONFIG_PATH, 'w') as _f:
                _mig.write(_f)
            print('[config] migrated Dump1090.json_port 30047 -> 8080')

    if not os.path.exists(WEB_CONFIG_PATH):
        config = configparser.ConfigParser()
        config['Auth'] = {'username': 'JLBMaritime', 'password': 'Admin'}
        with open(WEB_CONFIG_PATH, 'w') as f:
            config.write(f)

    # ------------------------------------------------------------------
    # Serve the app
    # ------------------------------------------------------------------
    # The ADSB_HTTP_PORT env var is set to 80 by the systemd unit, with
    # CAP_NET_BIND_SERVICE granted via setcap on the venv python.  If
    # binding 80 fails (running outside systemd, or setcap missing), we
    # fall back to 5000 so the operator can still reach the UI.
    # We use waitress (production-grade WSGI) instead of Flask's
    # development server -- the dev server is single-threaded, has no
    # request timeout, and prints "WARNING: This is a development
    # server" every restart.
    # ------------------------------------------------------------------
    desired_port = int(os.environ.get('ADSB_HTTP_PORT', '80'))
    bind_host = os.environ.get('ADSB_HTTP_HOST', '0.0.0.0')
    try:
        from waitress import serve
        try:
            serve(app, host=bind_host, port=desired_port, threads=8,
                  ident='adsb-wifi-manager', clear_untrusted_proxy_headers=True)
        except (PermissionError, OSError) as port_err:
            print(f'[web] could not bind {bind_host}:{desired_port} ({port_err}); '
                  f'falling back to 5000', flush=True)
            serve(app, host=bind_host, port=5000, threads=8,
                  ident='adsb-wifi-manager', clear_untrusted_proxy_headers=True)
    except ImportError:
        # Last-ditch fallback for development on a machine without waitress.
        print('[web] waitress not installed, using Flask dev server on :5000', flush=True)
        app.run(host=bind_host, port=5000, debug=False)
