import config
import sys
import os
import time
from datetime import datetime
import threading

from device import DeviceFactory
from device.AbstractDeviceManager import DeviceSelector
from device import VideoFFmpeg
from device import SerialManager
from device import VideoHID
from device.DeviceSocketServer import DeviceSocketServer
from utils import logger

# Configure reduced logging - set to WARNING to reduce log output
logger.core_logger.setLevel(30)  # WARNING level
logger.serial_logger.setLevel(30)  # WARNING level
logger.hid_logger.setLevel(30)  # WARNING level
logger.ui_logger.setLevel(30)  # WARNING level

class DeviceGroupDemo:
    """
    Openterface Device Group Demo with Hot-Plug Detection
    
    This class demonstrates cross-platform device detection and monitoring
    functionality for Openterface devices.
    """
    
    def __init__(self):
        # Device configuration - Openterface VID/PID values
        self.HID_VID = "534D"
        self.HID_PID = "2109"
        self.Serial_port_VID = "1A86"
        self.Serial_port_PID = "7523"
        
        # Initialize device manager and selector
        self.device_manager = DeviceFactory.create_device_manager(
            self.Serial_port_VID, self.Serial_port_PID, 
            self.HID_VID, self.HID_PID
        )
        self.device_selector = DeviceSelector(self.device_manager)
        self.monitor = None
        self.selected_device_info = None
        self.socket_server = None
        self.running = True
        
        print(f"✅ Device Group Demo initialized for {DeviceFactory.get_current_platform()} platform")
        print(f"🔍 Device Configuration:")
        print(f"   Serial Port - VID:{self.Serial_port_VID} PID:{self.Serial_port_PID}")
        print(f"   HID Device  - VID:{self.HID_VID} PID:{self.HID_PID}")
        
        # Automatically start hotplug monitoring
        self.start_hotplug_monitoring()

    def format_device_brief(self, device):
        """Format device info briefly for display"""
        parts = []
        if device.get('serial_port_path'):
            parts.append(f"Serial:{device['serial_port_path']}")
        if device.get('camera_path'):
            parts.append(f"Video")
        if device.get('audio_path'):
            parts.append(f"Audio")
        if device.get('HID_path'):
            parts.append(f"HID")
        return " | ".join(parts) if parts else "Unknown device"

    def device_change_callback(self, event_data):
        """Callback function called when device changes are detected"""
        print(f"\n🚨 === Device Change Detected at {event_data['timestamp']} ===")
        
        changes_from_last = event_data['changes_from_last']
        changes_from_initial = event_data['changes_from_initial']
        
        # Report changes from last scan
        if changes_from_last['added_devices']:
            print(f"📱 NEW DEVICES CONNECTED ({len(changes_from_last['added_devices'])}):")
            for device in changes_from_last['added_devices']:
                print(f"  ➕ {self.format_device_brief(device)}")
        
        if changes_from_last['removed_devices']:
            print(f"🔌 DEVICES DISCONNECTED ({len(changes_from_last['removed_devices'])}):")
            for device in changes_from_last['removed_devices']:
                print(f"  ➖ {self.format_device_brief(device)}")
        
        if changes_from_last['modified_devices']:
            print(f"🔄 DEVICES MODIFIED ({len(changes_from_last['modified_devices'])}):")
            for change in changes_from_last['modified_devices']:
                print(f"  🔀 {self.format_device_brief(change['new'])}")
        
        # Report overall state compared to initial
        current_count = len(event_data['current_devices'])
        initial_count = len(event_data['initial_snapshot'].devices)
        print(f"📊 Total devices: {current_count} (was {initial_count} initially)")
        
        if changes_from_initial['added_devices']:
            print(f"📈 Net new since start: {len(changes_from_initial['added_devices'])}")
        
        if changes_from_initial['removed_devices']:
            print(f"📉 Net removed since start: {len(changes_from_initial['removed_devices'])}")
        
        print("=" * 60)

    def start_hotplug_monitoring(self, poll_interval=2.0):
        """Start hotplug monitoring"""
        print("🔧 Creating Cross-Platform Hotplug Monitor...")
        
        self.monitor = DeviceFactory.create_hotplug_monitor(
            serial_vid=self.Serial_port_VID,
            serial_pid=self.Serial_port_PID,
            hid_vid=self.HID_VID,
            hid_pid=self.HID_PID,
            poll_interval=poll_interval
        )
        
        # Add our callback function
        self.monitor.add_callback(self.device_change_callback)
        
        print("✅ Cross-platform hotplug monitor created and configured!")
        print(f"⏰ Polling interval: {self.monitor.poll_interval} seconds")
        
        # Start the monitoring process
        print("🚀 Starting hotplug monitoring...")
        self.monitor.start_monitoring()
        
        # Wait a moment for initial scan to complete
        time.sleep(1)
        
        # Display initial device state
        initial_state = self.monitor.get_initial_state()
        if initial_state:
            print(f"\n📋 Initial Device State (captured at {initial_state['timestamp']}):")
            print(f"   Found {initial_state['device_count']} device(s)")
            for i, device in enumerate(initial_state['devices'], 1):
                print(f"   {i}. {self.format_device_brief(device)}")
        else:
            print("⚠️  No initial devices found matching the specified VID/PID")
        
        print("🟢 Monitoring is now active!")
        print("💡 Connect or disconnect Openterface devices to see changes in real-time")

    def display_device_info(self):
        """Display detailed device information"""
        print("\n📱 Current Device Information")
        print("=" * 60)
        
        current_devices = self.device_manager.discover_devices()
        
        if not current_devices:
            print("   No devices found")
            return
        
        for i, device in enumerate(current_devices, 1):
            device_dict = device.to_dict()
            print(f"Device {i}:")
            print(f"   Port Chain: {device_dict.get('port_chain', 'Unknown')}")
            print(f"   Serial Port: {device_dict.get('serial_port_path', 'Not found')}")
            print(f"   HID Path: {device_dict.get('HID_path', 'Not found')}")
            print(f"   Camera: {device_dict.get('camera_path', 'Not found')}")
            print(f"   Audio: {device_dict.get('audio_path', 'Not found')}")
            print()

    def display_port_chains(self):
        """Display available port chains for device selection"""
        print("\n🎯 Device Selection by Port Chain:")
        print("=" * 60)
        
        grouped_devices = self.device_selector.list_devices_grouped_by_port_chain()
        if grouped_devices:
            for port_chain, devices in grouped_devices.items():
                print(f"Port Chain: {port_chain}")
                for device in devices:
                    print(f"  - {device}")
                print()
                
            # Example: Select first available device
            first_port_chain = list(grouped_devices.keys())[0]
            selected_device = self.device_selector.select_device_by_port_chain(first_port_chain)
            if selected_device:
                print(f"🎯 Example - Selected device from port chain '{first_port_chain}':")
                print(f"   {selected_device}")
        else:
            print("   No devices available for selection")

    def select_device_by_port_chain_interactive(self):
        """Interactive device selection by port chain with subdevice path display"""
        print("\n🎯 Interactive Device Selection by Port Chain")
        print("=" * 60)
        
        # Get current available devices
        current_devices = self.device_manager.discover_devices()
        
        if not current_devices:
            print("❌ No devices found for selection")
            return None
        
        # Group devices by port chain
        grouped_devices = {}
        for device in current_devices:
            device_dict = device.to_dict()
            port_chain = device_dict.get('port_chain', 'Unknown')
            if port_chain not in grouped_devices:
                grouped_devices[port_chain] = []
            grouped_devices[port_chain].append(device_dict)
        
        # Display available port chains
        port_chains = list(grouped_devices.keys())
        print(f"Available Port Chains ({len(port_chains)}):")
        
        for i, port_chain in enumerate(port_chains, 1):
            device_count = len(grouped_devices[port_chain])
            print(f"  {i}. Port Chain: {port_chain} ({device_count} device(s))")
            
            # Show brief device info for this port chain
            for device in grouped_devices[port_chain]:
                brief_info = self.format_device_brief(device)
                print(f"     └─ {brief_info}")
        
        print(f"  0. Cancel selection")
        print("-" * 60)
        
        # Get user selection
        while True:
            try:
                choice = input(f"\nSelect a port chain (0-{len(port_chains)}): ").strip()
                
                if choice == "0":
                    print("❌ Selection cancelled")
                    return None
                
                choice_num = int(choice)
                if 1 <= choice_num <= len(port_chains):
                    selected_port_chain = port_chains[choice_num - 1]
                    selected_devices = grouped_devices[selected_port_chain]
                    
                    print(f"\n✅ Selected Port Chain: {selected_port_chain}")
                    self.display_selected_device_details(selected_port_chain, selected_devices)
                    
                    # Store selected device info for socket control
                    self.selected_device_info = {
                        'port_chain': selected_port_chain,
                        'devices': selected_devices
                    }
                    
                    # Start socket server for device control
                    self.start_socket_server()
                    
                    return selected_port_chain, selected_devices
                else:
                    print(f"❌ Invalid choice. Please enter 0-{len(port_chains)}")
                    
            except ValueError:
                print("❌ Please enter a valid number")
            except KeyboardInterrupt:
                print("\n❌ Selection cancelled by user")
                return None

    def display_selected_device_details(self, port_chain, devices):
        """Display detailed information about the selected device and all its subdevices"""
        print(f"\n📋 Selected Device Details")
        print("=" * 60)
        print(f"🔗 Port Chain: {port_chain}")
        print(f"📊 Total Subdevices: {len(devices)}")
        print()
        
        # Organize subdevices by type
        subdevice_paths = {
            'Serial Port': [],
            'HID Device': [],
            'Camera': [],
            'Audio': []
        }
        
        # Collect all paths from all devices in this port chain
        for device in devices:
            if device.get('serial_port_path'):
                subdevice_paths['Serial Port'].append(device['serial_port_path'])
            if device.get('HID_path'):
                subdevice_paths['HID Device'].append(device['HID_path'])
            if device.get('camera_path'):
                subdevice_paths['Camera'].append(device['camera_path'])
            if device.get('audio_path'):
                subdevice_paths['Audio'].append(device['audio_path'])
        
        # Display organized subdevice information
        print("📱 Subdevice Paths:")
        for device_type, paths in subdevice_paths.items():
            if paths:
                print(f"\n  🔸 {device_type}:")
                for i, path in enumerate(paths, 1):
                    print(f"    {i}. {path}")
            else:
                print(f"\n  🔸 {device_type}: Not available")
        
        # Display detailed device information
        print(f"\n📝 Detailed Device Information:")
        for i, device in enumerate(devices, 1):
            print(f"\n  Device {i}:")
            print(f"    Serial Port ID: {device.get('serial_port', 'N/A')}")
            print(f"    Serial Port Path: {device.get('serial_port_path', 'N/A')}")
            print(f"    HID ID: {device.get('HID', 'N/A')}")
            print(f"    HID Path: {device.get('HID_path', 'N/A')}")
            print(f"    Camera ID: {device.get('camera', 'N/A')}")
            print(f"    Camera Path: {device.get('camera_path', 'N/A')}")
            print(f"    Audio ID: {device.get('audio', 'N/A')}")
            print(f"    Audio Path: {device.get('audio_path', 'N/A')}")
        
        print("=" * 60)
        print("✅ Device selection completed!")
        print("🌐 Socket server will start for device control...")

    def start_socket_server(self, host='localhost', port=8888):
        """Start socket server for device control using DeviceSocketServer"""
        try:
            # Pass device manager instead of selected device info
            self.socket_server = DeviceSocketServer(self.device_manager, host, port)
            success = self.socket_server.start_server()
            
            if success:
                print("✅ Socket server started successfully")
                print("📋 Clients can now discover and select devices via socket commands")
            else:
                print("❌ Failed to start socket server")
                
        except Exception as e:
            print(f"❌ Failed to create socket server: {e}")

    def stop_socket_server(self):
        """Stop the socket server"""
        if self.socket_server:
            self.socket_server.stop_server()
            self.socket_server = None

    # ...existing code...

    def get_port_chains_during_monitoring(self):
        """Get available port chains during active monitoring"""
        if not self.monitor:
            print("⚠️  Monitor not initialized")
            return []
        
        current_devices = self.device_manager.discover_devices()
        port_chains = []
        
        for device in current_devices:
            device_dict = device.to_dict()
            port_chain = device_dict.get('port_chain', 'Unknown')
            if port_chain not in port_chains:
                port_chains.append(port_chain)
        
        return port_chains

    def get_monitoring_status(self):
        """Check current monitoring status"""
        if not self.monitor:
            print("⚠️  Monitor not initialized")
            return
            
        current_state = self.monitor.get_current_state()
        initial_state = self.monitor.get_initial_state()
        
        if current_state and initial_state:
            print(f"\n📊 Current Monitoring Status:")
            print(f"   Initial devices: {initial_state['device_count']} (at {initial_state['timestamp']})")
            print(f"   Current devices: {current_state['device_count']} (at {current_state['timestamp']})")
            
            # Compare current with initial
            current_snapshot = self.monitor.device_manager.create_snapshot()
            changes = current_snapshot.compare_with(self.monitor.initial_snapshot)
            
            if changes['added_devices'] or changes['removed_devices']:
                print(f"\n🔄 Changes since start:")
                if changes['added_devices']:
                    print(f"   ➕ Added: {len(changes['added_devices'])} devices")
                if changes['removed_devices']:
                    print(f"   ➖ Removed: {len(changes['removed_devices'])} devices")
            else:
                print(f"\n✅ No changes since monitoring started")
                
            print(f"\n🏃‍♂️ Monitor is {'running' if self.monitor.running else 'stopped'}")

    def stop_monitoring(self):
        """Stop monitoring and display summary"""
        if not self.monitor:
            print("⚠️  No monitor to stop")
            return
            
        print("🛑 Stopping cross-platform hotplug monitoring...")
        self.monitor.stop_monitoring()
        print("✅ Monitoring stopped successfully!")
        
        # Display final summary
        final_state = self.monitor.get_current_state()
        initial_state = self.monitor.get_initial_state()
        
        if final_state and initial_state:
            print(f"\n📈 Final Summary:")
            print(f"   Platform: {DeviceFactory.get_current_platform()}")
            print(f"   Initial device count: {initial_state['device_count']}")
            print(f"   Final device count: {final_state['device_count']}")
            
            # Calculate final changes
            final_snapshot = self.monitor.device_manager.create_snapshot()
            final_changes = final_snapshot.compare_with(self.monitor.initial_snapshot)
            
            if final_changes['added_devices'] or final_changes['removed_devices']:
                print(f"   Net changes:")
                if final_changes['added_devices']:
                    print(f"     ➕ Added: {len(final_changes['added_devices'])} devices")
                if final_changes['removed_devices']:
                    print(f"     ➖ Removed: {len(final_changes['removed_devices'])} devices")
            else:
                print(f"   ✅ No net changes detected")


if __name__ == "__main__":
    print("🚀 Starting Openterface Device Group Demo")
    print(f"🖥️  Platform: {DeviceFactory.get_current_platform()}")
    print(f"✅ Platform supported: {DeviceFactory.is_platform_supported()}")
    
    demo = DeviceGroupDemo()
    
    try:
        # Wait for devices to be detected
        time.sleep(2)
        
        # Start socket server immediately - clients will discover and select devices
        print("\n� Starting socket server for client device control...")
        demo.start_socket_server()
        
        if demo.socket_server:
            print("\n📡 Socket server is running. Clients can discover and select devices.")
            print("� Available client commands: discover, select, serial, camera, hid, status")
            print("⏹️  Press Ctrl+C to stop")
            
            # Keep the program running
            while demo.running and (not demo.socket_server or demo.socket_server.running):
                time.sleep(1)
        else:
            print("⚠️  Failed to start socket server. Exiting...")
            
    except KeyboardInterrupt:
        print("\n\n🛑 Program interrupted by user")
    finally:
        demo.stop_socket_server()
        if demo.monitor:
            demo.stop_monitoring()
        print("\n🎯 Device Group Demo completed!")