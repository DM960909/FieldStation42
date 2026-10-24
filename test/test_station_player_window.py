from types import SimpleNamespace
from unittest.mock import Mock, patch

from fs42.station_player import StationPlayer


def test_playback_restores_mpv_window_and_fullscreen():
    mpv = SimpleNamespace(window_minimized=True, fullscreen=False)
    player = SimpleNamespace(mpv=mpv)

    with patch("fs42.station_player.platform.system", return_value="Linux"):
        StationPlayer._show_mpv_fullscreen(player)

    assert mpv.window_minimized is False
    assert mpv.fullscreen is True


def test_macos_playback_activates_the_mpv_process():
    mpv = SimpleNamespace(window_minimized=True, fullscreen=False)
    player = SimpleNamespace(
        mpv=mpv,
        _l=Mock(),
        _activate_mpv_after_guide=False,
    )

    with (
        patch("fs42.station_player.platform.system", return_value="Darwin"),
        patch("fs42.station_player.shutil.which", return_value="/usr/bin/osascript"),
        patch("fs42.station_player.subprocess.run") as run,
    ):
        StationPlayer._show_mpv_fullscreen(player)

    run.assert_called_once_with(
        [
            "/usr/bin/osascript",
            "-e",
            'tell application "System Events" to set frontmost of '
            '(first process whose name is "mpv") to true',
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )


def test_macos_playback_retries_activation_after_leaving_guide():
    mpv = SimpleNamespace(window_minimized=True, fullscreen=False)
    player = SimpleNamespace(
        mpv=mpv,
        _l=Mock(),
        _activate_mpv_after_guide=True,
    )

    with (
        patch("fs42.station_player.platform.system", return_value="Darwin"),
        patch("fs42.station_player.shutil.which", return_value="/usr/bin/osascript"),
        patch("fs42.station_player.subprocess.run") as run,
        patch("fs42.station_player.time.sleep") as sleep,
    ):
        StationPlayer._show_mpv_fullscreen(player)

    assert run.call_count == 2
    sleep.assert_called_once_with(0.5)
    assert player._activate_mpv_after_guide is False
