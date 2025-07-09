#!/usr/bin/env python3
"""
Example usage of the SerialManager for Openterface Mini KVM
"""

import logging
import time
from serialPort.SerialManager import SerialManager
from serialPort.Ch9329 import CMD_GET_INFO, CMD_GET_PARA_CFG

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for more detailed output
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def event_callback(event_type, data):
    """Callback function for serial port events"""
    print(f"Event: {event_type}, Data: {data}")

def data_ready_callback(data):
    """Callback function for received data"""
    print(f"Received data: {data.hex(' ')}")

def main():
    # Create SerialManager instance
    serial_manager = SerialManager()
    
    # Set callbacks
    serial_manager.set_event_callback(event_callback)
    serial_manager.set_data_ready_callback(data_ready_callback)
    
    # Specify the serial port path (modify this for your system)
    # Windows: "COM3", "COM4", etc.
    # Linux/Mac: "/dev/ttyUSB0", "/dev/ttyACM0", etc.
    port_path = "COM7"  # Change this to your actual port
    
    print(f"Attempting to connect to {port_path}...")
    
    # Connect to the device
    if serial_manager.connect(port_path):
        print(f"Successfully connected to: {serial_manager.get_port_name()}")
        
        try:
            # Keep the program running and periodically check device status
            while True:
                if serial_manager.is_ready():
                    print(f"Device Status:")
                    print(f"  Num Lock: {serial_manager.keyboard.num_lock_state}")
                    print(f"  Caps Lock: {serial_manager.keyboard.caps_lock_state}")
                    print(f"  Scroll Lock: {serial_manager.keyboard.scroll_lock_state}")
                    
                    # Send info command to refresh status
                    serial_manager.send_async_command(CMD_GET_INFO)
                    
                    time.sleep(5)
                else:
                    print("Device connection lost!")
                    break
                    
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            serial_manager.disconnect()
    else:
        print(f"Failed to connect to {port_path}")
        print("Please check:")
        print("1. The device is connected")
        print("2. The port path is correct")
        print("3. No other application is using the port")

if __name__ == "__main__":
    main()
