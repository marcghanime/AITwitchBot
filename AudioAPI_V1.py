import pygetwindow, pyautogui, pytesseract, threading, time
from PIL import Image
from typing import List


class AudioAPI:
    # Audio context thread variables
    transcription = ['']
    SLEEP_TIME = 2.5

    def listen_to_audio(self, stop_event: threading.Event):
        path = "result.png"
        old_audio_context = []

        while not stop_event.is_set():
            titles = pygetwindow.getAllTitles()
            if "Live Caption" in titles:
                window = pygetwindow.getWindowsWithTitle("Live Caption")[0]
                left, top = window.topleft
                pyautogui.screenshot(path, region=(left + 20, top + 40, window.width - 40, window.height - 80))
                text: str = pytesseract.image_to_string(Image.open(path))
                
                new_audio_context = text.splitlines()
                self.transcription = self.merge_audio_context(new_audio_context, old_audio_context)
                
                if len(self.transcription) > 50: self.transcription = self.transcription[-50:]
                
            time.sleep(self.SLEEP_TIME)


    def merge_audio_context(self, new_context: List[str], old_context: List[str]):
        for line in new_context[:-1]:
            if line not in old_context:
                old_context.append(line)

        return old_context


    def get_transcription(self) -> List[str]:
        return self.transcription.copy()