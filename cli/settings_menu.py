"""
Settings Menu - System settings and information
Part of JLBMaritime ADS-B & Wi-Fi Management System
"""

import os
import subprocess
import configparser
import zipfile
import tempfile
from datetime import datetime
from cli.utils import *

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'adsb_server_config.conf')
WEB_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'web_config.conf')

def show_settings_menu():
    """Show settings menu"""
    while True:
        clear_screen()
        print_header("Settings")
        
        print("[1] System Information")
        print("[2] Backup Configuration")
        print("[3] Back to Main Menu")
        
        choice = get_choice("Enter choice [1-3]", 1, 3)
        
        if choice is None:
            continue
        elif choice == 1:
            system_info()
        elif choice == 2:
            backup_config()
        elif choice == 3:
            break

def system_info():
    """Display system information"""
    clear_screen()
    print_subheader("System Information")
    
    try:
        # Hostname
        hostname = subprocess.run(['hostname'], capture_output=True, text=True).stdout.strip()
        print(f"{Color.BOLD}Hostname:{Color.ENDC} {hostname}")
        
        # Uptime
        uptime = subprocess.run(['uptime', '-p'], capture_output=True, text=True).stdout.strip()
        print(f"{Color.BOLD}Uptime:{Color.ENDC} {uptime}")
        
        # OS Info
        if os.path.exists('/etc/os-release'):
            with open('/etc/os-release', 'r') as f:
                for line in f:
                    if line.startswith('PRETTY_NAME='):
                        os_name = line.split('=')[1].strip().strip('"')
                        print(f"{Color.BOLD}OS:{Color.ENDC} {os_name}")
                        break
        
        # IP address
        ip_result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
        if ip_result.stdout:
            ips = ip_result.stdout.strip().split()
            if ips:
                print(f"{Color.BOLD}IP Address:{Color.ENDC} {ips[0]}")
        
    except Exception as e:
        print_error(f"Error retrieving system information: {e}")
    
    wait_for_enter()

def backup_config():
    """Backup configuration files"""
    clear_screen()
    print_subheader("Backup Configuration")
    
    try:
        # Create backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"adsb_backup_{timestamp}.zip"
        backup_path = os.path.join(tempfile.gettempdir(), backup_filename)
        
        print_info(f"Creating backup: {backup_filename}")
        
        # Create zip file
        with zipfile.ZipFile(backup_path, 'w') as zf:
            if os.path.exists(CONFIG_PATH):
                zf.write(CONFIG_PATH, 'adsb_server_config.conf')
                print_success("Added ADS-B configuration")
            
            if os.path.exists(WEB_CONFIG_PATH):
                zf.write(WEB_CONFIG_PATH, 'web_config.conf')
                print_success("Added web configuration")
        
        print_success(f"\nBackup created: {backup_path}")
        print_info("You can download this file using scp or similar tool")
        
    except Exception as e:
        print_error(f"Backup failed: {e}")
    
    wait_for_enter()
