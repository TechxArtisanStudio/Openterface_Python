import socket
import json
import threading
from serialPort.SerialManager import SerialManager


class DeviceSocketServer:
    """
    Socket server for controlling Openterface devices remotely
    
    Provides JSON-based API for device discovery, selection, and control
    """
    
    def __init__(self, device_manager, host='localhost', port=16688):
        self.device_manager = device_manager
        self.client_selected_devices = {}  # Track selected devices per client
        self.host = host
        self.port = port
        self.socket_server = None
        self.socket_thread = None
        self.running = True
        
    def start_server(self):
        """Start the socket server"""
        try:
            self.socket_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket_server.bind((self.host, self.port))
            self.socket_server.listen(5)
            
            print(f"\n🌐 Socket server started on {self.host}:{self.port}")
            print("📡 Waiting for client connections to control devices...")
            print("🎮 Available commands: discover, select, serial, camera, hid, status, stop")
            
            self.socket_thread = threading.Thread(target=self.handle_socket_connections)
            self.socket_thread.daemon = True
            self.socket_thread.start()
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to start socket server: {e}")
            return False

    def handle_socket_connections(self):
        """Handle incoming socket connections"""
        while self.running:
            try:
                client_socket, address = self.socket_server.accept()
                print(f"🔗 Client connected from {address}")
                
                client_thread = threading.Thread(
                    target=self.handle_client, 
                    args=(client_socket, address)
                )
                client_thread.daemon = True
                client_thread.start()
                
            except Exception as e:
                if self.running:
                    print(f"❌ Socket connection error: {e}")

    def handle_client(self, client_socket, address):
        """Handle individual client commands"""
        try:
            # Initialize client session
            client_id = f"{address[0]}:{address[1]}"
            self.client_selected_devices[client_id] = None
            
            while self.running:
                data = client_socket.recv(1024).decode('utf-8')
                if not data:
                    break
                
                try:
                    command = json.loads(data)
                    response = self.process_device_command(command, client_id)
                    client_socket.send(json.dumps(response).encode('utf-8'))
                    
                except json.JSONDecodeError:
                    error_response = {"error": "Invalid JSON format"}
                    client_socket.send(json.dumps(error_response).encode('utf-8'))
                    
        except Exception as e:
            print(f"❌ Client {address} error: {e}")
        finally:
            # Clean up client session
            if client_id in self.client_selected_devices:
                del self.client_selected_devices[client_id]
            client_socket.close()
            print(f"🔌 Client {address} disconnected")

    def process_device_command(self, command, client_id):
        """Process device control commands"""
        cmd_type = command.get('type', '').lower()
        
        if cmd_type == 'discover':
            return self.handle_discover_command()
        elif cmd_type == 'select':
            return self.handle_select_command(command, client_id)
        elif cmd_type == 'serial':
            return self.handle_serial_command(command, client_id)
        elif cmd_type == 'camera':
            return self.handle_camera_command(command, client_id)
        elif cmd_type == 'hid':
            return self.handle_hid_command(command, client_id)
        elif cmd_type == 'status':
            return self.get_device_status(client_id)
        elif cmd_type == 'stop':
            self.running = False
            return {"status": "Stopping server"}
        else:
            return {"error": f"Unknown command type: {cmd_type}"}

    def handle_discover_command(self):
        """Handle device discovery command"""
        try:
            current_devices = self.device_manager.discover_devices()
            
            if not current_devices:
                return {
                    "status": "success",
                    "action": "discover",
                    "devices": [],
                    "message": "No devices found"
                }
            
            # Group devices by port chain
            grouped_devices = {}
            for device in current_devices:
                device_dict = device.to_dict()
                port_chain = device_dict.get('port_chain', 'Unknown')
                if port_chain not in grouped_devices:
                    grouped_devices[port_chain] = []
                grouped_devices[port_chain].append(device_dict)
            
            # Format response
            devices_list = []
            for port_chain, devices in grouped_devices.items():
                device_entry = {
                    "port_chain": port_chain,
                    "device_count": len(devices),
                    "devices": devices,
                    "brief_info": self.format_device_brief(devices[0]) if devices else "No info"
                }
                devices_list.append(device_entry)
            
            return {
                "status": "success",
                "action": "discover",
                "devices": devices_list,
                "total_port_chains": len(devices_list),
                "message": f"Found {len(devices_list)} port chain(s)"
            }
            
        except Exception as e:
            return {"error": f"Device discovery error: {str(e)}"}

    def handle_select_command(self, command, client_id):
        """Handle device selection command"""
        try:
            port_chain = command.get('port_chain', '')
            
            if not port_chain:
                return {"error": "Port chain not specified"}
            
            # Discover current devices
            current_devices = self.device_manager.discover_devices()
            
            # Find devices with the specified port chain
            selected_devices = []
            for device in current_devices:
                device_dict = device.to_dict()
                if device_dict.get('port_chain') == port_chain:
                    selected_devices.append(device_dict)
            
            if not selected_devices:
                return {"error": f"No devices found with port chain: {port_chain}"}
            
            # Store selected device info for this client
            self.client_selected_devices[client_id] = {
                'port_chain': port_chain,
                'devices': selected_devices
            }
            
            print(f"🎯 Client {client_id} selected device: {port_chain}")
            
            return {
                "status": "success",
                "action": "select",
                "port_chain": port_chain,
                "device_count": len(selected_devices),
                "devices": selected_devices,
                "message": f"Device selected: {port_chain}"
            }
            
        except Exception as e:
            return {"error": f"Device selection error: {str(e)}"}

    def handle_serial_command(self, command, client_id):
        """Handle serial port commands"""
        try:
            # Check if client has selected a device
            selected_device_info = self.client_selected_devices.get(client_id)
            if not selected_device_info:
                return {"error": "No device selected. Use 'select' command first."}
            
            action = command.get('action', '')
            
            # Get serial port path from selected device
            serial_path = None
            for device in selected_device_info['devices']:
                if device.get('serial_port_path'):
                    serial_path = device['serial_port_path']
                    break
            
            if not serial_path:
                return {"error": "No serial port available in selected device"}
            
            if action == 'send':
                data = command.get('data', '')
                # TODO: Implement serial communication using SerialManager
                return {
                    "status": "success", 
                    "action": "send",
                    "port": serial_path,
                    "data": data,
                    "message": "Serial data sent (implementation needed)"
                }
                
            elif action == 'read':
                # TODO: Implement serial reading using SerialManager  
                return {
                    "status": "success",
                    "action": "read", 
                    "port": serial_path,
                    "data": "dummy_response",
                    "message": "Serial data read (implementation needed)"
                }
                
            elif action == 'open':
                # TODO: Implement serial port opening
                return {
                    "status": "success",
                    "action": "open",
                    "port": serial_path,
                    "message": "Serial port opened (implementation needed)"
                }
                
            elif action == 'close':
                # TODO: Implement serial port closing
                return {
                    "status": "success",
                    "action": "close",
                    "port": serial_path,
                    "message": "Serial port closed (implementation needed)"
                }
                
            else:
                return {"error": f"Unknown serial action: {action}"}
                
        except Exception as e:
            return {"error": f"Serial command error: {str(e)}"}

    def handle_camera_command(self, command, client_id):
        """Handle camera/video commands"""
        try:
            # Check if client has selected a device
            selected_device_info = self.client_selected_devices.get(client_id)
            if not selected_device_info:
                return {"error": "No device selected. Use 'select' command first."}
            
            action = command.get('action', '')
            
            # Get camera path from selected device
            camera_path = None
            for device in selected_device_info['devices']:
                if device.get('camera_path'):
                    camera_path = device['camera_path']
                    break
            
            if not camera_path:
                return {"error": "No camera available in selected device"}
            
            if action == 'start_stream':
                # TODO: Implement video streaming using VideoFFmpeg
                return {
                    "status": "success",
                    "action": "start_stream",
                    "camera": camera_path,
                    "message": "Camera stream started (implementation needed)"
                }
                
            elif action == 'stop_stream':
                # TODO: Implement stopping video stream
                return {
                    "status": "success", 
                    "action": "stop_stream",
                    "camera": camera_path,
                    "message": "Camera stream stopped (implementation needed)"
                }
                
            elif action == 'capture':
                # TODO: Implement frame capture
                return {
                    "status": "success",
                    "action": "capture",
                    "camera": camera_path,
                    "message": "Frame captured (implementation needed)"
                }
                
            elif action == 'get_info':
                # TODO: Get camera information
                return {
                    "status": "success",
                    "action": "get_info",
                    "camera": camera_path,
                    "info": {"width": 1920, "height": 1080, "fps": 30},
                    "message": "Camera info retrieved (dummy data)"
                }
                
            else:
                return {"error": f"Unknown camera action: {action}"}
                
        except Exception as e:
            return {"error": f"Camera command error: {str(e)}"}

    def handle_hid_command(self, command, client_id):
        """Handle HID device commands"""
        try:
            # Check if client has selected a device
            selected_device_info = self.client_selected_devices.get(client_id)
            if not selected_device_info:
                return {"error": "No device selected. Use 'select' command first."}
            
            action = command.get('action', '')
            
            # Get HID path from selected device
            hid_path = None
            for device in selected_device_info['devices']:
                if device.get('HID_path'):
                    hid_path = device['HID_path']
                    break
            
            if not hid_path:
                return {"error": "No HID device available in selected device"}
            
            if action == 'send_report':
                report_data = command.get('data', [])
                # TODO: Implement HID report sending using VideoHID
                return {
                    "status": "success",
                    "action": "send_report", 
                    "hid": hid_path,
                    "data": report_data,
                    "message": "HID report sent (implementation needed)"
                }
                
            elif action == 'read_report':
                # TODO: Implement HID report reading
                return {
                    "status": "success",
                    "action": "read_report",
                    "hid": hid_path,
                    "data": [],
                    "message": "HID report read (implementation needed)"
                }
                
            elif action == 'open':
                # TODO: Implement HID device opening
                return {
                    "status": "success",
                    "action": "open",
                    "hid": hid_path,
                    "message": "HID device opened (implementation needed)"
                }
                
            elif action == 'close':
                # TODO: Implement HID device closing
                return {
                    "status": "success",
                    "action": "close",
                    "hid": hid_path,
                    "message": "HID device closed (implementation needed)"
                }
                
            else:
                return {"error": f"Unknown HID action: {action}"}
                
        except Exception as e:
            return {"error": f"HID command error: {str(e)}"}

    def get_device_status(self, client_id):
        """Get current device status for client"""
        selected_device_info = self.client_selected_devices.get(client_id)
        
        if not selected_device_info:
            return {
                "status": "success",
                "client_id": client_id,
                "selected_device": None,
                "message": "No device selected"
            }
        
        return {
            "status": "success",
            "client_id": client_id,
            "selected_device": {
                "port_chain": selected_device_info['port_chain'],
                "device_count": len(selected_device_info['devices']),
                "devices": selected_device_info['devices']
            },
            "server": {
                "host": self.host,
                "port": self.port,
                "running": self.running
            }
        }
        """Handle serial port commands"""
        try:
            action = command.get('action', '')
            
            # Get serial port path from selected device
            serial_path = None
            for device in self.selected_device_info['devices']:
                if device.get('serial_port_path'):
                    serial_path = device['serial_port_path']
                    break
            
            if not serial_path:
                return {"error": "No serial port available in selected device"}
            
            if action == 'send':
                data = command.get('data', '')
                # TODO: Implement serial communication using SerialManager
                return {
                    "status": "success", 
                    "action": "send",
                    "port": serial_path,
                    "data": data,
                    "message": "Serial data sent (implementation needed)"
                }
                
            elif action == 'read':
                # TODO: Implement serial reading using SerialManager  
                return {
                    "status": "success",
                    "action": "read", 
                    "port": serial_path,
                    "data": "dummy_response",
                    "message": "Serial data read (implementation needed)"
                }
                
            elif action == 'open':
                # TODO: Implement serial port opening
                return {
                    "status": "success",
                    "action": "open",
                    "port": serial_path,
                    "message": "Serial port opened (implementation needed)"
                }
                
            elif action == 'close':
                # TODO: Implement serial port closing
                return {
                    "status": "success",
                    "action": "close",
                    "port": serial_path,
                    "message": "Serial port closed (implementation needed)"
                }
                
            else:
                return {"error": f"Unknown serial action: {action}"}
                
        except Exception as e:
            return {"error": f"Serial command error: {str(e)}"}

    def handle_camera_command(self, command):
        """Handle camera/video commands"""
        try:
            action = command.get('action', '')
            
            # Get camera path from selected device
            camera_path = None
            for device in self.selected_device_info['devices']:
                if device.get('camera_path'):
                    camera_path = device['camera_path']
                    break
            
            if not camera_path:
                return {"error": "No camera available in selected device"}
            
            if action == 'start_stream':
                # TODO: Implement video streaming using VideoFFmpeg
                return {
                    "status": "success",
                    "action": "start_stream",
                    "camera": camera_path,
                    "message": "Camera stream started (implementation needed)"
                }
                
            elif action == 'stop_stream':
                # TODO: Implement stopping video stream
                return {
                    "status": "success", 
                    "action": "stop_stream",
                    "camera": camera_path,
                    "message": "Camera stream stopped (implementation needed)"
                }
                
            elif action == 'capture':
                # TODO: Implement frame capture
                return {
                    "status": "success",
                    "action": "capture",
                    "camera": camera_path,
                    "message": "Frame captured (implementation needed)"
                }
                
            elif action == 'get_info':
                # TODO: Get camera information
                return {
                    "status": "success",
                    "action": "get_info",
                    "camera": camera_path,
                    "info": {"width": 1920, "height": 1080, "fps": 30},
                    "message": "Camera info retrieved (dummy data)"
                }
                
            else:
                return {"error": f"Unknown camera action: {action}"}
                
        except Exception as e:
            return {"error": f"Camera command error: {str(e)}"}

    def handle_hid_command(self, command):
        """Handle HID device commands"""
        try:
            action = command.get('action', '')
            
            # Get HID path from selected device
            hid_path = None
            for device in self.selected_device_info['devices']:
                if device.get('HID_path'):
                    hid_path = device['HID_path']
                    break
            
            if not hid_path:
                return {"error": "No HID device available in selected device"}
            
            if action == 'send_report':
                report_data = command.get('data', [])
                # TODO: Implement HID report sending using VideoHID
                return {
                    "status": "success",
                    "action": "send_report", 
                    "hid": hid_path,
                    "data": report_data,
                    "message": "HID report sent (implementation needed)"
                }
                
            elif action == 'read_report':
                # TODO: Implement HID report reading
                return {
                    "status": "success",
                    "action": "read_report",
                    "hid": hid_path,
                    "data": [],
                    "message": "HID report read (implementation needed)"
                }
                
            elif action == 'open':
                # TODO: Implement HID device opening
                return {
                    "status": "success",
                    "action": "open",
                    "hid": hid_path,
                    "message": "HID device opened (implementation needed)"
                }
                
            elif action == 'close':
                # TODO: Implement HID device closing
                return {
                    "status": "success",
                    "action": "close",
                    "hid": hid_path,
                    "message": "HID device closed (implementation needed)"
                }
                
            else:
                return {"error": f"Unknown HID action: {action}"}
                
        except Exception as e:
            return {"error": f"HID command error: {str(e)}"}

    def get_device_status(self):
        """Get current device status"""
        if not self.selected_device_info:
            return {"error": "No device selected"}
        
        return {
            "status": "success",
            "selected_device": {
                "port_chain": self.selected_device_info['port_chain'],
                "device_count": len(self.selected_device_info['devices']),
                "devices": self.selected_device_info['devices']
            },
            "server": {
                "host": self.host,
                "port": self.port,
                "running": self.running
            }
        }

    def stop_server(self):
        """Stop the socket server"""
        self.running = False
        if self.socket_server:
            try:
                self.socket_server.close()
                print("🌐 Socket server stopped")
            except Exception as e:
                print(f"❌ Error stopping socket server: {e}")

    def update_selected_device(self, selected_device_info):
        """Update the selected device information"""
        self.selected_device_info = selected_device_info
        print(f"🔄 Updated selected device: {selected_device_info['port_chain']}")

    def format_device_brief(self, device):
        """Format device info briefly for display"""
        parts = []
        if device.get('serial_port_path'):
            parts.append(f"Serial:{device['serial_port_path']}")
        if device.get('camera_path'):
            parts.append(f"Video")
        if device.get('audio_path'):
            parts.append(f"Audio")
        if device.get('HID_path'):
            parts.append(f"HID")
        return " | ".join(parts) if parts else "Unknown device"
