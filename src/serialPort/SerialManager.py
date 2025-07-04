import serial
from device import Ch9329
import threading

class SerialManager:
    def __init__(self):
        self.ser_port

    def open_serial_port(self,device_path):
        try:
            self.ser_port = serial.Serial(
                port=device_path,
                baudrate=115200,
                timeout=1
            )
            print(f"Successfully open serial port: {device_path}")
        except serial.SerialException as e:
            print(f"Can not open the serial port {device_path} - {e}")
    
    