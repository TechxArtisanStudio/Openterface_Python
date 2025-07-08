#!/usr/bin/env python3
"""
Test script for SerialManager functionality
"""

import unittest
import sys
import os
from unittest.mock import Mock, patch, MagicMock

# Add the parent directory to the path to import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from serialPort.SerialManager import SerialManager
from serialPort.Ch9329 import (
    CMD_GET_INFO, CMD_GET_PARA_CFG, CMD_RESET, CMD_SET_DEFAULT_CFG,
    CmdGetInfoResult, CmdDataParamConfig, CmdDataResult, CmdResetResult,
    DEF_CMD_SUCCESS, DEF_CMD_ERR_TIMEOUT, DEF_CMD_ERR_HEAD,
    DEF_CMD_ERR_CMD, DEF_CMD_ERR_SUM, DEF_CMD_ERR_PARA, DEF_CMD_ERR_OPERATE
)

class TestSerialManager(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        self.serial_manager = SerialManager()
        
    def tearDown(self):
        """Clean up after tests"""
        self.serial_manager.close_port()
    
    def test_initialization(self):
        """Test SerialManager initialization"""
        self.assertFalse(self.serial_manager.ready)
        self.assertIsNone(self.serial_manager.ser_port)
        self.assertEqual(self.serial_manager.command_delay_ms, 0)
        self.assertFalse(self.serial_manager.num_lock_state)
        self.assertFalse(self.serial_manager.caps_lock_state)
        self.assertFalse(self.serial_manager.scroll_lock_state)
    
    def test_calculate_checksum(self):
        """Test checksum calculation"""
        data = bytes.fromhex("57 AB 00 01 00")
        expected_checksum = (0x57 + 0xAB + 0x00 + 0x01 + 0x00) & 0xFF
        calculated_checksum = SerialManager.calculate_checksum(data)
        self.assertEqual(calculated_checksum, expected_checksum)
    
    def test_update_special_key_state(self):
        """Test special key state updates"""
        # Test all LEDs off
        self.serial_manager.update_special_key_state(0x00)
        self.assertFalse(self.serial_manager.num_lock_state)
        self.assertFalse(self.serial_manager.caps_lock_state)
        self.assertFalse(self.serial_manager.scroll_lock_state)
        
        # Test Num Lock on
        self.serial_manager.update_special_key_state(0x01)
        self.assertTrue(self.serial_manager.num_lock_state)
        self.assertFalse(self.serial_manager.caps_lock_state)
        self.assertFalse(self.serial_manager.scroll_lock_state)
        
        # Test Caps Lock on
        self.serial_manager.update_special_key_state(0x02)
        self.assertFalse(self.serial_manager.num_lock_state)
        self.assertTrue(self.serial_manager.caps_lock_state)
        self.assertFalse(self.serial_manager.scroll_lock_state)
        
        # Test Scroll Lock on
        self.serial_manager.update_special_key_state(0x04)
        self.assertFalse(self.serial_manager.num_lock_state)
        self.assertFalse(self.serial_manager.caps_lock_state)
        self.assertTrue(self.serial_manager.scroll_lock_state)
        
        # Test all LEDs on
        self.serial_manager.update_special_key_state(0x07)
        self.assertTrue(self.serial_manager.num_lock_state)
        self.assertTrue(self.serial_manager.caps_lock_state)
        self.assertTrue(self.serial_manager.scroll_lock_state)
    
    @patch('serial.Serial')
    def test_connect_success(self, mock_serial):
        """Test successful device connection"""
        mock_serial_instance = Mock()
        mock_serial_instance.is_open = True
        mock_serial_instance.name = "COM1"
        mock_serial_instance.in_waiting = 0
        mock_serial.return_value = mock_serial_instance
        
        # Mock the sync command to return valid data
        with patch.object(self.serial_manager, 'send_sync_command') as mock_sync:
            mock_sync.return_value = b'\x57\xab\x00\x08\x32' + b'\x00' * 50  # Mock config response
            
            result = self.serial_manager.connect("COM1")
            
            self.assertTrue(result)
            self.assertTrue(self.serial_manager.is_ready())
    
    @patch('serial.Serial')
    def test_connect_failure(self, mock_serial):
        """Test connection failure"""
        mock_serial.side_effect = Exception("Port not found")
        
        result = self.serial_manager.connect("COM999")
        
        self.assertFalse(result)
        self.assertFalse(self.serial_manager.is_ready())
    
    def test_disconnect(self):
        """Test disconnection"""
        # Mock a connection first
        self.serial_manager.ser_port = Mock()
        self.serial_manager.ser_port.name = "COM1"
        self.serial_manager.ser_port.is_open = True
        self.serial_manager.ready = True
        
        self.serial_manager.disconnect()
        
        self.assertFalse(self.serial_manager.is_ready())
        self.assertIsNone(self.serial_manager.ser_port)
    
    def test_set_callbacks(self):
        """Test setting callback functions"""
        event_callback = Mock()
        data_callback = Mock()
        
        self.serial_manager.set_event_callback(event_callback)
        self.serial_manager.set_data_ready_callback(data_callback)
        
        self.assertEqual(self.serial_manager.event_callback, event_callback)
        self.assertEqual(self.serial_manager.data_ready_callback, data_callback)
    
    def test_command_delay(self):
        """Test command delay setting"""
        self.serial_manager.set_command_delay(100)
        self.assertEqual(self.serial_manager.command_delay_ms, 100)

class TestCh9329Structures(unittest.TestCase):
    """Test Ch9329 data structures"""
    
    def test_cmd_get_info_result(self):
        """Test CmdGetInfoResult parsing"""
        # Sample data for GET_INFO response
        data = bytes.fromhex("57 AB 00 01 08 01 01 03 00 00 00 00 00")
        
        result = CmdGetInfoResult(data)
        
        self.assertEqual(result.prefix, 0xAB57)  # Little endian
        self.assertEqual(result.addr1, 0x00)
        self.assertEqual(result.cmd, 0x01)
        self.assertEqual(result.len, 0x08)
        self.assertEqual(result.version, 0x01)
        self.assertEqual(result.targetConnected, 0x01)
        self.assertEqual(result.indicators, 0x03)
    
    def test_cmd_data_param_config(self):
        """Test CmdDataParamConfig parsing"""
        # Create sample configuration data
        data = bytearray(55)
        data[0] = 0x57  # prefix1
        data[1] = 0xAB  # prefix2
        data[2] = 0x00  # addr1
        data[3] = 0x08  # cmd
        data[4] = 0x32  # len
        data[5] = 0x82  # mode
        data[6] = 0x80  # cfg
        
        config = CmdDataParamConfig(bytes(data))
        
        self.assertEqual(config.prefix1, 0x57)
        self.assertEqual(config.prefix2, 0xAB)
        self.assertEqual(config.addr1, 0x00)
        self.assertEqual(config.cmd, 0x08)
        self.assertEqual(config.len, 0x32)
        self.assertEqual(config.mode, 0x82)
        self.assertEqual(config.cfg, 0x80)

def run_tests():
    """Run all tests"""
    print("Running SerialManager tests...")
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestSerialManager))
    suite.addTests(loader.loadTestsFromTestCase(TestCh9329Structures))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
