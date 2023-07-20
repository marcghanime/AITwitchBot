import io, pyaudio, threading, string, re
import speech_recognition as sr
from datetime import datetime, timedelta
from queue import Queue
from tempfile import NamedTemporaryFile
from time import sleep
from faster_whisper import WhisperModel
from models import Config
from typing import Callable, List


RECORD_TIMOUT = 4
PHRASE_TIMEOUT = 2
SAMPLE_RATE = 48000
VIRTUAL_AUDIO_CABLE_NAME = 'CABLE Output (VB-Audio Virtual '

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
    transcription_queue1 = Queue()
    transcription_queue2 = Queue()
    config = Config
    verbal_mention_callback: Callable[[List[str]], None]
    detected_lines = []
    detected_lines_queue = Queue()
    translator = str.maketrans('', '', string.punctuation)

    audio_model: WhisperModel
    source: sr.Microphone

    def __init__(self, config: Config, verbal_mention_callback: Callable[[List[str]], None]):
        print("Initializing Audio API...")

        self.verbal_mention_callback = verbal_mention_callback
        self.config = config

        # Load the model.
        self.audio_model = WhisperModel("base.en", device="cpu", compute_type="int8")
        
        # Find the index of the virtual audio cable.
        dev_index = -1
        p = pyaudio.PyAudio()
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if (dev['name'] == VIRTUAL_AUDIO_CABLE_NAME and dev['hostApi'] == 0):
                dev_index = int(dev['index'])

        if dev_index == -1:
            print("Could not find Virtual Audio Cable Output! Please make sure it is installed and named correctly in AudioAPI.py as VIRTUAL_AUDIO_CABLE_NAME.")
            print("Here are your current audio devices:\n")
            for i in range(p.get_device_count()):
                dev = p.get_device_info_by_index(i)
                print(f"'{dev['name']}'")
            print("\nExiting...")
            exit()

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
                index = 0
                while not DATA_QUEUE.empty() and index < 2:
                    data = DATA_QUEUE.get()
                    self.last_sample += data
                    index += 1

                # Use AudioData to convert the raw data to wav data.
                audio_data = sr.AudioData(self.last_sample, self.source.SAMPLE_RATE, self.source.SAMPLE_WIDTH)
                wav_data = io.BytesIO(audio_data.get_wav_data())

                # Write wav data to the temporary file as bytes.
                with open(self.temp_file, 'w+b') as f:
                    f.write(wav_data.read())

                text = ""
                # Read the transcription.
                segments, _ = self.audio_model.transcribe(self.temp_file, beam_size=5)
                for segment in segments:
                    text += segment.text
                
                text = text.replace("fuck", "f***").replace("Fuck", "F***")

                # If we detected a pause between recordings, add a new item to our transcripion.
                # Otherwise edit the existing one.
                if phrase_complete:
                    self.transcription[-1] = self.remove_overlap(self.transcription[-1], text)
                    self.transcription.append(text)
                else:
                    self.transcription[-1] = text

                # keep only the last 20 sentences
                if len(self.transcription) > 30: self.transcription = self.transcription[-30:]

                if self.verbal_mention_detected(text):
                    self.verbal_mention_callback(self.transcription.copy())

                with self.transcription_queue1.mutex: self.transcription_queue1.queue.clear()
                self.transcription_queue1.put(self.transcription.copy())

                with self.transcription_queue2.mutex: self.transcription_queue2.queue.clear()
                self.transcription_queue2.put(self.transcription.copy())

                # Infinite loops are bad for processors, must sleep.
                sleep(0.1)

    # we need to do this since we keep the last second of the last recording in the new recording
    # this leeds to better results since the last word is not cut off
    def remove_overlap(self, first_string: str, second_string: str) -> str:
        overlap = None
        ends_with_dot: bool = first_string.endswith(".")
        ends_with_three_dots: bool = first_string.endswith("...")

        splitted_first_string = first_string.split()
        splitted_second_string = second_string.split()

        # remove the last word
        last_word = "" if len(splitted_first_string) == 0 else first_string.split()[-1]
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
        if not overlap and len(splitted_second_string) > 0 and splitted_second_string[0] != last_word: 
            first_string = f"{first_string} {last_word}"
        
        # remove trailing and starting whitespaces
        first_string = first_string.strip()

        # cleanup if ',' is remaining
        if first_string.endswith(","): first_string = first_string[:-1]
        
        return first_string
    
    
    def verbal_mention_detected(self, text: str):
        detected = False
        
        lines = text.splitlines()[:-2]
        previous_detected_lines = list(map(lambda line: line["line"], self.detected_lines))
        lines = filter(lambda line: line not in previous_detected_lines, lines)

        for line in lines:
            #remove punctuation
            stripped_line = line.translate(self.translator)
            found = next((word for word in self.config.detection_words if word in stripped_line.lower()), None)
            if found:
                # Replace the word with LibsGPT
                fixed_line = re.sub(r'\b{}\b'.format(found), self.config.bot_nickname, stripped_line, flags=re.IGNORECASE)
                # Add the line to the detected lines
                self.detected_lines.append({"line": line, "fixed_line": fixed_line, "responded": False})
                
                with self.detected_lines_queue.mutex: self.detected_lines_queue.queue.clear()
                self.detected_lines_queue.put(self.detected_lines.copy())
                detected = True
        
        return detected