import json
import dataclasses
import argparse

import whisper

from models import Config


def main():
    parser = argparse.ArgumentParser(description='Setup the bot.')
    parser.add_argument('--lite', action='store_true', help='Use as little resources as possible.')
    args = parser.parse_args()

    print("checking/downloading whisper model...")
    
    if args.lite:
        whisper.load_model("base.en")
    else:
        whisper.load_model("large")

    try:
        with open("config.json", "r", encoding='utf-8'):
            pass
    except FileNotFoundError:
        with open("config.json", "w", encoding='utf-8') as outfile:
            json.dump(dataclasses.asdict(Config()), outfile, indent=4)
        print("config.json created. ")

    print("Setup finished. Please fill out the config file before starting the bot.")


if __name__ == '__main__':
    main()
