from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Callable, Any
from datetime import datetime
import copy

class DeviceInfo:
    """Data class to represent device information in a cross-platform way"""
    
    def __init__(self, 
                 port_chain: str = "",
                 serial_port: str = "",
                 serial_port_path: str = "",
                 hid_device: str = "",
                 hid_path: str = "",
                 camera_device: str = "",
                 camera_path: str = "",
                 audio_device: str = "",
                 audio_path: str = "",
                 platform_specific: Dict[str, Any] = None):
        """
        Initialize device information
        
        Args:
            port_chain: Unique identifier for the device's physical port chain
            serial_port: Serial port device identifier
            serial_port_path: System path to access serial port
            hid_device: HID device identifier
            hid_path: System path to access HID device
            camera_device: Camera device identifier
            camera_path: System path to access camera
            audio_device: Audio device identifier
            audio_path: System path to access audio
            platform_specific: Additional platform-specific data
        """
        self.port_chain = port_chain
        self.serial_port = serial_port
        self.serial_port_path = serial_port_path
        self.hid_device = hid_device
        self.hid_path = hid_path
        self.camera_device = camera_device
        self.camera_path = camera_path
        self.audio_device = audio_device
        self.audio_path = audio_path
        self.platform_specific = platform_specific or {}
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for compatibility"""
        return {
            'port_chain': self.port_chain,
            'serial_port': self.serial_port,
            'serial_port_path': self.serial_port_path,
            'HID': self.hid_device,
            'HID_path': self.hid_path,
            'camera': self.camera_device,
            'camera_path': self.camera_path,
            'audio': self.audio_device,
            'audio_path': self.audio_path,
            'platform_specific': self.platform_specific
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeviceInfo':
        """Create from dictionary for compatibility"""
        return cls(
            port_chain=data.get('port_chain', ''),
            serial_port=data.get('serial_port', ''),
            serial_port_path=data.get('serial_port_path', ''),
            hid_device=data.get('HID', ''),
            hid_path=data.get('HID_path', ''),
            camera_device=data.get('camera', ''),
            camera_path=data.get('camera_path', ''),
            audio_device=data.get('audio', ''),
            audio_path=data.get('audio_path', ''),
            platform_specific=data.get('platform_specific', {})
        )
    
    def get_unique_key(self) -> str:
        """Generate a unique key for this device"""
        return f"{self.port_chain}-{self.serial_port}-{self.hid_device}"
    
    def __eq__(self, other) -> bool:
        """Check equality with another DeviceInfo"""
        if not isinstance(other, DeviceInfo):
            return False
        return self.get_unique_key() == other.get_unique_key()
    
    def __str__(self) -> str:
        """String representation"""
        parts = []
        if self.serial_port_path:
            parts.append(f"Serial:{self.serial_port_path}")
        if self.camera_path:
            parts.append("Camera")
        if self.audio_path:
            parts.append("Audio")
        if self.hid_path:
            parts.append("HID")
        return f"Device[{self.port_chain}]: " + " | ".join(parts) if parts else f"Device[{self.port_chain}]: Unknown"


class DeviceSnapshot:
    """Cross-platform device snapshot for comparing device states"""
    
    def __init__(self, devices: List[DeviceInfo]):
        self.timestamp = datetime.now()
        self.devices = devices
        
    def compare_with(self, other: 'DeviceSnapshot') -> Dict[str, List[DeviceInfo]]:
        """Compare this snapshot with another snapshot"""
        changes = {
            'added_devices': [],
            'removed_devices': [],
            'modified_devices': []
        }
        
        # Convert device lists to dictionaries for easier comparison
        current_devices = {dev.get_unique_key(): dev for dev in self.devices}
        other_devices = {dev.get_unique_key(): dev for dev in other.devices}
        
        # Find added devices
        for key, device in current_devices.items():
            if key not in other_devices:
                changes['added_devices'].append(device)
        
        # Find removed devices
        for key, device in other_devices.items():
            if key not in current_devices:
                changes['removed_devices'].append(device)
        
        # Find modified devices (currently just checking if different objects)
        for key, device in current_devices.items():
            if key in other_devices:
                if device.to_dict() != other_devices[key].to_dict():
                    changes['modified_devices'].append({
                        'old': other_devices[key],
                        'new': device
                    })
        
        return changes


class AbstractDeviceManager(ABC):
    """Abstract base class for cross-platform device management"""
    
    def __init__(self, serial_vid: str, serial_pid: str, hid_vid: str, hid_pid: str):
        """
        Initialize the device manager
        
        Args:
            serial_vid: Vendor ID for serial devices
            serial_pid: Product ID for serial devices
            hid_vid: Vendor ID for HID devices
            hid_pid: Product ID for HID devices
        """
        self.serial_vid = serial_vid
        self.serial_pid = serial_pid
        self.hid_vid = hid_vid
        self.hid_pid = hid_pid
        
    @abstractmethod
    def discover_devices(self) -> List[DeviceInfo]:
        """
        Discover all devices matching the specified VID/PID
        
        Returns:
            List of DeviceInfo objects representing found devices
        """
        pass
    
    @abstractmethod
    def get_port_chain(self, device_identifier: Any) -> str:
        """
        Get the port chain for a device
        
        Args:
            device_identifier: Platform-specific device identifier
            
        Returns:
            String representing the port chain
        """
        pass
    
    def get_devices_by_port_chain(self, target_port_chain: str) -> List[DeviceInfo]:
        """
        Get devices matching a specific port chain
        
        Args:
            target_port_chain: The port chain to search for
            
        Returns:
            List of DeviceInfo objects with matching port chain
        """
        all_devices = self.discover_devices()
        return [dev for dev in all_devices if dev.port_chain == target_port_chain]
    
    def list_available_port_chains(self) -> List[str]:
        """
        List all available port chains
        
        Returns:
            List of unique port chain strings
        """
        all_devices = self.discover_devices()
        port_chains = set(dev.port_chain for dev in all_devices if dev.port_chain)
        return sorted(list(port_chains))
    
    def create_snapshot(self) -> DeviceSnapshot:
        """
        Create a snapshot of current device state
        
        Returns:
            DeviceSnapshot object
        """
        devices = self.discover_devices()
        return DeviceSnapshot(devices)


class AbstractHotplugMonitor(ABC):
    """Abstract base class for cross-platform hotplug monitoring"""
    
    def __init__(self, device_manager: AbstractDeviceManager, poll_interval: float = 2.0):
        """
        Initialize the hotplug monitor
        
        Args:
            device_manager: The device manager to use for discovery
            poll_interval: Time in seconds between device scans
        """
        self.device_manager = device_manager
        self.poll_interval = poll_interval
        self.callbacks = []
        self.running = False
        self.thread = None
        self.initial_snapshot = None
        self.last_snapshot = None
        
    def add_callback(self, callback: Callable):
        """Add a callback function to be called when device changes are detected"""
        self.callbacks.append(callback)
        
    def remove_callback(self, callback: Callable):
        """Remove a callback function"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
    
    def start_monitoring(self):
        """Start monitoring for device changes"""
        if self.running:
            return
            
        # Capture initial device state
        self.initial_snapshot = self.device_manager.create_snapshot()
        self.last_snapshot = copy.deepcopy(self.initial_snapshot)
        
        self.running = True
        self.thread = self._create_monitor_thread()
        self.thread.start()
    
    def stop_monitoring(self):
        """Stop monitoring for device changes"""
        if not self.running:
            return
            
        self.running = False
        if self.thread:
            self.thread.join(timeout=5.0)
    
    @abstractmethod
    def _create_monitor_thread(self):
        """Create and return the monitoring thread"""
        pass
    
    def _handle_device_changes(self, current_snapshot: DeviceSnapshot):
        """Handle detected device changes"""
        changes = current_snapshot.compare_with(self.last_snapshot)
        
        # Check if there are any changes
        if (changes['added_devices'] or 
            changes['removed_devices'] or 
            changes['modified_devices']):
            
            # Compare with initial snapshot
            initial_changes = current_snapshot.compare_with(self.initial_snapshot)
            
            # Call registered callbacks
            for callback in self.callbacks:
                try:
                    callback({
                        'timestamp': current_snapshot.timestamp,
                        'current_devices': [dev.to_dict() for dev in current_snapshot.devices],
                        'changes_from_last': {
                            'added_devices': [dev.to_dict() for dev in changes['added_devices']],
                            'removed_devices': [dev.to_dict() for dev in changes['removed_devices']],
                            'modified_devices': changes['modified_devices']
                        },
                        'changes_from_initial': {
                            'added_devices': [dev.to_dict() for dev in initial_changes['added_devices']],
                            'removed_devices': [dev.to_dict() for dev in initial_changes['removed_devices']],
                            'modified_devices': initial_changes['modified_devices']
                        },
                        'initial_snapshot': self.initial_snapshot,
                        'current_snapshot': current_snapshot
                    })
                except Exception as e:
                    print(f"Error in hotplug callback: {e}")
        
        # Update last snapshot
        self.last_snapshot = current_snapshot
    
    def get_current_state(self):
        """Get current device state"""
        if self.last_snapshot:
            return {
                'timestamp': self.last_snapshot.timestamp,
                'devices': [dev.to_dict() for dev in self.last_snapshot.devices],
                'device_count': len(self.last_snapshot.devices)
            }
        return None
    
    def get_initial_state(self):
        """Get initial device state"""
        if self.initial_snapshot:
            return {
                'timestamp': self.initial_snapshot.timestamp,
                'devices': [dev.to_dict() for dev in self.initial_snapshot.devices],
                'device_count': len(self.initial_snapshot.devices)
            }
        return None


class DeviceSelector:
    """Helper class for device selection by port chain"""
    
    def __init__(self, device_manager: AbstractDeviceManager):
        self.device_manager = device_manager
    
    def list_devices_grouped_by_port_chain(self) -> Dict[str, List[DeviceInfo]]:
        """
        List all devices grouped by their port chain
        
        Returns:
            Dictionary mapping port chain to list of devices
        """
        all_devices = self.device_manager.discover_devices()
        grouped = {}
        
        for device in all_devices:
            port_chain = device.port_chain or "unknown"
            if port_chain not in grouped:
                grouped[port_chain] = []
            grouped[port_chain].append(device)
            
        return grouped
    
    def select_device_by_port_chain(self, port_chain: str) -> Optional[DeviceInfo]:
        """
        Select the first device matching the given port chain
        
        Args:
            port_chain: The port chain to search for
            
        Returns:
            DeviceInfo object if found, None otherwise
        """
        devices = self.device_manager.get_devices_by_port_chain(port_chain)
        return devices[0] if devices else None
    
    def interactive_device_selection(self) -> Optional[DeviceInfo]:
        """
        Interactive device selection (for CLI applications)
        
        Returns:
            Selected DeviceInfo or None if cancelled
        """
        grouped_devices = self.list_devices_grouped_by_port_chain()
        
        if not grouped_devices:
            print("No devices found.")
            return None
        
        print("Available devices:")
        port_chains = list(grouped_devices.keys())
        
        for i, port_chain in enumerate(port_chains, 1):
            devices = grouped_devices[port_chain]
            print(f"{i}. Port Chain: {port_chain}")
            for device in devices:
                print(f"   {device}")
        
        try:
            choice = int(input("Select device by number (0 to cancel): "))
            if choice == 0:
                return None
            if 1 <= choice <= len(port_chains):
                selected_port_chain = port_chains[choice - 1]
                return self.select_device_by_port_chain(selected_port_chain)
            else:
                print("Invalid selection.")
                return None
        except (ValueError, KeyboardInterrupt):
            return None
