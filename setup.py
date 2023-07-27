import json
from models import Config
import dataclasses
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

    print("Setup finished. Please fill out the config file before starting the bot.")

if __name__ == '__main__':
    main()