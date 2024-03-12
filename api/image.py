import io
import os
import subprocess
import base64


class ImageAPI:
    # Take screenshot of twitch stream
    def take_screenshot(self) -> io.BytesIO:       
        # Run the streamlink command
        streamlink_process = subprocess.Popen(
            ['streamlink', f"twitch.tv/{os.environ['target_channel']}", '480p', '--quiet', '--stdout', '--twitch-disable-ads', '--twitch-low-latency'],
            stdout=subprocess.PIPE)

        # Pipe the output to ffmpeg
        ffmpeg_process = subprocess.Popen(
            ['ffmpeg', '-i', 'pipe:0', '-vframes', '1', '-vcodec', 'png', '-f', 'image2pipe', '-loglevel', 'panic', '-'],
            stdin=streamlink_process.stdout,
            stdout=subprocess.PIPE)

        # Read the output into a BytesIO object
        image_bytes = io.BytesIO(ffmpeg_process.communicate()[0])

        # Close the processes
        streamlink_process.kill()
        ffmpeg_process.kill()

        return image_bytes
    

    # Get the screenshot as a base64 string
    def get_base64_screenshot(self):
        # Get the screenshot as a BytesIO object
        image_bytes = self.take_screenshot()

        # Encode the image data to base64
        return base64.b64encode(image_bytes.getvalue()).decode('utf-8')