import struct

# Const defination bytes
MOUSE_ABS_ACTION_PREFIX = bytes.fromhex("57 AB 00 04 07 02")
MOUSE_REL_ACTION_PREFIX = bytes.fromhex("57 AB 00 05 05 01")
CMD_GET_PARA_CFG = bytes.fromhex("57 AB 00 08 00")
CMD_GET_INFO = bytes.fromhex("57 AB 00 01 00")
CMD_RESET = bytes.fromhex("57 AB 00 0F 00")
CMD_SET_DEFAULT_CFG = bytes.fromhex("57 AB 00 0C 00")
CMD_SET_USB_STRING_PREFIX = bytes.fromhex("57 AB 00 0B")
CMD_SEND_KB_GENERAL_DATA = bytes.fromhex("57 AB 00 02 08 00 00 00 00 00 00 00 00")
CMD_SET_PARA_CFG_PREFIX = bytes.fromhex("57 AB 00 09 32 82 80 00 00 01 C2 00")
CMD_SET_PARA_CFG_MID = bytes.fromhex("08 00 00 03 86 1a 29 e1 00 00 00 01 00 0d 00 00 00 00 00 00 00") + bytes(22)

RESERVED_2BYTES = bytes.fromhex("08 00")
PACKAGE_INTERVAL = bytes.fromhex("00 03")
KEYBOARD_UPLOAD_INTERVAL = bytes.fromhex("00 00")
KEYBOARD_RELEASE_TIMEOUT = bytes.fromhex("00 03")
KEYBOARD_AUTO_ENTER = bytes.fromhex("00")
KEYBOARD_ENTER = bytes.fromhex("0D 00 00 00 00 00 00 00")
FILTER = bytes.fromhex("00 00 00 00 00 00 00 00")
SPEED_MODE = bytes.fromhex("00")
RESERVED_4BYTES = bytes.fromhex("00 00 00 00")

# Command return code
DEF_CMD_SUCCESS = 0x00
DEF_CMD_ERR_TIMEOUT = 0xE1
DEF_CMD_ERR_HEAD = 0xE2
DEF_CMD_ERR_CMD = 0xE3
DEF_CMD_ERR_SUM = 0xE4
DEF_CMD_ERR_PARA = 0xE5
DEF_CMD_ERR_OPERATE = 0xE6

def to_little_endian_16(value):
    return struct.unpack('<H', struct.pack('>H', value))[0]

def to_little_endian_32(value):
    return struct.unpack('<I', struct.pack('>I', value))[0]

def from_bytes(fmt, data):
    return struct.unpack(fmt, data)

# Struct defination
class CmdGetInfoResult:
    def __init__(self, data):
        fields = struct.unpack('<HBBBBBBBBBBB', data[:13])
        (self.prefix, self.addr1, self.cmd, self.len, self.version,
         self.targetConnected, self.indicators, self.reserved1,
         self.reserved2, self.reserved3, self.reserved4, self.reserved5,
         self.sum) = fields

    def dump(self):
        print(f"prefix: {hex(self.prefix)} | addr1: {self.addr1} | cmd: {hex(self.cmd)} | len: {self.len} | version: {self.version} | targetConnected: {self.targetConnected} | indicators: {self.indicators}")

class CmdDataParamConfig:
    def __init__(self, data):
        fields = struct.unpack('<BBBBBBBxIHHHHHHBIIIBBHHHHB', data[:55])
        (self.prefix1, self.prefix2, self.addr1, self.cmd, self.len, self.mode, self.cfg, self.baudrate,
         self.reserved1, self.serial_interval, self.vid, self.pid, self.keyboard_upload_interval,
         self.keyboard_release_timeout, self.keyboard_auto_enter, self.enterkey1, self.enterkey2,
         self.filter_start, self.filter_end, self.custom_usb_desc, self.speed_mode,
         self.reserved2, self.reserved3, self.reserved4, self.sum) = fields

    def dump(self):
        print(f"prefix: {hex(self.prefix1)}{hex(self.prefix2)} | addr1: {self.addr1} | cmd: {hex(self.cmd)} | len: {self.len} | mode: {hex(self.mode)} | cfg: {hex(self.cfg)} | addr2: N/A | baudrate: {self.baudrate} | reserved1: {hex(self.reserved1)} | serial_interval: {self.serial_interval} | vid: {hex(self.vid)} | pid: {hex(self.pid)} | keyboard_upload_interval: {self.keyboard_upload_interval} | keyboard_release_timeout: {self.keyboard_release_timeout} | keyboard_auto_enter: {self.keyboard_auto_enter} | enterkey1: {hex(self.enterkey1)} | enterkey2: {hex(self.enterkey2)} | filter_start: {hex(self.filter_start)} | filter_end: {hex(self.filter_end)} | custom_usb_desc: {self.custom_usb_desc} | speed_mode: {self.speed_mode} | reserved2: {hex(self.reserved2)} | reserved3: {hex(self.reserved3)} | reserved4: {hex(self.reserved4)} | sum: {hex(self.sum)}")

class CmdDataResult:
    def __init__(self, data):
        fields = struct.unpack('<HBBBBB', data[:7])
        (self.prefix, self.addr1, self.cmd, self.len, self.data, self.sum) = fields

    def dump(self):
        print(f"prefix: {hex(self.prefix)} | addr1: {self.addr1} | cmd: {hex(self.cmd)} | len: {self.len} | data: {hex(self.data)} | sum: {hex(self.sum)}")

class CmdReset:
    def __init__(self, data):
        fields = struct.unpack('<BBBBB', data[:5])
        (self.prefix_high, self.prefix_low, self.addr1, self.cmd, self.len) = fields

    def dump(self):
        print(f"prefix: {self.prefix_high} {self.prefix_low} | addr1: {self.addr1} | cmd: {self.cmd} | len: {self.len}")

class CmdResetResult:
    def __init__(self, data):
        fields = struct.unpack('<HBBBBB', data[:7])
        (self.prefix, self.addr1, self.cmd, self.len, self.data, self.sum) = fields

    def dump(self):
        print(f"prefix: {hex(self.prefix)} | addr1: {self.addr1} | cmd: {hex(self.cmd)} | len: {self.len} | data: {self.data} | sum: {hex(self.sum)}")

def dump_error(status, data):
    if status != 0x00:
        if status == DEF_CMD_ERR_TIMEOUT:
            print(f"Error({hex(status)}), Serial response timeout, data: {data.hex(' ')}")
        elif status == DEF_CMD_ERR_HEAD:
            print(f"Error({hex(status)}), Packet header error, data: {data.hex(' ')}")
        elif status == DEF_CMD_ERR_CMD:
            print(f"Error({hex(status)}), Command error, data: {data.hex(' ')}")
        elif status == DEF_CMD_ERR_SUM:
            print(f"Error({hex(status)}), Checksum error, data: {data.hex(' ')}")
        elif status == DEF_CMD_ERR_PARA:
            print(f"Error({hex(status)}), Argument error, data: {data.hex(' ')}")
        elif status == DEF_CMD_ERR_OPERATE:
            print(f"Error({hex(status)}), Execution error, data: {data.hex(' ')}")
        else:
            print(f"Error({hex(status)}), Unknown error, data: {data.hex(' ')}")