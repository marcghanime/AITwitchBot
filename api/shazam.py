import os
import io
import requests
import base64
import subprocess


class ShazamAPI:
    def detect_song(self):
        # record audio from the stream
        bytes = self.record_audio()
        
        # get audio data from the file
        base64_data = self.get_audio_data(bytes)
        
        # get the result from the shazam API
        song = self.get_shazam_result(base64_data)
        
        return song


    # records output audio from the stream.
    def record_audio(self):
        # Run the streamlink command
        streamlink_process = subprocess.Popen(
            ['streamlink', f"twitch.tv/{os.environ['target_channel']}", 'audio_only', '--quiet', '--stdout', '--twitch-disable-ads', '--twitch-low-latency'],
            stdout=subprocess.PIPE)
        
        # Pipe the output to ffmpeg with 1 channel and 44100 sample rate for 8 seconds
        ffmpeg_process = subprocess.Popen(
            ['ffmpeg', '-i', 'pipe:0', '-ac', '1', '-ar', '44100', '-t', '8', '-f', 'wav', '-loglevel', 'panic', '-'],
            stdin=streamlink_process.stdout,
            stdout=subprocess.PIPE)
        
        # Read the output into a BytesIO object
        audio_bytes = io.BytesIO(ffmpeg_process.communicate()[0])

        # Close the processes
        streamlink_process.kill()
        ffmpeg_process.kill()

        # return the audio bytes
        return audio_bytes


    # Get the audio data from the file
    def get_audio_data(self, bytes: io.BytesIO):
        # Encode the audio data to base64
        base64_data = base64.b64encode(bytes.getvalue()).decode('utf-8')

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