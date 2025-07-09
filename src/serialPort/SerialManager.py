import serial
from serialPort.Ch9329 import  *
import time
import logging
import struct
from datetime import datetime
from typing import Optional, Callable

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
        
        # LED states
        self.num_lock_state = False
        self.caps_lock_state = False
        self.scroll_lock_state = False
        
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
        self.num_lock_state = bool(data & 0x01)
        self.caps_lock_state = bool(data & 0x02)
        self.scroll_lock_state = bool(data & 0x04)
    
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
    
    def get_num_lock_state(self) -> bool:
        """Get Num Lock state"""
        return self.num_lock_state
    
    def get_caps_lock_state(self) -> bool:
        """Get Caps Lock state"""
        return self.caps_lock_state
    
    def get_scroll_lock_state(self) -> bool:
        """Get Scroll Lock state"""
        return self.scroll_lock_state
    
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
        
        return self.send_async_command(bytes(cmd), force=True)
    
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
            # time.sleep(0.05)  # Small delay
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
        if not self.is_ready():
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
        if not self.is_ready():
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
        
        return self.send_async_command(bytes(cmd), force=True)
    
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
        if not self.is_ready():
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
        
        return self.send_async_command(bytes(cmd), force=True)
    
    def send_mouse_click(self, button: str = "left", double_click: bool = False) -> bool:
        """
        Send mouse click
        
        Args:
            button: "left", "right", or "middle"
            double_click: Whether to perform a double click
        
        Returns:
            bool: True if successful
        """
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
        if not self.is_ready():
            return False
        
        # Clamp to valid range
        scroll_delta = max(-127, min(127, scroll_delta))
        
        # Convert negative values to signed bytes
        if scroll_delta < 0:
            scroll_delta = 256 + scroll_delta
        
        # Build mouse scroll command
        cmd = bytearray(MOUSE_REL_ACTION_PREFIX)
        cmd.extend([0, 0, 0, scroll_delta])  # buttons=0, x=0, y=0, wheel=scroll_delta
        
        return self.send_async_command(bytes(cmd), force=True)

