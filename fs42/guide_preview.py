import os
import shutil
import subprocess
import threading

FFMPEG_FALLBACKS = ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg")


def find_ffmpeg():
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in FFMPEG_FALLBACKS:
        if os.path.exists(candidate):
            return candidate
    return None


class LivePreview:
    """Decodes a muted, low-resolution copy of a video in real time for the guide's preview box."""

    def __init__(self, path, start_seconds=0.0, width=320, height=180, fps=12):
        self.path = path
        self.start_seconds = max(0.0, float(start_seconds or 0.0))
        self.width = int(width)
        self.height = int(height)
        self.fps = fps
        self.frame_size = self.width * self.height * 3
        self.ended = False
        self.received_frame = False
        self._proc = None
        self._lock = threading.Lock()
        self._frame = None

    def command(self, ffmpeg):
        scale = (
            f"fps={self.fps},"
            f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
            f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:black"
        )
        return [
            ffmpeg, "-v", "error", "-nostdin",
            "-re", "-ss", f"{self.start_seconds:.2f}", "-i", self.path,
            "-an", "-sn", "-vf", scale,
            "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ]

    def start(self):
        ffmpeg = find_ffmpeg()
        if not ffmpeg or not self.path or not os.path.exists(self.path):
            self.ended = True
            return False
        try:
            self._proc = subprocess.Popen(
                self.command(ffmpeg),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except OSError:
            self.ended = True
            return False
        threading.Thread(target=self._read_frames, daemon=True).start()
        return True

    def _read_frames(self):
        stream = self._proc.stdout
        try:
            while True:
                data = stream.read(self.frame_size)
                if len(data) < self.frame_size:
                    break
                with self._lock:
                    self._frame = data
                self.received_frame = True
        except (OSError, ValueError):
            pass
        finally:
            self.ended = True

    def latest_frame(self):
        """Returns the newest unseen frame as RGB bytes, or None."""
        with self._lock:
            frame, self._frame = self._frame, None
        return frame

    def stop(self):
        proc = self._proc
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
