import numpy as np
import sounddevice as sd
import threading, queue

class StreamingTTSPlayer:
    def __init__(self):
        self._stop_flag = threading.Event()
        self._queue = queue.Queue()
        self._thread = None

    async def play_pcm_stream(self, response):
        self._stop_flag.clear()
        while not self._queue.empty():
            self._queue.get_nowait()

        self._thread = threading.Thread(target=self._audio_consumer_thread, daemon=True)
        self._thread.start()

        async for chunk in response.iter_bytes():
            if self._stop_flag.is_set():
                break
            self._queue.put(chunk)

        self._queue.put(None)

    def _audio_consumer_thread(self):
        buffer_accumulator = b""
        with sd.OutputStream(samplerate=24000, channels=1, dtype="float32") as stream:
            while not self._stop_flag.is_set():
                chunk = self._queue.get()
                if chunk is None:
                    break

                buffer_accumulator += chunk
                process_len = len(buffer_accumulator) // 2 * 2
                if process_len == 0:
                    continue

                aligned = buffer_accumulator[:process_len]
                buffer_accumulator = buffer_accumulator[process_len:]

                audio_data = np.frombuffer(aligned, dtype=np.int16).astype(np.float32) / 32768.0
                if len(audio_data) > 0:
                    stream.write(audio_data)

    def stop(self):
        self._stop_flag.set()
        self._queue.put(None)
        sd.stop()
