import uuid
import logging
import threading
import subprocess

from utils.pubsub import PubSub, PubEvents

class FfmpegBase:
    pubsub: PubSub
    pubsub_id: uuid.UUID

    # Threading variables
    lock: threading.Lock
    ffmpeg_process: subprocess.Popen[bytes]

    logger = logging.getLogger("ffmpeg_base")

    def __init__(self, pubsub: PubSub):
        self.pubsub = pubsub

        # Threading variables
        self.lock = threading.Lock()
        self.ffmpeg_process: subprocess.Popen[bytes] = None

        # Subscribe to the shutdown event
        self.pubsub.subscribe(PubEvents.SHUTDOWN, self.shutdown)


    def shutdown(self):
        # Kill the ffmpeg process
        if self.ffmpeg_process is not None:
            self.ffmpeg_process.kill()


    # Get the bytes from the stream
    def get_bytes(self, in_bytes: bytes):
        try:
            # Check if the ffmpeg process is running
            if self.ffmpeg_process is None:
                return
            
            # write the bytes to the stdin
            self.ffmpeg_process.stdin.write(in_bytes)

        except BrokenPipeError as e:
            return
        except Exception as e:
            self.logger.error(f"[FFMPEG GET BYTES] {e}")


    # start receiving bytes from the stream
    def start_recording(self):
        # Acquire the lock
        self.lock.acquire()

        # Subscribe to the stream bytes event
        self.pubsub_id = self.pubsub.subscribe(PubEvents.STREAM_BYTES, self.get_bytes)

    # stop receiving bytes from the stream
    def stop_recording(self):
        # Close the process
        if self.ffmpeg_process is not None:
            self.ffmpeg_process.kill()
            self.ffmpeg_process = None

        # Unsubscribe from the stream bytes event
        self.pubsub.unsubscribe(PubEvents.STREAM_BYTES, self.pubsub_id)

        # Release the lock
        self.lock.release()