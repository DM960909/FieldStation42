import subprocess
import time

import pytest

from fs42.guide_preview import LivePreview, find_ffmpeg

pytestmark = pytest.mark.skipif(find_ffmpeg() is None, reason="ffmpeg is not installed")


def make_video(path):
    subprocess.run(
        [
            find_ffmpeg(), "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=320x180:rate=10",
            "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
    )


def wait_for_frame(preview, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        frame = preview.latest_frame()
        if frame:
            return frame
        time.sleep(0.05)
    return None


def test_preview_decodes_muted_rgb_frames_at_the_requested_size(tmp_path):
    video = tmp_path / "clip.mp4"
    make_video(video)
    preview = LivePreview(str(video), start_seconds=0.5, width=160, height=90)

    try:
        assert preview.start() is True
        frame = wait_for_frame(preview)
    finally:
        preview.stop()

    assert frame is not None
    assert len(frame) == 160 * 90 * 3
    assert preview.received_frame is True


def test_preview_reports_missing_media_without_raising(tmp_path):
    preview = LivePreview(str(tmp_path / "missing.mp4"))

    assert preview.start() is False
    assert preview.ended is True
    assert preview.latest_frame() is None
    preview.stop()


def test_preview_stop_terminates_ffmpeg(tmp_path):
    video = tmp_path / "clip.mp4"
    make_video(video)
    preview = LivePreview(str(video), width=160, height=90)
    preview.start()
    wait_for_frame(preview)

    preview.stop()

    assert preview._proc.poll() is not None
