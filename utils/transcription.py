import os
import time
import threading
import logging
import subprocess
import numpy as np

from whisper_live.transcriber import WhisperModel
from faster_whisper.transcribe import TranscriptionInfo, Segment, Iterable

from utils.pubsub import PubSub, PubEvents


logging.basicConfig(level=logging.ERROR)


class TranscriptionServer:
    def __init__(self, pubsub: PubSub, language: str, model: str):
        self.pubsub = pubsub

        self.stop_event = threading.Event()

        # subscribe to showtdown event
        self.pubsub.subscribe(PubEvents.SHUTDOWN, self.stop)

        # Start the transcription server
        self.client = ServeClientFasterWhisper(
            pubsub=pubsub,
            language=language,
            model=model,
        )

        logging.info("Running Transcription Server.")

        self.client.start()

        # Start the audio processing thread
        self.audio_processing_thread = threading.Thread(target=self.process_audio_frames)
        self.audio_processing_thread.start()
    

    @staticmethod
    def bytes_to_float_array(audio_bytes):
        raw_data = np.frombuffer(buffer=audio_bytes, dtype=np.int16)
        return raw_data.astype(np.float32) / 32768.0


    # Process the audio frames from the stream
    def process_audio_frames(self):
        logging.info("Connecting to stream...")

        streamlink_process: subprocess.Popen[bytes]
        ffmpeg_process: subprocess.Popen[bytes]
        
        try:
            # Run the streamlink command
            streamlink_process = subprocess.Popen(
                ['streamlink', f"twitch.tv/{os.environ['target_channel']}", 'audio_only', '--quiet', '--stdout', '--twitch-disable-ads', '--twitch-low-latency'],
                stdout=subprocess.PIPE)
            
            # Pipe the output to ffmpeg
            ffmpeg_process = subprocess.Popen(
                ['ffmpeg', '-i', 'pipe:0', '-f', 's16le', '-acodec', 'pcm_s16le', '-ac', '1', '-ar', '16000', '-loglevel', 'panic', '-'],
                stdin=streamlink_process.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Process the stream
            logging.info("Processing stream...")
            while not self.stop_event.is_set():
                # Read the audio stream
                in_bytes = ffmpeg_process.stdout.read(4096 * 2)  # 2 bytes per sample
                
                # If no bytes are read, break the loop
                if not in_bytes:
                    break

                # Convert the bytes to a float array
                audio_array = self.bytes_to_float_array(in_bytes)

                # Send the audio array to the server
                self.client.add_frames(audio_array)

        except Exception as e:
            logging.error(f"Failed to connect to stream: {e}")

        finally:
            # Kill the processes
            logging.info("Killing processes...")
            if streamlink_process:
                streamlink_process.kill()
            
            if ffmpeg_process:
                ffmpeg_process.kill()

        logging.info("Stream processing finished.")

        # if stop event is not set, send a shutdown event
        if not self.stop_event.is_set():
            self.pubsub.publish(PubEvents.SHUTDOWN)


    def stop(self):
        self.stop_event.set()
        self.client.stop()


class ServeClientFasterWhisper():
    def __init__(self, pubsub: PubSub, language: str = None, model: str = "small.en"):
        # variables
        self.RATE = 16000
        self.frames = b""
        self.timestamp_offset = 0.0
        self.frames_np = None
        self.frames_offset = 0.0
        self.text = []
        self.current_out = ''
        self.prev_out = ''
        self.t_start = None
        self.same_output_threshold = 0
        self.show_prev_out_thresh = 5   # if pause(no output from whisper) show previous output for 5 seconds
        self.add_pause_thresh = 3       # add a blank to segment list as a pause(no speech) for 3 seconds
        self.transcript = []
        self.send_last_n_segments = 10

        # threading
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.resume_event = threading.Event()

        # Available whisper model sizes
        self.model_sizes = [
            "tiny", "tiny.en", "base", "base.en", "small", "small.en",
            "medium", "medium.en", "large-v2", "large-v3",
        ]

        self.pubsub = pubsub

        # subscribe to pubsub events
        self.pubsub.subscribe(PubEvents.PAUSE_TRANSCRIPTION, self.pause)
        self.pubsub.subscribe(PubEvents.RESUME_TRANSCRIPTION, self.resume)

        # Check if the model is valid
        if model not in self.model_sizes and not os.path.exists(model):
            return
        
        # Setup parameters
        self.language = "en" if model.endswith("en") else language
        self.no_speech_thresh = 0.45

        # Initialize the transcriber
        self.transcriber = WhisperModel(
            model_size_or_path=model,
            device="cpu",
            compute_type="int8",
            local_files_only=False,
        )


    # Start the transcription thread.
    def start(self):
        self.transcription_thread = threading.Thread(target=self.speech_to_text)
        self.transcription_thread.start()
        self.resume_event.set()


    # Pause the transciption thread.
    def pause(self):
        self.resume_event.clear()


    # Resume the transcription thread.
    def resume(self):
        self.resume_event.set()


    # Stop the transcription thread.
    def stop(self):
        self.stop_event.set()
        self.transcription_thread.join()


    # Add audio frames to the ongoing audio stream buffer.
    def add_frames(self, frame_np: np.ndarray, max_buffer_seconds: int = 45):
        self.lock.acquire()

        # Check if the buffer size exceeds the threshold
        if self.frames_np is not None and self.frames_np.shape[0] > max_buffer_seconds*self.RATE:
            # Discard the oldest 30 seconds of audio data
            self.frames_offset += 30.0
            self.frames_np = self.frames_np[int(30*self.RATE):]
        
        # Initialize the buffer with the provided audio frame
        if self.frames_np is None:
            self.frames_np = frame_np.copy()
        
        # Append the audio frame to the buffer
        else:
            self.frames_np = np.concatenate((self.frames_np, frame_np), axis=0)

        self.lock.release()


    # Update the timestamp offset based on audio buffer status.
    def clip_audio_if_no_valid_segment(self):
        # Clip audio if the current chunk exceeds 30 seconds, this basically implies that
        # no valid segment for the last 30 seconds from whisper
        
        if self.frames_np[int((self.timestamp_offset - self.frames_offset)*self.RATE):].shape[0] > 25 * self.RATE:
            duration = self.frames_np.shape[0] / self.RATE
            self.timestamp_offset = self.frames_offset + duration - 5


    # Retrieves the next chunk of audio data for processing based on the current offsets.
    def get_audio_chunk_for_processing(self):

        # calculate the number of samples to take based on the difference between the current timestamp offset and the frame's offset
        samples_take = max(0, (self.timestamp_offset - self.frames_offset) * self.RATE)
        
        # retrieve the next chunk of audio data for processing
        input_bytes: np.ndarray = self.frames_np[int(samples_take):].copy()

        # calculate the duration of the audio chunk
        duration: float = input_bytes.shape[0] / self.RATE

        return input_bytes, duration


    # Prepares the segments of transcribed text to be sent to be published.
    def prepare_segments(self, last_segment=None) -> list:
        segments = []

        # if the number of segments is greater than the specified threshold, only include the last n segments
        if len(self.transcript) >= self.send_last_n_segments:
            segments = self.transcript[-self.send_last_n_segments:].copy()
        else:
            segments = self.transcript.copy()
        
        # add the last segment if provided
        if last_segment is not None:
            segments = segments + [last_segment]

        return segments
    

    # Updates the language attribute based on the detected language information.
    def set_language(self, info: TranscriptionInfo):
        if info.language_probability > 0.5:
            self.language = info.language
            logging.info(f"Detected language {self.language} with probability {info.language_probability}")


    # Transcribes the provided audio sample using the configured transcriber instance.
    def transcribe_audio(self, input_sample):

        # Transcribe the audio chunk
        result, info = self.transcriber.transcribe(
            input_sample,
            language=self.language,
            vad_filter=True,
            vad_parameters={"threshold": 0.5}
        )
        
        # update the language if it is not set
        if self.language is None:
            self.set_language(info)
        
        return result


    # Retrieves previously generated transcription outputs if no new transcription is available from the current audio chunks.
    def get_previous_output(self) -> list:
        segments = []

        # initialize the start time if it is not set
        if self.t_start is None:
            self.t_start = time.time()
        
        # if the time since the last output is within the threshold, show the previous output
        if time.time() - self.t_start < self.show_prev_out_thresh:
            segments = self.prepare_segments()

        # add a blank if there is no speech for the specified duration
        if len(self.text) and self.text[-1] != '':
            if time.time() - self.t_start > self.add_pause_thresh:
                self.text.append('')

        return segments


    # Handle the transcription output, updating the transcript and sending data to the client.
    def handle_transcription_output(self, result: Iterable[Segment], duration: float):
        segments = []

        # if there is output from whisper
        if len(result):
            self.t_start = None
            last_segment = self.update_segments(result, duration)
            segments = self.prepare_segments(last_segment)
        
        # show previous output if there is pause i.e. no output from whisper
        else:
            segments = self.get_previous_output()

        # send the segments to the client
        self.pubsub.publish(PubEvents.TRANSCRIPT, segments)
    

    # Process an audio stream in an infinite loop, continuously transcribing the speech.
    def speech_to_text(self):

        # loop until the stop event is set
        while not self.stop_event.is_set():            
            # if there are no frames to process, continue
            if self.frames_np is None:
                continue
            
            # if the resume event is not set, wait
            if not self.resume_event.is_set():
                self.resume_event.wait()

            self.clip_audio_if_no_valid_segment()

            # get the next chunk of audio data for processing
            input_bytes, duration = self.get_audio_chunk_for_processing()

            # if the duration of the audio chunk is less than 1 second, continue
            if duration < 1.0:
                continue

            try:
                # transcribe the audio chunk
                input_sample = input_bytes.copy()
                result = self.transcribe_audio(input_sample)

                # if the language is not set, continue until it is detected
                if self.language is None:
                    continue

                # handle the transcription output
                self.handle_transcription_output(result, duration)

            except Exception as e:
                logging.error(f"[ERROR]: Failed to transcribe audio chunk: {e}")
                time.sleep(0.01)

            # Sleep to avoid high CPU usage
            time.sleep(5)

        logging.info("[INFO]: Exiting speech to text thread")

    
    # Formats a transcription segment with precise start and end times alongside the transcribed text.
    def format_segment(self, start: float, end: float, text: str) -> dict:
        return {
            'start': "{:.3f}".format(start),
            'end': "{:.3f}".format(end),
            'text': text
        }


    # Processes the segments from whisper. Appends all the segments to the list except for the last segment assuming that it is incomplete.
    def update_segments(self, segments: Iterable[Segment], duration: float) -> dict | None:
        offset = None
        self.current_out = ''
        last_segment = None

        # process complete segments
        if len(segments) > 1:
            # process all segments except the last one
            for i, s in enumerate(segments[:-1]):
                segment: Segment = s
                
                # add the segment text to the list
                text = segment.text
                self.text.append(text)

                # get the start and end times for the segment
                start, end = self.timestamp_offset + segment.start, self.timestamp_offset + min(duration, segment.end)

                # if the start time is greater than or equal to the end time, skip
                if start >= end:
                    continue

                # if the segment has no speech, skip
                if segment.no_speech_prob > self.no_speech_thresh:
                    continue
                
                # add the segment to the transcript
                self.transcript.append(self.format_segment(start, end, text))
                
                # update the offset
                offset = min(duration, segment.end)

        # process the last segment
        self.current_out += segments[-1].text
        last_segment = self.format_segment(
            self.timestamp_offset + segments[-1].start,
            self.timestamp_offset + min(duration, segments[-1].end),
            self.current_out
        )

        # check if the current incomplete segment is the same as the previous one
        if self.current_out.strip() == self.prev_out.strip() and self.current_out != '':
            self.same_output_threshold += 1
        else:
            self.same_output_threshold = 0

        # if same incomplete segment is seen multiple times then update the offset and append the segment to the list
        if self.same_output_threshold > 5:

            # add the segment to the transcript
            if not len(self.text) or self.text[-1].strip().lower() != self.current_out.strip().lower():
                self.text.append(self.current_out)
                self.transcript.append(self.format_segment(
                    self.timestamp_offset,
                    self.timestamp_offset + duration,
                    self.current_out
                ))

            # reset variables    
            self.current_out = ''
            offset = duration
            self.same_output_threshold = 0
            last_segment = None
        
        # update the previous output
        else:
            self.prev_out = self.current_out

        # update offset
        if offset is not None:
            self.timestamp_offset += offset

        return last_segment
