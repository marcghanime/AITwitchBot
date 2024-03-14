import base64
import subprocess

from utils.ffmpeg_base import FfmpegBase

class ImageAPI(FfmpegBase):
    # Take screenshot of twitch stream
    def take_screenshot(self) -> bytes:  
        # Start recording the stream 
        self.start_recording()

        # Pipe the stream output to ffmpeg
        self.ffmpeg_process = subprocess.Popen(
            ['ffmpeg', '-i', 'pipe:0', '-vframes', '1', '-vcodec', 'png', '-f', 'image2pipe', '-loglevel', 'panic', '-'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE)

        # Wait for all the bytes to be written to stdout
        out_bytes = self.ffmpeg_process.stdout.read(480 * 640 * 3)  # 3 bytes per pixel

        # Stop recording the stream
        self.stop_recording()

        return out_bytes
    

    # Get the screenshot as a base64 string
    def get_base64_screenshot(self):
        # Get the screenshot as bytes
        image_bytes = self.take_screenshot()

        # Encode the image data to base64
        return base64.b64encode(image_bytes).decode('utf-8')