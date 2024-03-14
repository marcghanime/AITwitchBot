import os
import logging
import threading
import subprocess

from utils.pubsub import PubSub, PubEvents

class Stream:
    pubsub: PubSub

    # Threading variables
    processing_thread: threading.Thread
    stop_event: threading.Event

    def __init__(self, pubsub: PubSub):
        self.pubsub = pubsub
        self.stop_event = threading.Event()
        self.recording = threading.Event()
        
        # Subscribe to the shutdown event
        self.pubsub.subscribe(PubEvents.SHUTDOWN, self.stop)


    # Start reading the stream
    def start(self):
        # Start the processing thread
        self.processing_thread = threading.Thread(target=self.process)
        self.processing_thread.start()


    # Stop reading the stream    
    def stop(self):
        self.stop_event.set()


    # Process the stream
    def process(self):
        logging.info("Connecting to stream...")

        streamlink_process: subprocess.Popen[bytes]
        
        try:
            # Run the streamlink command
            streamlink_process = subprocess.Popen(
                ['streamlink', f"twitch.tv/{os.environ['target_channel']}", '480p', '--quiet', '--stdout', '--twitch-disable-ads', '--twitch-low-latency'],
                stdout=subprocess.PIPE)

            # Process the stream
            logging.info("Reading stream...")

            while not self.stop_event.is_set():
                # Read the stream data
                out_bytes = streamlink_process.stdout.read(4096 * 2)  # 2 bytes per sample
                
                # If no bytes are read, break the loop
                if not out_bytes:
                    break

                # Publish the bytes
                self.pubsub.publish(PubEvents.STREAM_BYTES, out_bytes)
                
        except Exception as e:
            # Log the error
            logging.error(f"Failed to connect to stream: {e}")

        finally:
            # Kill the streamlink process
            if streamlink_process:
                streamlink_process.kill()

        logging.info("Stream processing finished.")

        # if stop event is not set, send a shutdown event
        if not self.stop_event.is_set():
            self.pubsub.publish(PubEvents.SHUTDOWN)