import json
from queue import Empty
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fs42.guide_tk import GuideCommands
from fs42.station_player import PlayerOutcome, PlayerState, StationPlayer


class FakeQueue:
    def __init__(self, messages=()):
        self.messages = list(messages)
        self.sent = []

    def put(self, message):
        self.sent.append(message)

    def get_nowait(self):
        if self.messages:
            return self.messages.pop(0)
        raise Empty


class FakeProcess:
    def __init__(self, target, args):
        self.args = args

    def start(self):
        pass

    def join(self, timeout):
        pass

    def is_alive(self):
        return False


def make_player(responses, mpv=None, **extra):
    mpv = mpv or SimpleNamespace(loop_playlist="no", stop=Mock(), time_pos=0)
    player = SimpleNamespace(
        mpv=mpv,
        station_config={"network_name": "Guide", "channel_number": 0},
        current_playing_file_path=None,
        _l=Mock(),
        input_check_fn=Mock(side_effect=list(responses)),
        handle_runtime_command_outcome=Mock(return_value=False),
        is_non_interrupting=StationPlayer.is_non_interrupting,
        previous_station_config=None,
        _last_program=None,
        GUIDE_NAV_KEYS=StationPlayer.GUIDE_NAV_KEYS,
    )
    player._guide_preview_context = lambda: StationPlayer._guide_preview_context(player)
    player._guide_nav_command = lambda response: StationPlayer._guide_nav_command(player, response)
    player._poll_guide_tune = StationPlayer._poll_guide_tune
    player._close_guide = lambda queue, process: StationPlayer._close_guide(player, queue, process)
    for key, value in extra.items():
        setattr(player, key, value)
    return player


def run_guide(player, guide_config, queues):
    queue_iter = iter(queues)
    with (
        patch("fs42.station_player.multiprocessing.Queue", side_effect=lambda: next(queue_iter)),
        patch("fs42.station_player.multiprocessing.Process", FakeProcess),
        patch("fs42.station_player.update_status_socket"),
        patch(
            "fs42.station_player.StationManager",
            return_value=SimpleNamespace(server_conf={"date_time_format": "%Y-%m-%dT%H:%M:%S"}),
        ),
        patch("fs42.station_player.time.sleep"),
    ):
        return StationPlayer.show_guide(player, guide_config)


def test_guide_music_loops_until_guide_closes_then_restores_playlist():
    mpv = SimpleNamespace(loop_playlist="no", stop=Mock(), time_pos=0)
    response = PlayerOutcome(PlayerState.CHANNEL_CHANGE, "{}")
    player = make_player([response], mpv=mpv)

    def play_guide_track(path):
        assert path.endswith(".mp3")
        assert mpv.loop_playlist == "inf"
        player.current_playing_file_path = path
        return True

    player.play_file = Mock(side_effect=play_guide_track)

    result = run_guide(
        player,
        {"play_sound": True, "sound_to_play": "/music/guide.mp3"},
        [FakeQueue(), FakeQueue()],
    )

    assert result is response
    player.play_file.assert_called_once_with("/music/guide.mp3")
    mpv.stop.assert_called_once_with()
    assert mpv.loop_playlist == "no"
    assert player.current_playing_file_path is None


def web_key(key):
    return PlayerOutcome(PlayerState.SUCCESS, f"web_key:{key}")


def test_remote_nav_keys_are_forwarded_to_the_guide_instead_of_ignored():
    leave = PlayerOutcome(PlayerState.CHANNEL_CHANGE, "{}")
    player = make_player([web_key("PageDown"), web_key("PageUp"), web_key("Enter"), leave])
    guide_queue = FakeQueue()

    result = run_guide(player, {}, [guide_queue, FakeQueue()])

    assert result is leave
    assert guide_queue.sent == [
        GuideCommands.nav_down,
        GuideCommands.nav_up,
        GuideCommands.nav_select,
        GuideCommands.hide_window,
    ]


def test_guide_selection_closes_the_guide_and_tunes_that_channel():
    player = make_player([None])
    guide_queue = FakeQueue()
    events = FakeQueue([{"event": "tune", "channel": 13}])

    result = run_guide(player, {}, [guide_queue, events])

    assert result.status == PlayerState.CHANNEL_CHANGE
    assert json.loads(result.payload) == {"command": "direct", "channel": 13}
    assert guide_queue.sent == [GuideCommands.hide_window]
    assert player._activate_mpv_after_guide is True


def test_guide_receives_the_program_that_was_playing_for_its_preview():
    watching = {"network_name": "Retro Cartoons", "channel_number": 12, "network_type": "standard"}
    program = {
        "path": "/media/cartoon.mp4",
        "title": "Cartoon",
        "channel_number": 12,
        "network_name": "Retro Cartoons",
    }
    mpv = SimpleNamespace(loop_playlist="no", stop=Mock(), time_pos=95.5)
    player = make_player(
        [PlayerOutcome(PlayerState.CHANNEL_CHANGE, "{}")],
        mpv=mpv,
        previous_station_config=watching,
        _last_program=program,
        current_playing_file_path="/media/cartoon.mp4",
    )
    captured = {}

    class CapturingProcess(FakeProcess):
        def __init__(self, target, args):
            captured["args"] = args

    queue_iter = iter([FakeQueue(), FakeQueue()])
    with (
        patch("fs42.station_player.multiprocessing.Queue", side_effect=lambda: next(queue_iter)),
        patch("fs42.station_player.multiprocessing.Process", CapturingProcess),
        patch("fs42.station_player.update_status_socket"),
        patch(
            "fs42.station_player.StationManager",
            return_value=SimpleNamespace(server_conf={"date_time_format": "%Y-%m-%dT%H:%M:%S"}),
        ),
        patch("fs42.station_player.time.sleep"),
    ):
        StationPlayer.show_guide(player, {})

    preview = captured["args"][3]
    assert preview["path"] == "/media/cartoon.mp4"
    assert preview["start"] == 95.5
    assert preview["channel_number"] == 12


def test_no_preview_when_the_guide_was_opened_from_the_guide_or_without_a_program():
    player = make_player([], previous_station_config={"channel_number": 0, "network_type": "guide"})
    assert StationPlayer._guide_preview_context(player) is None

    player = make_player([], previous_station_config={"channel_number": 12, "network_type": "standard"})
    assert StationPlayer._guide_preview_context(player) is None
