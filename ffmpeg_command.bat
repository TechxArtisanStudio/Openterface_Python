.\ffmpeg.exe -f dshow -i video="@device_pnp_\\?\usb#vid_534d&pid_2109&mi_00#7&1ff4451e&2&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global" 
-c:v h264_nvenc -pix_fmt nv12 -r 25 -g 25 -b:v 2M -maxrate 2M -bufsize 4M 
-f rtp rtp://192.168.100.66:1234 -sdp_file stream.sdp

ffmpeg -f dshow -i video="@device_pnp_\\?\usb#vid_534d&pid_2109&mi_00#7&1ff4451e&2&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global" -f dshow -i audio="@device_cm_{33D9A762-90C8-11D0-BD43-00A0C911CE86}\wave_{066429B6-13A5-4869-8029-DED24018DB36}" -c:v h264_nvenc -pix_fmt nv12 -r 25 -g 25 -b:v 2M -maxrate 2M -bufsize 4M -c:a aac -ar 48000 -b:a 128k -flags +low_delay -f rtp_mpegts rtp://192.168.100.66:1234 -sdp_file stream.sdp

ffmpeg
-f dshow -i video="@device_pnp_\\?\usb#vid_534d&pid_2109&mi_00#7&1ff4451e&2&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global" 
-f dshow -i audio="@device_cm_{33D9A762-90C8-11D0-BD43-00A0C911CE86}\wave_{066429B6-13A5-4869-8029-DED24018DB36}" 
-c:v h264_nvenc -pix_fmt nv12 -r 25 -g 25 -b:v 2M -maxrate 2M -bufsize 4M 
-c:a libmp3lame -ar 44100 -b:a 128k 
-map 0:v -map 1:a 
-use_wallclock_as_timestamps 1 -async 1 
-flags +low_delay -ttl 64 
-f rtp_mpegts "rtp://192.168.100.66:1234?pkt_size=1316&localaddr=192.168.100.1" 
-sdp_file stream.sdp