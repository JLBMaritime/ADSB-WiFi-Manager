#!/usr/bin/env python3
"""
ADS-B & WiFi Manager - Interactive CLI
Part of JLBMaritime ADS-B & Wi-Fi Management System

Remote management interface for SSH access
"""

import sys
import os
import subprocess

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from cli.utils import *
from cli.wifi_menu import show_wifi_menu
from cli.adsb_menu import show_adsb_menu
from cli.service_menu import show_service_menu, get_service_status
from cli.logs_menu import show_logs_menu
from cli.settings_menu import show_settings_menu

# Add WiFi controller for status
from wifi_manager.wifi_controller import WiFiController

def get_system_status():
    """Get current system status for main menu"""
    status = {}
    
    # ADS-B Server status
    try:
        result = subprocess.run(['systemctl', 'is-active', 'adsb-server'],
                              capture_output=True, text=True)
        status['adsb_running'] = (result.stdout.strip() == 'active')
        
        # Get uptime if running
        if status['adsb_running']:
            uptime_result = subprocess.run(['systemctl', 'show', 'adsb-server',
                                          '--property=ActiveEnterTimestamp'],
                                         capture_output=True, text=True)
            if '=' in uptime_result.stdout:
                status['adsb_uptime'] = uptime_result.stdout.split('=')[1].strip()
            else:
                status['adsb_uptime'] = 'Unknown'
        else:
            status['adsb_uptime'] = 'N/A'
    except:
        status['adsb_running'] = False
        status['adsb_uptime'] = 'Unknown'
    
    # WiFi status
    try:
        wifi = WiFiController('wlan0')
        current = wifi.get_current_network()
        if current and current.get('ssid'):
            status['wifi_connected'] = True
            status['wifi_ssid'] = current['ssid']
            status['wifi_ip'] = current.get('ip', 'Unknown')
        else:
            status['wifi_connected'] = False
            status['wifi_ssid'] = 'Not Connected'
            status['wifi_ip'] = 'N/A'
    except:
        status['wifi_connected'] = False
        status['wifi_ssid'] = 'Unknown'
        status['wifi_ip'] = 'N/A'
    
    # Hostname
    try:
        hostname_result = subprocess.run(['hostname'], capture_output=True, text=True)
        status['hostname'] = hostname_result.stdout.strip()
    except:
        status['hostname'] = 'Unknown'
    
    return status

def show_main_menu():
    """Display main menu"""
    while True:
        clear_screen()
        print_header("JLBMaritime ADS-B & WiFi Manager - Remote CLI")
        
        # Get and display system status
        status = get_system_status()
        
        print(f"{Color.BOLD}System Status:{Color.ENDC}")
        
        # ADS-B Server
        adsb_status = print_status_indicator(status['adsb_running'])
        print(f"  ADS-B Server: {adsb_status}", end='')
        if status['adsb_running'] and status['adsb_uptime'] != 'N/A':
            print(f" ({Color.CYAN}{status['adsb_uptime']}{Color.ENDC})")
        else:
            print()
        
        # WiFi
        if status['wifi_connected']:
            print(f"  WiFi: {Color.GREEN}Connected to {status['wifi_ssid']}{Color.ENDC} ({status['wifi_ip']})")
        else:
            print(f"  WiFi: {Color.RED}Not Connected{Color.ENDC}")
        
        # Hostname
        print(f"  Hostname: {Color.CYAN}{status['hostname']}{Color.ENDC}")
        
        print_separator()
        
        # Menu options
        print("\n[1] Dashboard & Status")
        print("[2] WiFi Manager")
        print("[3] ADS-B Configuration")
        print("[4] Service Control")
        print("[5] Logs & Troubleshooting")
        print("[6] Settings")
        print("[7] Exit")
        
        choice = get_choice("Enter choice [1-7]", 1, 7)
        
        if choice is None:
            continue
        elif choice == 1:
            show_dashboard()
        elif choice == 2:
            show_wifi_menu()
        elif choice == 3:
            show_adsb_menu()
        elif choice == 4:
            show_service_menu()
        elif choice == 5:
            show_logs_menu()
        elif choice == 6:
            show_settings_menu()
        elif choice == 7:
            clear_screen()
            print(f"\n{Color.CYAN}Thank you for using JLBMaritime ADS-B Manager!{Color.ENDC}\n")
            sys.exit(0)

def show_dashboard():
    """Show detailed dashboard"""
    clear_screen()
    print_header("Dashboard & Status")
    
    status = get_system_status()
    
    print_subheader("ADS-B Server")
    adsb_status = print_status_indicator(status['adsb_running'])
    print(f"Status: {adsb_status}")
    if status['adsb_running']:
        print(f"Uptime: {Color.CYAN}{status['adsb_uptime']}{Color.ENDC}")
    
    print_subheader("Network")
    if status['wifi_connected']:
        print(f"WiFi: {Color.GREEN}Connected{Color.ENDC}")
        print(f"Network: {Color.CYAN}{status['wifi_ssid']}{Color.ENDC}")
        print(f"IP Address: {Color.CYAN}{status['wifi_ip']}{Color.ENDC}")
    else:
        print(f"WiFi: {Color.RED}Not Connected{Color.ENDC}")
    
    print_subheader("System")
    print(f"Hostname: {Color.CYAN}{status['hostname']}{Color.ENDC}")
    
    try:
        # Uptime
        uptime = subprocess.run(['uptime', '-p'], capture_output=True, text=True)
        print(f"System Uptime: {Color.CYAN}{uptime.stdout.strip()}{Color.ENDC}")
        
        # Load average
        with open('/proc/loadavg', 'r') as f:
            load = f.read().split()[:3]
            print(f"Load Average: {Color.CYAN}{' '.join(load)}{Color.ENDC}")
    except:
        pass
    
    wait_for_enter()

def main():
    """Main entry point"""
    try:
        show_main_menu()
    except KeyboardInterrupt:
        clear_screen()
        print(f"\n{Color.YELLOW}Interrupted by user{Color.ENDC}\n")
        sys.exit(0)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
