# Openterface Python

## Overview

Openterface Python is an open-source programing interfce for Openterface MiniKVM (Keyboard, Video, Mouse) over USB solution designed for automation, remote control, and system management. It enables video/audio capture, advanced image processing, AI-based recognition, and full keyboard/mouse control over network protocols. The system is cross-platform and supports integration with Jupyter Notebooks for automation and scripting.

## Architecture

```mermaid
graph LR
    A[Target Machine] -- "Video/Audio" --> B[Openterface MiniKVM]
    A -- "Keyboard/Mouse" --> B
    B -- "USB" --> C[Host Machine <Python>]
    C -- "Video/Audio Streaming" --> D[Python Client]
    C <-- "Keyboard/Mouse" --> D

```

- **Target Machine**: The system to be controlled.
- **Openterface MiniKVM**: Hardware for video/audio captureing and keyboard/mouse control.
- **Host Machine**: Runs the KVM server (Python, cross-platform).
- **Python Client**: User computer accessing the KVM server python or notebook.

## Features

### Video Capture & Processing
- Video/audio capture via FFMPEG
- Image processing and streaming (MJPG, H264)
- Advanced AI logic for:
  - System text OCR
  - Mouse detection
  - System, blue screen, and BIOS recognition

### Keyboard Control
- US 101 keyboard emulation
- Multi-language and multimedia keyboard support

### Mouse Control
- Absolute and relative mouse movement

### Automation & Integration
- OS installation automation
- BIOS auto-configuration
- Jupyter Notebook integration for scripting and automation

## Installation

```bash
pip install -r requirements.txt
pip install -e .
```

## Requirements

- Python 3.7+
- [python-ffmpeg](https://pypi.org/project/python-ffmpeg/)
- [hidapi](https://pypi.org/project/hidapi/)
- [pyserial](https://pypi.org/project/pyserial/)

## Usage

### Example: Video Streaming in Jupyter Notebook

See `src/notebook/example.ipynb` for a working example.

```python
from device import DeviceGroupsWin
from device import VideoFFmpeg

HID_VID = "534D"
HID_PID = "2109"
Serial_port_VID = "1A86"
Serial_port_PID = "7523"
device_info_list = DeviceGroupsWin.search_phycial_device(Serial_port_VID, Serial_port_PID, HID_VID, HID_PID)
video_path = device_info_list[0]['camera_path']
audio_path = device_info_list[0]['audio_path']
video_url = "rtp://192.168.100.66:5000"
VideoFFmpeg.start_stream(video_path, audio_path, video_url, "windows")
```

### Running the Main Application

```bash
python src/main.py
```

## Automation Scenarios

- **OS Installation Automation**: Automate OS setup via remote KVM control.
- **BIOS Auto Configuration**: Scripted BIOS navigation and configuration using AI-based recognition.

## License

This project is licensed under the MIT License.

## Contact

For questions or contributions, please open an issue or submit a pull request.

