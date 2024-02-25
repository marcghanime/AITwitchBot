import threading

from queue import Queue
from utils.models import Config
from utils.transcripton import TranscriptionClient
from utils.pubsub import PubSub, PubEvents

class AudioAPI:
    config = Config
    pubsub = PubSub
    client = TranscriptionClient

    # Transcription variables
    transcript_queue = Queue()

    # thread variables
    stop_event = threading.Event()
    read_transcript_thread: threading.Thread


    def __init__(self, config: Config, pubsub: PubSub):
        self.config = config
        self.pubsub = pubsub

        # Subscribe to the shutdown event
        self.pubsub.subscribe(PubEvents.SHUTDOWN, self.stop)


    def start(self):
        # Initialize the Whisper transcription client
        self.client = TranscriptionClient(self.config, self.transcript_queue, lang="en")

        # Connect the client to the backend
        success = self.client.connect()

        # If the connection was not successful, send a shutdown event
        if not success:
            print("[ERROR]: Failed to connect to the transcription server")
            self.pubsub.publish(PubEvents.SHUTDOWN)
            return
        
        # Start the client
        self.client.start()

        # Start the read_transcript thread
        self.read_transcript_thread = threading.Thread(target=self.read_transcript)
        self.read_transcript_thread.start()


    # Stop the client and the read_transcript thread
    def stop(self):
        self.client.stop()
        self.stop_event.set()

        try:
            self.read_transcript_thread.join()
        except:
            pass


    # Read the transcript from the queue
    def read_transcript(self):
        while not self.stop_event.is_set():
            # Get the transcript from the queue
            try: 
                transcript = self.transcript_queue.get(timeout=1)
            except:
                continue

            # keep the last entries of duplicates with the same start
            transcript = list({v['start']:v for v in transcript}.values())

            # Publish the transcript
            self.pubsub.publish(PubEvents.TRANSCRIPT, transcript)
