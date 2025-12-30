"""
ADS-B Configuration Menu - Interactive ADS-B server configuration
Part of JLBMaritime ADS-B & Wi-Fi Management System
"""

import sys
import os
import configparser
import socket

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from cli.utils import *

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'adsb_server_config.conf')

def show_adsb_menu():
    """Show ADS-B configuration menu"""
    while True:
        clear_screen()
        print_header("ADS-B Configuration")
        
        # Show current config
        config = load_config()
        print(f"Output Format: {Color.GREEN}{config['output_format'].upper()}{Color.ENDC}")
        print(f"Filter Mode: {Color.GREEN}{config['filter_mode'].upper()}{Color.ENDC}")
        if config['altitude_filter_enabled']:
            print(f"Altitude Filter: {Color.YELLOW}Max {config['max_altitude']}ft{Color.ENDC}")
        print(f"Endpoints: {Color.CYAN}{len(config['endpoints'])}{Color.ENDC}")
        
        print_separator()
        
        print("\n[1] Set Output Format")
        print("[2] Configure Filters")
        print("[3] Manage Endpoints")
        print("[4] View Full Configuration")
        print("[5] Save & Restart Server")
        print("[6] Back to Main Menu")
        
        choice = get_choice("Enter choice [1-6]", 1, 6)
        
        if choice is None:
            continue
        elif choice == 1:
            set_output_format()
        elif choice == 2:
            configure_filters()
        elif choice == 3:
            manage_endpoints()
        elif choice == 4:
            view_full_config()
        elif choice == 5:
            save_and_restart()
        elif choice == 6:
            break

def load_config():
    """Load ADS-B configuration"""
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    
    return {
        'output_format': config.get('Output', 'format', fallback='sbs1'),
        'filter_mode': config.get('Filter', 'mode', fallback='all'),
        'icao_list': [icao.strip() for icao in config.get('Filter', 'icao_list', fallback='').split(',') if icao.strip()],
        'altitude_filter_enabled': config.getboolean('Filter', 'altitude_filter_enabled', fallback=False),
        'max_altitude': config.getint('Filter', 'max_altitude', fallback=10000),
        'endpoints': load_endpoints(config)
    }

def load_endpoints(config):
    """Load endpoint configuration"""
    endpoints = []
    count = config.getint('Endpoints', 'count', fallback=0)
    for i in range(count):
        name = config.get('Endpoints', f'endpoint_{i}_name', fallback='')
        ip = config.get('Endpoints', f'endpoint_{i}_ip', fallback='')
        port = config.get('Endpoints', f'endpoint_{i}_port', fallback='')
        if ip and port:
            endpoints.append({'name': name, 'ip': ip, 'port': port})
    return endpoints

def set_output_format():
    """Set output format"""
    clear_screen()
    print_subheader("Set Output Format")
    
    print("[1] SBS1 Streaming - Real-time SBS1 format data")
    print("[2] JSON Objects - Individual JSON aircraft objects")
    print("[3] JSON→SBS1 - JSON data converted to SBS1 format")
    
    choice = get_choice("\nSelect format [1-3]", 1, 3)
    
    if choice is None:
        return
    
    formats = ['sbs1', 'json', 'json_to_sbs1']
    selected_format = formats[choice - 1]
    
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    
    if not config.has_section('Output'):
        config.add_section('Output')
    
    config.set('Output', 'format', selected_format)
    
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)
    
    print_success(f"Output format set to: {selected_format.upper()}")
    print_warning("Remember to restart the server for changes to take effect")
    wait_for_enter()

def configure_filters():
    """Configure filter settings"""
    while True:
        clear_screen()
        print_subheader("Configure Filters")
        
        config_data = load_config()
        
        print(f"Current Filter Mode: {Color.GREEN}{config_data['filter_mode'].upper()}{Color.ENDC}")
        if config_data['filter_mode'] == 'specific':
            print(f"ICAO List: {', '.join(config_data['icao_list']) if config_data['icao_list'] else 'None'}")
        
        if config_data['altitude_filter_enabled']:
            print(f"Altitude Filter: {Color.YELLOW}Enabled (Max: {config_data['max_altitude']}ft){Color.ENDC}")
        else:
            print(f"Altitude Filter: {Color.CYAN}Disabled{Color.ENDC}")
        
        print_separator()
        
        print("\n[1] Set Filter Mode (All/Specific)")
        print("[2] Manage ICAO List")
        print("[3] Configure Altitude Filter")
        print("[4] Back")
        
        choice = get_choice("Enter choice [1-4]", 1, 4)
        
        if choice is None or choice == 4:
            break
        elif choice == 1:
            set_filter_mode()
        elif choice == 2:
            manage_icao_list()
        elif choice == 3:
            configure_altitude_filter()

def set_filter_mode():
    """Set filter mode"""
    clear_screen()
    print_subheader("Set Filter Mode")
    
    print("[1] All Aircraft - Forward all aircraft data")
    print("[2] Specific ICAOs - Only forward specific aircraft")
    
    choice = get_choice("\nSelect mode [1-2]", 1, 2)
    
    if choice is None:
        return
    
    mode = 'all' if choice == 1 else 'specific'
    
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    config.set('Filter', 'mode', mode)
    
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)
    
    print_success(f"Filter mode set to: {mode.upper()}")
    wait_for_enter()

def manage_icao_list():
    """Manage ICAO filter list"""
    while True:
        clear_screen()
        print_subheader("ICAO Filter List")
        
        config_data = load_config()
        
        if config_data['icao_list']:
            print("Current ICAOs:\n")
            for i, icao in enumerate(config_data['icao_list'], 1):
                print(f"  [{i}] {icao}")
        else:
            print_warning("No ICAOs in list")
        
        print_separator()
        print("\n[1] Add ICAO")
        print("[2] Remove ICAO")
        print("[3] Clear All")
        print("[4] Back")
        
        choice = get_choice("Enter choice [1-4]", 1, 4)
        
        if choice is None or choice == 4:
            break
        elif choice == 1:
            add_icao()
        elif choice == 2:
            remove_icao()
        elif choice == 3:
            clear_icao_list()

def add_icao():
    """Add ICAO to filter list"""
    icao = get_input("\nEnter ICAO code (e.g., A92F2D)")
    if not icao:
        return
    
    icao = icao.strip().upper()
    
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    
    current_list = [i.strip() for i in config.get('Filter', 'icao_list', fallback='').split(',') if i.strip()]
    
    if icao in current_list:
        print_warning(f"ICAO {icao} already in list")
    else:
        current_list.append(icao)
        config.set('Filter', 'icao_list', ','.join(current_list))
        
        with open(CONFIG_PATH, 'w') as f:
            config.write(f)
        
        print_success(f"Added {icao} to filter list")
    
    wait_for_enter()

def remove_icao():
    """Remove ICAO from filter list"""
    config_data = load_config()
    
    if not config_data['icao_list']:
        print_warning("No ICAOs to remove")
        wait_for_enter()
        return
    
    print("\nSelect ICAO to remove:\n")
    for i, icao in enumerate(config_data['icao_list'], 1):
        print(f"[{i}] {icao}")
    
    choice = get_choice(f"\nSelect [1-{len(config_data['icao_list'])}], or 0 to cancel", 0, len(config_data['icao_list']))
    
    if choice is None or choice == 0:
        return
    
    removed_icao = config_data['icao_list'][choice - 1]
    config_data['icao_list'].remove(removed_icao)
    
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    config.set('Filter', 'icao_list', ','.join(config_data['icao_list']))
    
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)
    
    print_success(f"Removed {removed_icao}")
    wait_for_enter()

def clear_icao_list():
    """Clear all ICAOs"""
    if not confirm("Clear all ICAOs from filter list?"):
        return
    
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    config.set('Filter', 'icao_list', '')
    
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)
    
    print_success("ICAO list cleared")
    wait_for_enter()

def configure_altitude_filter():
    """Configure altitude filtering"""
    clear_screen()
    print_subheader("Altitude Filter")
    
    config_data = load_config()
    
    print("[1] Enable Altitude Filter")
    print("[2] Disable Altitude Filter")
    print("[3] Set Maximum Altitude")
    
    choice = get_choice("\nEnter choice [1-3]", 1, 3)
    
    if choice is None:
        return
    
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    
    if choice == 1:
        config.set('Filter', 'altitude_filter_enabled', 'true')
        print_success("Altitude filter enabled")
    elif choice == 2:
        config.set('Filter', 'altitude_filter_enabled', 'false')
        print_success("Altitude filter disabled")
    elif choice == 3:
        alt = get_input("Enter maximum altitude (feet)", str(config_data['max_altitude']))
        try:
            alt_int = int(alt)
            config.set('Filter', 'max_altitude', str(alt_int))
            print_success(f"Maximum altitude set to {alt_int}ft")
        except ValueError:
            print_error("Invalid altitude value")
    
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)
    
    wait_for_enter()

def manage_endpoints():
    """Manage TCP endpoints"""
    while True:
        clear_screen()
        print_subheader("TCP Endpoints")
        
        config_data = load_config()
        
        if config_data['endpoints']:
            headers = ["#", "Name", "IP", "Port"]
            rows = []
            for i, ep in enumerate(config_data['endpoints'], 1):
                rows.append([str(i), ep['name'] or 'Unnamed', ep['ip'], ep['port']])
            print_table(headers, rows)
        else:
            print_warning("No endpoints configured")
        
        print_separator()
        print("\n[1] Add Endpoint")
        print("[2] Remove Endpoint")
        print("[3] Test Endpoint")
        print("[4] Back")
        
        choice = get_choice("Enter choice [1-4]", 1, 4)
        
        if choice is None or choice == 4:
            break
        elif choice == 1:
            add_endpoint()
        elif choice == 2:
            remove_endpoint()
        elif choice == 3:
            test_endpoint()

def add_endpoint():
    """Add TCP endpoint"""
    clear_screen()
    print_subheader("Add Endpoint")
    
    name = get_input("Enter endpoint name (optional)", "")
    ip = get_input("Enter IP address")
    port = get_input("Enter port number")
    
    if not ip or not port:
        print_warning("Operation cancelled")
        wait_for_enter()
        return
    
    try:
        port_int = int(port)
    except ValueError:
        print_error("Invalid port number")
        wait_for_enter()
        return
    
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    
    endpoints = load_endpoints(config)
    endpoints.append({'name': name, 'ip': ip, 'port': str(port_int)})
    
    config.set('Endpoints', 'count', str(len(endpoints)))
    for i, ep in enumerate(endpoints):
        config.set('Endpoints', f'endpoint_{i}_name', ep['name'])
        config.set('Endpoints', f'endpoint_{i}_ip', ep['ip'])
        config.set('Endpoints', f'endpoint_{i}_port', ep['port'])
    
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)
    
    print_success(f"Added endpoint {ip}:{port_int}")
    wait_for_enter()

def remove_endpoint():
    """Remove endpoint"""
    config_data = load_config()
    
    if not config_data['endpoints']:
        print_warning("No endpoints to remove")
        wait_for_enter()
        return
    
    print("\nSelect endpoint to remove:\n")
    for i, ep in enumerate(config_data['endpoints'], 1):
        print(f"[{i}] {ep['name'] or 'Unnamed'} - {ep['ip']}:{ep['port']}")
    
    choice = get_choice(f"\nSelect [1-{len(config_data['endpoints'])}], or 0 to cancel", 0, len(config_data['endpoints']))
    
    if choice is None or choice == 0:
        return
    
    removed = config_data['endpoints'].pop(choice - 1)
    
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    
    config.set('Endpoints', 'count', str(len(config_data['endpoints'])))
    
    # Rewrite all endpoints
    for i, ep in enumerate(config_data['endpoints']):
        config.set('Endpoints', f'endpoint_{i}_name', ep['name'])
        config.set('Endpoints', f'endpoint_{i}_ip', ep['ip'])
        config.set('Endpoints', f'endpoint_{i}_port', ep['port'])
    
    # Remove old endpoint entries
    for i in range(len(config_data['endpoints']), len(config_data['endpoints']) + 10):
        config.remove_option('Endpoints', f'endpoint_{i}_name')
        config.remove_option('Endpoints', f'endpoint_{i}_ip')
        config.remove_option('Endpoints', f'endpoint_{i}_port')
    
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)
    
    print_success(f"Removed endpoint {removed['ip']}:{removed['port']}")
    wait_for_enter()

def test_endpoint():
    """Test endpoint connection"""
    config_data = load_config()
    
    if not config_data['endpoints']:
        print_warning("No endpoints to test")
        wait_for_enter()
        return
    
    print("\nSelect endpoint to test:\n")
    for i, ep in enumerate(config_data['endpoints'], 1):
        print(f"[{i}] {ep['name'] or 'Unnamed'} - {ep['ip']}:{ep['port']}")
    
    choice = get_choice(f"\nSelect [1-{len(config_data['endpoints'])}]", 1, len(config_data['endpoints']))
    
    if choice is None:
        return
    
    ep = config_data['endpoints'][choice - 1]
    
    print_info(f"Testing connection to {ep['ip']}:{ep['port']}...")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((ep['ip'], int(ep['port'])))
        sock.close()
        
        if result == 0:
            print_success("Connection successful!")
        else:
            print_error("Connection failed")
    except Exception as e:
        print_error(f"Test failed: {e}")
    
    wait_for_enter()

def view_full_config():
    """View full configuration"""
    clear_screen()
    print_subheader("Full Configuration")
    
    config_data = load_config()
    
    print(f"{Color.BOLD}Output Format:{Color.ENDC} {config_data['output_format']}")
    print(f"{Color.BOLD}Filter Mode:{Color.ENDC} {config_data['filter_mode']}")
    
    if config_data['filter_mode'] == 'specific':
        print(f"{Color.BOLD}ICAO List:{Color.ENDC} {', '.join(config_data['icao_list']) if config_data['icao_list'] else 'None'}")
    
    print(f"{Color.BOLD}Altitude Filter:{Color.ENDC} {'Enabled' if config_data['altitude_filter_enabled'] else 'Disabled'}")
    if config_data['altitude_filter_enabled']:
        print(f"{Color.BOLD}Max Altitude:{Color.ENDC} {config_data['max_altitude']}ft")
    
    print(f"\n{Color.BOLD}Endpoints:{Color.ENDC}")
    if config_data['endpoints']:
        for ep in config_data['endpoints']:
            print(f"  • {ep['name'] or 'Unnamed'}: {ep['ip']}:{ep['port']}")
    else:
        print("  None configured")
    
    wait_for_enter()

def save_and_restart():
    """Save configuration and restart server"""
    if not confirm("Save configuration and restart ADS-B server?"):
        return
    
    print_info("Restarting ADS-B server...")
    
    try:
        import subprocess
        subprocess.run(['sudo', 'systemctl', 'restart', 'adsb-server'], check=True)
        print_success("Server restarted successfully")
    except Exception as e:
        print_error(f"Failed to restart server: {e}")
    
    wait_for_enter()
