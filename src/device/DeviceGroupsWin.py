import ctypes
from ctypes import wintypes
import re
from typing import List, Any
from utils import logger
import hid
from video import VideoFFmpeg
from device.AbstractDeviceManager import AbstractDeviceManager, AbstractHotplugMonitor, DeviceInfo, DeviceSnapshot
import serial.tools.list_ports
import time
import threading
from datetime import datetime
import copy

CoreLogger = logger.core_logger

# Global variables for hot-plugging detection
_initial_device_snapshot = None
_current_device_snapshot = None
_hotplug_monitoring = False
_hotplug_thread = None
_hotplug_callbacks = []

# Constants
DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010
DIGCF_ALLCLASSES = 0x00000004
SPDRP_HARDWAREID = 0x00000001
ERROR_NO_MORE_ITEMS = 259

# Structures
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.ULONG),
        ("Data2", wintypes.USHORT),
        ("Data3", wintypes.USHORT),
        ("Data4", ctypes.c_ubyte * 8),
    ]

class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", GUID),
        ("DevInst", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]

# Load DLLs
setupapi = ctypes.WinDLL('setupapi')
cfgmgr32 = ctypes.WinDLL('cfgmgr32')

# SetupAPI functions
SetupDiGetClassDevs = setupapi.SetupDiGetClassDevsW
SetupDiGetClassDevs.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
SetupDiGetClassDevs.restype = wintypes.HANDLE

SetupDiEnumDeviceInfo = setupapi.SetupDiEnumDeviceInfo
SetupDiEnumDeviceInfo.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(SP_DEVINFO_DATA)]
SetupDiEnumDeviceInfo.restype = wintypes.BOOL

SetupDiGetDeviceRegistryProperty = setupapi.SetupDiGetDeviceRegistryPropertyW
SetupDiGetDeviceRegistryProperty.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(SP_DEVINFO_DATA), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
]
SetupDiGetDeviceRegistryProperty.restype = wintypes.BOOL

SetupDiDestroyDeviceInfoList = setupapi.SetupDiDestroyDeviceInfoList
SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

# CfgMgr32 functions
CM_Get_Parent = cfgmgr32.CM_Get_Parent
CM_Get_Parent.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, wintypes.ULONG]
CM_Get_Parent.restype = wintypes.DWORD

CM_Get_Device_ID = cfgmgr32.CM_Get_Device_IDW
CM_Get_Device_ID.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.WCHAR), wintypes.ULONG, wintypes.ULONG]
CM_Get_Device_ID.restype = wintypes.DWORD

CM_Get_Child = cfgmgr32.CM_Get_Child
CM_Get_Child.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, wintypes.ULONG]
CM_Get_Child.restype = wintypes.DWORD

# USB Device Interface GUID
GUID_DEVINTERFACE_USB_DEVICE = GUID(
    0xA5DCBF10, 0x6530, 0x11D2,
    (ctypes.c_ubyte * 8)(0x90, 0x1F, 0x00, 0xC0, 0x4F, 0xB9, 0x51, 0xED)
)

def get_device_parent(dev_inst):
    """Get the direct parent device instance."""
    parent_dev_inst = wintypes.DWORD()
    if CM_Get_Parent(ctypes.byref(parent_dev_inst), dev_inst, 0) == 0:
        return parent_dev_inst.value
    return None

def get_device_id(dev_inst):
    buffer = (wintypes.WCHAR * 256)()
    if CM_Get_Device_ID(dev_inst, buffer, 256, 0) == 0:
        return ctypes.wstring_at(buffer)
    return "Unknown"

def get_hardware_id(hDevInfo, dev_info_data):
    buffer_size = wintypes.DWORD(0)
    SetupDiGetDeviceRegistryProperty(
        hDevInfo, ctypes.byref(dev_info_data), SPDRP_HARDWAREID,
        None, None, 0, ctypes.byref(buffer_size)
    )

    if ctypes.get_last_error() == ERROR_NO_MORE_ITEMS:
        return "Unknown"

    buffer = (ctypes.c_wchar * max(256, buffer_size.value // 2))()
    reg_data_type = wintypes.DWORD()
    if SetupDiGetDeviceRegistryProperty(
        hDevInfo, ctypes.byref(dev_info_data), SPDRP_HARDWAREID,
        ctypes.byref(reg_data_type), ctypes.byref(buffer), ctypes.sizeof(buffer),
        ctypes.byref(buffer_size)
    ):
        return ctypes.wstring_at(ctypes.addressof(buffer))
    return "Unknown"

def get_sibling_devices_by_parent(parent_dev_inst):
    siblings = []

    # Create a new device info set for all classes to enumerate devices
    hDevInfo = SetupDiGetClassDevs(None, None, None, DIGCF_PRESENT | DIGCF_ALLCLASSES)
    if hDevInfo == wintypes.HANDLE(-1).value:
        return []

    try:
        dev_info_data = SP_DEVINFO_DATA()
        dev_info_data.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
        index = 0

        while SetupDiEnumDeviceInfo(hDevInfo, index, ctypes.byref(dev_info_data)):
            current_parent = wintypes.DWORD()
            if CM_Get_Parent(ctypes.byref(current_parent), dev_info_data.DevInst, 0) == 0:
                if current_parent.value == parent_dev_inst:
                    hwid = get_hardware_id(hDevInfo, dev_info_data)
                    dev_id = get_device_id(dev_info_data.DevInst)
                    siblings.append({"hardware_id": hwid, "device_id": dev_id})
            index += 1
    finally:
        SetupDiDestroyDeviceInfoList(hDevInfo)

    return siblings

def get_port_chain(dev_inst):
    port_chain = []
    depth = 0
    while dev_inst and depth < 3:  # Limit to 3 levels
        dev_id = get_device_id(dev_inst)
        port_chain.append(dev_id)
        parent = wintypes.DWORD()
        if CM_Get_Parent(ctypes.byref(parent), dev_inst, 0) != 0:
            break
        dev_inst = parent.value
        depth += 1
    port_chain.reverse()
    return port_chain

def find_usb_devices_with_vid_pid(vid, pid):
    target_hwid = f"VID_{vid.upper()}&PID_{pid.upper()}"
    result = []

    hDevInfo = SetupDiGetClassDevs(
        ctypes.byref(GUID_DEVINTERFACE_USB_DEVICE), None, None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )
    if hDevInfo == wintypes.HANDLE(-1).value:
        raise ctypes.WinError()

    try:
        dev_info_data = SP_DEVINFO_DATA()
        dev_info_data.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
        index = 0

        while SetupDiEnumDeviceInfo(hDevInfo, index, ctypes.byref(dev_info_data)):
            hwid = get_hardware_id(hDevInfo, dev_info_data)
            if target_hwid in hwid.upper():
                parent_dev_inst = get_device_parent(dev_info_data.DevInst)
                if parent_dev_inst is not None:
                    port_chain = get_port_chain(dev_info_data.DevInst)
                    siblings = get_sibling_devices_by_parent(parent_dev_inst)
                    children = get_child_devices(dev_info_data.DevInst)
                    result.append({
                        "port_chain": port_chain,
                        "siblings": siblings,
                        "children": children
                    })
            index += 1
    finally:
        SetupDiDestroyDeviceInfoList(hDevInfo)

    return result

def get_child_devices(dev_inst):
    children = []

    child_dev_inst = wintypes.DWORD()
    if CM_Get_Child(ctypes.byref(child_dev_inst), dev_inst, 0) == 0:
        while True:
            hwid = get_hardware_id_from_devinst(child_dev_inst.value)
            dev_id = get_device_id(child_dev_inst.value)
            children.append({"hardware_id": hwid, "device_id": dev_id})

            next_child_dev_inst = wintypes.DWORD()
            if CM_Get_Sibling(ctypes.byref(next_child_dev_inst), child_dev_inst.value, 0) != 0:
                break
            child_dev_inst = next_child_dev_inst

            grandchildren = get_child_devices(child_dev_inst.value)
            children.extend(grandchildren)

    return children

def get_hardware_id_from_devinst(dev_inst):
    hDevInfo = SetupDiGetClassDevs(None, None, None, DIGCF_PRESENT | DIGCF_ALLCLASSES)
    if hDevInfo == wintypes.HANDLE(-1).value:
        return "Unknown"

    try:
        dev_info_data = SP_DEVINFO_DATA()
        dev_info_data.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
        index = 0

        while SetupDiEnumDeviceInfo(hDevInfo, index, ctypes.byref(dev_info_data)):
            if dev_info_data.DevInst == dev_inst:
                return get_hardware_id(hDevInfo, dev_info_data)
            index += 1
    finally:
        SetupDiDestroyDeviceInfoList(hDevInfo)

    return "Unknown"

def CM_Get_Sibling(dnDevInstSibling, dnDevInstDev, ulFlags):
    return cfgmgr32.CM_Get_Sibling(dnDevInstSibling, dnDevInstDev, ulFlags)

def collect_device_ids(Serial_vid, Serial_pid, HID_vid, HID_pid):
    """
    According VID/PID find physical device, collect serial_port、HID、camera、audio device id
    return device_hardware_id_list.
    """
    devices = find_usb_devices_with_vid_pid(HID_vid, HID_pid)
    device_info_list = []
    if devices:
        for i, device in enumerate(devices, 1):
            port_chain = ""
            device_hardware_info = {
                "serial_port": "",
                "serial_port_path": "",
                "HID": "",
                "HID_path": b"",
                "camera": "",
                "camera_path": "",
                "audio": "",
                "audio_path": ""
            }
            CoreLogger.info(f"Device {i} Port Chain:")
            tmp = ""
            for j, dev_id in enumerate(device["port_chain"], 1):
                CoreLogger.info(f"{j}. {dev_id}")
                if j ==1:
                    tmp = str(int(dev_id[-1])+1) + "-"
                if j==2:
                    port_chain = tmp + dev_id[-1]
                if 2 < j < len(device["port_chain"]):
                    port_chain += f"-{dev_id[-1]}"
                if j == len(device["port_chain"]):
                    port_chain += f".2"
                
            # CoreLogger.info(f"Device {i} Serial port (same parent):")
            if device["siblings"]:
                for k, sibling in enumerate(device["siblings"], 1):
                    if Serial_vid.upper() in sibling['hardware_id'] and Serial_pid.upper() in sibling['hardware_id']:
                        device_hardware_info["serial_port"] = sibling['device_id']
                        device_hardware_info["serial_port_path"] = port_chain
                        CoreLogger.info(f"{k}. Hardware ID: {sibling['hardware_id']}")
                        CoreLogger.info(f"   Device ID: {sibling['device_id']}")
                        CoreLogger.info(f" Device location: {port_chain}")
            else:
                CoreLogger.info("No siblings found.")
            # CoreLogger.info(f"Device {i} Openterface child devices:")
            if device["children"]:
                for l, child in enumerate(device["children"], 1):
                    if not ("&0002" in child['device_id'] or "&0004" in child['device_id']):
                        CoreLogger.info(f"{l}. Hardware ID: {child['hardware_id']}")
                        CoreLogger.info(f"   Device ID: {child['device_id']} (type: {type(child['device_id'])})")
                        if "HID" in child['hardware_id']:
                            device_hardware_info["HID"] = child['device_id']
                        elif "MI_00" in child['hardware_id']:
                            device_hardware_info["camera"] = child['device_id']
                        elif "Audio" in child['hardware_id']:
                            device_hardware_info["audio"] = child['device_id']
            else:
                CoreLogger.info("No children found.")
            device_info_list.append(device_hardware_info)
    else:
        CoreLogger.info("No devices found with the specified VID and PID.")
    return device_info_list

def find_com_port_by_device_location(device_path):
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if port.location == device_path:
            return port.name

def find_HID_by_device_id(device_id):
    InstanceID = device_id.split('\\')[-1]
    for device in hid.enumerate():
        path_str = device['path'].decode(errors='replace')
        if InstanceID.lower() in path_str:
            return device['path']

def find_camera_audio_by_device_info(device_info):
    devs = VideoFFmpeg.list_windows_devices()
    camera_id = device_info['camera'].split('\\')[-1]
    audio_id = device_info['audio'].rsplit('.', 1)[-1]
    camera_path = ""
    audio_path = ""
    for i, dev in enumerate(devs):
        if camera_id.lower() in dev:
            camera_path = dev
        if audio_id in dev:
            audio_path = dev
    return camera_path, audio_path

def match_device_path(device_info):
    """
    Match the device path based on the device ID.
    This function is a placeholder and should be implemented based on specific requirements.
    """
    # Placeholder implementation
    if device_info['serial_port']:
        device_info['serial_port_path'] = find_com_port_by_device_location(device_info['serial_port_path'])
        CoreLogger.info(f"Matched Serial Port Path: {device_info['serial_port_path']}")
    if device_info["HID"]:
        device_info['HID_path'] = find_HID_by_device_id(device_info["HID"])
        CoreLogger.info(f"Matched HID Path: {device_info['HID_path']}")
    if device_info['camera'] and device_info['audio']:
        device_info['camera_path'], device_info['audio_path'] = find_camera_audio_by_device_info(device_info)
        CoreLogger.info(f"Matched camera Path: {device_info['camera_path']}")
        CoreLogger.info(f"Matched audio Path: {device_info['audio_path']}")

def search_phycial_device(SerialVid, SerialPID, HIDVID, HIDPID):
    device_info_list = collect_device_ids(SerialVid, SerialPID, HIDVID, HIDPID)
    for device_info in device_info_list:
        match_device_path(device_info)
    return device_info_list

class WindowsDeviceManager(AbstractDeviceManager):
    """Windows implementation of the abstract device manager"""
    
    def __init__(self, serial_vid: str, serial_pid: str, hid_vid: str, hid_pid: str):
        super().__init__(serial_vid, serial_pid, hid_vid, hid_pid)
    
    def discover_devices(self) -> List[DeviceInfo]:
        """Discover all devices matching the specified VID/PID on Windows"""
        device_info_list = []
        devices = find_usb_devices_with_vid_pid(self.hid_vid, self.hid_pid)
        
        if devices:
            for i, device in enumerate(devices, 1):
                port_chain = self._build_port_chain(device["port_chain"])
                
                device_info = DeviceInfo(
                    port_chain=port_chain,
                    platform_specific={'raw_device_data': device}
                )
                
                # Process siblings (serial ports)
                if device["siblings"]:
                    for sibling in device["siblings"]:
                        if self.serial_vid.upper() in sibling['hardware_id'] and self.serial_pid.upper() in sibling['hardware_id']:
                            device_info.serial_port = sibling['device_id']
                            device_info.serial_port_path = port_chain
                
                # Process children (HID, camera, audio)
                if device["children"]:
                    for child in device["children"]:
                        if not ("&0002" in child['device_id'] or "&0004" in child['device_id']):
                            if "HID" in child['hardware_id']:
                                device_info.hid_device = child['device_id']
                            elif "MI_00" in child['hardware_id']:
                                device_info.camera_device = child['device_id']
                            elif "Audio" in child['hardware_id']:
                                device_info.audio_device = child['device_id']
                
                # Match device paths
                self._match_device_paths(device_info)
                device_info_list.append(device_info)
        
        return device_info_list
    
    def get_port_chain(self, device_identifier: Any) -> str:
        """Get the port chain for a Windows device instance"""
        if isinstance(device_identifier, int):
            # Assume it's a device instance
            return self._build_port_chain(get_port_chain(device_identifier))
        return str(device_identifier)
    
    def _build_port_chain(self, raw_port_chain: list) -> str:
        """Build a formatted port chain string from raw Windows data"""
        if not raw_port_chain:
            return ""
        
        port_chain = ""
        tmp = ""
        
        for j, dev_id in enumerate(raw_port_chain, 1):
            if j == 1:
                tmp = str(int(dev_id[-1]) + 1) + "-"
            if j == 2:
                port_chain = tmp + dev_id[-1]
            if 2 < j < len(raw_port_chain):
                port_chain += f"-{dev_id[-1]}"
            if j == len(raw_port_chain):
                port_chain += ".2"
        
        return port_chain
    
    def _match_device_paths(self, device_info: DeviceInfo):
        """Match Windows device paths for the device"""
        # Match serial port
        if device_info.serial_port:
            device_info.serial_port_path = find_com_port_by_device_location(device_info.port_chain)
        
        # Match HID path
        if device_info.hid_device:
            device_info.hid_path = find_HID_by_device_id(device_info.hid_device)
        
        # Match camera and audio paths
        if device_info.camera_device and device_info.audio_device:
            camera_path, audio_path = find_camera_audio_by_device_info({
                'camera': device_info.camera_device,
                'audio': device_info.audio_device
            })
            device_info.camera_path = camera_path
            device_info.audio_path = audio_path


class WindowsHotplugMonitor(AbstractHotplugMonitor):
    """Windows implementation of the abstract hotplug monitor"""
    
    def __init__(self, device_manager: WindowsDeviceManager, poll_interval: float = 2.0):
        super().__init__(device_manager, poll_interval)
    
    def _create_monitor_thread(self):
        """Create the Windows monitoring thread"""
        return threading.Thread(target=self._monitor_loop, daemon=True)
    
    def _monitor_loop(self):
        """Main monitoring loop for Windows"""
        while self.running:
            try:
                # Capture current device state
                current_snapshot = self.device_manager.create_snapshot()
                
                # Handle any changes
                self._handle_device_changes(current_snapshot)
                
                # Wait for next poll
                time.sleep(self.poll_interval)
                
            except Exception as e:
                CoreLogger.error(f"Error in Windows hotplug monitoring loop: {e}")
                time.sleep(self.poll_interval)


# Legacy compatibility classes
class HotplugMonitor(WindowsHotplugMonitor):
    """Legacy compatibility class"""
    
    def __init__(self, serial_vid: str, serial_pid: str, hid_vid: str, hid_pid: str, poll_interval: float = 2.0):
        device_manager = WindowsDeviceManager(serial_vid, serial_pid, hid_vid, hid_pid)
        super().__init__(device_manager, poll_interval)


class DeviceSnapshot:
    """Legacy compatibility class"""
    
    def __init__(self, serial_vid: str, serial_pid: str, hid_vid: str, hid_pid: str):
        self.timestamp = datetime.now()
        self.serial_vid = serial_vid
        self.serial_pid = serial_pid
        self.hid_vid = hid_vid
        self.hid_pid = hid_pid
        
        # Create device manager and get devices
        device_manager = WindowsDeviceManager(serial_vid, serial_pid, hid_vid, hid_pid)
        device_infos = device_manager.discover_devices()
        
        # Convert to legacy format
        self.devices = [device.to_dict() for device in device_infos]
        
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
        for key in dev1.keys():
            if dev1.get(key) != dev2.get(key):
                return False
        return True

class HotplugMonitor:
    """Monitor device hot-plugging events"""
    
    def __init__(self, serial_vid, serial_pid, hid_vid, hid_pid, poll_interval=2.0):
        self.serial_vid = serial_vid
        self.serial_pid = serial_pid
        self.hid_vid = hid_vid
        self.hid_pid = hid_pid
        self.poll_interval = poll_interval
        self.callbacks = []
        self.running = False
        self.thread = None
        self.initial_snapshot = None
        self.last_snapshot = None
        
    def add_callback(self, callback):
        """Add a callback function to be called when device changes are detected"""
        self.callbacks.append(callback)
        
    def remove_callback(self, callback):
        """Remove a callback function"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
    
    def start_monitoring(self):
        """Start monitoring for device changes"""
        if self.running:
            CoreLogger.warning("Hot-plug monitoring is already running")
            return
            
        # Capture initial device state
        self.initial_snapshot = DeviceSnapshot(
            self.serial_vid, self.serial_pid,
            self.hid_vid, self.hid_pid
        )
        self.last_snapshot = copy.deepcopy(self.initial_snapshot)
        
        CoreLogger.info(f"Initial device snapshot captured at {self.initial_snapshot.timestamp}")
        CoreLogger.info(f"Found {len(self.initial_snapshot.devices)} initial devices")
        
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        
        CoreLogger.info("Hot-plug monitoring started")
    
    def stop_monitoring(self):
        """Stop monitoring for device changes"""
        if not self.running:
            CoreLogger.warning("Hot-plug monitoring is not running")
            return
            
        self.running = False
        if self.thread:
            self.thread.join(timeout=5.0)
            
        CoreLogger.info("Hot-plug monitoring stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                # Capture current device state
                current_snapshot = DeviceSnapshot(
                    self.serial_vid, self.serial_pid,
                    self.hid_vid, self.hid_pid
                )
                
                # Compare with last snapshot
                changes = current_snapshot.compare_with(self.last_snapshot)
                
                # Check if there are any changes
                if (changes['added_devices'] or 
                    changes['removed_devices'] or 
                    changes['modified_devices']):
                    
                    CoreLogger.info(f"Device changes detected at {current_snapshot.timestamp}")
                    
                    # Log changes
                    if changes['added_devices']:
                        CoreLogger.info(f"Added devices: {len(changes['added_devices'])}")
                        for device in changes['added_devices']:
                            CoreLogger.info(f"  + {self._format_device_info(device)}")
                    
                    if changes['removed_devices']:
                        CoreLogger.info(f"Removed devices: {len(changes['removed_devices'])}")
                        for device in changes['removed_devices']:
                            CoreLogger.info(f"  - {self._format_device_info(device)}")
                    
                    if changes['modified_devices']:
                        CoreLogger.info(f"Modified devices: {len(changes['modified_devices'])}")
                        for change in changes['modified_devices']:
                            CoreLogger.info(f"  ~ {self._format_device_info(change['new'])}")
                    
                    # Compare with initial snapshot
                    initial_changes = current_snapshot.compare_with(self.initial_snapshot)
                    
                    # Call registered callbacks
                    for callback in self.callbacks:
                        try:
                            callback({
                                'timestamp': current_snapshot.timestamp,
                                'current_devices': current_snapshot.devices,
                                'changes_from_last': changes,
                                'changes_from_initial': initial_changes,
                                'initial_snapshot': self.initial_snapshot,
                                'current_snapshot': current_snapshot
                            })
                        except Exception as e:
                            CoreLogger.error(f"Error in hotplug callback: {e}")
                
                # Update last snapshot
                self.last_snapshot = current_snapshot
                
                # Wait for next poll
                time.sleep(self.poll_interval)
                
            except Exception as e:
                CoreLogger.error(f"Error in hotplug monitoring loop: {e}")
                time.sleep(self.poll_interval)
    
    def _format_device_info(self, device):
        """Format device info for logging"""
        parts = []
        if device.get('serial_port_path'):
            parts.append(f"Serial:{device['serial_port_path']}")
        if device.get('HID_path'):
            parts.append(f"HID:{device['HID_path']}")
        if device.get('camera_path'):
            parts.append(f"Camera:{device['camera_path']}")
        if device.get('audio_path'):
            parts.append(f"Audio:{device['audio_path']}")
        return " | ".join(parts) if parts else "Unknown device"
    
    def get_current_state(self):
        """Get current device state"""
        if self.last_snapshot:
            return {
                'timestamp': self.last_snapshot.timestamp,
                'devices': self.last_snapshot.devices,
                'device_count': len(self.last_snapshot.devices)
            }
        return None
    
    def get_initial_state(self):
        """Get initial device state"""
        if self.initial_snapshot:
            return {
                'timestamp': self.initial_snapshot.timestamp,
                'devices': self.initial_snapshot.devices,
                'device_count': len(self.initial_snapshot.devices)
            }
        return None

# Convenience functions for global hotplug monitoring
def start_global_hotplug_monitoring(serial_vid, serial_pid, hid_vid, hid_pid, 
                                   poll_interval=2.0, callback=None):
    """Start global hotplug monitoring"""
    global _hotplug_monitor
    
    _hotplug_monitor = HotplugMonitor(serial_vid, serial_pid, hid_vid, hid_pid, poll_interval)
    
    if callback:
        _hotplug_monitor.add_callback(callback)
    
    _hotplug_monitor.start_monitoring()
    return _hotplug_monitor

def stop_global_hotplug_monitoring():
    """Stop global hotplug monitoring"""
    global _hotplug_monitor
    
    if '_hotplug_monitor' in globals() and _hotplug_monitor:
        _hotplug_monitor.stop_monitoring()
        _hotplug_monitor = None

def get_global_hotplug_monitor():
    """Get the global hotplug monitor instance"""
    global _hotplug_monitor
    return _hotplug_monitor if '_hotplug_monitor' in globals() else None

if __name__ == "__main__":
    device_info_list = search_phycial_device("1a86", "7523", "534D", "2109")
    for device_hardware_id in device_info_list:
        print("\n")
        for key, value in device_hardware_id.items():
            CoreLogger.info(f"{key} : {value}")
