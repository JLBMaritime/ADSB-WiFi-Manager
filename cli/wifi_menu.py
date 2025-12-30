"""
WiFi Manager Menu - Interactive WiFi management interface
Part of JLBMaritime ADS-B & Wi-Fi Management System
"""

import sys
import os
from getpass import getpass

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from wifi_manager.wifi_controller import WiFiController
from cli.utils import *

wifi = WiFiController('wlan0')

def show_wifi_menu():
    """Show WiFi manager menu"""
    while True:
        clear_screen()
        print_header("WiFi Manager")
        
        # Show current connection
        current = wifi.get_current_network()
        if current and current.get('ssid'):
            ip = current.get('ip', 'Unknown')
            print(f"Current Network: {Color.GREEN}{current['ssid']}{Color.ENDC} ({ip}) ✓")
        else:
            print(f"Current Network: {Color.RED}Not Connected{Color.ENDC}")
        
        print_separator()
        
        print("\n[1] Scan for Networks")
        print("[2] View Saved Networks")
        print("[3] Connect to Network")
        print("[4] Forget Network")
        print("[5] Run Ping Test")
        print("[6] Network Diagnostics")
        print("[7] Back to Main Menu")
        
        choice = get_choice("Enter choice [1-7]", 1, 7)
        
        if choice is None:
            continue
        elif choice == 1:
            scan_networks()
        elif choice == 2:
            view_saved_networks()
        elif choice == 3:
            connect_to_network()
        elif choice == 4:
            forget_network()
        elif choice == 5:
            run_ping_test()
        elif choice == 6:
            show_diagnostics()
        elif choice == 7:
            break

def scan_networks():
    """Scan and display available networks"""
    clear_screen()
    print_subheader("Scanning for Networks")
    
    print_info("Scanning... This may take a few seconds...")
    
    try:
        networks = wifi.scan_networks()
        
        if not networks:
            print_warning("No networks found")
            wait_for_enter()
            return
        
        print(f"\n{Color.GREEN}Found {len(networks)} networks:{Color.ENDC}\n")
        
        headers = ["#", "SSID", "Signal", "Security", "In Use"]
        rows = []
        
        for i, network in enumerate(networks, 1):
            ssid = truncate_text(network.get('ssid', 'Hidden'), 25)
            signal = network.get('signal', 'N/A')
            signal_bars = format_signal_strength(signal) if signal != 'N/A' else 'N/A'
            security = "Secured" if network.get('secured') else "Open"
            in_use = "✓" if network.get('in_use') else ""
            
            rows.append([
                str(i),
                ssid,
                f"{signal_bars} ({signal}dBm)" if signal != 'N/A' else 'N/A',
                security,
                in_use
            ])
        
        print_table(headers, rows)
        
    except Exception as e:
        print_error(f"Error scanning networks: {e}")
    
    wait_for_enter()

def view_saved_networks():
    """View saved networks"""
    clear_screen()
    print_subheader("Saved Networks")
    
    try:
        saved = wifi.get_saved_networks()
        current = wifi.get_current_network()
        current_ssid = current.get('ssid') if current else None
        
        if not saved:
            print_warning("No saved networks")
            wait_for_enter()
            return
        
        headers = ["#", "SSID", "Status"]
        rows = []
        
        for i, network in enumerate(saved, 1):
            ssid = truncate_text(network, 25)
            status = f"{Color.GREEN}Connected{Color.ENDC}" if network == current_ssid else ""
            rows.append([str(i), ssid, status])
        
        print_table(headers, rows)
        
    except Exception as e:
        print_error(f"Error retrieving saved networks: {e}")
    
    wait_for_enter()

def connect_to_network():
    """Connect to a WiFi network"""
    clear_screen()
    print_subheader("Connect to Network")
    
    ssid = get_input("Enter SSID (network name)")
    if not ssid:
        print_warning("Operation cancelled")
        wait_for_enter()
        return
    
    password = getpass("Enter password (leave empty for open network): ")
    
    print_info(f"Connecting to {ssid}...")
    
    try:
        success = wifi.connect_to_network(ssid, password if password else None)
        
        if success:
            print_success(f"Successfully connected to {ssid}")
        else:
            print_error(f"Failed to connect to {ssid}")
    except Exception as e:
        print_error(f"Connection error: {e}")
    
    wait_for_enter()

def forget_network():
    """Forget a saved network"""
    clear_screen()
    print_subheader("Forget Network")
    
    try:
        saved = wifi.get_saved_networks()
        current = wifi.get_current_network()
        current_ssid = current.get('ssid') if current else None
        
        if not saved:
            print_warning("No saved networks to forget")
            wait_for_enter()
            return
        
        print("Saved networks:\n")
        for i, network in enumerate(saved, 1):
            status = " (Currently connected)" if network == current_ssid else ""
            print(f"[{i}] {network}{Color.YELLOW}{status}{Color.ENDC}")
        
        choice = get_choice(f"\nSelect network to forget [1-{len(saved)}], or 0 to cancel", 0, len(saved))
        
        if choice is None or choice == 0:
            print_warning("Operation cancelled")
            wait_for_enter()
            return
        
        ssid = saved[choice - 1]
        
        if ssid == current_ssid:
            print_error("Cannot forget currently connected network")
            wait_for_enter()
            return
        
        if not confirm(f"Forget network '{ssid}'?"):
            print_warning("Operation cancelled")
            wait_for_enter()
            return
        
        success = wifi.forget_network(ssid)
        
        if success:
            print_success(f"Network '{ssid}' forgotten")
        else:
            print_error(f"Failed to forget network '{ssid}'")
            
    except Exception as e:
        print_error(f"Error: {e}")
    
    wait_for_enter()

def run_ping_test():
    """Run a ping test"""
    clear_screen()
    print_subheader("Ping Test")
    
    host = get_input("Enter host to ping", "8.8.8.8")
    
    print_info(f"Pinging {host}...")
    
    try:
        result = wifi.ping_test(host)
        
        print()
        if result['success']:
            print_success("Ping successful")
        else:
            print_error("Ping failed")
        
        print(f"\n{Color.CYAN}Output:{Color.ENDC}")
        print(result['output'])
        
    except Exception as e:
        print_error(f"Ping test error: {e}")
    
    wait_for_enter()

def show_diagnostics():
    """Show network diagnostics"""
    clear_screen()
    print_subheader("Network Diagnostics")
    
    try:
        diag = wifi.get_diagnostics()
        
        print(f"{Color.BOLD}Interface:{Color.ENDC} {diag.get('interface', 'N/A')}")
        print(f"{Color.BOLD}IP Address:{Color.ENDC} {diag.get('ip', 'N/A')}")
        print(f"{Color.BOLD}Netmask:{Color.ENDC} {diag.get('netmask', 'N/A')}")
        print(f"{Color.BOLD}Gateway:{Color.ENDC} {diag.get('gateway', 'N/A')}")
        print(f"{Color.BOLD}DNS Servers:{Color.ENDC} {diag.get('dns', 'N/A')}")
        print(f"{Color.BOLD}MAC Address:{Color.ENDC} {diag.get('mac', 'N/A')}")
        
        if 'status' in diag:
            print(f"\n{Color.BOLD}Status:{Color.ENDC}")
            print(diag['status'])
        
    except Exception as e:
        print_error(f"Error retrieving diagnostics: {e}")
    
    wait_for_enter()
