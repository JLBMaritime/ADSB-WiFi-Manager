#!/usr/bin/env python3
"""
ADS-B Server - Receives ADS-B data from dump1090-fa and forwards to configured endpoints
Part of JLBMaritime ADS-B & Wi-Fi Management System
Supports: SBS1, JSON, and JSON→SBS1 output modes
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
        self.aircraft_states = {}  # Track aircraft altitude for SBS1 mode
        self.output_format = 'sbs1'  # Default output format
        
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
                
            # Load endpoints - preserve existing socket connections
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
                    if key in old_endpoints:
                        new_endpoints.append({
                            'name': name,
                            'ip': ip,
                            'port': port,
                            'socket': old_endpoints[key]['socket']  # Preserve socket!
                        })
                    else:
                        # New endpoint
                        new_endpoints.append({
                            'name': name,
                            'ip': ip,
                            'port': port,
                            'socket': None
                        })
            
            # Close sockets for removed endpoints
            new_keys = {f"{ep['ip']}:{ep['port']}" for ep in new_endpoints}
            for key, old_ep in old_endpoints.items():
                if key not in new_keys and old_ep['socket']:
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
            
    def connect_to_dump1090(self):
        """Connect to dump1090-fa SBS1 port"""
        host = self.config.get('Dump1090', 'host', fallback='127.0.0.1')
        port = self.config.getint('Dump1090', 'sbs1_port', fallback=30003)
        
        try:
            self.dump1090_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.dump1090_socket.settimeout(10)
            self.dump1090_socket.connect((host, port))
            self.logger.info(f"Connected to dump1090-fa SBS1 at {host}:{port}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to dump1090-fa: {e}")
            self.dump1090_socket = None
            return False
    
    def fetch_json_data(self):
        """Fetch JSON data from dump1090"""
        try:
            host = self.config.get('Dump1090', 'host', fallback='127.0.0.1')
            json_port = self.config.getint('Dump1090', 'json_port', fallback=8080)
            
            url = f"http://{host}:{json_port}/data/aircraft.json"
            with urllib.request.urlopen(url, timeout=5) as response:
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
            
            # Get current timestamp
            now = datetime.utcnow()
            date_str = now.strftime('%Y/%m/%d')
            time_str = now.strftime('%H:%M:%S.%f')[:-3]
            
            # SBS1 format
            sbs1_line = f"MSG,3,1,1,{icao},1,{date_str},{time_str},{date_str},{time_str},{callsign},{altitude},{speed},{track},{lat},{lon}"
            
            return sbs1_line + '\n'
        except Exception as e:
            self.logger.error(f"JSON→SBS1 conversion error: {e}")
            return None
            
    def connect_to_endpoints(self):
        """Connect to all configured endpoints"""
        for endpoint in self.endpoints:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((endpoint['ip'], endpoint['port']))
                endpoint['socket'] = sock
                self.logger.info(f"Connected to endpoint {endpoint['ip']}:{endpoint['port']}")
            except Exception as e:
                self.logger.warning(f"Failed to connect to {endpoint['ip']}:{endpoint['port']}: {e}")
                endpoint['socket'] = None
                
    def reconnect_endpoint(self, endpoint):
        """Attempt to reconnect to a failed endpoint"""
        try:
            if endpoint['socket']:
                try:
                    endpoint['socket'].close()
                except:
                    pass
                    
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((endpoint['ip'], endpoint['port']))
            endpoint['socket'] = sock
            self.logger.info(f"Reconnected to endpoint {endpoint['ip']}:{endpoint['port']}")
            return True
        except Exception as e:
            self.logger.debug(f"Reconnect failed for {endpoint['ip']}:{endpoint['port']}: {e}")
            endpoint['socket'] = None
            return False
            
    def filter_message(self, message):
        """Check if message should be forwarded based on filter"""
        # SBS1 format: MSG,3,1,1,ICAO,1,DATE,TIME,DATE,TIME,CALLSIGN,ALTITUDE,SPEED,TRACK,LAT,LON...
        #              0   1 2 3  4    5  6    7    8    9     10      11       12     13    14  15
        try:
            parts = message.split(',')
            
            # Check altitude filter first (applies to all modes)
            if self.altitude_filter_enabled and len(parts) > 11:
                altitude_str = parts[11].strip()
                if altitude_str:  # Altitude field not empty
                    try:
                        altitude = int(altitude_str)
                        if altitude > self.max_altitude:
                            return False  # Reject aircraft above max altitude
                    except ValueError:
                        pass  # Invalid altitude, continue with other filters
            
            # If filter_all mode, accept everything (that passed altitude filter)
            if self.filter_all:
                return True
            
            # Check ICAO filter for specific mode
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
            if endpoint['socket']:
                try:
                    endpoint['socket'].sendall(message_bytes)
                except Exception as e:
                    self.logger.warning(f"Failed to send to {endpoint['ip']}:{endpoint['port']}: {e}")
                    endpoint['socket'] = None
                    # Attempt reconnection in background
                    threading.Thread(target=self.reconnect_endpoint, args=(endpoint,), daemon=True).start()
                    
    def run_sbs1_mode(self):
        """Run in SBS1 streaming mode"""
        self.logger.info("ADS-B Server starting in SBS1 mode...")
        
        while self.running:
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
            
            try:
                while self.running:
                    # Reload config periodically (for updates)
                    if time.time() - reconnect_time > 30:
                        old_config = self.config_file
                        self.load_config()
                        reconnect_time = time.time()
                        
                    try:
                        data = self.dump1090_socket.recv(4096)
                        if not data:
                            self.logger.warning("dump1090-fa connection lost")
                            break
                            
                        buffer += data.decode('utf-8', errors='ignore')
                        
                        # Process complete messages (lines)
                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            line = line.strip()
                            
                            if line and self.filter_message(line):
                                self.forward_message(line + '\n')
                                
                    except socket.timeout:
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
        
        # Log JSON endpoint
        host = self.config.get('Dump1090', 'host', fallback='127.0.0.1')
        json_port = self.config.getint('Dump1090', 'json_port', fallback=8080)
        url = f"http://{host}:{json_port}/data/aircraft.json"
        self.logger.info(f"Polling JSON data from: {url}")
        
        # Connect to endpoints
        self.connect_to_endpoints()
        
        reconnect_time = time.time()
        stats_time = time.time()
        first_success = False
        total_sent = 0
        
        while self.running:
            try:
                # Reload config periodically
                if time.time() - reconnect_time > 30:
                    self.load_config()
                    reconnect_time = time.time()
                
                # Fetch JSON data
                aircraft_list = self.fetch_json_data()
                
                # Log first successful fetch
                if aircraft_list and not first_success:
                    self.logger.info(f"✓ Successfully connected to JSON endpoint ({len(aircraft_list)} aircraft visible)")
                    first_success = True
                
                # Filter and forward each aircraft
                sent_count = 0
                for aircraft in aircraft_list:
                    if self.filter_json_aircraft(aircraft):
                        # Send as individual JSON object
                        json_str = json.dumps(aircraft) + '\n'
                        self.forward_message(json_str)
                        sent_count += 1
                
                total_sent += sent_count
                
                # Log stats every 30 seconds
                if time.time() - stats_time > 30:
                    self.logger.info(f"JSON polling: {len(aircraft_list)} aircraft, {sent_count} filtered, {total_sent} total sent")
                    stats_time = time.time()
                
                # Poll every 1 second
                time.sleep(1)
                
            except Exception as e:
                self.logger.error(f"JSON mode error: {e}")
                time.sleep(5)
        
        self.logger.info("ADS-B Server stopped")
    
    def run_json_to_sbs1_mode(self):
        """Run in JSON→SBS1 conversion mode"""
        self.logger.info("ADS-B Server starting in JSON→SBS1 mode...")
        
        # Log JSON endpoint
        host = self.config.get('Dump1090', 'host', fallback='127.0.0.1')
        json_port = self.config.getint('Dump1090', 'json_port', fallback=8080)
        url = f"http://{host}:{json_port}/data/aircraft.json"
        self.logger.info(f"Polling JSON data from: {url}")
        self.logger.info("Converting JSON → SBS1 format")
        
        # Connect to endpoints
        self.connect_to_endpoints()
        
        reconnect_time = time.time()
        stats_time = time.time()
        first_success = False
        total_sent = 0
        
        while self.running:
            try:
                # Reload config periodically
                if time.time() - reconnect_time > 30:
                    self.load_config()
                    reconnect_time = time.time()
                
                # Fetch JSON data
                aircraft_list = self.fetch_json_data()
                
                # Log first successful fetch
                if aircraft_list and not first_success:
                    self.logger.info(f"✓ Successfully connected to JSON endpoint ({len(aircraft_list)} aircraft visible)")
                    first_success = True
                
                # Filter, convert and forward each aircraft
                sent_count = 0
                for aircraft in aircraft_list:
                    if self.filter_json_aircraft(aircraft):
                        # Convert to SBS1 and send
                        sbs1_message = self.json_to_sbs1(aircraft)
                        if sbs1_message:
                            self.forward_message(sbs1_message)
                            sent_count += 1
                
                total_sent += sent_count
                
                # Log stats every 30 seconds
                if time.time() - stats_time > 30:
                    self.logger.info(f"JSON→SBS1: {len(aircraft_list)} aircraft, {sent_count} converted & sent, {total_sent} total")
                    stats_time = time.time()
                
                # Poll every 1 second
                time.sleep(1)
                
            except Exception as e:
                self.logger.error(f"JSON→SBS1 mode error: {e}")
                time.sleep(5)
        
        self.logger.info("ADS-B Server stopped")
    
    def run(self):
        """Main server loop - routes to appropriate mode"""
        self.running = True
        
        # Log mode selection
        self.logger.info(f"Starting ADS-B Server in {self.output_format} mode")
        
        # Route to appropriate mode
        if self.output_format == 'json':
            self.run_json_mode()
        elif self.output_format == 'json_to_sbs1':
            self.run_json_to_sbs1_mode()
        else:  # Default to sbs1
            self.run_sbs1_mode()
        
    def stop(self):
        """Stop the server"""
        self.logger.info("Stopping ADS-B Server...")
        self.running = False
        
        # Close all connections
        if self.dump1090_socket:
            try:
                self.dump1090_socket.close()
            except:
                pass
                
        for endpoint in self.endpoints:
            if endpoint['socket']:
                try:
                    endpoint['socket'].close()
                except:
                    pass

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
