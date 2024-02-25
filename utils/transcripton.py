import numpy as np
import subprocess
import threading
import json
import websocket
import uuid
import time
import queue

from utils.models import Config

class TranscriptionClient:
    def __init__(
        self,
        config: Config,
        transcript_queue: queue.Queue,
        lang: str = None,
        model: str = "small",
    ):
        self.config = config

        # websocket variables
        self.uid = str(uuid.uuid4())
        self.last_response_recieved = None

        # whisper variables
        self.language = lang
        self.model = model

        # transcript variables
        self.transcript_queue = transcript_queue
        self.transcript = []

        # status variables
        self.recording = False
        self.waiting = False
        self.server_error = False
        self.ws_closed = False

        # thread variables
        self.stop_event = threading.Event()
        self.processing_thread: threading.Thread
            
    def connect(self):
        # initialize the websocket client
        socket_url = f"ws://localhost:9090"
        self.client_socket = websocket.WebSocketApp(
            socket_url,
            on_open=lambda ws: self.on_open(ws),
            on_message=lambda ws, message: self.on_message(ws, message),
            on_error=lambda ws, error: self.on_error(ws, error),
            on_close=lambda ws, close_status_code, close_msg: self.on_close(
                ws, close_status_code, close_msg
            ),
        )

        # start websocket client in a thread
        self.ws_thread = threading.Thread(target=self.client_socket.run_forever)
        self.ws_thread.setDaemon(True)
        self.ws_thread.start()

        # wait for server to be ready
        while not self.recording:
            if self.waiting or self.server_error or self.ws_closed:
                return False
        
        # successfully connected
        return True


    def start(self):
        # start processing the audio in a new thread
        self.processing_thread = threading.Thread(target=self.process_audio)
        self.processing_thread.start()


    def stop(self):
        self.stop_event.set()
        
        try:
            self.processing_thread.join()
        except Exception as e:
            pass
        
        self.close_websocket()


    def on_message(self, ws, message):
        self.last_response_recieved = time.time()
        message = json.loads(message)

        if self.uid != message.get("uid"):
            print("[ERROR]: invalid client uid")
            return

        if "status" in message.keys():
            if message["status"] == "WAIT":
                self.waiting = True
                print(
                    f"[INFO]:Server is full. Estimated wait time {round(message['message'])} minutes."
                )
            elif message["status"] == "ERROR":
                print(f"Message from Server: {message['message']}")
                self.server_error = True
            return

        if "message" in message.keys() and message["message"] == "DISCONNECT":
            print("[INFO]: Server overtime disconnected.")
            self.recording = False

        if "message" in message.keys() and message["message"] == "SERVER_READY":
            self.recording = True
            self.server_backend = message["backend"]
            print(f"[INFO]: Server Running with backend {self.server_backend}")
            return

        if "language" in message.keys():
            self.language = message.get("language")
            lang_prob = message.get("language_prob")
            print(
                f"[INFO]: Server detected language {self.language} with probability {lang_prob}"
            )
            return

        if "segments" not in message.keys():
            return

        message = message["segments"]
        text = []
        n_segments = len(message)

        if n_segments:
            for i, seg in enumerate(message):
                if text and text[-1] == seg["text"]:
                    # already got it
                    continue
                text.append(seg["text"])

                if i == n_segments-1: 
                    self.last_segment = seg
                elif self.server_backend == "faster_whisper":
                    if not len(self.transcript) or float(seg['start']) >= float(self.transcript[-1]['end']):
                        self.transcript.append(seg)
        
        self.transcript_queue.put(self.transcript)
        


    def on_error(self, ws, error):
        print(error)


    def on_close(self, ws, close_status_code, close_msg):
        self.ws_closed = True
        print(f"[INFO]: Websocket connection closed: {close_status_code}: {close_msg}")


    def on_open(self, ws):
        print("[INFO]: Opened connection")
        ws.send(
            json.dumps(
                {
                    "uid": self.uid,
                    "language": self.language,
                    "task": "transcribe",
                    "model": self.model,
                }
            )
        )

    @staticmethod
    def bytes_to_float_array(audio_bytes):
        raw_data = np.frombuffer(buffer=audio_bytes, dtype=np.int16)
        return raw_data.astype(np.float32) / 32768.0


    def send_packet_to_server(self, message):
        try:
            self.client_socket.send(message, websocket.ABNF.OPCODE_BINARY)
        except Exception as e:
            print(e)


    def close_websocket(self):
        try:
            self.client_socket.close()
        except Exception as e:
            print("[ERROR]: Error closing WebSocket:", e)

        try:
            self.ws_thread.join()
        except Exception as e:
            print("[ERROR:] Error joining WebSocket thread:", e)

        print("[INFO]: WebSocket closed.")



    def process_audio(self):
        print("[INFO]: Connecting to stream...")
        
        # Initialize the processes
        streamlink_process = None
        ffmpeg_process = None
        
        try:
            # Run the streamlink command
            streamlink_process = subprocess.Popen(
                ['streamlink', f'twitch.tv/{self.config.target_channel}', 'audio_only', '--quiet', '--stdout', '--twitch-disable-ads', '--twitch-low-latency'],
                stdout=subprocess.PIPE)
            
            # Pipe the output to ffmpeg
            ffmpeg_process = subprocess.Popen(
                ['ffmpeg', '-i', 'pipe:0', '-f', 's16le', '-acodec', 'pcm_s16le', '-ac', '1', '-ar', '16000', '-loglevel', 'panic', '-'],
                stdin=streamlink_process.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Process the stream
            print("[INFO]: Processing stream...")
            while not self.stop_event.is_set():
                # Read the audio stream
                in_bytes = ffmpeg_process.stdout.read(4096 * 2)  # 2 bytes per sample
                
                # If no bytes are read, break the loop
                if not in_bytes:
                    break

                # Convert the bytes to a float array
                audio_array = self.bytes_to_float_array(in_bytes)

                # Send the audio array to the server
                self.send_packet_to_server(audio_array.tobytes())

        except Exception as e:
            print(f"[ERROR]: Failed to connect to stream: {e}")

        finally:
            # Kill the processes
            print ("[INFO]: Killing processes...")
            if streamlink_process:
                streamlink_process.kill()
            
            if ffmpeg_process:
                ffmpeg_process.kill()

        print("[INFO] stream processing finished.")