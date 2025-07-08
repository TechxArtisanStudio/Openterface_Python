import subprocess
import re
import os

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

def start_stream(video_input, audio_input, rtp_video_url, platform="windows"):
    if platform == "windows":
        video_source = ['-f', 'dshow', '-i', f'video={video_input}']
    elif platform == "linux":
        video_source = ['-f', 'v4l2', '-i', f'{video_input}']
    elif platform == "macos":
        video_source = ['-f', 'avfoundation', '-i', f'{video_input}']
    else:
        raise ValueError("Unsupported platform. Choose from 'windows', 'linux', or 'macos'.")

    current_dir = os.getcwd()
    sdp_file_path = os.path.join(current_dir, 'output.sdp')

    command = [
        'ffmpeg',
        *video_source,
        # *audio_source,

        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        '-preset', 'ultrafast',
        '-g', '25',
        '-b:v', '1024k',

        '-flags', '+low_delay',
        '-f:rtp', 'udp://',  

        '-metadata:s:v', 'title=Video',


        '-sdp_file', sdp_file_path,

        '-f', 'rtp', rtp_video_url,

    ]

    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE)

        process.wait()
    except KeyboardInterrupt:

        process.terminate()
    except Exception as e:
        print("Error:", str(e))


if __name__ == "__main__":
    devs = list_windows_devices()

    print("Available Video Devices:")
    for i, dev in enumerate(devs):
        print(f" {dev}")