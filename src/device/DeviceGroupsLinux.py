import pyudev
import serial.tools.list_ports
import hid
import threading
import time
import os
import glob
import subprocess
from datetime import datetime
from typing import List, Any, Dict, Optional
from utils import logger
from video import VideoFFmpeg
from device.AbstractDeviceManager import AbstractDeviceManager, AbstractHotplugMonitor, DeviceInfo, DeviceSnapshot
import copy

CoreLogger = logger.core_logger

def find_usb_devices_with_vid_pid(vid: str, pid: str) -> List[Dict]:
    """Find USB devices with specific VID/PID using pyudev"""
    context = pyudev.Context()
    result = []
    
    # Find USB devices with matching VID/PID
    for device in context.list_devices(subsystem='usb', DEVTYPE='usb_device'):
        device_vid = device.get('ID_VENDOR_ID', '').lower()
        device_pid = device.get('ID_MODEL_ID', '').lower()
        
        if device_vid == vid.lower() and device_pid == pid.lower():
            # Get device path and build port chain
            devpath = device.get('DEVPATH', '')
            port_chain = build_linux_port_chain(devpath)
            
            # Find related devices (children and siblings)
            children = find_child_devices(device)
            siblings = find_sibling_devices(device)
            
            result.append({
                "port_chain": [port_chain],
                "siblings": siblings,
                "children": children,
                "device_path": devpath,
                "device_info": {
                    "vid": device_vid,
                    "pid": device_pid,
                    "vendor": device.get('ID_VENDOR', ''),
                    "model": device.get('ID_MODEL', ''),
                    "serial": device.get('ID_SERIAL_SHORT', '')
                }
            })
    
    return result

def build_linux_port_chain(devpath: str) -> str:
    """Build a readable port chain from Linux device path"""
    if not devpath:
        return ""
    
    # Extract port information from devpath
    # Example: /devices/pci0000:00/0000:00:14.0/usb1/1-2/1-2.1
    parts = devpath.split('/')
    port_parts = []
    
    for part in parts:
        if part.startswith('usb'):
            # USB bus number
            bus_num = part[3:]
            port_parts.append(f"usb{bus_num}")
        elif '-' in part and '.' in part:
            # Port chain like 1-2.1
            port_parts.append(part)
    
    return "-".join(port_parts) if port_parts else devpath

def find_child_devices(parent_device) -> List[Dict]:
    """Find child devices of a USB device"""
    children = []
    
    for child in parent_device.children:
        # Get device info
        device_info = {
            "hardware_id": child.get('ID_MODEL', 'Unknown'),
            "device_id": child.device_path,
            "subsystem": child.subsystem,
            "devtype": child.get('DEVTYPE', ''),
            "vendor_id": child.get('ID_VENDOR_ID', ''),
            "product_id": child.get('ID_MODEL_ID', '')
        }
        children.append(device_info)
        
        # Recursively find grandchildren
        grandchildren = find_child_devices(child)
        children.extend(grandchildren)
    
    return children

def find_sibling_devices(device) -> List[Dict]:
    """Find sibling devices (devices with same parent)"""
    siblings = []
    
    if device.parent:
        for sibling in device.parent.children:
            if sibling != device:
                device_info = {
                    "hardware_id": sibling.get('ID_MODEL', 'Unknown'),
                    "device_id": sibling.device_path,
                    "subsystem": sibling.subsystem,
                    "devtype": sibling.get('DEVTYPE', ''),
                    "vendor_id": sibling.get('ID_VENDOR_ID', ''),
                    "product_id": sibling.get('ID_MODEL_ID', '')
                }
                siblings.append(device_info)
    
    return siblings

def find_serial_ports_by_port_chain(serial_vid: str, serial_pid: str, target_port_chain: str) -> List[Dict]:
    """Find serial ports by VID/PID and match them to a specific port chain (flexible matching)"""
    context = pyudev.Context()
    matching_ports = []
    
    # Extract the main port part from target_port_chain (e.g., "usb1-1-5.1" -> "1-5")
    target_port_main = ""
    if '-' in target_port_chain:
        parts = target_port_chain.split('-')
        if len(parts) >= 3:  # usb1-1-5.1 -> ["usb1", "1", "5.1"]
            # Get the main port part (1-5 from 1-5.1)
            main_part = parts[2].split('.')[0]  # "5.1" -> "5"
            target_port_main = f"{parts[1]}-{main_part}"  # "1-5"
    
    CoreLogger.debug(f"Looking for serial ports on main port: {target_port_main}")
    
    # Check all serial ports and see if they match the main port chain
    serial_ports = list(serial.tools.list_ports.comports())
    for port in serial_ports:
        if port.vid and port.pid:
            port_vid = f"{port.vid:04x}"
            port_pid = f"{port.pid:04x}"
            
            # Check if this port's VID/PID matches our target
            if port_vid.lower() == serial_vid.lower() and port_pid.lower() == serial_pid.lower():
                CoreLogger.debug(f"Found matching VID/PID serial port: {port.device}")
                
                # Try to find the USB device path for this serial port
                try:
                    # Look for the USB device this serial port belongs to
                    for device in context.list_devices(subsystem='tty'):
                        if device.device_node == port.device:
                            # Traverse up to find the USB parent
                            current = device
                            while current.parent:
                                if current.parent.subsystem == 'usb' and current.parent.get('DEVTYPE') == 'usb_device':
                                    usb_device = current.parent
                                    devpath = usb_device.get('DEVPATH', '')
                                    port_chain = build_linux_port_chain(devpath)
                                    
                                    CoreLogger.debug(f"Serial port {port.device} found on port chain: {port_chain}")
                                    
                                    # Extract main port from this port chain for comparison
                                    port_main = ""
                                    if '-' in port_chain:
                                        parts = port_chain.split('-')
                                        if len(parts) >= 3:
                                            main_part = parts[2].split('.')[0]
                                            port_main = f"{parts[1]}-{main_part}"
                                    
                                    # Match on the main port (e.g., "1-5" matches "1-5")
                                    if port_main == target_port_main:
                                        CoreLogger.info(f"Serial port {port.device} matches main port {target_port_main}")
                                        matching_ports.append({
                                            "device": port.device,
                                            "name": port.name,
                                            "description": port.description,
                                            "hwid": port.hwid,
                                            "vid": port_vid,
                                            "pid": port_pid,
                                            "serial_number": port.serial_number,
                                            "location": port.location,
                                            "manufacturer": port.manufacturer,
                                            "product": port.product,
                                            "port_chain": port_chain
                                        })
                                    break
                                current = current.parent
                            break
                except Exception as e:
                    CoreLogger.debug(f"Error finding USB parent for serial port {port.device}: {e}")
                    continue
    
    # If still no match, try a more flexible approach using location/hwid
    if not matching_ports and target_port_main:
        CoreLogger.debug(f"No direct match found, trying flexible matching for {target_port_main}")
        
        for port in serial_ports:
            if port.vid and port.pid:
                port_vid = f"{port.vid:04x}"
                port_pid = f"{port.pid:04x}"
                
                if port_vid.lower() == serial_vid.lower() and port_pid.lower() == serial_pid.lower():
                    # Check if the port location or hwid contains our target port info
                    port_location = port.location or ""
                    port_hwid = port.hwid or ""
                    
                    # Look for the main port pattern in location/hwid
                    if target_port_main in port_location or target_port_main in port_hwid:
                        CoreLogger.info(f"Serial port {port.device} matched via location/hwid for port {target_port_main}")
                        matching_ports.append({
                            "device": port.device,
                            "name": port.name,
                            "description": port.description,
                            "hwid": port.hwid,
                            "vid": port_vid,
                            "pid": port_pid,
                            "serial_number": port.serial_number,
                            "location": port.location,
                            "manufacturer": port.manufacturer,
                            "product": port.product,
                            "port_chain": target_port_chain
                        })
    
    return matching_ports

def find_hid_devices_by_port_chain(hid_vid: str, hid_pid: str, target_port_chain: str) -> List[Dict]:
    """Find HID devices by VID/PID and match them to a specific port chain"""
    matching_devices = []
    
    # Get all HID devices with matching VID/PID
    for hid_device in hid.enumerate():
        device_vid_hid = f"{hid_device['vendor_id']:04x}"
        device_pid_hid = f"{hid_device['product_id']:04x}"
        
        if device_vid_hid.lower() == hid_vid.lower() and device_pid_hid.lower() == hid_pid.lower():
            hid_path = hid_device['path'].decode('utf-8', errors='ignore')
            
            # Extract USB port info from HID path
            # HID path format is usually like: /dev/hidraw1 or 1-5.1:1.4
            # We need to match the USB port part (like 1-5.1) to our target port chain
            
            # Extract port part from target_port_chain (e.g., "usb1-1-5.1" -> "1-5.1")
            target_port_part = target_port_chain.split('-', 1)[-1] if '-' in target_port_chain else target_port_chain
            
            # Check if the HID path contains the target port part
            if target_port_part in hid_path:
                matching_devices.append({
                    "path": hid_device['path'],
                    "vendor_id": device_vid_hid,
                    "product_id": device_pid_hid,
                    "manufacturer_string": hid_device.get('manufacturer_string', ''),
                    "product_string": hid_device.get('product_string', ''),
                    "serial_number": hid_device.get('serial_number', ''),
                    "interface_number": hid_device.get('interface_number', -1),
                    "port_chain": target_port_chain
                })
    
    return matching_devices

def find_video_devices_by_port_chain(target_port_chain: str) -> List[Dict]:
    """Find video devices associated with a specific port chain"""
    context = pyudev.Context()
    matching_devices = []
    
    # Look for video devices and try to match them to the port chain
    for device in context.list_devices(subsystem='video4linux'):
        # Traverse up the device tree to find the USB parent
        current = device
        while current.parent:
            if current.parent.subsystem == 'usb' and current.parent.get('DEVTYPE') == 'usb_device':
                usb_device = current.parent
                devpath = usb_device.get('DEVPATH', '')
                port_chain = build_linux_port_chain(devpath)
                
                if port_chain == target_port_chain:
                    device_node = device.device_node
                    if device_node:
                        matching_devices.append({
                            "device": device_node,
                            "name": f"Video Device {device_node}",
                            "info": f"USB Video device on port {port_chain}",
                            "port_chain": port_chain
                        })
                break
            current = current.parent
    
    return matching_devices

def find_audio_devices_by_port_chain(target_port_chain: str) -> List[Dict]:
    """Find audio devices associated with a specific port chain"""
    context = pyudev.Context()
    matching_devices = []
    
    # Look for sound devices and try to match them to the port chain
    for device in context.list_devices(subsystem='sound'):
        # Traverse up the device tree to find the USB parent
        current = device
        while current.parent:
            if current.parent.subsystem == 'usb' and current.parent.get('DEVTYPE') == 'usb_device':
                usb_device = current.parent
                devpath = usb_device.get('DEVPATH', '')
                port_chain = build_linux_port_chain(devpath)
                
                if port_chain == target_port_chain:
                    device_node = device.device_node
                    if device_node:
                        matching_devices.append({
                            "device": device_node,
                            "name": f"Audio Device on port {port_chain}",
                            "info": f"USB Audio device",
                            "port_chain": port_chain
                        })
                break
            current = current.parent
    
    # Also check ALSA cards for USB audio
    try:
        result = subprocess.run(['aplay', '-l'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            for line in lines:
                if 'USB' in line and 'card' in line.lower():
                    # This is a rough match - could be improved with more detailed parsing
                    matching_devices.append({
                        "device": line.strip(),
                        "name": f"USB Audio Device",
                        "info": line.strip(),
                        "port_chain": target_port_chain  # Associate with target port chain
                    })
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    return matching_devices

def find_video_devices() -> List[Dict]:
    """Find video devices (cameras)"""
    devices = []
    
    # Look for video devices in /dev/video*
    video_devices = glob.glob('/dev/video*')
    
    for video_dev in video_devices:
        try:
            # Get device info using v4l2-ctl if available
            result = subprocess.run(['v4l2-ctl', '--device', video_dev, '--info'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                devices.append({
                    "device": video_dev,
                    "name": f"Video Device {video_dev}",
                    "info": result.stdout.strip()
                })
            else:
                # Fallback: just add the device path
                devices.append({
                    "device": video_dev,
                    "name": f"Video Device {video_dev}",
                    "info": "No detailed info available"
                })
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # v4l2-ctl not available or timeout
            devices.append({
                "device": video_dev,
                "name": f"Video Device {video_dev}",
                "info": "v4l2-ctl not available"
            })
    
    return devices

def find_audio_devices() -> List[Dict]:
    """Find audio devices"""
    devices = []
    
    # Look for audio devices using ALSA
    try:
        # List audio cards
        result = subprocess.run(['aplay', '-l'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            for line in lines:
                if 'card' in line.lower():
                    devices.append({
                        "device": line.strip(),
                        "name": f"Audio Device",
                        "info": line.strip()
                    })
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    # Also check /dev/snd/
    snd_devices = glob.glob('/dev/snd/*')
    for snd_dev in snd_devices:
        if os.path.exists(snd_dev):
            devices.append({
                "device": snd_dev,
                "name": f"Sound Device {snd_dev}",
                "info": "ALSA sound device"
            })
    
    return devices

def collect_device_ids(serial_vid: str, serial_pid: str, hid_vid: str, hid_pid: str) -> List[Dict]:
    """
    According VID/PID find physical device, collect serial_port、HID、camera、audio device id
    return device_hardware_id_list grouped by port chain.
    """
    devices = find_usb_devices_with_vid_pid(hid_vid, hid_pid)
    device_info_list = []
    
    if devices:
        for i, device in enumerate(devices, 1):
            port_chain = device["port_chain"][0] if device["port_chain"] else ""
            CoreLogger.info(f"Device {i} Port Chain: {port_chain}")
            
            device_hardware_info = {
                "serial_port": "",
                "serial_port_path": "",
                "HID": "",
                "HID_path": b"",
                "camera": "",
                "camera_path": "",
                "audio": "",
                "audio_path": "",
                "port_chain": port_chain
            }
            
            # Find serial ports specifically for this port chain
            serial_ports = find_serial_ports_by_port_chain(serial_vid, serial_pid, port_chain)
            if serial_ports:
                device_hardware_info["serial_port"] = serial_ports[0]["device"]
                device_hardware_info["serial_port_path"] = serial_ports[0]["device"]
                CoreLogger.info(f"Found serial port: {serial_ports[0]['device']} on port chain: {port_chain}")
            
            # Find HID devices specifically for this port chain
            hid_devices = find_hid_devices_by_port_chain(hid_vid, hid_pid, port_chain)
            if hid_devices:
                device_hardware_info["HID"] = hid_devices[0]["product_string"]
                device_hardware_info["HID_path"] = hid_devices[0]["path"]
                CoreLogger.info(f"Found HID device: {hid_devices[0]['product_string']} on port chain: {port_chain}")
            
            # Find video devices specifically for this port chain
            video_devices = find_video_devices_by_port_chain(port_chain)
            if video_devices:
                device_hardware_info["camera"] = video_devices[0]["name"]
                device_hardware_info["camera_path"] = video_devices[0]["device"]
                CoreLogger.info(f"Found video device: {video_devices[0]['device']} on port chain: {port_chain}")
            
            # Find audio devices specifically for this port chain
            audio_devices = find_audio_devices_by_port_chain(port_chain)
            if audio_devices:
                device_hardware_info["audio"] = audio_devices[0]["name"]
                device_hardware_info["audio_path"] = audio_devices[0]["device"]
                CoreLogger.info(f"Found audio device: {audio_devices[0]['device']} on port chain: {port_chain}")
            
            device_info_list.append(device_hardware_info)
    else:
        CoreLogger.info("No devices found with the specified VID and PID.")
    
    return device_info_list

def search_physical_device(serial_vid: str, serial_pid: str, hid_vid: str, hid_pid: str) -> List[Dict]:
    """Search for physical devices and return their information"""
    return collect_device_ids(serial_vid, serial_pid, hid_vid, hid_pid)

class LinuxDeviceManager(AbstractDeviceManager):
    """Linux implementation of the abstract device manager"""
    
    def __init__(self, serial_vid: str, serial_pid: str, hid_vid: str, hid_pid: str):
        super().__init__(serial_vid, serial_pid, hid_vid, hid_pid)
        self.context = pyudev.Context()

    def discover_devices(self) -> List[DeviceInfo]:
        """Discover all devices matching the specified VID/PID on Linux"""
        device_info_list = []
        devices = find_usb_devices_with_vid_pid(self.hid_vid, self.hid_pid)
        
        if devices:
            for i, device in enumerate(devices, 1):
                port_chain = device["port_chain"][0] if device["port_chain"] else ""
                
                device_info = DeviceInfo(
                    port_chain=port_chain,
                    platform_specific={'device_info': device.get('device_info', {})}
                )
                
                # Find serial ports specifically for this port chain
                serial_ports = find_serial_ports_by_port_chain(self.serial_vid, self.serial_pid, port_chain)
                if serial_ports:
                    device_info.serial_port = serial_ports[0]["device"]
                    device_info.serial_port_path = serial_ports[0]["device"]
                
                # Find HID devices specifically for this port chain
                hid_devices = find_hid_devices_by_port_chain(self.hid_vid, self.hid_pid, port_chain)
                if hid_devices:
                    device_info.hid_device = hid_devices[0]["product_string"]
                    device_info.hid_path = hid_devices[0]["path"]
                
                # Find video devices specifically for this port chain
                video_devices = find_video_devices_by_port_chain(port_chain)
                if video_devices:
                    device_info.camera_device = video_devices[0]["name"]
                    device_info.camera_path = video_devices[0]["device"]
                
                # Find audio devices specifically for this port chain
                audio_devices = find_audio_devices_by_port_chain(port_chain)
                if audio_devices:
                    device_info.audio_device = audio_devices[0]["name"]
                    device_info.audio_path = audio_devices[0]["device"]
                
                device_info_list.append(device_info)
        
        return device_info_list
    
    def get_port_chain(self, device_identifier: Any) -> str:
        """Get the port chain for a Linux device"""
        if isinstance(device_identifier, str):
            return device_identifier
        return str(device_identifier)

class LinuxHotplugMonitor(AbstractHotplugMonitor):
    """Linux implementation of the abstract hotplug monitor"""
    def __init__(self, device_manager: LinuxDeviceManager, poll_interval: float = 2.0):
        super().__init__(device_manager, poll_interval)

    def _create_monitor_thread(self):
        return threading.Thread(target=self._monitor_loop, daemon=True)

    def _monitor_loop(self):
        while self.running:
            try:
                current_snapshot = self.device_manager.create_snapshot()
                self._handle_device_changes(current_snapshot)
                time.sleep(self.poll_interval)
            except Exception as e:
                CoreLogger.error(f"Error in Linux hotplug monitoring loop: {e}")
                time.sleep(self.poll_interval)

# Legacy compatibility classes (optional, for API parity)
class HotplugMonitor(LinuxHotplugMonitor):
    """Legacy compatibility class"""
    
    def __init__(self, serial_vid: str, serial_pid: str, hid_vid: str, hid_pid: str, poll_interval: float = 2.0):
        device_manager = LinuxDeviceManager(serial_vid, serial_pid, hid_vid, hid_pid)
        super().__init__(device_manager, poll_interval)


class DeviceSnapshot:
    """Legacy compatibility class for Linux"""
    
    def __init__(self, serial_vid: str, serial_pid: str, hid_vid: str, hid_pid: str):
        self.timestamp = datetime.now()
        self.serial_vid = serial_vid
        self.serial_pid = serial_pid
        self.hid_vid = hid_vid
        self.hid_pid = hid_pid
        
        # Create device manager and get devices
        device_manager = LinuxDeviceManager(serial_vid, serial_pid, hid_vid, hid_pid)
        device_infos = device_manager.discover_devices()
        
        # Convert to legacy format without unpicklable objects
        self.devices = []
        for device in device_infos:
            device_dict = device.to_dict()
            # Ensure platform_specific doesn't contain unpicklable objects
            if 'platform_specific' in device_dict:
                platform_data = device_dict['platform_specific']
                # Only keep serializable data
                device_dict['platform_specific'] = {
                    k: v for k, v in platform_data.items() 
                    if isinstance(v, (str, int, float, bool, list, dict, type(None)))
                }
            self.devices.append(device_dict)
        
    def compare_with(self, other_snapshot):
        """Compare this snapshot with another snapshot"""
        changes = {
            'added_devices': [],
            'removed_devices': [],
            'modified_devices': []
        }
        
        # Convert device lists to dictionaries for easier comparison
        current_devices = {self._device_key(dev): dev for dev in self.devices}
        other_devices = {self._device_key(dev): dev for dev in other_snapshot.devices}
        
        # Find added devices
        for key, device in current_devices.items():
            if key not in other_devices:
                changes['added_devices'].append(device)
        
        # Find removed devices
        for key, device in other_devices.items():
            if key not in current_devices:
                changes['removed_devices'].append(device)
        
        # Find modified devices
        for key, device in current_devices.items():
            if key in other_devices:
                if not self._devices_equal(device, other_devices[key]):
                    changes['modified_devices'].append({
                        'old': other_devices[key],
                        'new': device
                    })
        
        return changes
    
    def _device_key(self, device):
        """Generate a unique key for a device"""
        return f"{device.get('serial_port', '')}-{device.get('HID', '')}-{device.get('camera', '')}"
    
    def _devices_equal(self, dev1, dev2):
        """Check if two devices are equal"""
        # Compare only the important fields, not platform_specific
        important_fields = ['serial_port', 'serial_port_path', 'HID', 'HID_path', 
                          'camera', 'camera_path', 'audio', 'audio_path', 'port_chain']
        
        for field in important_fields:
            if dev1.get(field) != dev2.get(field):
                return False
        return True

# Backward compatibility functions (without port chain filtering)
def find_serial_ports_by_vid_pid(vid: str, pid: str) -> List[Dict]:
    """Find serial ports by VID/PID (all instances)"""
    ports = []
    for port in serial.tools.list_ports.comports():
        if port.vid and port.pid:
            port_vid = f"{port.vid:04x}"
            port_pid = f"{port.pid:04x}"
            if port_vid.lower() == vid.lower() and port_pid.lower() == pid.lower():
                ports.append({
                    "device": port.device,
                    "name": port.name,
                    "description": port.description,
                    "hwid": port.hwid,
                    "vid": port_vid,
                    "pid": port_pid,
                    "serial_number": port.serial_number,
                    "location": port.location,
                    "manufacturer": port.manufacturer,
                    "product": port.product
                })
    return ports

def find_hid_devices_by_vid_pid(vid: str, pid: str) -> List[Dict]:
    """Find HID devices by VID/PID (all instances)"""
    devices = []
    for device in hid.enumerate():
        device_vid = f"{device['vendor_id']:04x}"
        device_pid = f"{device['product_id']:04x}"
        if device_vid.lower() == vid.lower() and device_pid.lower() == pid.lower():
            devices.append({
                "path": device['path'],
                "vendor_id": device_vid,
                "product_id": device_pid,
                "manufacturer_string": device.get('manufacturer_string', ''),
                "product_string": device.get('product_string', ''),
                "serial_number": device.get('serial_number', ''),
                "interface_number": device.get('interface_number', -1)
            })
    return devices

# Additional convenience functions for Linux device search
def list_all_serial_ports() -> List[Dict]:
    """List all available serial ports"""
    ports = []
    for port in serial.tools.list_ports.comports():
        port_info = {
            "device": port.device,
            "name": port.name,
            "description": port.description,
            "hwid": port.hwid,
            "vid": f"{port.vid:04x}" if port.vid else None,
            "pid": f"{port.pid:04x}" if port.pid else None,
            "serial_number": port.serial_number,
            "location": port.location,
            "manufacturer": port.manufacturer,
            "product": port.product
        }
        ports.append(port_info)
        CoreLogger.info(f"Serial Port: {port.device} - {port.description}")
    return ports

def list_all_hid_devices() -> List[Dict]:
    """List all available HID devices"""
    devices = []
    for device in hid.enumerate():
        device_info = {
            "path": device['path'],
            "vendor_id": f"{device['vendor_id']:04x}",
            "product_id": f"{device['product_id']:04x}",
            "manufacturer_string": device.get('manufacturer_string', ''),
            "product_string": device.get('product_string', ''),
            "serial_number": device.get('serial_number', ''),
            "interface_number": device.get('interface_number', -1)
        }
        devices.append(device_info)
        CoreLogger.info(f"HID Device: {device['product_string']} - VID:{device_info['vendor_id']} PID:{device_info['product_id']}")
    return devices

def list_all_video_devices() -> List[Dict]:
    """List all available video devices"""
    devices = find_video_devices()
    for device in devices:
        CoreLogger.info(f"Video Device: {device['device']} - {device['name']}")
    return devices

def list_all_audio_devices() -> List[Dict]:
    """List all available audio devices"""
    devices = find_audio_devices()
    for device in devices:
        CoreLogger.info(f"Audio Device: {device['device']} - {device['name']}")
    return devices

def debug_serial_port_info(serial_vid: str, serial_pid: str) -> None:
    """Debug function to show detailed serial port information"""
    CoreLogger.info(f"=== DEBUG: Serial Port Analysis for VID:{serial_vid.upper()} PID:{serial_pid.upper()} ===")
    
    # Show all serial ports with their details
    serial_ports = list(serial.tools.list_ports.comports())
    CoreLogger.info(f"Found {len(serial_ports)} total serial ports:")
    
    for i, port in enumerate(serial_ports, 1):
        CoreLogger.info(f"\nSerial Port {i}:")
        CoreLogger.info(f"  Device: {port.device}")
        CoreLogger.info(f"  Name: {port.name}")
        CoreLogger.info(f"  Description: {port.description}")
        CoreLogger.info(f"  VID: {f'{port.vid:04x}' if port.vid else 'None'}")
        CoreLogger.info(f"  PID: {f'{port.pid:04x}' if port.pid else 'None'}")
        CoreLogger.info(f"  Serial Number: {port.serial_number}")
        CoreLogger.info(f"  Location: {port.location}")
        CoreLogger.info(f"  Manufacturer: {port.manufacturer}")
        CoreLogger.info(f"  Product: {port.product}")
        CoreLogger.info(f"  HWID: {port.hwid}")
        
        # Check if this matches our target VID/PID
        if port.vid and port.pid:
            port_vid = f"{port.vid:04x}"
            port_pid = f"{port.pid:04x}"
            if port_vid.lower() == serial_vid.lower() and port_pid.lower() == serial_pid.lower():
                CoreLogger.info(f"  *** MATCHES TARGET VID/PID ***")
        
        # Try to find the USB parent device
        try:
            import pyudev
            context = pyudev.Context()
            for device in context.list_devices(subsystem='tty'):
                if device.device_node == port.device:
                    CoreLogger.info(f"  TTY Device Path: {device.device_path}")
                    
                    # Traverse up to find USB parent
                    current = device
                    level = 0
                    while current.parent and level < 5:  # Limit to 5 levels
                        parent = current.parent
                        CoreLogger.info(f"  Parent Level {level}: {parent.subsystem} - {parent.get('DEVTYPE', 'N/A')}")
                        
                        if parent.subsystem == 'usb' and parent.get('DEVTYPE') == 'usb_device':
                            devpath = parent.get('DEVPATH', '')
                            port_chain = build_linux_port_chain(devpath)
                            CoreLogger.info(f"  USB Parent Port Chain: {port_chain}")
                            CoreLogger.info(f"  USB Parent VID: {parent.get('ID_VENDOR_ID', 'N/A')}")
                            CoreLogger.info(f"  USB Parent PID: {parent.get('ID_MODEL_ID', 'N/A')}")
                            break
                        
                        current = parent
                        level += 1
                    break
        except Exception as e:
            CoreLogger.info(f"  Error getting USB parent: {e}")
    
    CoreLogger.info(f"\n=== END DEBUG ===\n")

def extract_main_port_from_chain(port_chain: str) -> str:
    """Extract the main port from a port chain (e.g., 'usb1-1-5.1' -> '1-5')"""
    if '-' in port_chain:
        parts = port_chain.split('-')
        if len(parts) >= 3:  # usb1-1-5.1 -> ["usb1", "1", "5.1"]
            # Get the main port part (1-5 from 1-5.1)
            main_part = parts[2].split('.')[0]  # "5.1" -> "5"
            return f"{parts[1]}-{main_part}"  # "1-5"
    return port_chain

if __name__ == "__main__":
    # Example usage
    CoreLogger.info("=== Linux Device Search Example ===")
    
    # Example VID/PID values (replace with your actual values)
    serial_vid = "1a86"
    serial_pid = "7523"
    hid_vid = "534D"
    hid_pid = "2109"
    
    CoreLogger.info(f"Searching for devices with Serial VID:{serial_vid} PID:{serial_pid}, HID VID:{hid_vid} PID:{hid_pid}")
    
    # Search for specific devices
    device_info_list = search_physical_device(serial_vid, serial_pid, hid_vid, hid_pid)
    
    CoreLogger.info(f"\nFound {len(device_info_list)} matching device groups:")
    for i, device_hardware_id in enumerate(device_info_list, 1):
        CoreLogger.info(f"\n--- Device Group {i} ---")
        for key, value in device_hardware_id.items():
            CoreLogger.info(f"{key}: {value}")
    
    # List all devices for reference
    CoreLogger.info("\n=== All Available Devices ===")
    
    CoreLogger.info("\n--- All Serial Ports ---")
    list_all_serial_ports()
    
    CoreLogger.info("\n--- All HID Devices ---")
    list_all_hid_devices()
    
    CoreLogger.info("\n--- All Video Devices ---")
    list_all_video_devices()
    
    CoreLogger.info("\n--- All Audio Devices ---")
    list_all_audio_devices()

    # Debug serial port information
    debug_serial_port_info(serial_vid, serial_pid)
