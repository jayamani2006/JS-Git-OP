"""
engine.py
Captures loopback audio from VB-Cable Output and fans it out, in real
time, to N physical playback devices simultaneously — each with its
own independent gain and on/off state.
"""

import threading
import queue
import numpy as np
import sounddevice as sd

BLOCK_SIZE = 1024
CHANNELS = 2


class OutputBranch:
    """One physical output device: its own stream, gain, and buffer."""

    def __init__(self, device_id: int, samplerate: int, name: str = ""):
        self.device_id = device_id
        self.name = name
        self.samplerate = samplerate
        self.gain = 1.0
        self.enabled = True
        self.buf = queue.Queue(maxsize=50)
        self.stream = sd.OutputStream(
            device=device_id,
            samplerate=samplerate,
            channels=CHANNELS,
            blocksize=BLOCK_SIZE,
            callback=self._callback,
        )

    def _callback(self, outdata, frames, time_info, status):
        try:
            data = self.buf.get_nowait()
        except queue.Empty:
            outdata.fill(0)
            return
        if not self.enabled:
            outdata.fill(0)
            return
        outdata[:] = data * self.gain

    def push(self, frame: np.ndarray):
        if self.buf.full():
            try:
                self.buf.get_nowait()  # drop oldest to stay real-time
            except queue.Empty:
                pass
        self.buf.put_nowait(frame)

    def start(self):
        self.stream.start()

    def stop(self):
        self.stream.stop()
        self.stream.close()


class RouterEngine:
    """Captures VB-Cable loopback and fans out to all registered branches."""

    def __init__(self, cable_output_id: int, samplerate: int = 48000):
        self.cable_output_id = cable_output_id
        self.samplerate = samplerate
        self.branches: dict[int, OutputBranch] = {}
        self._capture_stream = None
        self._lock = threading.Lock()

    def add_branch(self, device_id: int, name: str = ""):
        with self._lock:
            if device_id in self.branches:
                return
            branch = OutputBranch(device_id, self.samplerate, name)
            branch.start()
            self.branches[device_id] = branch

    def remove_branch(self, device_id: int):
        with self._lock:
            b = self.branches.pop(device_id, None)
            if b:
                b.stop()

    def set_gain(self, device_id: int, gain: float):
        if device_id in self.branches:
            self.branches[device_id].gain = gain

    def set_enabled(self, device_id: int, enabled: bool):
        if device_id in self.branches:
            self.branches[device_id].enabled = enabled

    def _capture_callback(self, indata, frames, time_info, status):
        frame = indata.copy()
        with self._lock:
            for branch in self.branches.values():
                branch.push(frame)

    def start(self):
        self._capture_stream = sd.InputStream(
            device=self.cable_output_id,
            samplerate=self.samplerate,
            channels=CHANNELS,
            blocksize=BLOCK_SIZE,
            callback=self._capture_callback,
        )
        self._capture_stream.start()

    def stop(self):
        if self._capture_stream:
            self._capture_stream.stop()
            self._capture_stream.close()
        with self._lock:
            for b in list(self.branches.values()):
                b.stop()
            self.branches.clear()
