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
    MAX_RETRIES = 2
    
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
        """Connect to a specific serial port"""
        if baudrate is None:
            baudrate = self.DEFAULT_BAUDRATE
            
        self.logger.info(f"Connecting to serial port: {port_path} at {baudrate} baud")
        
        # Try to open port with retries
        open_success = False
        for retry in range(self.MAX_RETRIES):
            open_success = self.open_port(port_path, baudrate)
            if open_success:
                break
            time.sleep(0.1)
        
        if not open_success:
            self.logger.error(f"Failed to open serial port: {port_path}")
            return False
        
        # Send parameter configuration command to verify it's our device
        ret_bytes = self.send_sync_command(CMD_GET_PARA_CFG, force=True)
        device_responded = False
        
        if ret_bytes:
            try:
                self.logger.debug(f"Received {len(ret_bytes)} bytes: {ret_bytes.hex(' ')}")
                
                # Check if we have the minimum expected response
                if len(ret_bytes) >= 7:
                    # Try to parse as a simple result first (might be an error response)
                    if len(ret_bytes) == 7:
                        result = CmdDataResult(ret_bytes)
                        result.dump()
                        if result.data == DEF_CMD_SUCCESS:
                            self.logger.info("Device responded successfully but with minimal data")
                            device_responded = True
                        else:
                            self.logger.warning(f"Device returned error code: {hex(result.data)}")
                            dump_error(result.data, ret_bytes)
                            # Still consider this a valid device response
                            device_responded = True
                    elif len(ret_bytes) >= 55:
                        # Try to parse as full configuration
                        config = CmdDataParamConfig(ret_bytes)
                        config.dump()
                        self.logger.info("Device parameter configuration retrieved successfully")
                        device_responded = True
                    else:
                        self.logger.warning(f"Unexpected response length: {len(ret_bytes)} bytes")
                        self.logger.debug(f"Response data: {ret_bytes.hex(' ')}")
                        # If we got any response with valid checksum, assume it's our device
                        device_responded = True
                else:
                    self.logger.error("Response too short to parse")
            except Exception as e:
                self.logger.error(f"Failed to parse parameter configuration: {e}")
                self.logger.debug(f"Raw response ({len(ret_bytes)} bytes): {ret_bytes.hex(' ')}")
                # Don't fail completely - if we got bytes, it might still be our device
                device_responded = bool(ret_bytes)
        
        if not device_responded:
            self.logger.warning("No response from device, trying with 9600 baudrate")
            self.close_port()
            
            # Try with original baudrate
            if self.open_port(port_path, self.ORIGINAL_BAUDRATE):
                # First try factory reset which is simpler
                self.logger.info("Trying factory reset first...")
                reset_success = self.factory_reset_hid_chip()
                if reset_success:
                    self.logger.info("Factory reset successful, reconnecting...")
                    self.close_port()
                    time.sleep(2)  # Give device time to reset
                    if self.open_port(port_path, baudrate):
                        ret_bytes = self.send_sync_command(CMD_GET_PARA_CFG, force=True)
                        if ret_bytes:
                            try:
                                self.logger.debug(f"After factory reset - received {len(ret_bytes)} bytes: {ret_bytes.hex(' ')}")
                                device_responded = True
                                self.logger.info("Device factory reset and connected successfully")
                            except Exception as e:
                                self.logger.error(f"Error parsing response after factory reset: {e}")
                                self.close_port()
                                return False
                        else:
                            self.close_port()
                            return False
                    else:
                        return False
                else:
                    # If factory reset fails, try full reconfiguration
                    if self.reconfigure_hid_chip():
                        self.close_port()
                        time.sleep(1)
                        if self.open_port(port_path, baudrate):
                            ret_bytes = self.send_sync_command(CMD_GET_PARA_CFG, force=True)
                            if ret_bytes:
                                try:
                                    self.logger.debug(f"After reconfig - received {len(ret_bytes)} bytes: {ret_bytes.hex(' ')}")
                                    device_responded = True
                                    self.logger.info("Device reconfigured and connected successfully")
                                except Exception as e:
                                    self.logger.error(f"Error parsing response after reconfiguration: {e}")
                                    self.close_port()
                                    return False
                            else:
                                self.close_port()
                                return False
                        else:
                            return False
                    else:
                        self.close_port()
                        return False
            else:
                return False
        
        # Mark as ready and send initial status command
        self.ready = True
        if self.event_callback:
            self.event_callback("connected", port_path)
        
        # Send info command to get device status
        self.send_sync_command(CMD_GET_INFO, force=True)
        
        self.logger.info("Serial port connection completed successfully")
        return True
    
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
        baudrate = self.ser_port.baudrate
        self.close_port()
        time.sleep(0.1)
        return self.open_port(port_name, baudrate)
    
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
        """Reconfigure HID chip to default baudrate and mode"""
        self.logger.info("Reconfiguring HID chip...")
        
        # Build configuration command from scratch based on C++ implementation
        # Command structure: [prefix] [addr] [cmd] [len] [mode] [cfg] [addr2] [baudrate] + config data
        cmd = bytearray()
        
        # Header: 57 AB 00 09 32
        cmd.extend(bytes.fromhex("57 AB 00 09 32"))
        
        # Mode and config: 82 80 00 00
        cmd.extend(bytes.fromhex("82 80 00 00"))
        
        # Baudrate (115200 as little endian 32-bit)
        cmd.extend(struct.pack('<I', 115200))
        
        # Reserved 2 bytes
        cmd.extend(RESERVED_2BYTES)
        
        # Package interval
        cmd.extend(PACKAGE_INTERVAL)
        
        # VID (0x1a86 for CH340 - common for these devices)
        cmd.extend(struct.pack('<H', 0x1a86))
        
        # PID (0x29e1 or similar)
        cmd.extend(struct.pack('<H', 0x29e1))
        
        # Keyboard upload interval
        cmd.extend(KEYBOARD_UPLOAD_INTERVAL)
        
        # Keyboard release timeout
        cmd.extend(KEYBOARD_RELEASE_TIMEOUT)
        
        # Keyboard auto enter
        cmd.extend(KEYBOARD_AUTO_ENTER)
        
        # Enter key configuration
        cmd.extend(KEYBOARD_ENTER)
        
        # Filter
        cmd.extend(FILTER)
        
        # Speed mode
        cmd.extend(SPEED_MODE)
        
        # Reserved 4 bytes
        cmd.extend(RESERVED_4BYTES)
        
        # Send the command
        ret_bytes = self.send_sync_command(bytes(cmd), force=True)
        if ret_bytes:
            try:
                result = CmdDataResult(ret_bytes)
                result.dump()
                success = result.data == DEF_CMD_SUCCESS
                if success:
                    self.logger.info("HID chip reconfigured successfully")
                else:
                    dump_error(result.data, ret_bytes)
                return success
            except Exception as e:
                self.logger.error(f"Failed to parse reconfigure response: {e}")
        
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
        """Reset HID chip"""
        port_name = self.ser_port.name if self.ser_port else None
        if self.reconfigure_hid_chip():
            self.close_port()
            time.sleep(1)
            if port_name and self.open_port(port_name, self.DEFAULT_BAUDRATE):
                return self.send_reset_command()
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