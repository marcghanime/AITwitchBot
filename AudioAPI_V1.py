import pygetwindow, pyautogui, pytesseract, threading
from typing import List, Callable
import string, re
from models import Config


class AudioAPI:
    # Audio context thread variables
    transcription = ['']
    config = Config
    detected_lines = []
    translator = str.maketrans('', '', string.punctuation)
    verbal_mention_callback: Callable[[], None]

    def __init__(self, config: Config, verbal_mention_callback: Callable[[], None]):
        self.verbal_mention_callback = verbal_mention_callback
        self.config = config


    def listen_to_audio(self, stop_event: threading.Event):
        old_audio_context = []

        while not stop_event.is_set():
            titles = pygetwindow.getAllTitles()
            if "Live Caption" in titles:
                window = pygetwindow.getWindowsWithTitle("Live Caption")[0]
                left, top = window.topleft
                img = pyautogui.screenshot(region=(left + 20, top + 40, window.width - 40, window.height - 80))
                text: str = pytesseract.image_to_string(img)
                
                new_audio_context = text.splitlines()
                self.transcription = self.merge_audio_context(new_audio_context, old_audio_context)
                
                if len(self.transcription) > 50: self.transcription = self.transcription[-50:]

                if self.verbal_mention_detected(text):
                    self.verbal_mention_callback()


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
                detected = True
        
        return detected


    def merge_audio_context(self, new_context: List[str], old_context: List[str]):
        for line in new_context[:-1]:
            if line not in old_context:
                old_context.append(line)

        return old_context


    def get_detected_lines(self):
        return self.detected_lines.copy()


    def get_transcription(self) -> List[str]:
        return self.transcription.copy()