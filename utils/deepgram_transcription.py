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
        
        # Transcript
        self.transcript = []
        self.transcript_duration_limit = 300

        # subscribe to showtdown event
        self.pubsub.subscribe(PubEvents.SHUTDOWN, self.stop)    

        # Create the WebSocket client
        ws_url = self.create_ws_url()
        extra_headers={"Authorization": f"Token {os.environ['deepgram_api_key']}"}

        self.ws = websocket.WebSocketApp(ws_url,
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


    def create_ws_url(self):
        # Options
        encoding = "linear16"
        sample_rate = 16000
        channels = 1
        model = "nova-2"

        # Create the WebSocket URL
        ws_url = f"wss://api.deepgram.com/v1/listen?model={model}&encoding={encoding}&sample_rate={sample_rate}&channels={channels}&smart_format=true"
        
        # Add keywords
        keywords = [os.environ['bot_username'], os.environ['target_channel']]
        for keyword in keywords:
            ws_url += f"&keywords={keyword}"

        return ws_url


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
            'duration': "{:.3f}".format(duration),
            'text': text
        }

        # append the segment to the transcript
        self.transcript.append(segment)

        # calculate the duration of the transcript
        transcript_duration = sum([float(segment['duration']) for segment in self.transcript])

        # keep the last 5 minutes of the transcript
        while transcript_duration > self.transcript_duration_limit:
            self.transcript.pop(0)
            transcript_duration = sum([float(segment['duration']) for segment in self.transcript])

        # publish the transcript
        self.pubsub.publish(PubEvents.TRANSCRIPT, self.transcript)


    # Handle errors
    def on_error(self, ws, error):
        logging.error(error)


    # Handle the closing of the WebSocket connection
    def on_close(self, ws, close_status_code, close_msg):
        logging.debug(f"WebSocket connection closed: {close_status_code} - {close_msg}")