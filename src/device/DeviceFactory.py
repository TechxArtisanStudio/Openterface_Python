"""
Cross-platform device manager factory
"""
import platform
from typing import Optional
from device.AbstractDeviceManager import AbstractDeviceManager, AbstractHotplugMonitor, DeviceSelector

def create_device_manager(serial_vid: str, serial_pid: str, hid_vid: str, hid_pid: str) -> AbstractDeviceManager:
    """
    Create a device manager appropriate for the current platform
    
    Args:
        serial_vid: Vendor ID for serial devices
        serial_pid: Product ID for serial devices
        hid_vid: Vendor ID for HID devices
        hid_pid: Product ID for HID devices
        
    Returns:
        Platform-appropriate device manager instance
        
    Raises:
        NotImplementedError: If the current platform is not supported
    """
    system = platform.system().lower()
    
    if system == "windows":
        from device.DeviceGroupsWin import WindowsDeviceManager
        return WindowsDeviceManager(serial_vid, serial_pid, hid_vid, hid_pid)
    elif system == "linux":
        from device.DeviceGroupsLinux import LinuxDeviceManager
        return LinuxDeviceManager(serial_vid, serial_pid, hid_vid, hid_pid)
    elif system == "darwin":  # macOS
        # TODO: Implement macOS device manager
        raise NotImplementedError("macOS device manager not yet implemented")
    else:
        raise NotImplementedError(f"Platform '{system}' is not supported")


def create_hotplug_monitor(serial_vid: str, serial_pid: str, hid_vid: str, hid_pid: str, 
                          poll_interval: float = 2.0) -> AbstractHotplugMonitor:
    """
    Create a hotplug monitor appropriate for the current platform
    
    Args:
        serial_vid: Vendor ID for serial devices
        serial_pid: Product ID for serial devices
        hid_vid: Vendor ID for HID devices
        hid_pid: Product ID for HID devices
        poll_interval: Time in seconds between device scans
        
    Returns:
        Platform-appropriate hotplug monitor instance
        
    Raises:
        NotImplementedError: If the current platform is not supported
    """
    system = platform.system().lower()
    
    if system == "windows":
        from device.DeviceGroupsWin import WindowsDeviceManager, WindowsHotplugMonitor
        device_manager = WindowsDeviceManager(serial_vid, serial_pid, hid_vid, hid_pid)
        return WindowsHotplugMonitor(device_manager, poll_interval)
    elif system == "linux":
        from device.DeviceGroupsLinux import LinuxDeviceManager, LinuxHotplugMonitor
        device_manager = LinuxDeviceManager(serial_vid, serial_pid, hid_vid, hid_pid)
        return LinuxHotplugMonitor(device_manager, poll_interval)
    elif system == "darwin":  # macOS
        # TODO: Implement macOS hotplug monitor
        raise NotImplementedError("macOS hotplug monitor not yet implemented")
    else:
        raise NotImplementedError(f"Platform '{system}' is not supported")


def create_device_selector(serial_vid: str, serial_pid: str, hid_vid: str, hid_pid: str) -> DeviceSelector:
    """
    Create a device selector for the current platform
    
    Args:
        serial_vid: Vendor ID for serial devices
        serial_pid: Product ID for serial devices
        hid_vid: Vendor ID for HID devices
        hid_pid: Product ID for HID devices
        
    Returns:
        DeviceSelector instance
    """
    device_manager = create_device_manager(serial_vid, serial_pid, hid_vid, hid_pid)
    return DeviceSelector(device_manager)


# Convenience function for Openterface devices
def create_openterface_device_manager() -> AbstractDeviceManager:
    """Create device manager with Openterface default VID/PID values"""
    return create_device_manager("1A86", "7523", "534D", "2109")


def create_openterface_hotplug_monitor(poll_interval: float = 2.0) -> AbstractHotplugMonitor:
    """Create hotplug monitor with Openterface default VID/PID values"""
    return create_hotplug_monitor("1A86", "7523", "534D", "2109", poll_interval)


def create_openterface_device_selector() -> DeviceSelector:
    """Create device selector with Openterface default VID/PID values"""
    return create_device_selector("1A86", "7523", "534D", "2109")


# Platform detection utilities
def get_supported_platforms():
    """Get list of supported platforms"""
    return ["windows", "linux"]  # TODO: Add "darwin" when implemented


def is_platform_supported(platform_name: Optional[str] = None) -> bool:
    """Check if a platform is supported"""
    if platform_name is None:
        platform_name = platform.system().lower()
    return platform_name in get_supported_platforms()


def get_current_platform() -> str:
    """Get the current platform name"""
    return platform.system().lower()
