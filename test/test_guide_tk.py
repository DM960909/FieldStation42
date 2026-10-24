from queue import Empty
from types import SimpleNamespace
from unittest.mock import Mock

from fs42.guide_tk import GuideApp, GuideCommands, GuideSelection, GuideView, GuideWindowConf


class QueueWithoutQsize:
    def get_nowait(self):
        return GuideCommands.hide_window

    def qsize(self):
        raise NotImplementedError


def test_guide_tick_handles_hide_message_without_queue_size():
    app = SimpleNamespace(
        queue=QueueWithoutQsize(),
        destroy=Mock(),
        after=Mock(),
    )

    GuideApp.tick(app)

    app.destroy.assert_called_once_with()
    app.after.assert_not_called()


def test_guide_tick_reschedules_when_queue_is_empty():
    class EmptyQueue:
        def get_nowait(self):
            raise Empty

    tick = Mock()
    app = SimpleNamespace(
        queue=EmptyQueue(),
        tick=tick,
        after=Mock(),
    )

    GuideApp.tick(app)

    app.after.assert_called_once_with(100, tick)


def test_guide_tick_forwards_navigation_and_keeps_polling_after_errors():
    messages = [GuideCommands.nav_down, GuideCommands.nav_select]

    class Queue:
        def get_nowait(self):
            if messages:
                return messages.pop(0)
            raise Empty

    view = SimpleNamespace(handle_command=Mock(side_effect=[RuntimeError("boom"), None]))
    tick = Mock()
    app = SimpleNamespace(queue=Queue(), view=view, tick=tick, after=Mock())

    GuideApp.tick(app)

    assert [call.args[0] for call in view.handle_command.call_args_list] == [
        GuideCommands.nav_down,
        GuideCommands.nav_select,
    ]
    app.after.assert_called_once_with(100, tick)


def test_guide_layout_fits_header_rows_details_and_footer_at_common_resolutions():
    for width, height, station_count in (
        (720, 480, 3),
        (1920, 1080, 8),
        (2560, 1440, 14),
    ):
        conf = GuideWindowConf(w=width, h=height)
        conf.schedule_row_count = station_count
        conf._calc_internals()

        used_height = (
            conf.grid_top
            + conf.sched_h * (conf.slot_count + 1)
            + conf.detail_panel_height
            + conf.footer_height
        )
        assert used_height <= conf.height
        assert 5 <= conf.slot_count <= 8


def test_guide_preview_box_sits_in_the_top_right_corner():
    conf = GuideWindowConf(w=2560, h=1440)

    assert conf.preview_x + conf.preview_width < conf.width
    assert conf.preview_x > conf.width / 2
    assert conf.preview_y + conf.preview_height < conf.top_section_height
    assert abs(conf.preview_width / conf.preview_height - 16 / 9) < 0.02


def test_selection_wraps_and_scrolls_to_keep_the_cursor_visible():
    selection = GuideSelection(count=10, slots=4)

    selection.move(-1)
    assert selection.index == 9
    assert list(selection.visible_rows()) == [6, 7, 8, 9]

    selection.move(1)
    assert selection.index == 0
    assert list(selection.visible_rows()) == [0, 1, 2, 3]

    for _ in range(5):
        selection.move(1)
    assert selection.index == 5
    assert 5 in selection.visible_rows()


def test_selection_with_few_channels_never_scrolls():
    selection = GuideSelection(count=3, slots=5)

    selection.move(1)
    selection.move(1)

    assert selection.index == 2
    assert list(selection.visible_rows()) == [0, 1, 2]


def test_select_channel_reports_the_highlighted_channel_to_the_player():
    events = Mock()
    view = SimpleNamespace(
        tuning=False,
        events=events,
        meta=[{"channel_number": 12}, {"channel_number": 13}],
        selection=GuideSelection(count=2, slots=5),
    )
    view.selection.select(1)

    GuideView.select_channel(view)

    events.put.assert_called_once_with({"event": "tune", "channel": 13})
    assert view.tuning is True
