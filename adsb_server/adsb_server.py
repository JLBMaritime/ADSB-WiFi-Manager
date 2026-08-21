#!/usr/bin/env python3
"""
ADS-B Server - FIXED VERSION with stability improvements
Part of JLBMaritime ADS-B & Wi-Fi Management System
Supports: SBS1, JSON, and JSON→SBS1 output modes

STABILITY FIXES:
- Added socket timeouts to prevent indefinite blocking
- Fixed socket/connection leaks
- Added connection limits
- Proper thread cleanup
- Resource monitoring
- Watchdog-compatible
"""

import socket
import threading
import time
import logging
import configparser
import os
import sys
import json
import urllib.request
from datetime import datetime, timedelta
import psutil  # For resource monitoring

class ADSBServer:
    def __init__(self, config_file):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.running = False
        self.dump1090_socket = None
        self.endpoint_sockets = []
        self.filter_icao_list = []
        self.filter_all = True
        self.altitude_filter_enabled = False
        self.max_altitude = 10000
        self.endpoints = []
        self.aircraft_states = {}
        self.output_format = 'sbs1'
        
        # Stability improvements
        self.reconnection_threads = set()  # Track reconnection threads
        self.max_reconnect_threads = 5  # Limit concurrent reconnections
        self.socket_timeout = 30  # 30 second socket timeout
        self.endpoint_timeout = 5  # Endpoint connect/send timeout (keeps main loop responsive)
        self.source_stale_after = 300  # Reconnect if no SBS1 data for this long (quiet airspace is normal)
        self.last_resource_check = time.time()

        # Liveness heartbeat: proves the main loop is iterating (not that data
        # flows). Used to gate the systemd watchdog ping.
        self.last_heartbeat = time.time()
        self.heartbeat_stale_after = 75  # > worst legitimate iteration gap (~55s)
        
        # Setup logging
        self.setup_logging()
        self.load_config()
        
    def setup_logging(self):
        """Configure logging with 72-hour rotation"""
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, 'adsb_server.log')
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Start log rotation thread
        threading.Thread(target=self.log_rotation_worker, daemon=True).start()
        
        # Start resource monitor thread
        threading.Thread(target=self.resource_monitor_worker, daemon=True).start()
        
    def resource_monitor_worker(self):
        """Monitor system resources and log warnings"""
        while True:
            try:
                time.sleep(300)  # Check every 5 minutes
                
                # Get process info
                process = psutil.Process()
                mem_info = process.memory_info()
                mem_mb = mem_info.rss / 1024 / 1024
                
                # Count open file descriptors
                try:
                    num_fds = process.num_fds()
                except:
                    num_fds = len(process.open_files())
                
                # Log resource usage
                self.logger.info(f"Resource check: Memory={mem_mb:.1f}MB, FDs={num_fds}, "
                               f"Endpoints={len([e for e in self.endpoints if e.get('socket')])}, "
                               f"Threads={threading.active_count()}")
                
                # Warn if resources high
                if mem_mb > 200:
                    self.logger.warning(f"High memory usage: {mem_mb:.1f}MB")
                if num_fds > 100:
                    self.logger.warning(f"High file descriptor count: {num_fds}")
                if threading.active_count() > 10:
                    self.logger.warning(f"High thread count: {threading.active_count()}")
                    
                # Clean up dead threads from reconnection set
                self.reconnection_threads = {t for t in self.reconnection_threads if t.is_alive()}
                    
            except Exception as e:
                self.logger.error(f"Resource monitor error: {e}")
        
    def log_rotation_worker(self):
        """Purge logs every 72 hours"""
        while True:
            time.sleep(3600)  # Check every hour
            try:
                log_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs', 'adsb_server.log')
                if os.path.exists(log_file):
                    file_time = datetime.fromtimestamp(os.path.getmtime(log_file))
                    if datetime.now() - file_time > timedelta(hours=72):
                        self.logger.info("Rotating log file (72 hours)")
                        open(log_file, 'w').close()
            except Exception as e:
                self.logger.error(f"Log rotation error: {e}")
                
    def load_config(self):
        """Load configuration from file"""
        try:
            if not os.path.exists(self.config_file):
                self.create_default_config()
                
            self.config.read(self.config_file)
            
            # Load output format
            self.output_format = self.config.get('Output', 'format', fallback='sbs1')
            
            # Load filter settings
            filter_mode = self.config.get('Filter', 'mode', fallback='all')
            self.filter_all = (filter_mode.lower() == 'all')
            
            if not self.filter_all:
                icao_string = self.config.get('Filter', 'icao_list', fallback='')
                self.filter_icao_list = [icao.strip().upper() for icao in icao_string.split(',') if icao.strip()]
            
            # Load altitude filter settings
            self.altitude_filter_enabled = self.config.getboolean('Filter', 'altitude_filter_enabled', fallback=False)
            self.max_altitude = self.config.getint('Filter', 'max_altitude', fallback=10000)

            # Stale-source backstop threshold (seconds without SBS1 data before
            # a precautionary reconnect; SBS1 is silent with no aircraft in range)
            self.source_stale_after = self.config.getint('Dump1090', 'source_stale_after', fallback=300)
                
            # Load endpoints - properly clean up old ones
            old_endpoints = {f"{ep['ip']}:{ep['port']}": ep for ep in self.endpoints}
            new_endpoints = []
            endpoint_count = self.config.getint('Endpoints', 'count', fallback=0)
            
            for i in range(endpoint_count):
                name = self.config.get('Endpoints', f'endpoint_{i}_name', fallback='')
                ip = self.config.get('Endpoints', f'endpoint_{i}_ip', fallback=None)
                port = self.config.getint('Endpoints', f'endpoint_{i}_port', fallback=None)
                
                if ip and port:
                    key = f"{ip}:{port}"
                    # Reuse existing socket if endpoint unchanged
                    if key in old_endpoints and old_endpoints[key].get('socket'):
                        new_endpoints.append({
                            'name': name,
                            'ip': ip,
                            'port': port,
                            'socket': old_endpoints[key]['socket'],
                            'backoff': old_endpoints[key].get('backoff', 1.0),
                            'next_retry_at': old_endpoints[key].get('next_retry_at', 0)
                        })
                    else:
                        old_ep = old_endpoints.get(key, {})
                        new_endpoints.append({
                            'name': name,
                            'ip': ip,
                            'port': port,
                            'socket': None,
                            'backoff': old_ep.get('backoff', 1.0),
                            'next_retry_at': old_ep.get('next_retry_at', 0)
                        })
            
            # Close sockets for removed endpoints
            new_keys = {f"{ep['ip']}:{ep['port']}" for ep in new_endpoints}
            for key, old_ep in old_endpoints.items():
                if key not in new_keys and old_ep.get('socket'):
                    try:
                        old_ep['socket'].close()
                        self.logger.info(f"Closed connection to removed endpoint {key}")
                    except:
                        pass
            
            self.endpoints = new_endpoints
                    
            self.logger.info(f"Configuration loaded: Filter={'ALL' if self.filter_all else self.filter_icao_list}, Endpoints={len(self.endpoints)}")
            
        except Exception as e:
            self.logger.error(f"Error loading config: {e}")
            
    def create_default_config(self):
        """Create default configuration file"""
        self.config['Dump1090'] = {
            'host': '127.0.0.1',
            'sbs1_port': '30003',
            'json_port': '8080'
        }
        self.config['Output'] = {
            'format': 'sbs1'
        }
        self.config['Filter'] = {
            'mode': 'specific',
            'icao_list': 'A92F2D,A932E4,A9369B,A93A52',
            'altitude_filter_enabled': 'false',
            'max_altitude': '10000'
        }
        self.config['Endpoints'] = {
            'count': '0'
        }
        
        with open(self.config_file, 'w') as f:
            self.config.write(f)
            
    def tune_socket(self, sock):
        """Enable TCP keepalive so a half-open peer eventually errors out.
        Idle 60s, then probes every 20s, 5 failures => dead peer detected in
        ~160s and recv() raises instead of waiting forever."""
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            for name, val in (("TCP_KEEPIDLE", 60),
                              ("TCP_KEEPINTVL", 20),
                              ("TCP_KEEPCNT", 5)):
                opt = getattr(socket, name, None)  # Linux-only constants
                if opt is not None:
                    try:
                        sock.setsockopt(socket.IPPROTO_TCP, opt, val)
                    except OSError:
                        pass
        except OSError:
            pass

    def connect_to_dump1090(self):
        """Connect to dump1090-fa SBS1 port with timeout"""
        host = self.config.get('Dump1090', 'host', fallback='127.0.0.1')
        port = self.config.getint('Dump1090', 'sbs1_port', fallback=30003)

        try:
            self.dump1090_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.dump1090_socket.settimeout(self.socket_timeout)  # Set timeout
            self.tune_socket(self.dump1090_socket)
            self.dump1090_socket.connect((host, port))
            self.logger.info(f"Connected to dump1090-fa SBS1 at {host}:{port}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to dump1090-fa: {e}")
            if self.dump1090_socket:
                try:
                    self.dump1090_socket.close()
                except:
                    pass
            self.dump1090_socket = None
            return False
    
    def fetch_json_data(self):
        """Fetch JSON data from dump1090 with timeout"""
        try:
            host = self.config.get('Dump1090', 'host', fallback='127.0.0.1')
            json_port = self.config.getint('Dump1090', 'json_port', fallback=8080)
            
            url = f"http://{host}:{json_port}/data/aircraft.json"
            # FIXED: Added timeout to prevent infinite hang
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                return data.get('aircraft', [])
        except urllib.error.URLError as e:
            self.logger.warning(f"Cannot reach JSON endpoint: {e.reason}")
            return []
        except Exception as e:
            self.logger.error(f"Error fetching JSON from {url}: {e}")
            return []
    
    def filter_json_aircraft(self, aircraft):
        """Filter JSON aircraft object"""
        try:
            icao = aircraft.get('hex', '').upper()
            altitude = aircraft.get('alt_baro') or aircraft.get('alt_geom')
            
            # Check altitude filter
            if self.altitude_filter_enabled and altitude:
                if altitude > self.max_altitude:
                    return False
            
            # Check ICAO filter
            if self.filter_all:
                return True
            
            return icao in self.filter_icao_list
        except:
            return False
    
    def json_to_sbs1(self, aircraft):
        """Convert JSON aircraft object to SBS1 format"""
        try:
            icao = aircraft.get('hex', '').upper()
            callsign = aircraft.get('flight', '').strip()
            altitude = aircraft.get('alt_baro') or aircraft.get('alt_geom') or ''
            speed = aircraft.get('gs') or ''
            track = aircraft.get('track') or ''
            lat = aircraft.get('lat') or ''
            lon = aircraft.get('lon') or ''
            
            now = datetime.utcnow()
            date_str = now.strftime('%Y/%m/%d')
            time_str = now.strftime('%H:%M:%S.%f')[:-3]
            
            sbs1_line = f"MSG,3,1,1,{icao},1,{date_str},{time_str},{date_str},{time_str},{callsign},{altitude},{speed},{track},{lat},{lon}"
            
            return sbs1_line + '\n'
        except Exception as e:
            self.logger.error(f"JSON→SBS1 conversion error: {e}")
            return None
            
    def endpoint_backoff_failure(self, endpoint):
        """Record a failed endpoint attempt: exponential backoff 1->30s"""
        backoff = min(endpoint.get('backoff', 1.0) * 2, 30.0)
        endpoint['backoff'] = backoff
        endpoint['next_retry_at'] = time.time() + backoff

    def connect_to_endpoints(self):
        """Connect to all configured endpoints with timeout"""
        for endpoint in self.endpoints:
            if not endpoint.get('socket') and time.time() >= endpoint.get('next_retry_at', 0):
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(self.endpoint_timeout)  # Set timeout
                    self.tune_socket(sock)
                    sock.connect((endpoint['ip'], endpoint['port']))
                    endpoint['socket'] = sock
                    endpoint['backoff'] = 1.0
                    endpoint['next_retry_at'] = 0
                    self.logger.info(f"Connected to endpoint {endpoint['ip']}:{endpoint['port']}")
                except Exception as e:
                    self.logger.warning(f"Failed to connect to {endpoint['ip']}:{endpoint['port']}: {e}")
                    endpoint['socket'] = None
                    self.endpoint_backoff_failure(endpoint)

    def reconnect_endpoint(self, endpoint):
        """Attempt to reconnect to a failed endpoint"""
        try:
            # Clean up old socket
            if endpoint.get('socket'):
                try:
                    endpoint['socket'].close()
                except:
                    pass
                endpoint['socket'] = None

            # Create new socket with timeout
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.endpoint_timeout)
            self.tune_socket(sock)
            sock.connect((endpoint['ip'], endpoint['port']))
            endpoint['socket'] = sock
            endpoint['backoff'] = 1.0
            endpoint['next_retry_at'] = 0
            self.logger.info(f"Reconnected to endpoint {endpoint['ip']}:{endpoint['port']}")
            return True
        except Exception as e:
            self.logger.debug(f"Reconnect failed for {endpoint['ip']}:{endpoint['port']}: {e}")
            endpoint['socket'] = None
            self.endpoint_backoff_failure(endpoint)
            return False
        finally:
            # Remove this thread from tracking
            try:
                self.reconnection_threads.discard(threading.current_thread())
            except:
                pass
            
    def filter_message(self, message):
        """Check if message should be forwarded based on filter"""
        try:
            parts = message.split(',')
            
            # Check altitude filter
            if self.altitude_filter_enabled and len(parts) > 11:
                altitude_str = parts[11].strip()
                if altitude_str:
                    try:
                        altitude = int(altitude_str)
                        if altitude > self.max_altitude:
                            return False
                    except ValueError:
                        pass
            
            # If filter_all mode, accept everything
            if self.filter_all:
                return True
            
            # Check ICAO filter
            if len(parts) > 4:
                icao = parts[4].strip().upper()
                return icao in self.filter_icao_list
                
        except:
            pass
            
        return False
        
    def forward_message(self, message):
        """Forward message to all connected endpoints"""
        message_bytes = message.encode('utf-8')

        for endpoint in self.endpoints:
            if endpoint.get('socket'):
                try:
                    endpoint['socket'].sendall(message_bytes)
                    endpoint['backoff'] = 1.0  # Healthy: reset backoff
                    continue
                except Exception as e:
                    self.logger.warning(f"Failed to send to {endpoint['ip']}:{endpoint['port']}: {e}")
                    try:
                        endpoint['socket'].close()
                    except:
                        pass
                    endpoint['socket'] = None

            # No socket (never connected, or send just failed): retry with
            # exponential backoff so a dead endpoint is never given up on
            # but also never hammered.
            # FIXED: Limit concurrent reconnection threads
            if time.time() >= endpoint.get('next_retry_at', 0) and \
                    len(self.reconnection_threads) < self.max_reconnect_threads:
                # Claim the retry slot now so every message doesn't spawn a thread;
                # reconnect_endpoint doubles the backoff if the attempt fails
                endpoint['next_retry_at'] = time.time() + endpoint.get('backoff', 1.0)
                thread = threading.Thread(target=self.reconnect_endpoint, args=(endpoint,), daemon=True)
                self.reconnection_threads.add(thread)
                thread.start()

    def run_sbs1_mode(self):
        """Run in SBS1 streaming mode"""
        self.logger.info("ADS-B Server starting in SBS1 mode...")
        
        while self.running:
            self.last_heartbeat = time.time()

            # Connect to dump1090
            if not self.dump1090_socket:
                if not self.connect_to_dump1090():
                    self.logger.info("Waiting for dump1090-fa connection... (retry in 10s)")
                    time.sleep(10)
                    continue

            # Connect to endpoints
            self.connect_to_endpoints()

            # Main data processing loop
            buffer = ""
            reconnect_time = time.time()
            last_data_at = time.time()

            try:
                while self.running:
                    self.last_heartbeat = time.time()

                    # Reload config periodically
                    if time.time() - reconnect_time > 30:
                        self.load_config()
                        reconnect_time = time.time()

                    try:
                        # Receive with timeout
                        data = self.dump1090_socket.recv(4096)
                        if not data:
                            self.logger.warning("dump1090-fa connection lost")
                            break

                        last_data_at = time.time()
                        buffer += data.decode('utf-8', errors='ignore')

                        # Process complete messages
                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            line = line.strip()

                            if line and self.filter_message(line):
                                self.forward_message(line + '\n')

                    except socket.timeout as e:
                        # Since Python 3.10 socket.timeout is TimeoutError, so
                        # a keepalive-detected dead peer (ETIMEDOUT, has errno)
                        # lands here too -- distinguish it from the timeout
                        # machinery's quiet interval (no errno).
                        if getattr(e, 'errno', None) is not None:
                            self.logger.error(f"Error receiving data: {e}")
                            break
                        # No data is NORMAL (quiet airspace). Backstop: if we
                        # have heard nothing for source_stale_after seconds,
                        # drop and redial -- covers a wedged-but-connected
                        # dump1090 and any half-open state the TCP keepalive
                        # probes miss. Reconnecting locally is cheap.
                        if time.time() - last_data_at > self.source_stale_after:
                            self.logger.warning(
                                f"No SBS1 data for {int(time.time() - last_data_at)}s -- "
                                "reconnecting to dump1090 as a precaution")
                            break
                        continue
                    except Exception as e:
                        self.logger.error(f"Error receiving data: {e}")
                        break
                        
            except Exception as e:
                self.logger.error(f"Server error: {e}")
                
            # Clean up connection
            if self.dump1090_socket:
                try:
                    self.dump1090_socket.close()
                except:
                    pass
                self.dump1090_socket = None
                
            # Wait before reconnecting
            if self.running:
                time.sleep(5)
                
        self.logger.info("ADS-B Server stopped")
    
    def run_json_mode(self):
        """Run in JSON polling mode"""
        self.logger.info("ADS-B Server starting in JSON mode...")
        
        host = self.config.get('Dump1090', 'host', fallback='127.0.0.1')
        json_port = self.config.getint('Dump1090', 'json_port', fallback=8080)
        url = f"http://{host}:{json_port}/data/aircraft.json"
        self.logger.info(f"Polling JSON data from: {url}")
        
        self.connect_to_endpoints()
        
        reconnect_time = time.time()
        stats_time = time.time()
        first_success = False
        total_sent = 0
        
        while self.running:
            try:
                self.last_heartbeat = time.time()

                # Reload config periodically
                if time.time() - reconnect_time > 30:
                    self.load_config()
                    reconnect_time = time.time()

                # Fetch JSON data
                aircraft_list = self.fetch_json_data()

                if aircraft_list and not first_success:
                    self.logger.info(f"✓ Successfully connected to JSON endpoint ({len(aircraft_list)} aircraft visible)")
                    first_success = True

                # Filter and forward
                sent_count = 0
                for aircraft in aircraft_list:
                    if self.filter_json_aircraft(aircraft):
                        json_str = json.dumps(aircraft) + '\n'
                        self.forward_message(json_str)
                        sent_count += 1
                
                total_sent += sent_count
                
                # Log stats every 30 seconds
                if time.time() - stats_time > 30:
                    self.logger.info(f"JSON polling: {len(aircraft_list)} aircraft, {sent_count} filtered, {total_sent} total sent")
                    stats_time = time.time()
                
                time.sleep(1)
                
            except Exception as e:
                self.logger.error(f"JSON mode error: {e}")
                time.sleep(5)
        
        self.logger.info("ADS-B Server stopped")
    
    def run_json_to_sbs1_mode(self):
        """Run in JSON→SBS1 conversion mode"""
        self.logger.info("ADS-B Server starting in JSON→SBS1 mode...")
        
        host = self.config.get('Dump1090', 'host', fallback='127.0.0.1')
        json_port = self.config.getint('Dump1090', 'json_port', fallback=8080)
        url = f"http://{host}:{json_port}/data/aircraft.json"
        self.logger.info(f"Polling JSON data from: {url}")
        self.logger.info("Converting JSON → SBS1 format")
        
        self.connect_to_endpoints()
        
        reconnect_time = time.time()
        stats_time = time.time()
        first_success = False
        total_sent = 0
        
        while self.running:
            try:
                self.last_heartbeat = time.time()

                # Reload config periodically
                if time.time() - reconnect_time > 30:
                    self.load_config()
                    reconnect_time = time.time()

                # Fetch JSON data
                aircraft_list = self.fetch_json_data()

                if aircraft_list and not first_success:
                    self.logger.info(f"✓ Successfully connected to JSON endpoint ({len(aircraft_list)} aircraft visible)")
                    first_success = True

                # Filter, convert and forward
                sent_count = 0
                for aircraft in aircraft_list:
                    if self.filter_json_aircraft(aircraft):
                        sbs1_message = self.json_to_sbs1(aircraft)
                        if sbs1_message:
                            self.forward_message(sbs1_message)
                            sent_count += 1
                
                total_sent += sent_count
                
                # Log stats every 30 seconds
                if time.time() - stats_time > 30:
                    self.logger.info(f"JSON→SBS1: {len(aircraft_list)} aircraft, {sent_count} converted & sent, {total_sent} total")
                    stats_time = time.time()
                
                time.sleep(1)
                
            except Exception as e:
                self.logger.error(f"JSON→SBS1 mode error: {e}")
                time.sleep(5)
        
        self.logger.info("ADS-B Server stopped")
    
    def _sd_notify(self, msg):
        """Stdlib sd_notify(3) -- no external package so a missing dependency
        can never turn Type=notify into a boot loop. No-op outside systemd."""
        addr = os.environ.get("NOTIFY_SOCKET")
        af_unix = getattr(socket, "AF_UNIX", None)
        if not addr or af_unix is None:
            return
        if addr.startswith("@"):
            addr = "\0" + addr[1:]
        try:
            s = socket.socket(af_unix, socket.SOCK_DGRAM)
            try:
                s.connect(addr)
                s.sendall(msg)
            finally:
                s.close()
        except OSError:
            pass

    def watchdog_pinger_worker(self):
        """Send READY=1 then WATCHDOG=1 pings, but only while the main loop's
        heartbeat is fresh -- a wedged loop stops the pings and systemd
        (WatchdogSec) kills and restarts us."""
        self._sd_notify(b"READY=1")

        interval = 10.0
        wd_usec = os.environ.get("WATCHDOG_USEC")
        if wd_usec:
            try:
                interval = min(10.0, max(1.0, int(wd_usec) / 1_000_000 / 2))
            except ValueError:
                pass

        while True:
            age = time.time() - self.last_heartbeat
            if age < self.heartbeat_stale_after:
                self._sd_notify(b"WATCHDOG=1")
            else:
                self.logger.error(f"Main loop heartbeat stale ({age:.0f}s) -- "
                                  "withholding watchdog ping; systemd will restart us")
            time.sleep(interval)

    def run(self):
        """Main server loop"""
        self.running = True

        self.logger.info(f"Starting ADS-B Server in {self.output_format} mode")

        # Watchdog pinger must start before the blocking mode loop so
        # READY=1 reaches systemd immediately (Type=notify)
        threading.Thread(target=self.watchdog_pinger_worker, daemon=True,
                         name="sdnotify-watchdog").start()

        # Route to appropriate mode
        if self.output_format == 'json':
            self.run_json_mode()
        elif self.output_format == 'json_to_sbs1':
            self.run_json_to_sbs1_mode()
        else:
            self.run_sbs1_mode()
        
    def stop(self):
        """Stop the server and clean up all resources"""
        self.logger.info("Stopping ADS-B Server...")
        self.running = False
        
        # Close dump1090 connection
        if self.dump1090_socket:
            try:
                self.dump1090_socket.close()
            except:
                pass
                
        # Close all endpoint connections
        for endpoint in self.endpoints:
            if endpoint.get('socket'):
                try:
                    endpoint['socket'].close()
                except:
                    pass
                endpoint['socket'] = None
        
        # Wait for reconnection threads to finish (with timeout)
        for thread in list(self.reconnection_threads):
            if thread.is_alive():
                thread.join(timeout=2)
        
        self.logger.info("ADS-B Server stopped - all resources cleaned up")

def main():
    """Main entry point"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'adsb_server_config.conf')
    
    server = ADSBServer(config_path)
    
    # Handle graceful shutdown
    import signal
    def signal_handler(sig, frame):
        server.stop()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        server.run()
    except KeyboardInterrupt:
        server.stop()

if __name__ == "__main__":
    main()
