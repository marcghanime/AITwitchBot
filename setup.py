import json
from models import Config
import dataclasses
import pyaudio
from faster_whisper import WhisperModel

def main():
    print("checking/downloading whisper model...")
    WhisperModel("base.en", device="cpu", compute_type="int8")

    try:
        with open("config.json", "r") as infile:
            pass
    except FileNotFoundError:
        with open ("config.json", "w") as outfile: json.dump(dataclasses.asdict(Config()), outfile, indent=4)
        print("config.json created. ")

    dev_index = -1
    p = pyaudio.PyAudio()
    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        if (dev['name'] == 'CABLE Output (VB-Audio Virtual' and dev['hostApi'] == 0):
            dev_index = int(dev['index'])
    
    if not dev_index == -1:
        print("WARNING: Virtual Audio Cable not found! Either install it or Change 'VIRTUAL_AUDIO_CABLE_NAME' in ChatAPI.py to the corresponding name in your system")

    print("Setup finished. Please fill out the config file before starting the bot.")

if __name__ == '__main__':
    main()