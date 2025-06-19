import ctypes
from ctypes import wintypes
import re

# Define SetupAPI constants
DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010
DIGCF_ALLCLASSES = 0x00000004
SPDRP_HARDWAREID = 0x00000001
ERROR_NO_MORE_ITEMS = 259

# Define GUID structure
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.ULONG),
        ("Data2", wintypes.USHORT),
        ("Data3", wintypes.USHORT),
        ("Data4", ctypes.c_ubyte * 8),
    ]

# Define SP_DEVINFO_DATA structure
class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", GUID),
        ("DevInst", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]

# Define SP_DEVICE_INTERFACE_DATA structure
class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]

# Define SP_DEVICE_INTERFACE_DETAIL_DATA structure
class SP_DEVICE_INTERFACE_DETAIL_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("DevicePath", wintypes.WCHAR * 1),
    ]

# Load SetupAPI and CMAPI
setupapi = ctypes.WinDLL('setupapi')
cfgmgr32 = ctypes.WinDLL('cfgmgr32')

# Define function prototypes
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

CM_Get_Parent = cfgmgr32.CM_Get_Parent
CM_Get_Parent.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, wintypes.ULONG]
CM_Get_Parent.restype = wintypes.DWORD

CM_Get_Device_ID = cfgmgr32.CM_Get_Device_IDW
CM_Get_Device_ID.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.WCHAR), wintypes.ULONG, wintypes.ULONG]
CM_Get_Device_ID.restype = wintypes.DWORD

SetupDiDestroyDeviceInfoList = setupapi.SetupDiDestroyDeviceInfoList
SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

# USB device class GUID
GUID_DEVINTERFACE_USB_DEVICE = GUID(
    0xA5DCBF10, 0x6530, 0x11D2,
    (ctypes.c_ubyte * 8)(0x90, 0x1F, 0x00, 0xC0, 0x4F, 0xB9, 0x51, 0xED)
)

def get_sibling_devices(hDevInfo, parent_dev_inst):
    """Get all devices under the same parent node."""
    siblings = []
    sibling_info_data = SP_DEVINFO_DATA()
    sibling_info_data.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
    sibling_index = 0

    while SetupDiEnumDeviceInfo(hDevInfo, sibling_index, ctypes.byref(sibling_info_data)):
        # Get parent of this device
        current_parent = wintypes.DWORD()
        if CM_Get_Parent(ctypes.byref(current_parent), sibling_info_data.DevInst, 0) == 0:
            if current_parent.value == parent_dev_inst:
                # Get hardware ID
                buffer_size = wintypes.DWORD(0)
                SetupDiGetDeviceRegistryProperty(
                    hDevInfo, ctypes.byref(sibling_info_data), SPDRP_HARDWAREID,
                    None, None, 0, ctypes.byref(buffer_size)
                )

                buffer = (ctypes.c_wchar * max(256, buffer_size.value // 2))()  # Ensure sufficient buffer
                reg_data_type = wintypes.DWORD()
                if SetupDiGetDeviceRegistryProperty(
                    hDevInfo, ctypes.byref(sibling_info_data), SPDRP_HARDWAREID,
                    ctypes.byref(reg_data_type), ctypes.byref(buffer), ctypes.sizeof(buffer),
                    ctypes.byref(buffer_size)
                ):
                    hwid = ctypes.wstring_at(ctypes.addressof(buffer))
                else:
                    hwid = "Unknown"

                # Get device ID
                dev_id_buffer = (wintypes.WCHAR * 256)()
                if CM_Get_Device_ID(sibling_info_data.DevInst, dev_id_buffer, 256, 0) == 0:
                    device_id = ctypes.wstring_at(dev_id_buffer)
                else:
                    device_id = "Unknown"

                siblings.append({"hardware_id": hwid, "device_id": device_id})

        sibling_index += 1

    return siblings

def get_port_chains(vid, pid):
    # Format VID and PID
    target_hwid = f"VID_{vid.upper()}&PID_{pid.upper()}"
    all_devices = []

    # Get device information set for USB devices to find target
    hDevInfo_usb = SetupDiGetClassDevs(
        ctypes.byref(GUID_DEVINTERFACE_USB_DEVICE), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )
    if hDevInfo_usb == wintypes.HANDLE(-1).value:
        raise ctypes.WinError()

    # Get device information set for all classes to find siblings
    hDevInfo_all = SetupDiGetClassDevs(
        None, None, None, DIGCF_PRESENT | DIGCF_ALLCLASSES
    )
    if hDevInfo_all == wintypes.HANDLE(-1).value:
        SetupDiDestroyDeviceInfoList(hDevInfo_usb)
        raise ctypes.WinError()

    try:
        # Enumerate USB devices
        device_info_data = SP_DEVINFO_DATA()
        device_info_data.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
        index = 0

        while SetupDiEnumDeviceInfo(hDevInfo_usb, index, ctypes.byref(device_info_data)):
            # Get hardware ID buffer size
            buffer_size = wintypes.DWORD(0)
            SetupDiGetDeviceRegistryProperty(
                hDevInfo_usb, ctypes.byref(device_info_data), SPDRP_HARDWAREID,
                None, None, 0, ctypes.byref(buffer_size)
            )

            if ctypes.get_last_error() == ERROR_NO_MORE_ITEMS:
                break

            # Allocate buffer for hardware ID
            buffer = (ctypes.c_wchar * max(256, buffer_size.value // 2))()
            reg_data_type = wintypes.DWORD()

            if SetupDiGetDeviceRegistryProperty(
                hDevInfo_usb, ctypes.byref(device_info_data), SPDRP_HARDWAREID,
                ctypes.byref(reg_data_type), ctypes.byref(buffer), ctypes.sizeof(buffer),
                ctypes.byref(buffer_size)
            ):
                # Convert buffer to string
                hwid = ctypes.wstring_at(ctypes.addressof(buffer))
                if target_hwid in hwid.upper():
                    # Get port chain for this device
                    port_chain = []
                    dev_inst = device_info_data.DevInst
                    parent_dev_inst = wintypes.DWORD()
                    while dev_inst:
                        # Get device ID
                        dev_id_buffer = (wintypes.WCHAR * 256)()
                        if CM_Get_Device_ID(dev_inst, dev_id_buffer, 256, 0) == 0:
                            port_chain.append(ctypes.wstring_at(dev_id_buffer))

                        # Get parent device
                        if CM_Get_Parent(ctypes.byref(parent_dev_inst), dev_inst, 0) != 0:
                            parent_dev_inst = None
                            break
                        dev_inst = parent_dev_inst.value

                    port_chain.reverse()  # Reverse to go from root to device

                    # Get all sibling devices under the same parent
                    siblings = get_sibling_devices(hDevInfo_all, parent_dev_inst.value) if parent_dev_inst else []

                    all_devices.append({
                        "port_chain": port_chain,
                        "siblings": siblings
                    })

            index += 1

    finally:
        SetupDiDestroyDeviceInfoList(hDevInfo_usb)
        SetupDiDestroyDeviceInfoList(hDevInfo_all)

    return all_devices

# Example usage
if __name__ == "__main__":
    vid = "1a86"  # Example VID
    pid = "7523"  # Example PID
    try:
        devices = get_port_chains(vid, pid)
        if devices:
            for i, device in enumerate(devices, 1):
                print(f"\nDevice {i} Port Chain:")
                for j, device_id in enumerate(device["port_chain"], 1):
                    print(f"{j}. {device_id}")
                print(f"\nDevice {i} Siblings (same parent):")
                if device["siblings"]:
                    for k, sibling in enumerate(device["siblings"], 1):
                        print(f"{k}. Hardware ID: {sibling['hardware_id']}")
                        print(f"   Device ID: {sibling['device_id']}")
                else:
                    print("No siblings found.")
        else:
            print("No devices found with the specified VID and PID.")
    except WindowsError as e:
        print(f"Error: {e}")