import config
if config.PLATFORM == "win32":
    from device import DeviceGroupsWin
from device import VideoFFmpeg

if __name__ == "__main__":
    device_info_list = DeviceGroupsWin.search_phycial_device("1a86", "7523", "534D", "2109")
    video_path = device_info_list[0]['camera_path']
    audio_path = device_info_list[0]['audio_path']
    video_url = "rtp://192.168.100.66:5000"

    VideoFFmpeg.start_stream(video_path, audio_path, video_url, "windows")