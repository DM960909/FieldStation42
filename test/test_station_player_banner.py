from unittest.mock import Mock

from fs42.station_player import StationPlayer


def test_channel_banner_includes_tuned_channel_and_program():
    player = type(
        "Player",
        (),
        {
            "station_config": {
                "channel_number": 12,
                "network_name": "Retro Cartoons",
            },
            "mpv": Mock(),
        },
    )()

    StationPlayer._show_channel_banner(player, "Episode One\nSeason 1")

    player.mpv.command.assert_called_once_with(
        "show-text",
        "CH 012  RETRO CARTOONS\nNOW PLAYING  Episode One Season 1",
        5000,
    )


def test_pending_channel_banner_only_shows_once():
    player = type(
        "Player",
        (),
        {
            "_channel_banner_pending": True,
            "_show_channel_banner": Mock(),
        },
    )()

    StationPlayer._show_pending_channel_banner(player, "Episode One")
    StationPlayer._show_pending_channel_banner(player, "Episode Two")

    player._show_channel_banner.assert_called_once_with("Episode One")
    assert player._channel_banner_pending is False
