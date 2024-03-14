import os
import base64
import requests
import subprocess

from utils.ffmpeg_base import FfmpegBase


class ShazamAPI(FfmpegBase):
    def detect_song(self):
        # record audio from the stream
        bytes = self.record_audio()
        
        # get audio data from the file
        base64_data = self.get_audio_data(bytes)
        
        # get the result from the shazam API
        song = self.get_shazam_result(base64_data)
        
        return song


    # records output audio from the stream.
    def record_audio(self) -> bytes:
        # Start recording the stream
        self.start_recording()
        
        # Pipe the output to ffmpeg with 1 channel and 44100 sample rate for 8 seconds
        self.ffmpeg_process = subprocess.Popen(
            ['ffmpeg', '-i', 'pipe:0', '-ac', '1', '-ar', '44100', '-t', '8', '-acodec', 'pcm_s16le', '-f', 'wav', '-loglevel', 'panic', '-'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE)
        
        # Total Bytes = 8 seconds * 44100 Hz * 1 channel * 2 bytes/sample = 705600 bytes
        # Wait for all the bytes to be written to stdout
        out_bytes = self.ffmpeg_process.stdout.read(705600)  

        # Stop recording the stream
        self.stop_recording()

        # return the audio bytes
        return out_bytes


    # Get the audio data from the file
    def get_audio_data(self, bytes: bytes):
        # Encode the audio data to base64
        base64_data = base64.b64encode(bytes).decode('utf-8')

        return base64_data


    # Get the result from the shazam API
    def get_shazam_result(self, base64_data):
        url = "https://shazam.p.rapidapi.com/songs/v2/detect"

        querystring = {"timezone":"America/Chicago","locale":"en-US"}

        payload = base64_data
        headers = {
            "content-type": "text/plain",
            "X-RapidAPI-Key": os.environ["shazam_api_key"],
            "X-RapidAPI-Host": "shazam.p.rapidapi.com"
        }

        # Send the request to the API
        response = requests.post(url, data=payload, headers=headers, params=querystring)

        # Check if the request was successful
        if response.status_code == 200:
            result = response.json()
            matches = result['matches']

            # Check if there are any matches
            if len(matches) > 0:
                song = result['track']['share']['text']
                return song
            else:
                return "No matches found"
        else:
            return "Error"