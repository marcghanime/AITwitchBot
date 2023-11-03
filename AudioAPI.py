import threading
import string
import re
import time
from typing import Callable, List
from queue import Queue, Empty
from tempfile import NamedTemporaryFile

from faster_whisper import WhisperModel
import soundcard as sc
import soundfile as sf
import numpy as np

from models import Config


RECORD_TIMOUT = 4
SAMPLE_RATE = 48000


class AudioAPI:
    config = Config
    audio_model: WhisperModel

    # translator for removing punctuation
    no_punctuation = str.maketrans('', '', string.punctuation)

    # Variables for verbal mention detection
    detected_lines = []
    detected_lines_queue = Queue()

    # Thread variables
    stop_event = threading.Event()
    thread: threading.Thread
    data_queue = Queue()

    # Transcriptions
    transcription = ['']
    transcription_queue1 = Queue()
    transcription_queue2 = Queue()

    def __init__(self, config: Config):
        print("Initializing Audio API...")
        self.config = config

        # Load the model.
        self.audio_model = WhisperModel("medium.en", device="cuda", compute_type="float16")

        print("Audio API Initialized.")

    # Start the main thread.
    def start(self):
        self.thread = threading.Thread(target=self.listen_to_audio)
        self.thread.daemon = True
        self.thread.start()
        print("Audio API Started.")

    # Stop the main thread.
    def stop(self):
        self.stop_event.set()
        self.thread.join()
        print("Audio API Stopped.")

    # Thread that records output audio from the default speaker.
    def recording_thread(self):
        speaker_id = str(sc.default_speaker().name)
        speaker_output = sc.get_microphone(speaker_id, include_loopback=True)
        data = []

        # Keep recording until we have enough valid data.
        while not self.stop_event.is_set():
            data = speaker_output.record(
                samplerate=SAMPLE_RATE, numframes=SAMPLE_RATE*RECORD_TIMOUT)

            # remove zeros arrays from the new data
            data = data[np.abs(data).max(axis=1) > 0]

            # If we have enough data, break out of the loop.
            if len(data) >= SAMPLE_RATE*RECORD_TIMOUT:
                # Push the data into the thread safe queue.
                self.data_queue.put(data)
                data = []

            # Check if defaut speaker has changed
            if speaker_id != str(sc.default_speaker().name):
                speaker_id = str(sc.default_speaker().name)
                speaker_output = sc.get_microphone(
                    speaker_id, include_loopback=True)

            # Sleep for a bit to prevent the thread from hogging the CPU.
            time.sleep(0.1)


    def listen_to_audio(self):
        # Start the recording thread.
        recording_thread = threading.Thread(target=self.recording_thread)
        recording_thread.start()

        # initate sample with an empty 2 dimentional array
        sample = np.empty((0, 2))

        # Temp file used to save the audio data and then transcribe it.
        temp_file = NamedTemporaryFile(suffix=".wav").name

        while not self.stop_event.is_set():
            # Get the data from the thread safe queue.
            try:
                data = self.data_queue.get(timeout=5)
            except Empty:
                self.put_transcription()
                continue

            # keep the last second of the last recording
            sample = sample[-SAMPLE_RATE:]
            sample = np.concatenate((sample, data))

            # Save the audio data to a temp file.
            sf.write(file=temp_file, data=sample, samplerate=SAMPLE_RATE)

            # Transcribe the audio data.
            text = ""
            segments, _ = self.audio_model.transcribe(
                temp_file, without_timestamps=True)
            for segment in segments:
                text += segment.text

            # TODO add seperate function for censoring
            text = text.replace("fuck", "f***").replace("Fuck", "F***")

            # Update the transcription
            self.transcription[-1] = self.remove_overlap(
                self.transcription[-1], text)
            self.transcription.append(text.strip())

            # keep only the last 20 sentences
            if len(self.transcription) > 20:
                self.transcription = self.transcription[-20:]

            # check if the bot was mentioned verbally
            if self.detect_verbal_mention():
                self.verbal_mention_callback(self.transcription.copy())

            self.put_transcription()
        # Join the recording thread after the while loop is stopped.
        recording_thread.join()

    # we need to do this since we keep the last second of the last recording in the new recording
    # this leeds to better results since the last word is not cut off

    def remove_overlap(self, first_string: str, second_string: str) -> str:
        overlap = None

        # split the strings into words
        splitted_first_string = first_string.split()
        splitted_second_string = second_string.split()

        # remove the last word from the first string
        last_word = "" if len(
            splitted_first_string) == 0 else splitted_first_string[-1]
        first_string = " ".join(splitted_first_string[:-1]).strip()
        splitted_first_string = first_string.split()

        # the first string with the last word removed
        end = first_string.lower()
        end_stripped = end.translate(self.no_punctuation)

        # find overlap
        for i in range(len(second_string)):
            start = second_string.lower()[:i]
            start_stripped = start.translate(self.no_punctuation)

            if end_stripped.endswith(start_stripped):
                overlap = i

        # remove the overlap
        for word in splitted_first_string[::-1]:
            if overlap and overlap >= len(word):
                splitted_first_string.pop()
                overlap -= len(word) + 1  # +1 for the space
            else:
                first_string = " ".join(splitted_first_string).strip()
                break

        # if no overlap and the last word isn't in second_string, add it back to first_string
        read_last_word = len(splitted_second_string) > 0 and splitted_second_string[0] != last_word
        if overlap is None and read_last_word:
            first_string = f"{first_string} {last_word}"

        # remove trailing and starting whitespaces
        first_string = first_string.strip()

        # cleanup if ',' is remaining
        if first_string.endswith(","):
            first_string = first_string[:-1]

        return first_string
    

    def put_transcription(self):
        # put the data in the queues for the other APIs to access
        with self.transcription_queue1.mutex:
            self.transcription_queue1.queue.clear()
        self.transcription_queue1.put(self.transcription.copy())

        with self.transcription_queue2.mutex:
            self.transcription_queue2.queue.clear()
        self.transcription_queue2.put(self.transcription.copy())


    def detect_verbal_mention(self):
        detected = False

        # remove the last 2 lines to give time to make sure the sentences are completed
        lines = self.transcription.copy()[:-2]

        # remove the lines that have already been detected
        previous_detected_lines = list(
            map(lambda line: line["line"], self.detected_lines))
        lines = filter(lambda line: line not in previous_detected_lines, lines)

        for line in lines:
            # remove punctuation
            stripped_line = line.translate(self.no_punctuation)

            # check if any of the detection words are in the line
            found = next(
                (word for word in self.config.detection_words if word in stripped_line.lower()), None)

            if found:
                # Replace the word with bot's name
                fixed_line = re.sub(r'\b{}\b'.format(
                    found), self.config.bot_username, stripped_line, flags=re.IGNORECASE)

                # Add the line to the detected lines
                self.detected_lines.append(
                    {"line": line, "fixed_line": fixed_line, "responded": False})

                # put the data in the queue for the other APIs to access
                with self.detected_lines_queue.mutex:
                    self.detected_lines_queue.queue.clear()
                self.detected_lines_queue.put(self.detected_lines.copy())
                detected = True

        return detected

    def set_verbal_mention_callback(self, callback: Callable[[List[str]], None]):
        self.verbal_mention_callback = callback