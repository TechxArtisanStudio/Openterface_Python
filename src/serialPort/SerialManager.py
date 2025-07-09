import serial
from serialPort.Ch9329 import  *
import time
import logging
import struct
from datetime import datetime
from typing import Optional, Callable
from .KeyboardManager import KeyboardManager
from .MouseManager import MouseManager

class SerialManager:
    # Constants
    ORIGINAL_BAUDRATE = 9600
    DEFAULT_BAUDRATE = 115200
    CONNECTION_TIMEOUT = 2  # 2 seconds
    MAX_RETRIES = 3  # Increased retry count
    
    def __init__(self):
        self.ser_port: Optional[serial.Serial] = None
        self.ready = False
        self.event_callback: Optional[Callable] = None
        self.is_switch_to_host = False
        self.is_target_usb_connected = False
        
        # Initialize keyboard and mouse managers
        self.keyboard = KeyboardManager(self)
        self.mouse = MouseManager(self)
        
        # Data callback
        self.data_ready_callback: Optional[Callable] = None
        
        # Timing
        self.latest_update_time = datetime.now()
        self.last_command_time = time.time()
        self.command_delay_ms = 0
        
        # Initialize logging
        self.logger = logging.getLogger(__name__)
    
    def connect(self, port_path: str, baudrate: int = None) -> bool:
        """
        Connect to a specific serial port
        
        Args:
            port_path: Serial port path (e.g., "COM7", "/dev/ttyUSB0")
            baudrate: Ignored - always uses 115200
            
        Returns:
            bool: True if connected successfully
        """
        # Always force 115200 as the target baudrate, regardless of input
        target_baudrate = self.DEFAULT_BAUDRATE
        
        self.logger.info(f"Connecting to serial port: {port_path} at {target_baudrate} baud")
        
        if self._attempt_connection(port_path, target_baudrate):
            self.logger.info(f"Successfully connected to {port_path} at {target_baudrate} baud")
            return True
        else:
            self.logger.error(f"Failed to connect to {port_path}")
            return False
    
    def _parse_config_baud_mode(self, config_bytes: bytes):
        """
        Parse baudrate and mode from CMD_GET_PARA_CFG response (see ch9329_en.md)
        Returns (baudrate, working_mode, serial_mode) or (None, None, None) if parse fails
        
        According to CH9329 protocol:
        - Byte 5: Working Mode (0x00-0x03 software, 0x80-0x83 hardware)  
        - Byte 6: Serial Communication Mode (0x00-0x02 software, 0x80-0x82 hardware)
        - Byte 7: Serial Communication Address
        - Bytes 8-11: Baudrate (high byte first, big endian)
        """
        try:
            if len(config_bytes) >= 56:  # Need at least 56 bytes for full config
                # Skip the header (57 AB 00 88 32) and get to the data portion
                data_start = 5  # Start after header
                working_mode = config_bytes[data_start]      # Byte 0 of data
                serial_mode = config_bytes[data_start + 1]   # Byte 1 of data
                address = config_bytes[data_start + 2]       # Byte 2 of data
                
                # Bytes 3-6 of data contain baudrate (big endian)
                baud_bytes = config_bytes[data_start + 3:data_start + 7]
                baudrate = int.from_bytes(baud_bytes, byteorder='big')
                
                self.logger.debug(f"Parsed config: working_mode=0x{working_mode:02X}, serial_mode=0x{serial_mode:02X}, address=0x{address:02X}, baudrate={baudrate}")
                return baudrate, working_mode, serial_mode
        except Exception as e:
            self.logger.error(f"Failed to parse config: {e}")
        return None, None, None

    def _attempt_connection(self, port_path: str, target_baudrate: int) -> bool:
        """
        Attempt a single connection to the serial port
        
        Args:
            port_path: Serial port path
            target_baudrate: Target baudrate (115200)
            
        Returns:
            bool: True if connection successful
        """
        # Clean up any existing connection
        if self.ser_port:
            self.close_port()
        
        # Try to open port with 115200 first (most common case)
        open_success = False
        for retry in range(self.MAX_RETRIES):
            try:
                open_success = self.open_port(port_path, target_baudrate)
                if open_success:
                    break
            except Exception as e:
                self.logger.warning(f"Port open attempt {retry + 1} failed: {e}")
            time.sleep(0.2)
        if not open_success:
            self.logger.warning(f"Failed to open serial port at {target_baudrate} baud")
            return False

        # Send CMD_GET_PARA_CFG and check baudrate/mode
        ret_bytes = self.send_sync_command(CMD_GET_PARA_CFG, force=True, timeout=2.0)
        if ret_bytes and len(ret_bytes) >= 56:
            baudrate, working_mode, serial_mode = self._parse_config_baud_mode(ret_bytes)
            self.logger.info(f"Device config: baudrate={baudrate}, working_mode=0x{working_mode:02X}, serial_mode=0x{serial_mode:02X}")
            
            # Check if baudrate is correct and we're in protocol mode (0x00 or 0x80)
            if baudrate == target_baudrate and (serial_mode == 0x00 or serial_mode == 0x80):
                self.logger.info("Device already configured correctly")
                return self._finalize_connection(port_path)
            else:
                self.logger.warning(f"Device baudrate/mode incorrect, resetting HID chip...")
                if self.reset_hid_chip():
                    # Re-verify after reset
                    ret_bytes2 = self.send_sync_command(CMD_GET_PARA_CFG, force=True, timeout=2.0)
                    if ret_bytes2:
                        baudrate2, working_mode2, serial_mode2 = self._parse_config_baud_mode(ret_bytes2)
                        self.logger.info(f"After reset - baudrate={baudrate2}, working_mode=0x{working_mode2:02X}, serial_mode=0x{serial_mode2:02X}")
                        if baudrate2 == target_baudrate and (serial_mode2 == 0x00 or serial_mode2 == 0x80):
                            return self._finalize_connection(port_path)
                        else:
                            self.logger.error(f"Device config still incorrect after reset")
                            return False
                    else:
                        self.logger.error("No response after reset")
                        return False
                else:
                    self.logger.error("Failed to reset HID chip")
                    return False
        else:
            self.logger.warning("No valid config response at 115200, attempting device reconfiguration from 9600...")
            return self._reconfigure_device_from_9600(port_path, target_baudrate)
    
    def _verify_device_response(self) -> bool:
        """
        Verify that the device responds to commands
        
        Returns:
            bool: True if device responds correctly
        """
        try:
            ret_bytes = self.send_sync_command(CMD_GET_PARA_CFG, force=True, timeout=2.0)
            if ret_bytes:
                self.logger.debug(f"Device responded with {len(ret_bytes)} bytes: {ret_bytes.hex(' ')}")
                
                # Check if we have the minimum expected response
                if len(ret_bytes) >= 7:
                    # Try to parse as a simple result first (might be an error response)
                    if len(ret_bytes) == 7:
                        result = CmdDataResult(ret_bytes)
                        result.dump()
                        if result.data == DEF_CMD_SUCCESS:
                            self.logger.info("Device responded successfully")
                            return True
                        else:
                            self.logger.warning(f"Device returned error code: {hex(result.data)}")
                            dump_error(result.data, ret_bytes)
                            return True  # Still a valid device response
                    elif len(ret_bytes) >= 55:
                        # Try to parse as full configuration
                        config = CmdDataParamConfig(ret_bytes)
                        config.dump()
                        self.logger.info("Device parameter configuration retrieved successfully")
                        return True
                    else:
                        self.logger.warning(f"Unexpected response length: {len(ret_bytes)} bytes")
                        return True  # If we got any response with valid checksum, assume it's our device
                else:
                    self.logger.error("Response too short to parse")
                    return False
            else:
                self.logger.warning("No response from device")
                return False
        except Exception as e:
            self.logger.error(f"Error verifying device response: {e}")
            return False
    
    def _reconfigure_device_from_9600(self, port_path: str, target_baudrate: int) -> bool:
        """
        Reconfigure device from 9600 to 115200 baudrate
        
        Args:
            port_path: Serial port path
            target_baudrate: Target baudrate (115200)
            
        Returns:
            bool: True if reconfiguration successful
        """
        self.close_port()
        
        # Try with original baudrate (9600)
        if not self.open_port(port_path, self.ORIGINAL_BAUDRATE):
            self.logger.error("Failed to open port at 9600 for reconfiguration")
            return False
        
        self.logger.info("Device opened at 9600. Attempting reconfiguration to 115200...")
        
        # Try factory reset first (simpler and more reliable)
        if self._try_factory_reset():
            return self._reconnect_after_reset(port_path, target_baudrate)
        
        # If factory reset fails, try full reconfiguration
        if self._try_full_reconfiguration():
            return self._reconnect_after_reset(port_path, target_baudrate)
        
        self.logger.error("Failed to reconfigure device")
        self.close_port()
        return False
    
    def _try_factory_reset(self) -> bool:
        """
        Attempt factory reset of the device
        
        Returns:
            bool: True if factory reset successful
        """
        try:
            self.logger.info("Attempting factory reset...")
            reset_success = self.factory_reset_hid_chip()
            if reset_success:
                self.logger.info("Factory reset completed successfully")
                return True
            else:
                self.logger.warning("Factory reset failed")
                return False
        except Exception as e:
            self.logger.error(f"Exception during factory reset: {e}")
            return False
    
    def _try_full_reconfiguration(self) -> bool:
        """
        Attempt full device reconfiguration
        
        Returns:
            bool: True if reconfiguration successful
        """
        try:
            self.logger.info("Attempting full device reconfiguration...")
            reconfig_success = self.reconfigure_hid_chip()
            if reconfig_success:
                self.logger.info("Full reconfiguration completed successfully")
                return True
            else:
                self.logger.warning("Full reconfiguration failed")
                return False
        except Exception as e:
            self.logger.error(f"Exception during reconfiguration: {e}")
            return False
    
    def _reconnect_after_reset(self, port_path: str, target_baudrate: int) -> bool:
        """
        Reconnect to device after reset/reconfiguration
        
        Args:
            port_path: Serial port path
            target_baudrate: Target baudrate (115200)
            
        Returns:
            bool: True if reconnection successful
        """
        self.close_port()
        time.sleep(2)  # Give device time to reset
        
        # Attempt to reconnect at target baudrate
        try:
            if self.open_port(port_path, target_baudrate):
                if self._verify_device_response():
                    return self._finalize_connection(port_path)
                else:
                    self.logger.warning("Device verification failed after reset")
            else:
                self.logger.warning("Failed to reopen port after reset")
        except Exception as e:
            self.logger.warning(f"Exception during reconnection: {e}")
        
        self.logger.error("Failed to reconnect after device reset")
        return False
    
    def _finalize_connection(self, port_path: str) -> bool:
        """
        Finalize the connection and set up the device
        
        Args:
            port_path: Serial port path
            
        Returns:
            bool: True if finalization successful
        """
        try:
            # Verify we're actually at the target baudrate
            if self.ser_port.baudrate != self.DEFAULT_BAUDRATE:
                self.logger.warning(f"Port opened at {self.ser_port.baudrate} instead of {self.DEFAULT_BAUDRATE}")
            
            # Mark as ready and send initial status command
            self.ready = True
            if self.event_callback:
                self.event_callback("connected", port_path)
            
            # Send info command to get device status
            self.send_sync_command(CMD_GET_INFO, force=True)
            
            return True
        except Exception as e:
            self.logger.error(f"Error finalizing connection: {e}")
            return False
    
    def open_port(self, device_path: str, baudrate: int = DEFAULT_BAUDRATE) -> bool:
        """Open serial port"""
        if self.ser_port and self.ser_port.is_open:
            if self.ser_port.name == device_path:
                return True
            self.close_port()
        
        if self.event_callback:
            self.event_callback("connecting", device_path)
        
        try:
            self.ser_port = serial.Serial(
                port=device_path,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.CONNECTION_TIMEOUT,
                write_timeout=self.CONNECTION_TIMEOUT
            )
            
            # Set RTS to low after opening the port
            self.ser_port.rts = False
            self.logger.debug(f"Set RTS to low on {device_path}")
            
            self.logger.info(f"Successfully opened serial port: {device_path} at {baudrate} baud")
            return True
        except serial.SerialException as e:
            self.logger.error(f"Cannot open serial port {device_path}: {e}")
            if self.event_callback:
                self.event_callback("connection_failed", device_path)
            return False
    
    def close_port(self):
        """Close serial port"""
        if self.ser_port and self.ser_port.is_open:
            port_name = self.ser_port.name
            try:
                self.ser_port.close()
                self.logger.info(f"Serial port {port_name} closed")
            except Exception as e:
                self.logger.error(f"Error closing serial port: {e}")
        self.ser_port = None
        self.ready = False
    
    def restart_port(self) -> bool:
        """Restart serial port connection"""
        if not self.ser_port:
            return False
        
        port_name = self.ser_port.name
        # Always use DEFAULT_BAUDRATE (115200) when restarting
        self.close_port()
        time.sleep(0.1)
        return self.open_port(port_name, self.DEFAULT_BAUDRATE)
    
    def write_data(self, data: bytes) -> bool:
        """Write data to serial port"""
        if not self.ser_port or not self.ser_port.is_open:
            self.logger.error("Serial port is not open")
            return False
        
        try:
            bytes_written = self.ser_port.write(data)
            self.ser_port.flush()
            self.logger.debug(f"Written {bytes_written} bytes: {data.hex(' ')}")
            return bytes_written == len(data)
        except serial.SerialException as e:
            self.logger.error(f"Error writing to serial port: {e}")
            return False
    
    def read_data(self, size: int = 1024) -> bytes:
        """Read data from serial port"""
        if not self.ser_port or not self.ser_port.is_open:
            return bytes()
        
        try:
            if self.ser_port.in_waiting > 0:
                data = self.ser_port.read(min(size, self.ser_port.in_waiting))
                if data:
                    self.latest_update_time = datetime.now()
                    self.logger.debug(f"Read {len(data)} bytes: {data.hex(' ')}")
                    self._process_received_data(data)
                return data
        except serial.SerialException as e:
            self.logger.error(f"Error reading from serial port: {e}")
        
        return bytes()
    
    def _process_received_data(self, data: bytes):
        """Process received data and update states"""
        try:
            # Check if it's a response to GET_INFO command
            if len(data) >= 13 and data[0:2] == bytes.fromhex("57 AB"):
                if data[3] == 0x01:  # GET_INFO response
                    info = CmdGetInfoResult(data)
                    # Update LED states from indicators
                    self.update_special_key_state(info.indicators)
                    
                    if self.data_ready_callback:
                        self.data_ready_callback(data)
        except Exception as e:
            self.logger.error(f"Error processing received data: {e}")
    
    def update_special_key_state(self, data: int):
        """Update special key states (Num Lock, Caps Lock, Scroll Lock)"""
        self.keyboard.update_special_key_state(data)
    
    def send_async_command(self, data: bytes, force: bool = False) -> bool:
        """Send asynchronous command"""
        if not force and not self.ready:
            return False
        
        # Apply command delay
        if self.command_delay_ms > 0:
            elapsed = (time.time() - self.last_command_time) * 1000
            if elapsed < self.command_delay_ms:
                time.sleep((self.command_delay_ms - elapsed) / 1000)
        
        # Calculate checksum and append
        command_with_checksum = data + bytes([self.calculate_checksum(data)])
        
        success = self.write_data(command_with_checksum)
        if success:
            self.last_command_time = time.time()
        
        return success
    
    def send_sync_command(self, data: bytes, force: bool = False, timeout: float = 1.0) -> bytes:
        """Send synchronous command and wait for response"""
        self.logger.debug(f"Sending command: {data.hex(' ')}")
        
        if not self.send_async_command(data, force):
            return bytes()
        
        # Wait for response
        start_time = time.time()
        response_data = bytes()
        
        while time.time() - start_time < timeout:
            if self.ser_port and self.ser_port.in_waiting > 0:
                chunk = self.read_data()
                response_data += chunk
                self.logger.debug(f"Accumulated response: {response_data.hex(' ')} ({len(response_data)} bytes)")
                
                # Check if we have a complete response
                if len(response_data) >= 7:  # Minimum response size
                    # For some responses, we might need to wait for more data
                    # Let's give it a bit more time to see if more data arrives
                    time.sleep(0.1)
                    if self.ser_port.in_waiting > 0:
                        additional_chunk = self.read_data()
                        response_data += additional_chunk
                        self.logger.debug(f"Final response: {response_data.hex(' ')} ({len(response_data)} bytes)")
                    
                    # Verify checksum
                    if self._verify_response_checksum(response_data):
                        return response_data
                    else:
                        self.logger.warning(f"Checksum verification failed for response: {response_data.hex(' ')}")
            
            time.sleep(0.01)  # Small delay to avoid busy waiting
        
        self.logger.warning(f"Command timeout. Partial response: {response_data.hex(' ')} ({len(response_data)} bytes)")
        return bytes()
    
    def _verify_response_checksum(self, data: bytes) -> bool:
        """Verify response checksum"""
        if len(data) < 2:
            self.logger.debug("Response too short for checksum verification")
            return False
        
        expected_checksum = data[-1]
        calculated_checksum = self.calculate_checksum(data[:-1])
        
        self.logger.debug(f"Checksum verification: expected=0x{expected_checksum:02x}, calculated=0x{calculated_checksum:02x}")
        
        is_valid = expected_checksum == calculated_checksum
        if not is_valid:
            self.logger.warning(f"Checksum mismatch: expected=0x{expected_checksum:02x}, calculated=0x{calculated_checksum:02x}")
        
        return is_valid
    
    @staticmethod
    def calculate_checksum(data: bytes) -> int:
        """Calculate checksum for command data"""
        return sum(data) & 0xFF
    
    def send_reset_command(self) -> bool:
        """Send reset command to HID chip"""
        ret_bytes = self.send_sync_command(CMD_RESET, force=True)
        if ret_bytes:
            try:
                result = CmdResetResult(ret_bytes)
                result.dump()
                return result.data == DEF_CMD_SUCCESS
            except Exception as e:
                self.logger.error(f"Failed to parse reset response: {e}")
        return False
    
    def reconfigure_hid_chip(self) -> bool:
        """Reconfigure HID chip to default baudrate while preserving other settings"""
        self.logger.info("Reconfiguring HID chip...")
        
        # Step 1: Get current configuration
        self.logger.info("Getting current chip configuration...")
        config_bytes = self.send_sync_command(CMD_GET_PARA_CFG, force=True, timeout=3.0)
        if not config_bytes or len(config_bytes) < 56:
            self.logger.error("Failed to get current chip configuration")
            return False
        
        # Step 2: Parse current configuration and modify only the baudrate
        try:
            # The response structure is: HEAD(2) + ADDR(1) + CMD(1) + LEN(1) + DATA(50) + SUM(1)
            # We need to extract the 50 bytes of configuration data
            if len(config_bytes) >= 56:
                # Extract the 50 bytes of configuration data (bytes 5-54)
                current_config = bytearray(config_bytes[5:55])
                
                self.logger.info(f"Current config length: {len(current_config)} bytes")
                self.logger.debug(f"Current config: {current_config.hex(' ')}")
                
                # Modify only the baudrate (bytes 3-6 in the config data)
                # Set baudrate to 115200 (big endian 32-bit)
                baudrate_bytes = struct.pack('>I', 115200)
                current_config[3:7] = baudrate_bytes
                
                # Ensure working mode is hardware mode (0x80)
                current_config[0] = 0x80
                
                # Ensure serial communication mode is protocol transmission mode (0x00)
                current_config[1] = 0x00
                
                self.logger.info("Modified config to set baudrate=115200, working_mode=0x80, serial_mode=0x00")
                self.logger.debug(f"Modified config: {current_config.hex(' ')}")
                
            else:
                self.logger.error(f"Configuration response too short: {len(config_bytes)} bytes")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to parse current configuration: {e}")
            return False
        
        # Step 3: Build CMD_SET_PARA_CFG command with modified configuration
        # Command structure: HEAD(2) + ADDR(1) + CMD(1) + LEN(1) + DATA(50) + SUM(1)
        cmd = bytearray()
        
        # Header: 57 AB 00 09 32 (HEAD + ADDR + CMD + LEN)
        cmd.extend(bytes.fromhex("57 AB 00 09 32"))  # 50 bytes = 0x32
        
        # Add the modified configuration data
        cmd.extend(current_config)
        
        # Step 4: Send the reconfiguration command
        self.logger.info("Sending reconfiguration command...")
        ret_bytes = self.send_sync_command(bytes(cmd), force=True, timeout=3.0)
        if ret_bytes:
            try:
                result = CmdDataResult(ret_bytes)
                result.dump()
                success = result.data == DEF_CMD_SUCCESS
                if success:
                    self.logger.info("HID chip reconfigured successfully")
                else:
                    self.logger.error(f"HID chip reconfiguration failed with error: {hex(result.data)}")
                    dump_error(result.data, ret_bytes)
                return success
            except Exception as e:
                self.logger.error(f"Failed to parse reconfigure response: {e}")
        else:
            self.logger.error("No response received for reconfiguration command")
        
        return False
    
    def factory_reset_hid_chip(self) -> bool:
        """Factory reset HID chip using set default cfg command"""
        self.logger.info("Factory resetting HID chip...")
        
        if self.event_callback:
            self.event_callback("factory_reset_start", None)
        
        ret_bytes = self.send_sync_command(CMD_SET_DEFAULT_CFG, force=True)
        
        if self.event_callback:
            self.event_callback("factory_reset_end", None)
        
        if ret_bytes:
            try:
                result = CmdDataResult(ret_bytes)
                result.dump()
                success = result.data == DEF_CMD_SUCCESS
                if success:
                    self.logger.info("HID chip factory reset successfully")
                else:
                    dump_error(result.data, ret_bytes)
                return success
            except Exception as e:
                self.logger.error(f"Failed to parse factory reset response: {e}")
        
        return False
    
    def reset_hid_chip(self) -> bool:
        """Reset HID chip and reopen serial port"""
        self.logger.info("Resetting HID chip...")
        
        # Save current port information
        port_name = self.ser_port.name if self.ser_port else None
        if not port_name:
            self.logger.error("No serial port available for reset")
            return False
        
        # Step 1: Send reconfigure command
        if not self.reconfigure_hid_chip():
            self.logger.error("Failed to reconfigure HID chip")
            return False
        
        # Step 2: Close the port and wait for device to reset
        self.logger.info("Closing port for device reset...")
        self.close_port()
        time.sleep(2)  # Give device more time to reset properly
        
        # Step 3: Reopen the port at the target baudrate
        self.logger.info(f"Reopening port {port_name} after reset...")
        if not self.open_port(port_name, self.DEFAULT_BAUDRATE):
            self.logger.error(f"Failed to reopen port {port_name} after reset")
            return False
        
        # Step 4: Verify the device is responding correctly
        self.logger.info("Verifying device response after reset...")
        ret_bytes = self.send_sync_command(CMD_GET_PARA_CFG, force=True, timeout=3.0)
        if ret_bytes and len(ret_bytes) >= 56:
            baudrate, working_mode, serial_mode = self._parse_config_baud_mode(ret_bytes)
            self.logger.info(f"Device config after reset: baudrate={baudrate}, working_mode=0x{working_mode:02X}, serial_mode=0x{serial_mode:02X}")
            
            # Check if configuration is correct
            if baudrate == self.DEFAULT_BAUDRATE and (serial_mode == 0x00 or serial_mode == 0x80):
                self.logger.info("HID chip reset completed successfully")
                return True
            else:
                self.logger.warning(f"Device configuration still incorrect after reset")
                return False
        else:
            self.logger.error("No valid response from device after reset")
            return False
    
    def set_command_delay(self, delay_ms: int):
        """Set delay between commands in milliseconds"""
        self.command_delay_ms = delay_ms
    
    def set_event_callback(self, callback: Callable):
        """Set event callback function"""
        self.event_callback = callback
    
    def set_data_ready_callback(self, callback: Callable):
        """Set data ready callback function"""
        self.data_ready_callback = callback
    
    def is_ready(self) -> bool:
        """Check if serial manager is ready"""
        return self.ready and self.ser_port and self.ser_port.is_open
    
    def get_port_name(self) -> Optional[str]:
        """Get current port name"""
        return self.ser_port.name if self.ser_port else None
    
    def disconnect(self):
        """Disconnect from the serial port"""
        if self.ser_port:
            port_name = self.ser_port.name
            self.close_port()
            if self.event_callback:
                self.event_callback("disconnected", port_name)
    
    def __del__(self):
        """Destructor"""
        self.close_port()
    
    # Convenience methods for backward compatibility
    def send_text(self, text: str) -> bool:
        """Send text by converting to key codes (convenience method)"""
        return self.keyboard.send_text(text)
    
    def send_key_press(self, key_code: int, modifier_keys: int = 0) -> bool:
        """Send a single key press (convenience method)"""
        return self.keyboard.send_key_press(key_code, modifier_keys)
    
    def send_key_combination(self, *keys) -> bool:
        """Send a key combination (convenience method)"""
        return self.keyboard.send_key_combination(*keys)
    
    def send_mouse_move_relative(self, delta_x: int, delta_y: int, buttons: int = 0) -> bool:
        """Send relative mouse movement (convenience method)"""
        return self.mouse.send_mouse_move_relative(delta_x, delta_y, buttons)
    
    def send_mouse_move_absolute(self, x: int, y: int, buttons: int = 0) -> bool:
        """Send absolute mouse positioning (convenience method)"""
        return self.mouse.send_mouse_move_absolute(x, y, buttons)
    
    def send_mouse_click(self, button: str = "left", double_click: bool = False) -> bool:
        """Send mouse click (convenience method)"""
        return self.mouse.send_mouse_click(button, double_click)
    
    def send_mouse_scroll(self, scroll_delta: int) -> bool:
        """Send mouse scroll wheel movement (convenience method)"""
        return self.mouse.send_mouse_scroll(scroll_delta)
    
    def get_num_lock_state(self) -> bool:
        """Get Num Lock state (convenience method)"""
        return self.keyboard.num_lock_state
    
    def get_caps_lock_state(self) -> bool:
        """Get Caps Lock state (convenience method)"""
        return self.keyboard.caps_lock_state
    
    def get_scroll_lock_state(self) -> bool:
        """Get Scroll Lock state (convenience method)"""
        return self.keyboard.scroll_lock_state