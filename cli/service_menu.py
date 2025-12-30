"""
Service Control Menu - Control ADS-B server service
Part of JLBMaritime ADS-B & Wi-Fi Management System
"""

import subprocess
from cli.utils import *

def show_service_menu():
    """Show service control menu"""
    while True:
        clear_screen()
        print_header("Service Control")
        
        # Get service status
        status = get_service_status()
        print(f"ADS-B Server Status: {print_status_indicator(status == 'active')}")
        
        print_separator()
        
        print("\n[1] Start Server")
        print("[2] Stop Server")
        print("[3] Restart Server")
        print("[4] View Detailed Status")
        print("[5] Back to Main Menu")
        
        choice = get_choice("Enter choice [1-5]", 1, 5)
        
        if choice is None:
            continue
        elif choice == 1:
            start_service()
        elif choice == 2:
            stop_service()
        elif choice == 3:
            restart_service()
        elif choice == 4:
            view_status()
        elif choice == 5:
            break

def get_service_status():
    """Get service status"""
    try:
        result = subprocess.run(['systemctl', 'is-active', 'adsb-server'],
                              capture_output=True, text=True)
        return result.stdout.strip()
    except:
        return "unknown"

def start_service():
    """Start the service"""
    clear_screen()
    print_subheader("Starting Service")
    
    try:
        subprocess.run(['sudo', 'systemctl', 'start', 'adsb-server'], check=True)
        print_success("ADS-B Server started successfully")
    except Exception as e:
        print_error(f"Failed to start server: {e}")
    
    wait_for_enter()

def stop_service():
    """Stop the service"""
    clear_screen()
    print_subheader("Stopping Service")
    
    if not confirm("Stop ADS-B Server?"):
        return
    
    try:
        subprocess.run(['sudo', 'systemctl', 'stop', 'adsb-server'], check=True)
        print_success("ADS-B Server stopped successfully")
    except Exception as e:
        print_error(f"Failed to stop server: {e}")
    
    wait_for_enter()

def restart_service():
    """Restart the service"""
    clear_screen()
    print_subheader("Restarting Service")
    
    if not confirm("Restart ADS-B Server?"):
        return
    
    try:
        subprocess.run(['sudo', 'systemctl', 'restart', 'adsb-server'], check=True)
        print_success("ADS-B Server restarted successfully")
    except Exception as e:
        print_error(f"Failed to restart server: {e}")
    
    wait_for_enter()

def view_status():
    """View detailed status"""
    clear_screen()
    print_subheader("Detailed Status")
    
    try:
        result = subprocess.run(['systemctl', 'status', 'adsb-server', '--no-pager'],
                              capture_output=True, text=True)
        print(result.stdout)
    except Exception as e:
        print_error(f"Error retrieving status: {e}")
    
    wait_for_enter()
