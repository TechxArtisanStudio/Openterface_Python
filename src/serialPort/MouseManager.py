import time
import logging
import struct
from typing import Optional
from .Ch9329 import MOUSE_ABS_ACTION_PREFIX, MOUSE_REL_ACTION_PREFIX


class MouseManager:
    """
    Handles mouse input functionality for the CH9329 device
    """
    
    def __init__(self, serial_manager):
        """
        Initialize MouseManager with a reference to SerialManager
        
        Args:
            serial_manager: Reference to SerialManager instance for communication
        """
        self.serial_manager = serial_manager
        self.logger = logging.getLogger(__name__)
    
    def send_mouse_move_relative(self, delta_x: int, delta_y: int, buttons: int = 0) -> bool:
        """
        Send relative mouse movement
        
        Args:
            delta_x: X movement (-127 to 127)
            delta_y: Y movement (-127 to 127)
            buttons: Mouse button state (bit 0=left, bit 1=right, bit 2=middle)
        
        Returns:
            bool: True if successful
        """
        if not self.serial_manager.is_ready():
            self.logger.error("Device not ready for mouse input")
            return False
        
        # Clamp values to valid range
        delta_x = max(-127, min(127, delta_x))
        delta_y = max(-127, min(127, delta_y))
        
        # Convert negative values to signed bytes
        if delta_x < 0:
            delta_x = 256 + delta_x
        if delta_y < 0:
            delta_y = 256 + delta_y
        
        # Build mouse relative movement command
        cmd = bytearray(MOUSE_REL_ACTION_PREFIX)
        cmd.extend([buttons, delta_x, delta_y, 0])  # buttons, x, y, wheel
        
        return self.serial_manager.send_async_command(bytes(cmd), force=True)
    
    def send_mouse_move_absolute(self, x: int, y: int, buttons: int = 0) -> bool:
        """
        Send absolute mouse positioning
        
        Args:
            x: X coordinate (0-32767)
            y: Y coordinate (0-32767)
            buttons: Mouse button state (bit 0=left, bit 1=right, bit 2=middle)
        
        Returns:
            bool: True if successful
        """
        if not self.serial_manager.is_ready():
            self.logger.error("Device not ready for mouse input")
            return False
        
        # Clamp values to valid range
        x = max(0, min(32767, x))
        y = max(0, min(32767, y))
        
        # Convert to little endian 16-bit values
        x_bytes = struct.pack('<H', x)
        y_bytes = struct.pack('<H', y)
        
        # Build mouse absolute positioning command
        cmd = bytearray(MOUSE_ABS_ACTION_PREFIX)
        cmd.extend([buttons])  # Mouse buttons
        cmd.extend(x_bytes)    # X coordinate (2 bytes)
        cmd.extend(y_bytes)    # Y coordinate (2 bytes)
        cmd.extend([0])        # Wheel
        
        return self.serial_manager.send_async_command(bytes(cmd), force=True)
    
    def send_mouse_click(self, button: str = "left", double_click: bool = False) -> bool:
        """
        Send mouse click
        
        Args:
            button: "left", "right", or "middle"
            double_click: Whether to perform a double click
        
        Returns:
            bool: True if successful
        """
        if not self.serial_manager.is_ready():
            return False
            
        button_map = {
            "left": 0x01,
            "right": 0x02,
            "middle": 0x04
        }
        
        button_code = button_map.get(button.lower(), 0x01)
        
        # Press button
        success = self.send_mouse_move_relative(0, 0, button_code)
        if success:
            time.sleep(0.05)
            # Release button
            success = self.send_mouse_move_relative(0, 0, 0)
            
            if double_click and success:
                time.sleep(0.05)
                # Second click
                success = self.send_mouse_move_relative(0, 0, button_code)
                if success:
                    time.sleep(0.05)
                    success = self.send_mouse_move_relative(0, 0, 0)
        
        return success
    
    def send_mouse_scroll(self, scroll_delta: int) -> bool:
        """
        Send mouse scroll wheel movement
        
        Args:
            scroll_delta: Scroll amount (-127 to 127, positive = up, negative = down)
        
        Returns:
            bool: True if successful
        """
        if not self.serial_manager.is_ready():
            return False
        
        # Clamp to valid range
        scroll_delta = max(-127, min(127, scroll_delta))
        
        # Convert negative values to signed bytes
        if scroll_delta < 0:
            scroll_delta = 256 + scroll_delta
        
        # Build mouse scroll command
        cmd = bytearray(MOUSE_REL_ACTION_PREFIX)
        cmd.extend([0, 0, 0, scroll_delta])  # buttons=0, x=0, y=0, wheel=scroll_delta
        
        return self.serial_manager.send_async_command(bytes(cmd), force=True)