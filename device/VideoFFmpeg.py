import subprocess
import re
def list_windows_devices():

    command = [
        'ffmpeg',
        '-hide_banner',  
        '-f', 'dshow', 
        '-list_devices', 'true',
        '-i', 'dummy'
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        output = result.stdout
        
        lines = output.splitlines()

        device = []
        for line in lines:
            line = line.strip()
            if "Alternative name" in line:
                match = re.search(r'"(.*?)"', line)
                if match:
                    device.append(match.group(1))
        return device

    except Exception as e:
        print("Error:", e)
        return [], []

if __name__ == "__main__":
    devs = list_windows_devices()

    print("Available Video Devices:")
    for i, dev in enumerate(devs):
        print(f" {dev}")