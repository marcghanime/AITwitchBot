import os
import json
import logging
import threading
import websocket
import subprocess

from utils.ffmpeg_base import FfmpegBase
from utils.pubsub import PubSub, PubEvents


class TranscriptionServer(FfmpegBase):
    def __init__(self, pubsub: PubSub):
        super().__init__(pubsub)
        
        self.pubsub = pubsub
        self.stop_event = threading.Event()

        # TODO add keywords
        # TODO add transcript length limit
        self.transcript = []

        # subscribe to showtdown event
        self.pubsub.subscribe(PubEvents.SHUTDOWN, self.stop)    

        # Create the WebSocket client
        encoding = "linear16"
        sample_rate = 16000
        channels = 1
        model = "nova-2"
        self.ws_url = f"wss://api.deepgram.com/v1/listen?model={model}&encoding={encoding}&sample_rate={sample_rate}&channels={channels}&smart_format=true"
        extra_headers={"Authorization": f"Token {os.environ['deepgram_api_key']}"}
        self.ws = websocket.WebSocketApp(self.ws_url,
            header=extra_headers,
            on_open=lambda ws: self.on_open(ws),
            on_message=lambda ws, message: self.on_message(ws, message),
            on_error=lambda ws, error: self.on_error(ws, error),
            on_close=lambda ws, close_status_code, close_msg: self.on_close(ws, close_status_code, close_msg)
        )


    # Start transcibing the stream
    def start(self):
        # start websocket client in a thread
        self.ws_thread = threading.Thread(target=self.ws.run_forever)
        self.ws_thread.start()

        # Start the audio processing thread
        self.audio_processing_thread = threading.Thread(target=self.process_audio_frames)
        self.audio_processing_thread.start()

        logging.info("Running Transcription Server.")


    # Stop transcibing the stream
    def stop(self):
        self.stop_event.set()
        self.ws.send(json.dumps({"type": "CloseStream"}))
        self.ws.close()


    # Process the audio frames from the stream
    def process_audio_frames(self):
        try: 
            self.start_recording()

            # Pipe the output to ffmpeg
            self.ffmpeg_process = subprocess.Popen(
                ['ffmpeg', '-i', 'pipe:0', '-f', 's16le', '-acodec', 'pcm_s16le', '-ac', '1', '-ar', '16000', '-loglevel', 'panic', '-'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Process the stream
            logging.info("Processing stream...")
            while not self.stop_event.is_set():
                # Read the audio stream
                out_bytes = self.ffmpeg_process.stdout.read(4096 * 2)

                # Send the audio stream to the WebSocket server
                self.ws.send(out_bytes, websocket.ABNF.OPCODE_BINARY)

        except Exception as e:
            logging.error(f"Failed to process stream: {e}")

        finally:
            self.stop_recording()


    # Handle the opening of the WebSocket connection
    def on_open(self, ws):
        logging.debug("WebSocket connection opened.")


    # Receive data from the WebSocket server
    def on_message(self, ws, message):
        json_message = json.loads(message)

        # Get the data
        start = json_message.get("start")
        duration = json_message.get("duration")
        end = start + duration
        text = json_message['channel']['alternatives'][0]['transcript']

        # create a segment
        segment = {
            'start': "{:.3f}".format(start),
            'end': "{:.3f}".format(end),
            'text': text
        }

        # append the segment to the transcript
        self.transcript.append(segment)

        # publish the transcript
        self.pubsub.publish(PubEvents.TRANSCRIPT, self.transcript)


    # Handle errors
    def on_error(self, ws, error):
        logging.error(error)


    # Handle the closing of the WebSocket connection
    def on_close(self, ws, close_status_code, close_msg):
        logging.debug(f"WebSocket connection closed: {close_status_code} - {close_msg}")