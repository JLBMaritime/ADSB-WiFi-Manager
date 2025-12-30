"""
Logs & Troubleshooting Menu
Part of JLBMaritime ADS-B & Wi-Fi Management System
"""

import os
import subprocess
from cli.utils import *

LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs', 'adsb_server.log')

def show_logs_menu():
    """Show logs menu"""
    while True:
        clear_screen()
        print_header("Logs & Troubleshooting")
        
        print("[1] View Recent Logs")
        print("[2] Filter Logs by Level")
        print("[3] Tail Logs (Live)")
        print("[4] Clear Logs")
        print("[5] Back to Main Menu")
        
        choice = get_choice("Enter choice [1-5]", 1, 5)
        
        if choice is None:
            continue
        elif choice == 1:
            view_logs()
        elif choice == 2:
            filter_logs()
        elif choice == 3:
            tail_logs()
        elif choice == 4:
            clear_logs()
        elif choice == 5:
            break

def view_logs():
    """View recent logs"""
    clear_screen()
    print_subheader("Recent Logs (Last 50 lines)")
    
    if not os.path.exists(LOG_PATH):
        print_warning("No log file found")
        wait_for_enter()
        return
    
    try:
        subprocess.run(['tail', '-n', '50', LOG_PATH])
    except:
        with open(LOG_PATH, 'r') as f:
            lines = f.readlines()
            for line in lines[-50:]:
                print(line, end='')
    
    wait_for_enter()

def filter_logs():
    """Filter logs by level"""
    clear_screen()
    print_subheader("Filter Logs")
    
    print("[1] ERROR only")
    print("[2] WARNING and ERROR")
    print("[3] INFO, WARNING, and ERROR (All)")
    
    choice = get_choice("\nSelect filter [1-3]", 1, 3)
    
    if choice is None:
        return
    
    levels = ['ERROR', 'WARNING', 'INFO']
    selected_levels = levels[:choice]
    
    clear_screen()
    print_subheader(f"Filtered Logs ({', '.join(selected_levels)})")
    
    if not os.path.exists(LOG_PATH):
        print_warning("No log file found")
        wait_for_enter()
        return
    
    try:
        with open(LOG_PATH, 'r') as f:
            for line in f:
                if any(level in line for level in selected_levels):
                    # Color code based on level
                    if 'ERROR' in line:
                        print(f"{Color.RED}{line.strip()}{Color.ENDC}")
                    elif 'WARNING' in line:
                        print(f"{Color.YELLOW}{line.strip()}{Color.ENDC}")
                    else:
                        print(line.strip())
    except Exception as e:
        print_error(f"Error reading logs: {e}")
    
    wait_for_enter()

def tail_logs():
    """Tail logs in real-time"""
    clear_screen()
    print_subheader("Live Logs (Press Ctrl+C to exit)")
    
    if not os.path.exists(LOG_PATH):
        print_warning("No log file found")
        wait_for_enter()
        return
    
    try:
        subprocess.run(['tail', '-f', LOG_PATH])
    except KeyboardInterrupt:
        print("\n")
    except Exception as e:
        print_error(f"Error tailing logs: {e}")
        wait_for_enter()

def clear_logs():
    """Clear log file"""
    clear_screen()
    print_subheader("Clear Logs")
    
    if not confirm("Clear all logs? This cannot be undone."):
        return
    
    try:
        with open(LOG_PATH, 'w') as f:
            f.write('')
        print_success("Logs cleared successfully")
    except Exception as e:
        print_error(f"Failed to clear logs: {e}")
    
    wait_for_enter()
