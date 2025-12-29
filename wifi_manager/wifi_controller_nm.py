#!/usr/bin/env python3
"""
WiFi Controller - NetworkManager Version
Manages WiFi connections on wlan0 using NetworkManager (nmcli)
Part of JLBMaritime ADS-B & Wi-Fi Management System
"""

import subprocess
import re
import time

class WiFiController:
    def __init__(self, interface='wlan0'):
        self.interface = interface
        
    def scan_networks(self):
        """Scan for available WiFi networks using nmcli"""
        try:
            # Rescan for networks
            subprocess.run(['sudo', 'nmcli', 'device', 'wifi', 'rescan'], 
                         capture_output=True, timeout=10)
            time.sleep(2)
            
            # Get scan results
            result = subprocess.run(['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 
                                   'device', 'wifi', 'list', 'ifname', self.interface], 
                                  capture_output=True, text=True, timeout=10)
            
            networks = []
            seen = set()
            
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                    
                parts = line.split(':')
                if len(parts) < 3:
                    continue
                    
                ssid = parts[0]
                signal = parts[1]
                security = parts[2]
                
                # Skip empty SSIDs and duplicates
                if not ssid or ssid in seen:
                    continue
                    
                seen.add(ssid)
                
                networks.append({
                    'ssid': ssid,
                    'signal': int(signal) if signal.isdigit() else 0,
                    'encrypted': bool(security and security != '--')
                })
                    
            return sorted(networks, key=lambda x: x['signal'], reverse=True)
            
        except Exception as e:
            print(f"Error scanning networks: {e}")
            return []
            
    def get_saved_networks(self):
        """Get list of saved network connections from NetworkManager"""
        try:
            result = subprocess.run(['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show'],
                                  capture_output=True, text=True)
            
            networks = []
            
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                    
                parts = line.split(':')
                if len(parts) >= 2 and parts[1] == '802-11-wireless':
                    # Skip the hotspot connection
                    if parts[0] != 'JLBMaritime-Hotspot':
                        networks.append({
                            'id': parts[0],
                            'ssid': parts[0]
                        })
                        
            return networks
            
        except Exception as e:
            print(f"Error getting saved networks: {e}")
            return []
            
    def get_current_network(self):
        """Get currently connected network info"""
        try:
            # Get active connection
            result = subprocess.run(['nmcli', '-t', '-f', 'NAME,TYPE,DEVICE', 
                                   'connection', 'show', '--active'],
                                  capture_output=True, text=True)
            
            ssid = None
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                parts = line.split(':')
                if len(parts) >= 3 and parts[1] == '802-11-wireless' and parts[2] == self.interface:
                    ssid = parts[0]
                    break
                    
            if not ssid:
                return None
                
            # Get IP address
            ip_result = subprocess.run(['ip', 'addr', 'show', self.interface],
                                      capture_output=True, text=True)
            
            ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', ip_result.stdout)
            ip_address = ip_match.group(1) if ip_match else 'Unknown'
            
            # Get signal strength
            signal_result = subprocess.run(['nmcli', '-t', '-f', 'IN-USE,SIGNAL,SSID', 
                                          'device','wifi', 'list', 'ifname', self.interface],
                                         capture_output=True, text=True)
            
            signal = 0
            for line in signal_result.stdout.strip().split('\n'):
                parts = line.split(':')
                if len(parts) >= 3 and parts[0] == '*' and parts[2] == ssid:
                    try:
                        signal = int(parts[1])
                    except:
                        signal = 0
                    break
                
            return {
                'ssid': ssid,
                'ip': ip_address,
                'signal': signal
            }
            
        except Exception as e:
            print(f"Error getting current network: {e}")
            return None
            
    def connect_to_network(self, ssid, password=None):
        """Connect to a WiFi network using NetworkManager"""
        try:
            # Check if connection already exists
            existing = subprocess.run(['nmcli', 'connection', 'show', ssid],
                                    capture_output=True, text=True)
            
            if existing.returncode == 0:
                # Connection exists, just activate it
                result = subprocess.run(['sudo', 'nmcli', 'connection', 'up', ssid],
                                      capture_output=True, text=True)
                return result.returncode == 0
            else:
                # Create new connection
                if password:
                    result = subprocess.run(['sudo', 'nmcli', 'device', 'wifi', 'connect', 
                                           ssid, 'password', password, 'ifname', self.interface],
                                          capture_output=True, text=True)
                else:
                    result = subprocess.run(['sudo', 'nmcli', 'device', 'wifi', 'connect', 
                                           ssid, 'ifname', self.interface],
                                          capture_output=True, text=True)
                
                return result.returncode == 0
            
        except Exception as e:
            print(f"Error connecting to network: {e}")
            return False
            
    def forget_network(self, ssid):
        """Remove a saved network connection"""
        try:
            result = subprocess.run(['sudo', 'nmcli', 'connection', 'delete', ssid],
                                  capture_output=True, text=True)
            return result.returncode == 0
            
        except Exception as e:
            print(f"Error forgetting network: {e}")
            return False
            
    def get_ip_address(self):
        """Get IP address of the interface"""
        try:
            result = subprocess.run(['ip', 'addr', 'show', self.interface],
                                  capture_output=True, text=True)
            
            ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', result.stdout)
            return ip_match.group(1) if ip_match else None
            
        except Exception as e:
            print(f"Error getting IP: {e}")
            return None
            
    def ping_test(self, host='8.8.8.8', count=4):
        """Run ping test"""
        try:
            result = subprocess.run(['ping', '-c', str(count), '-W', '2', host],
                                  capture_output=True, text=True)
            
            return {
                'success': result.returncode == 0,
                'output': result.stdout
            }
            
        except Exception as e:
            return {
                'success': False,
                'output': f"Error: {str(e)}"
            }
            
    def get_diagnostics(self):
        """Get network diagnostics information"""
        try:
            diagnostics = {}
            
            # Interface status from NetworkManager
            result = subprocess.run(['nmcli', 'device', 'show', self.interface],
                                  capture_output=True, text=True)
            diagnostics['interface_info'] = result.stdout
            
            # IP configuration
            result = subprocess.run(['ip', 'addr', 'show', self.interface],
                                  capture_output=True, text=True)
            diagnostics['ip_config'] = result.stdout
            
            # Gateway
            result = subprocess.run(['ip', 'route', 'show', 'default'],
                                  capture_output=True, text=True)
            gateway_match = re.search(r'default via (\d+\.\d+\.\d+\.\d+)', result.stdout)
            diagnostics['gateway'] = gateway_match.group(1) if gateway_match else 'None'
            
            # DNS from NetworkManager
            result = subprocess.run(['nmcli', 'device', 'show', self.interface],
                                  capture_output=True, text=True)
            dns_servers = []
            for line in result.stdout.split('\n'):
                if 'IP4.DNS' in line:
                    parts = line.split(':')
                    if len(parts) == 2:
                        dns_servers.append(parts[1].strip())
            diagnostics['dns'] = dns_servers
                
            return diagnostics
            
        except Exception as e:
            return {'error': str(e)}
