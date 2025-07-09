import time
import logging
from typing import Optional
from .Ch9329 import CMD_SEND_KB_GENERAL_DATA


class KeyboardManager:
    """
    Handles keyboard input functionality for the CH9329 device
    """
    
    def __init__(self, serial_manager):
        """
        Initialize KeyboardManager with a reference to SerialManager
        
        Args:
            serial_manager: Reference to SerialManager instance for communication
        """
        self.serial_manager = serial_manager
        self.logger = logging.getLogger(__name__)
        
        # LED states
        self.num_lock_state = False
        self.caps_lock_state = False
        self.scroll_lock_state = False
    
    def update_special_key_state(self, data: int):
        """Update special key states (Num Lock, Caps Lock, Scroll Lock)"""
        self.num_lock_state = bool(data & 0x01)
        self.caps_lock_state = bool(data & 0x02)
        self.scroll_lock_state = bool(data & 0x04)
    
    def send_keyboard_data(self, modifier_keys: int, key_codes: list) -> bool:
        """
        Send keyboard data to the device
        
        Args:
            modifier_keys: Bitmask for modifier keys according to CH9329 specification:
                           Bit 0: Left Ctrl, Bit 1: Left Shift, Bit 2: Left Alt, Bit 3: Left Windows
                           Bit 4: Right Ctrl, Bit 5: Right Shift, Bit 6: Right Alt, Bit 7: Right Windows
            key_codes: List of up to 6 key codes to send (HID usage codes)
        
        Returns:
            bool: True if command was sent successfully
        """
        if not self.serial_manager.is_ready():
            self.logger.error("Device not ready for keyboard input")
            return False

        # Ensure we don't exceed 6 key codes
        key_codes = key_codes[:6]
        
        # Pad with zeros if less than 6 keys
        while len(key_codes) < 6:
            key_codes.append(0)
        
        # Build keyboard command according to CH9329 specification:
        # HEAD: 0x57 0xAB, ADDR: 0x00, CMD: 0x02, LEN: 0x08
        # DATA: modifier_keys + 0x00 (reserved) + 6 key codes
        cmd = bytearray(CMD_SEND_KB_GENERAL_DATA)  # This is now "57 AB 00 02 08"
        cmd.append(modifier_keys)    # Byte 0: Modifier keys
        cmd.append(0x00)             # Byte 1: Reserved, always 0x00
        
        # Bytes 2-7: Up to 6 key codes
        for key_code in key_codes:
            cmd.append(key_code)
        
        return self.serial_manager.send_async_command(bytes(cmd), force=True)
    
    def send_key_press(self, key_code: int, modifier_keys: int = 0) -> bool:
        """
        Send a single key press
        
        Args:
            key_code: The key code to press
            modifier_keys: Optional modifier keys (Ctrl=0x01, Shift=0x02, Alt=0x04, GUI=0x08)
        
        Returns:
            bool: True if successful
        """
        # Send key press
        success = self.send_keyboard_data(modifier_keys, [key_code])
        if success:
            # Send key release
            success = self.send_keyboard_data(0, [])
        return success
    
    def send_text(self, text: str) -> bool:
        """
        Send text by converting to key codes
        
        Args:
            text: Text to send
        
        Returns:
            bool: True if successful
        """
        if not self.serial_manager.is_ready():
            return False
        
        for char in text:
            key_code, modifier = self._char_to_keycode(char)
            if key_code:
                if not self.send_key_press(key_code, modifier):
                    return False
                time.sleep(0.02)  # Small delay between characters
        
        return True
    
    def _char_to_keycode(self, char: str) -> tuple:
        """
        Convert a character to HID key code and modifier
        
        Args:
            char: Character to convert
        
        Returns:
            tuple: (key_code, modifier)
        """
        # Basic ASCII to HID key code mapping
        char_map = {
            'a': (0x04, 0), 'b': (0x05, 0), 'c': (0x06, 0), 'd': (0x07, 0), 'e': (0x08, 0),
            'f': (0x09, 0), 'g': (0x0A, 0), 'h': (0x0B, 0), 'i': (0x0C, 0), 'j': (0x0D, 0),
            'k': (0x0E, 0), 'l': (0x0F, 0), 'm': (0x10, 0), 'n': (0x11, 0), 'o': (0x12, 0),
            'p': (0x13, 0), 'q': (0x14, 0), 'r': (0x15, 0), 's': (0x16, 0), 't': (0x17, 0),
            'u': (0x18, 0), 'v': (0x19, 0), 'w': (0x1A, 0), 'x': (0x1B, 0), 'y': (0x1C, 0),
            'z': (0x1D, 0),
            
            'A': (0x04, 0x02), 'B': (0x05, 0x02), 'C': (0x06, 0x02), 'D': (0x07, 0x02), 'E': (0x08, 0x02),
            'F': (0x09, 0x02), 'G': (0x0A, 0x02), 'H': (0x0B, 0x02), 'I': (0x0C, 0x02), 'J': (0x0D, 0x02),
            'K': (0x0E, 0x02), 'L': (0x0F, 0x02), 'M': (0x10, 0x02), 'N': (0x11, 0x02), 'O': (0x12, 0x02),
            'P': (0x13, 0x02), 'Q': (0x14, 0x02), 'R': (0x15, 0x02), 'S': (0x16, 0x02), 'T': (0x17, 0x02),
            'U': (0x18, 0x02), 'V': (0x19, 0x02), 'W': (0x1A, 0x02), 'X': (0x1B, 0x02), 'Y': (0x1C, 0x02),
            'Z': (0x1D, 0x02),
            
            '1': (0x1E, 0), '2': (0x1F, 0), '3': (0x20, 0), '4': (0x21, 0), '5': (0x22, 0),
            '6': (0x23, 0), '7': (0x24, 0), '8': (0x25, 0), '9': (0x26, 0), '0': (0x27, 0),
            
            '!': (0x1E, 0x02), '@': (0x1F, 0x02), '#': (0x20, 0x02), '$': (0x21, 0x02), '%': (0x22, 0x02),
            '^': (0x23, 0x02), '&': (0x24, 0x02), '*': (0x25, 0x02), '(': (0x26, 0x02), ')': (0x27, 0x02),
            
            '\n': (0x28, 0),  # Enter
            '\t': (0x2B, 0),  # Tab
            ' ': (0x2C, 0),   # Space
            '-': (0x2D, 0), '_': (0x2D, 0x02),
            '=': (0x2E, 0), '+': (0x2E, 0x02),
            '[': (0x2F, 0), '{': (0x2F, 0x02),
            ']': (0x30, 0), '}': (0x30, 0x02),
            '\\': (0x31, 0), '|': (0x31, 0x02),
            ';': (0x33, 0), ':': (0x33, 0x02),
            "'": (0x34, 0), '"': (0x34, 0x02),
            '`': (0x35, 0), '~': (0x35, 0x02),
            ',': (0x36, 0), '<': (0x36, 0x02),
            '.': (0x37, 0), '>': (0x37, 0x02),
            '/': (0x38, 0), '?': (0x38, 0x02),
        }
        
        return char_map.get(char, (0, 0))
    
    def send_key_combination(self, *keys) -> bool:
        """
        Send a key combination (e.g., Ctrl+C, Alt+Tab)
        
        Args:
            *keys: Key names like 'ctrl', 'alt', 'shift', 'a', 'c', etc.
        
        Returns:
            bool: True if successful
        """
        if not self.serial_manager.is_ready():
            return False
            
        modifier = 0
        key_codes = []
        
        # Special key mappings (HID usage codes)
        special_keys = {
            'enter': 0x28, 'return': 0x28,
            'esc': 0x29, 'escape': 0x29,
            'backspace': 0x2A,
            'tab': 0x2B,
            'space': 0x2C,
            'capslock': 0x39,
            'f1': 0x3A, 'f2': 0x3B, 'f3': 0x3C, 'f4': 0x3D, 'f5': 0x3E, 'f6': 0x3F,
            'f7': 0x40, 'f8': 0x41, 'f9': 0x42, 'f10': 0x43, 'f11': 0x44, 'f12': 0x45,
            'up': 0x52, 'down': 0x51, 'left': 0x50, 'right': 0x4F,
            'home': 0x4A, 'end': 0x4D, 'pageup': 0x4B, 'pagedown': 0x4E,
            'delete': 0x4C, 'insert': 0x49,
        }
        
        for key in keys:
            key = key.lower()
            # CH9329 modifier bit mapping:
            # Bit 0: Left Ctrl, Bit 1: Left Shift, Bit 2: Left Alt, Bit 3: Left Windows
            # Bit 4: Right Ctrl, Bit 5: Right Shift, Bit 6: Right Alt, Bit 7: Right Windows
            if key in ['ctrl', 'control']:
                modifier |= 0x01  # Left Ctrl
            elif key == 'shift':
                modifier |= 0x02  # Left Shift
            elif key == 'alt':
                modifier |= 0x04  # Left Alt
            elif key in ['gui', 'win', 'cmd']:
                modifier |= 0x08  # Left Windows
            elif key == 'rctrl':
                modifier |= 0x10  # Right Ctrl
            elif key == 'rshift':
                modifier |= 0x20  # Right Shift
            elif key == 'ralt':
                modifier |= 0x40  # Right Alt
            elif key == 'rwin':
                modifier |= 0x80  # Right Windows
            elif key in special_keys:
                key_codes.append(special_keys[key])
            elif len(key) == 1:
                key_code, key_modifier = self._char_to_keycode(key)
                if key_code:
                    key_codes.append(key_code)
                    modifier |= key_modifier
        
        # Send key combination
        success = self.send_keyboard_data(modifier, key_codes)
        if success:
            time.sleep(0.05)
            # Release keys
            success = self.send_keyboard_data(0, [])
        
        return success