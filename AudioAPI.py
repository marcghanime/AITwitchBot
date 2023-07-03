import io, whisper, torch, pyaudio, threading
import speech_recognition as sr
from datetime import datetime, timedelta
from queue import Queue
from tempfile import NamedTemporaryFile
from time import sleep                


RECORD_TIMOUT = 5
PHRASE_TIMEOUT = 2.5
SAMPLE_RATE = 48000
VIRTUAL_AUDIO_CABLE_NAME = 'CABLE Output (VB-Audio Virtual'

# Thread safe Queue for passing data from the threaded recording callback.
DATA_QUEUE = Queue()

def record_callback(_, audio:sr.AudioData) -> None:
    """
    Threaded callback function to recieve audio data when recordings finish.
    audio: An AudioData containing the recorded bytes.
    """
    # Grab the raw bytes and push it into the thread safe queue.
    data = audio.get_raw_data()
    DATA_QUEUE.put(data)

class AudioAPI:
    # The last time a recording was retreived from the queue.
    phrase_time = None
    # Current raw audio bytes.
    last_sample = bytes()

    # We use SpeechRecognizer to record our audio because it has a nice feauture where it can detect when speech ends.
    recorder = sr.Recognizer()
    recorder.energy_threshold = 500
    # Definitely do this, dynamic energy compensation lowers the energy threshold dramtically to a point where the SpeechRecognizer never stops recording.
    recorder.dynamic_energy_threshold = False
    
    temp_file = NamedTemporaryFile().name
    transcription = ['']

    audio_model: whisper.Whisper
    source: sr.Microphone

    def __init__(self):
        print("Initializing Audio API...")

        # Load the model.    
        self.audio_model = whisper.load_model("small.en")
        
        # Find the index of the virtual audio cable.
        dev_index = 0
        p = pyaudio.PyAudio()
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if (dev['name'] == VIRTUAL_AUDIO_CABLE_NAME and dev['hostApi'] == 0):
                dev_index = int(dev['index'])

        # Create a background thread that will pass us raw audio bytes.
        # We could do this manually but SpeechRecognizer provides a nice helper.
        self.source = sr.Microphone(device_index=dev_index, sample_rate=SAMPLE_RATE)
        print("Audio API Initialized.")


    def listen_to_audio(self, stop_event: threading.Event):
        self.recorder.listen_in_background(self.source, record_callback, phrase_time_limit=RECORD_TIMOUT)

        while not stop_event.is_set():
            now = datetime.utcnow()
            
            # Pull raw recorded audio from the queue.
            if not DATA_QUEUE.empty():
                phrase_complete = False
                
                # If enough time has passed between recordings, consider the phrase complete.
                # Clear the current working audio buffer to start over with the new data. Keep the last second of audio.
                if self.phrase_time and now - self.phrase_time > timedelta(seconds=PHRASE_TIMEOUT):
                    self.last_sample = self.last_sample[-self.source.SAMPLE_RATE:]
                    phrase_complete = True

                # This is the last time we received new audio data from the queue.
                self.phrase_time = now

                # Concatenate our current audio data with the latest audio data.
                while not DATA_QUEUE.empty():
                    data = DATA_QUEUE.get()
                    self.last_sample += data

                # Use AudioData to convert the raw data to wav data.
                audio_data = sr.AudioData(self.last_sample, self.source.SAMPLE_RATE, self.source.SAMPLE_WIDTH)
                wav_data = io.BytesIO(audio_data.get_wav_data())

                # Write wav data to the temporary file as bytes.
                with open(self.temp_file, 'w+b') as f:
                    f.write(wav_data.read())

                # Read the transcription.
                result = self.audio_model.transcribe(self.temp_file, fp16=torch.cuda.is_available())
                text = str(result['text']).strip()

                # If we detected a pause between recordings, add a new item to our transcripion.
                # Otherwise edit the existing one.
                if phrase_complete:
                    self.transcription[-1] = self.remove_overlap(self.transcription[-1], text)
                    self.transcription.append(text)
                else:
                    self.transcription[-1] = text

                # keep only the last 20 sentences
                if len(self.transcription) > 20: self.transcription[-20:]

                # Infinite loops are bad for processors, must sleep.
                sleep(0.25)

    # we need to do this since we keep the last second of the last recording in the new recording
    # this leeds to better results since the last word is not cut off
    def remove_overlap(self, first_string: str, second_string: str) -> str:
        overlap = None
        ends_with_dot: bool = first_string.endswith(".")
        ends_with_three_dots: bool = first_string.endswith("...")

        # remove the last word
        last_word = first_string.split()[-1]
        first_string = " ".join(first_string.split()[:-1]).strip()

        first_string_lower = first_string.lower()
        second_string_lower = second_string.lower()

        if ends_with_dot: first_string_lower = first_string_lower[:-1]

        if ends_with_three_dots: first_string_lower = first_string_lower[:-3]

        # find overlap
        for i in range(len(second_string)):
            if first_string_lower.endswith(second_string_lower[:i]):
                overlap = second_string_lower[:i]

        # remove dot if overlap
        if overlap and ends_with_dot: first_string = first_string[:-1]

        # remove three dots    
        if overlap and ends_with_three_dots: first_string = first_string[:-3]

        # remove the overlap
        if overlap: first_string = first_string[:-len(overlap)]

        # if no overlap and the last word isn't in second_string, add it back to first_string
        if not overlap and second_string.split()[0] != last_word: 
            first_string = f"{first_string} {last_word}"
        
        # remove trailing and starting whitespaces
        first_string = first_string.strip()

        # cleanup if ',' is remaining
        if first_string.endswith(","): first_string = first_string[:-1]
        
        return first_string