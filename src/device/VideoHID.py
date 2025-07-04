import hid
from utils import logger

HIDLogger = logger.hid_logger

def list_hid_devices(VID, PID):
    for device in hid.enumerate():
        if device['vendor_id'] == VID and device['product_id'] == PID:
            HIDLogger.info(f"find the target device:")
            HIDLogger.info(f"  Vendor ID: {hex(device['vendor_id'])}, Product ID: {hex(device['product_id'])}")
            HIDLogger.info(f"  Product: {device['product_string']}")
            HIDLogger.info(f"  Manufacturer: {device['manufacturer_string']}")
            HIDLogger.info(f"  Path: {device['path']} type: {type(device['path'])}")
            if isinstance(device['path'], bytes):
                path_str = device['path'].decode(errors='replace')
            HIDLogger.info(f"  Path: {path_str} type: {type(path_str)}")
            
if __name__ == "__main__":
    VID = 0x534d  # Example Vendor ID
    PID = 0x2109  # Example Product ID
    list_hid_devices(VID, PID)