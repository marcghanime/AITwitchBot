import requests
import time
import base64

import soundcard as sc
import soundfile as sf
import numpy as np

from tempfile import NamedTemporaryFile
from pydub import AudioSegment
from models import Config


class ShazamAPI:
    config: Config

    def __init__(self, config: Config):
        self.config = config

    def detect_song(self):
        # record audio from the default speaker
        file = self.record_audio()
        
        # get audio data from the file
        base64_data = self.get_audio_data(file)
        
        # get the result from the shazam API
        song = self.get_shazam_result(base64_data)
        
        return song

    # Thread that records output audio from the default speaker.
    def record_audio(self):
        RECORD_TIMOUT = 8
        SAMPLE_RATE = 48000

        # Temp file used to save the audio data and then transcribe it.
        temp_file = NamedTemporaryFile(suffix=".wav").name

        speaker_id = str(sc.default_speaker().name)
        speaker_output = sc.get_microphone(speaker_id, include_loopback=True)
        data = []
        
        # Keep recording until we have enough valid data.
        while True:
            data = speaker_output.record(
                samplerate=SAMPLE_RATE, numframes=SAMPLE_RATE*RECORD_TIMOUT)

            # remove zeros arrays from the new data
            data = data[np.abs(data).max(axis=1) > 0]

            # If we have enough data, break out of the loop.
            if len(data) >= SAMPLE_RATE*RECORD_TIMOUT:
                # Push the data into the thread safe queue.
                # Save the audio data to a temp file.
                sf.write(file=temp_file, data=data, samplerate=SAMPLE_RATE)
                break

            # Check if defaut speaker has changed
            if speaker_id != str(sc.default_speaker().name):
                speaker_id = str(sc.default_speaker().name)
                speaker_output = sc.get_microphone(
                    speaker_id, include_loopback=True)

            # Sleep for a bit to prevent the thread from hogging the CPU.
            time.sleep(0.1)

        return temp_file

    # Get the audio data from the file
    def get_audio_data(self, file):
        audio = AudioSegment.from_file(file, format="wav")
       
        # Convert to mono, 44.1kHz sample rate, 16 bit sample width
        raw_audio = audio.set_channels(1).set_frame_rate(44100).set_sample_width(2).raw_data

        # Encode the audio data to base64
        base64_data = base64.b64encode(raw_audio)
        return base64_data

    # Get the result from the shazam API
    def get_shazam_result(self, base64_data):
        url = "https://shazam.p.rapidapi.com/songs/v2/detect"

        querystring = {"timezone":"America/Chicago","locale":"en-US"}

        payload = base64_data
        headers = {
            "content-type": "text/plain",
            "X-RapidAPI-Key": self.config.shazam_api_key,
            "X-RapidAPI-Host": "shazam.p.rapidapi.com"
        }

        # Send the request to the API
        response = requests.post(url, data=payload, headers=headers, params=querystring)

        # Check if the request was successful
        if response.status_code == 200:
            result = response.json()
            matches = result['matches']
            if len(matches) > 0:
                song = result['track']['share']['text']
                return song
            else:
                return "No matches found"
        else:
            return "Error"