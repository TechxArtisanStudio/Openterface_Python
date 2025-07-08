#!/usr/bin/env python3
"""
Serial Port Discovery Utility for Openterface Python
This utility helps find and select available serial ports.
"""

import sys
import platform

def find_serial_ports():
    """Find all available serial ports"""
    try:
        import serial.tools.list_ports
        ports = serial.tools.list_ports.comports()
        return ports
    except ImportError:
        print("Error: pyserial is not installed or not complete.")
        print("Please install with: pip install pyserial")
        return []

def filter_likely_ch9329_ports(ports):
    """Filter ports that are likely to be CH9329 devices"""
    likely_ports = []
    ch9329_indicators = [
        "CH340", "CH341", "ch340", "ch341",
        "USB-SERIAL", "usb serial", "USB Serial",
        "QinHeng", "qinheng", "1a86",  # CH340 vendor
        "USB2.0-Serial", "USB2.0-Ser"
    ]
    
    for port in ports:
        description = port.description.lower()
        manufacturer = getattr(port, 'manufacturer', '').lower()
        
        # Check if description or manufacturer contains CH9329 indicators
        for indicator in ch9329_indicators:
            if indicator.lower() in description or indicator.lower() in manufacturer:
                likely_ports.append(port)
                break
    
    return likely_ports

def display_ports(ports, title="Available Serial Ports"):
    """Display serial ports in a formatted way"""
    print(f"\n{title}:")
    print("-" * len(title))
    
    if not ports:
        print("  No ports found")
        return
    
    for i, port in enumerate(ports, 1):
        print(f"  {i:2d}. {port.device}")
        print(f"      Description: {port.description}")
        if hasattr(port, 'manufacturer') and port.manufacturer:
            print(f"      Manufacturer: {port.manufacturer}")
        if hasattr(port, 'vid') and port.vid:
            print(f"      VID: 0x{port.vid:04X}")
        if hasattr(port, 'pid') and port.pid:
            print(f"      PID: 0x{port.pid:04X}")
        print()

def get_port_selection(ports):
    """Get user's port selection"""
    if not ports:
        return None
    
    while True:
        try:
            print(f"\nSelect a port (1-{len(ports)}) or 'q' to quit: ", end="")
            choice = input().strip()
            
            if choice.lower() == 'q':
                return None
            
            index = int(choice) - 1
            if 0 <= index < len(ports):
                return ports[index].device
            else:
                print(f"Please enter a number between 1 and {len(ports)}")
        except ValueError:
            print("Please enter a valid number or 'q' to quit")
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            return None

def test_port_connection(port_path):
    """Test if we can connect to a port"""
    try:
        from SerialManager import SerialManager
        serial_manager = SerialManager()
        
        print(f"\nTesting connection to {port_path}...")
        success = serial_manager.connect(port_path)
        
        if success:
            print("✓ Connection successful!")
            print("✓ Device responds to commands")
            
            # Get some basic info
            if serial_manager.is_ready():
                print("✓ Device is ready for input")
            
            serial_manager.disconnect()
            return True
        else:
            print("✗ Connection failed")
            return False
            
    except ImportError:
        print("SerialManager not available for testing")
        return False
    except Exception as e:
        print(f"✗ Connection test failed: {e}")
        return False

def main():
    """Main function"""
    print("Openterface Python - Serial Port Discovery")
    print("=" * 45)
    
    # Platform-specific notes
    if platform.system() == "Windows":
        print("Note: On Windows, ports are typically named COM1, COM2, etc.")
    elif platform.system() == "Linux":
        print("Note: On Linux, ports are typically /dev/ttyUSB0, /dev/ttyACM0, etc.")
        print("You may need to run with sudo or add your user to the dialout group:")
        print("  sudo usermod -a -G dialout $USER")
    elif platform.system() == "Darwin":  # macOS
        print("Note: On macOS, ports are typically /dev/cu.usbserial-*, /dev/cu.usbmodem*, etc.")
    
    print("\nScanning for serial ports...")
    
    # Find all ports
    all_ports = find_serial_ports()
    if not all_ports:
        print("No serial ports found.")
        return
    
    # Filter likely CH9329 ports
    likely_ports = filter_likely_ch9329_ports(all_ports)
    
    # Display results
    if likely_ports:
        display_ports(likely_ports, "Likely Openterface/CH9329 Devices")
        display_ports([p for p in all_ports if p not in likely_ports], "Other Serial Ports")
        
        print("\nRecommendation: Try the 'Likely Openterface/CH9329 Devices' first.")
        
        # Let user select from likely ports first
        print("\nSelect from likely devices:")
        selected_port = get_port_selection(likely_ports)
        
        if not selected_port:
            print("\nSelect from all ports:")
            selected_port = get_port_selection(all_ports)
    else:
        display_ports(all_ports)
        selected_port = get_port_selection(all_ports)
    
    if selected_port:
        print(f"\nSelected port: {selected_port}")
        
        # Ask if user wants to test the connection
        try:
            test = input("\nTest connection? (y/N): ").strip().lower()
            if test in ['y', 'yes']:
                test_port_connection(selected_port)
        except KeyboardInterrupt:
            print("\nSkipping connection test.")
        
        print(f"\nTo use this port in your code:")
        print(f"  serial_manager = SerialManager()")
        print(f"  serial_manager.connect('{selected_port}')")
    else:
        print("\nNo port selected.")

if __name__ == "__main__":
    main()
