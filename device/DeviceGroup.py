class UsbDevice:
    camera_path: str
    audio_path: str
    serial_path: str
    hid_path: str

    camera_id: str
    audio_id: str
    serial_id: str
    hid_id: str

    def query_devicep_path_by_id(self, device_id: str , device_path: str):
        if device_id 

class DeviceGroup:
    def __init__(self):
        self.usb_devices = []

    def add_usb_device(self, usb_device: UsbDevice):
        self.usb_devices.append(usb_device)

    def get_usb_devices(self):
        return self.usb_devices

    def clear_usb_devices(self):
        self.usb_devices.clear()

    def __repr__(self):
        return f"DeviceGroup(usb_devices={self.usb_devices})"