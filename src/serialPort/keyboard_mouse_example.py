#!/usr/bin/env python3
"""
Keyboard and Mouse Input Example for Openterface Mini KVM
This example demonstrates how to send keyboard and mouse input to the target device.
"""

import logging
import time
from serialPort.SerialManager import SerialManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def wait_for_user(message):
    """Wait for user to press Enter before continuing"""
    input(f"\n{message}\nPress Enter to continue...")

def keyboard_examples(serial_manager):
    """Demonstrate keyboard input functionality"""
    print("\n" + "="*50)
    print("KEYBOARD INPUT EXAMPLES")
    print("="*50)
    
    if not serial_manager.is_ready():
        print("Device not ready!")
        return
    
    # Example 1: Send simple text
    wait_for_user("Example 1: Send simple text 'Hello World!'")
    print("Sending text: 'Hello World!'")
    serial_manager.keyboard.send_text("Hello World!")
    time.sleep(1)
    
    # Example 2: Send text with Enter
    wait_for_user("Example 2: Send text with Enter key")
    print("Sending: 'This is a new line' + Enter")
    serial_manager.keyboard.send_text("This is a new line\n")
    time.sleep(1)
    
    # Example 3: Key combinations
    wait_for_user("Example 3: Send Ctrl+A (Select All)")
    print("Sending: Ctrl+A")
    serial_manager.keyboard.send_key_combination("ctrl", "a")
    time.sleep(1)
    
    wait_for_user("Example 4: Send Ctrl+C (Copy)")
    print("Sending: Ctrl+C")
    serial_manager.keyboard.send_key_combination("ctrl", "c")
    time.sleep(1)
    
    wait_for_user("Example 5: Send Ctrl+V (Paste)")
    print("Sending: Ctrl+V")
    serial_manager.keyboard.send_key_combination("ctrl", "v")
    time.sleep(1)
    
    # Example 4: Function keys
    wait_for_user("Example 6: Send F1 key")
    print("Sending: F1")
    serial_manager.keyboard.send_key_combination("f1")
    time.sleep(1)
    
    # Example 5: Arrow keys
    wait_for_user("Example 7: Send arrow keys (Up, Down, Left, Right)")
    print("Sending arrow keys...")
    for direction in ["up", "down", "left", "right"]:
        print(f"  {direction.capitalize()} arrow")
        serial_manager.keyboard.send_key_combination(direction)
        time.sleep(0.5)
    
    # Example 6: Alt+Tab
    wait_for_user("Example 8: Send Alt+Tab (Switch windows)")
    print("Sending: Alt+Tab")
    serial_manager.keyboard.send_key_combination("alt", "tab")
    time.sleep(1)
    
    # Example 7: Special characters
    wait_for_user("Example 9: Send special characters")
    print("Sending: !@#$%^&*()")
    serial_manager.keyboard.send_text("!@#$%^&*()")
    time.sleep(1)
    
    # Example 8: Backspace
    wait_for_user("Example 10: Send Backspace key")
    print("Sending: Backspace")
    serial_manager.keyboard.send_key_combination("backspace")
    time.sleep(1)

def mouse_examples(serial_manager):
    """Demonstrate mouse input functionality"""
    print("\n" + "="*50)
    print("MOUSE INPUT EXAMPLES")
    print("="*50)
    
    if not serial_manager.is_ready():
        print("Device not ready!")
        return
    
    # Example 1: Mouse movement
    wait_for_user("Example 1: Move mouse cursor (relative movement)")
    print("Moving mouse in a square pattern...")
    movements = [(100, 0), (0, 100), (-100, 0), (0, -100)]
    for dx, dy in movements:
        print(f"  Moving by ({dx}, {dy})")
        serial_manager.mouse.send_mouse_move_relative(dx, dy)
        time.sleep(0.5)
    
    # Example 2: Mouse clicks
    wait_for_user("Example 2: Mouse clicks")
    print("Left click...")
    serial_manager.mouse.send_mouse_click("left")
    time.sleep(1)
    
    print("Right click...")
    serial_manager.mouse.send_mouse_click("right")
    time.sleep(1)
    
    print("Middle click...")
    serial_manager.mouse.send_mouse_click("middle")
    time.sleep(1)
    
    # Example 3: Double click
    wait_for_user("Example 3: Double click")
    print("Double clicking...")
    serial_manager.mouse.send_mouse_click("left", double_click=True)
    time.sleep(1)
    
    # Example 4: Mouse scroll
    wait_for_user("Example 4: Mouse scroll")
    print("Scrolling up...")
    for i in range(3):
        serial_manager.mouse.send_mouse_scroll(3)
        time.sleep(0.3)
    
    time.sleep(1)
    print("Scrolling down...")
    for i in range(3):
        serial_manager.mouse.send_mouse_scroll(-3)
        time.sleep(0.3)
    
    # Example 5: Absolute positioning
    wait_for_user("Example 5: Absolute mouse positioning")
    print("Moving to center of screen (assuming 1920x1080)...")
    serial_manager.mouse.send_mouse_move_absolute(960, 540)
    time.sleep(1)
    
    print("Moving to corners...")
    corners = [(0, 0), (1920, 0), (1920, 1080), (0, 1080)]
    for x, y in corners:
        print(f"  Moving to ({x}, {y})")
        serial_manager.mouse.send_mouse_move_absolute(x, y)
        time.sleep(0.8)

def advanced_examples(serial_manager):
    """Demonstrate advanced input combinations"""
    print("\n" + "="*50)
    print("ADVANCED INPUT EXAMPLES")
    print("="*50)
    
    if not serial_manager.is_ready():
        print("Device not ready!")
        return
    
    # Example 1: Open Run dialog and type command
    wait_for_user("Example 1: Open Windows Run dialog and type 'notepad'")
    print("Pressing Win+R...")
    serial_manager.keyboard.send_key_combination("win", "r")
    time.sleep(2)
    
    print("Typing 'notepad'...")
    serial_manager.keyboard.send_text("notepad")
    time.sleep(1)
    
    print("Pressing Enter...")
    serial_manager.keyboard.send_key_combination("enter")
    time.sleep(2)
    
    # Example 2: Type in notepad and save
    wait_for_user("Example 2: Type text in notepad")
    text = """Hello from Openterface Mini KVM!

This text was typed remotely using the CH9329 protocol.

Features demonstrated:
- Text input
- Key combinations
- Mouse control
- Special characters: !@#$%^&*()

Time: """ + time.strftime("%Y-%m-%d %H:%M:%S")
    
    print("Typing multi-line text...")
    serial_manager.keyboard.send_text(text)
    time.sleep(2)
    
    # Example 3: Save file with Ctrl+S
    wait_for_user("Example 3: Save file with Ctrl+S")
    print("Pressing Ctrl+S...")
    serial_manager.keyboard.send_key_combination("ctrl", "s")
    time.sleep(2)
    
    print("Typing filename 'openterface_test.txt'...")
    serial_manager.keyboard.send_text("openterface_test.txt")
    time.sleep(1)
    
    print("Pressing Enter to save...")
    serial_manager.keyboard.send_key_combination("enter")
    time.sleep(1)
    
    # Example 4: Mouse and keyboard combination
    wait_for_user("Example 4: Mouse and keyboard combination - select text")
    print("Pressing Ctrl+A to select all...")
    serial_manager.keyboard.send_key_combination("ctrl", "a")
    time.sleep(1)
    
    print("Moving mouse and clicking...")
    serial_manager.mouse.send_mouse_move_relative(50, 50)
    time.sleep(0.5)
    serial_manager.mouse.send_mouse_click("left")
    time.sleep(1)

def main():
    print("Openterface Mini KVM - Keyboard and Mouse Input Example")
    print("=" * 60)
    
    # Create SerialManager instance
    serial_manager = SerialManager()
    
    # Connect to device
    port_path = "COM7"  # Change this to your actual port
    print(f"Attempting to connect to {port_path}...")
    
    if not serial_manager.connect(port_path):
        print(f"Failed to connect to {port_path}")
        print("Please check:")
        print("1. The device is connected")
        print("2. The port path is correct")
        print("3. No other application is using the port")
        return
    
    print(f"Successfully connected to: {serial_manager.get_port_name()}")
    
    try:
        while True:
            print("\nSelect an example to run:")
            print("1. Keyboard Examples")
            print("2. Mouse Examples")
            print("3. Advanced Examples")
            print("4. Quick Test (Hello World)")
            print("5. Exit")
            
            choice = input("\nEnter your choice (1-5): ").strip()
            
            if choice == "1":
                keyboard_examples(serial_manager)
            elif choice == "2":
                mouse_examples(serial_manager)
            elif choice == "3":
                advanced_examples(serial_manager)
            elif choice == "4":
                print("Quick test: Sending 'Hello World!'")
                serial_manager.keyboard.send_text("Hello World!\n")
                print("Done!")
            elif choice == "5":
                break
            else:
                print("Invalid choice. Please try again.")
                
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        serial_manager.disconnect()
        print("Disconnected from device.")

if __name__ == "__main__":
    main()
