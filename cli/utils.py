"""
CLI Utilities - Colors, formatting, and helper functions
Part of JLBMaritime ADS-B & Wi-Fi Management System
"""

import os
import sys

class Color:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def clear_screen():
    """Clear the terminal screen"""
    os.system('clear' if os.name != 'nt' else 'cls')

def print_header(text):
    """Print a header with color and formatting"""
    width = 70
    print(f"\n{Color.CYAN}{'═' * width}{Color.ENDC}")
    print(f"{Color.BOLD}{Color.CYAN}   {text.center(width-6)}{Color.ENDC}")
    print(f"{Color.CYAN}{'═' * width}{Color.ENDC}\n")

def print_subheader(text):
    """Print a subheader"""
    print(f"\n{Color.BLUE}━━━ {text} ━━━{Color.ENDC}\n")

def print_success(text):
    """Print success message"""
    print(f"{Color.GREEN}✓ {text}{Color.ENDC}")

def print_error(text):
    """Print error message"""
    print(f"{Color.RED}✗ {text}{Color.ENDC}")

def print_warning(text):
    """Print warning message"""
    print(f"{Color.YELLOW}⚠ {text}{Color.ENDC}")

def print_info(text):
    """Print info message"""
    print(f"{Color.CYAN}ℹ {text}{Color.ENDC}")

def print_separator():
    """Print a separator line"""
    print(f"{Color.CYAN}{'─' * 70}{Color.ENDC}")

def print_table(headers, rows, col_widths=None):
    """Print a formatted table"""
    if not rows:
        print_info("No data to display")
        return
    
    # Calculate column widths if not provided
    if col_widths is None:
        col_widths = []
        for i, header in enumerate(headers):
            max_width = len(header)
            for row in rows:
                if i < len(row):
                    max_width = max(max_width, len(str(row[i])))
            col_widths.append(max_width + 2)
    
    # Print header
    header_line = ""
    for i, header in enumerate(headers):
        header_line += f"{Color.BOLD}{header.ljust(col_widths[i])}{Color.ENDC}"
    print(header_line)
    print(Color.CYAN + "─" * sum(col_widths) + Color.ENDC)
    
    # Print rows
    for row in rows:
        row_line = ""
        for i, cell in enumerate(row):
            if i < len(col_widths):
                row_line += str(cell).ljust(col_widths[i])
        print(row_line)

def get_input(prompt, default=None):
    """Get user input with optional default"""
    if default:
        prompt_text = f"{prompt} [{default}]: "
    else:
        prompt_text = f"{prompt}: "
    
    value = input(prompt_text).strip()
    return value if value else default

def get_choice(prompt, min_val=1, max_val=None):
    """Get a numeric choice from user"""
    while True:
        try:
            choice = input(f"\n{prompt}: ").strip()
            if not choice:
                continue
                
            choice_int = int(choice)
            if max_val and (choice_int < min_val or choice_int > max_val):
                print_error(f"Please enter a number between {min_val} and {max_val}")
                continue
            return choice_int
        except ValueError:
            print_error("Please enter a valid number")
        except KeyboardInterrupt:
            print("\n")
            return None

def confirm(prompt="Are you sure?"):
    """Get yes/no confirmation from user"""
    while True:
        response = input(f"\n{prompt} (y/n): ").strip().lower()
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no']:
            return False
        else:
            print_error("Please enter 'y' or 'n'")

def wait_for_enter(message="Press Enter to continue..."):
    """Wait for user to press Enter"""
    input(f"\n{Color.CYAN}{message}{Color.ENDC}")

def print_status_indicator(is_active):
    """Print a colored status indicator"""
    if is_active:
        return f"{Color.GREEN}● RUNNING{Color.ENDC}"
    else:
        return f"{Color.RED}● STOPPED{Color.ENDC}"

def format_signal_strength(signal):
    """Format WiFi signal strength as bars"""
    try:
        signal_int = int(signal)
        if signal_int >= -50:
            return f"{Color.GREEN}▮▮▮▮{Color.ENDC}"
        elif signal_int >= -60:
            return f"{Color.GREEN}▮▮▮{Color.ENDC}▯"
        elif signal_int >= -70:
            return f"{Color.YELLOW}▮▮{Color.ENDC}▯▯"
        else:
            return f"{Color.RED}▮{Color.ENDC}▯▯▯"
    except:
        return "▯▯▯▯"

def truncate_text(text, max_length=30):
    """Truncate text to max length with ellipsis"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."
