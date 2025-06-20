from dataclasses import dataclass
from typing import Optional

dataclass
class UsbDevice:
    DeviceID: str
    vendor_id: str
    product_id: str
    path: str
    serial: Optional[str] = None

class DeviceGroup:
    webcam: Optional[UsbDevice] = None
    audio_device: Optional[UsbDevice] = None
    serial_port: Optional[UsbDevice] = None
    hid_device: Optional[UsbDevice] = None

    def is_complete(self):
        return self.webcam and self.audio_device and self.serial_port and self.hid_device