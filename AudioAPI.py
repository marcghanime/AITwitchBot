import pygetwindow, pyautogui, pytesseract, threading, time, os
from PIL import Image
from typing import List


class AudioAPI:
    # Audio context thread variables
    audio_context: List[str] = []
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
                audio_context = self.merge_audio_context(new_audio_context, old_audio_context)
                
                if len(audio_context) > 50: audio_context = audio_context[-50:]
                
                time.sleep(self.SLEEP_TIME)


    def merge_audio_context(self, new_context: List[str], old_context: List[str]):
        for line in new_context[:-1]:
            if line not in old_context:
                old_context.append(line)

        return old_context


    def get_audio_context(self) -> List[str]:
        return self.audio_context