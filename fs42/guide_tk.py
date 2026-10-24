import os
import sys
import datetime
import glob
import traceback
from queue import Empty

sys.path.append(os.getcwd())

import tkinter as tk  # import Tkinter
from tkinter import font as tkfont
from PIL import Image, ImageTk
from fs42.guide_builder import GuideBuilder
from fs42.guide_preview import LivePreview
from fs42.station_manager import StationManager


class GuideWindowConf:
    def __init__(self, w=720, h=480):
        self.fullscreen = True

        self.width = w
        self.height = h

        # Palette: deep blue glossy panels with a gold selection highlight.
        self.bottom_bg = "#050f33"
        self.header_top = "#0a1f66"
        self.header_bottom = "#2a66d6"
        self.accent = "#ffd23f"
        self.channel_top = "#16367f"
        self.channel_bottom = "#091c52"
        self.time_top = "#1b3f94"
        self.time_bottom = "#0b2260"
        self.program_top = "#3d82e8"
        self.program_bottom = "#1d4fb4"
        self.empty_top = "#0e2562"
        self.empty_bottom = "#081a4a"
        self.selected_top = "#ffe785"
        self.selected_bottom = "#e8a900"
        self.selected_fg = "#14224f"
        self.schedule_fg = "#ffffff"
        self.message_fg = "#ffffff"

        self.pad = 10

        self.messages = [
            "Hello FieldStation42\nGuide preview",
            "Cheers!\nFrom us to you!",
            "FieldStation42 Guide\nOn cable mode.",
        ]
        self.message_rotation_rate = 10
        self.message_font_family = "Helvetica"
        self.message_font_size = 25

        # No longer drawn by the guide; still validated so existing configs keep loading.
        self.images = []
        self.footer_messages = []
        self.scroll_speed = 0

        self.network_font_family = "Helvetica"
        self.network_font_size = 15
        self.network_width_divisor = 4.0

        self.schedule_font_family = "Helvetica"
        self.schedule_font_size = 15

        self.footer_height = 34
        self._base_footer_height = self.footer_height
        self._base_pad = self.pad
        self.detail_height = 58

        self.schedule_row_count = 3
        self.schedule_col_count = 3
        # The grid always shows between these many channel rows, scrolling when there are more.
        self.min_visible_rows = 5
        self.max_visible_rows = 8

        self.play_sound = False
        self.sound_to_play = None
        self.normalize_titles = True

        self.top_section_ratio = 0.27

        self._calc_internals()

    def _calc_internals(self):
        self.scale_factor = max(0.75, self.height / 480)
        s = self.scale_factor
        self.pad = int(self._base_pad * s)
        self.footer_height = int(self._base_footer_height * s)
        self.half_h = self.height / 2
        self.half_w = self.width / 2

        self.top_section_height = int(self.height * self.top_section_ratio)
        self.bottom_section_height = self.height - self.top_section_height
        self.detail_panel_height = int(self.detail_height * s)
        self.grid_gap = int(self.pad * 0.6)
        self.grid_top = self.top_section_height + self.grid_gap

        self.preview_height = int(self.top_section_height * 0.66) // 2 * 2
        self.preview_width = int(self.preview_height * 16 / 9) // 2 * 2
        self.preview_x = self.width - self.pad - self.preview_width
        self.preview_y = self.pad

        self.margin = self.pad
        self.network_w = self.width / self.network_width_divisor
        self.sched_w = (self.width - self.margin * 2 - self.network_w) / self.schedule_col_count

        self.slot_count = max(self.min_visible_rows, min(self.max_visible_rows, self.schedule_row_count))
        grid_h = self.height - self.grid_top - self.detail_panel_height - self.footer_height
        # One extra row for the time header
        self.sched_h = max(1, grid_h / (self.slot_count + 1))
        self.visible_row_count = self.slot_count

        top_h = self.top_section_height
        self._wordmark_font = (self.message_font_family, -max(10, int(top_h * 0.30)), "bold italic")
        self._tagline_font = (self.message_font_family, -max(8, int(top_h * 0.15)), "bold italic")
        self._clock_font = (self.message_font_family, -max(8, int(top_h * 0.12)), "bold")
        self._message_font = (self.message_font_family, -max(8, int(top_h * 0.10 * self.message_font_size / 25)), "bold")
        self._caption_font = (self.message_font_family, -max(8, int(top_h * 0.085)), "bold")
        row_px = max(8, int(self.sched_h * 0.30))
        self._schedule_font = (self.schedule_font_family, -max(8, int(row_px * self.schedule_font_size / 15)), "bold")
        self._network_font = (self.network_font_family, -max(8, int(row_px * self.network_font_size / 15)), "bold")
        self._detail_title_font = (self.message_font_family, -max(8, int(self.detail_panel_height * 0.34)), "bold")
        self._detail_small_font = (self.message_font_family, -max(8, int(self.detail_panel_height * 0.2)), "bold")
        self._footer_font = (self.message_font_family, -max(8, int(self.footer_height * 0.42)), "bold")
        self._message_rotation_rate = self.message_rotation_rate * 1000

    def merge_config(self, to_merge):
        for key in to_merge:
            if hasattr(self, key):
                setattr(self, key, to_merge[key])
        if "footer_height" in to_merge:
            self._base_footer_height = to_merge["footer_height"]
        if "pad" in to_merge:
            self._base_pad = to_merge["pad"]
        self._calc_internals()

    def check_config(self, merge_conf):
        """Note: this should only be called from the startup checker since it merges the conf again"""
        self.merge_config(merge_conf)
        to_check = self.images.copy()

        # Check sound_to_play - can be a string (file or directory) or a list of files
        if self.play_sound and self.sound_to_play:
            if isinstance(self.sound_to_play, list):
                # It's a list - check each file
                for sound_file in self.sound_to_play:
                    to_check.append(sound_file)
            elif isinstance(self.sound_to_play, str):
                # It's a string - could be a file or directory
                if os.path.isdir(self.sound_to_play):
                    # Directory path - check if it has any mp3 files
                    mp3_files = glob.glob(os.path.join(self.sound_to_play, "*.mp3"))
                    if not mp3_files:
                        errors = [f"Guide channel directory {self.sound_to_play} exists but contains no .mp3 files"]
                        return errors
                else:
                    # Single file path - add to check list
                    to_check.append(self.sound_to_play)

        errors = []
        for fp in to_check:
            if not os.path.exists(fp):
                err = f"Guide channel config references a file named {fp} but it does not exist on disk"
                errors.append(err)

        # check that its fullscreen, or else that width and height are specified
        if not self.fullscreen:
            if not self.width or not self.height:
                err = """Guide channel fullscreen is set to false, but width or height is not speficied.
                If fullscreen is not set to true, please set both width and height in pixels.
                """
                errors.append(err)
        return errors


class GuideCommands:
    show_window = "show_window"
    hide_window = "hide_window"
    exit_process = "exit_process"
    nav_up = "nav_up"
    nav_down = "nav_down"
    nav_select = "nav_select"


class GuideSelection:
    """Tracks the highlighted channel row and which rows are scrolled into view."""

    def __init__(self, count=0, slots=5):
        self.count = count
        self.slots = max(1, slots)
        self.index = 0
        self.top = 0

    def set_count(self, count):
        self.count = count
        self.index = min(self.index, max(0, count - 1))
        self._scroll_to_index()

    def select(self, index):
        if self.count:
            self.index = max(0, min(index, self.count - 1))
            self._scroll_to_index()

    def move(self, delta):
        if self.count:
            self.index = (self.index + delta) % self.count
            self._scroll_to_index()

    def visible_rows(self):
        return range(self.top, min(self.count, self.top + self.slots))

    def _scroll_to_index(self):
        if self.index < self.top:
            self.top = self.index
        elif self.index >= self.top + self.slots:
            self.top = self.index - self.slots + 1
        self.top = max(0, min(self.top, max(0, self.count - self.slots)))


def _rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class GuideView:
    """Draws the whole guide on one canvas: header, preview box, channel grid, details and footer."""

    def __init__(self, parent, conf, events=None, preview=None):
        self.parent = parent
        self.conf = conf
        self.events = events
        self.preview_info = preview
        self.tuning = False

        self.canvas = tk.Canvas(
            parent,
            width=conf.width,
            height=conf.height,
            bg=conf.bottom_bg,
            highlightthickness=0,
            borderwidth=0,
        )
        self.canvas.place(x=0, y=0, width=conf.width, height=conf.height)

        self._images = {}
        self.fonts = {
            name: tkfont.Font(root=parent, family=spec[0], size=spec[1], weight="bold" if "bold" in spec[2] else "normal",
                              slant="italic" if "italic" in spec[2] else "roman")
            for name, spec in {
                "wordmark": conf._wordmark_font,
                "tagline": conf._tagline_font,
                "clock": conf._clock_font,
                "message": conf._message_font,
                "caption": conf._caption_font,
                "schedule": conf._schedule_font,
                "network": conf._network_font,
                "detail_title": conf._detail_title_font,
                "detail_small": conf._detail_small_font,
                "footer": conf._footer_font,
            }.items()
        }

        self.rows = []
        self.meta = []
        self.timings = []
        self.selection = GuideSelection(slots=conf.slot_count)

        self.stream = None
        self.preview_photo = None
        self.message_index = 0

        self._draw_header()
        self._start_preview()
        self.refresh_schedule(first=True)
        self.update_clock()
        self.rotate_message()
        self.update_preview()

    # ----- drawing helpers -------------------------------------------------

    def gradient(self, w, h, top, bottom, gloss=True):
        w, h = max(1, int(w)), max(1, int(h))
        key = (w, h, top, bottom, gloss)
        if key not in self._images:
            column = Image.new("RGB", (1, h))
            top_rgb, bottom_rgb = _rgb(top), _rgb(bottom)
            for y in range(h):
                color = _lerp(top_rgb, bottom_rgb, y / max(1, h - 1))
                if gloss and y < h / 2:
                    color = _lerp(color, (255, 255, 255), 0.14)
                column.putpixel((0, y), color)
            self._images[key] = ImageTk.PhotoImage(column.resize((w, h)))
        return self._images[key]

    def fit_text(self, text, font_name, max_width):
        font = self.fonts[font_name]
        text = " ".join(str(text).split())
        if max_width <= 0:
            return ""
        if font.measure(text) <= max_width:
            return text
        while text and font.measure(text + "…") > max_width:
            text = text[:-1]
        return text.rstrip() + "…" if text else ""

    def _panel(self, x, y, w, h, top, bottom, tag, outline=None):
        iw, ih = max(1, int(w)), max(1, int(h))
        self.canvas.create_image(x, y, image=self.gradient(iw, ih, top, bottom), anchor="nw", tags=tag)
        if outline:
            self.canvas.create_rectangle(x, y, x + iw, y + ih, outline=outline, width=1, tags=tag)

    def _text(self, x, y, text, font, fill, tag, anchor="w", max_width=None):
        if max_width is not None:
            text = self.fit_text(text, font, max_width)
        self.canvas.create_text(x, y, text=text, font=self.fonts[font], fill=fill, anchor=anchor, tags=tag)

    # ----- header ----------------------------------------------------------

    def _draw_header(self):
        conf, c = self.conf, self.canvas
        top_h = conf.top_section_height
        self._panel(0, 0, conf.width, top_h, conf.header_top, conf.header_bottom, "static")
        c.create_rectangle(0, top_h - max(2, int(conf.scale_factor)), conf.width, top_h,
                           fill=conf.accent, outline="", tags="static")

        x = conf.pad * 2
        c.create_text(x, top_h * 0.10, text="FIELDSTATION", font=self.fonts["wordmark"],
                      fill="white", anchor="nw", tags="static")
        word_w = self.fonts["wordmark"].measure("FIELDSTATION ")
        c.create_text(x + word_w, top_h * 0.10, text="42", font=self.fonts["wordmark"],
                      fill=conf.accent, anchor="nw", tags="static")
        c.create_text(x, top_h * 0.46, text="TV GUIDE", font=self.fonts["tagline"],
                      fill=conf.accent, anchor="nw", tags="static")
        c.create_text(x, top_h * 0.70, text="", font=self.fonts["clock"],
                      fill="white", anchor="nw", tags="clock")
        c.create_text(conf.preview_x - conf.pad * 2, top_h * 0.34, text="", font=self.fonts["message"],
                      fill=conf.accent, anchor="e", justify="right", tags="message")

        # preview frame: white bezel with a black screen
        px, py, pw, ph = conf.preview_x, conf.preview_y, conf.preview_width, conf.preview_height
        bezel = max(2, int(conf.scale_factor * 1.5))
        c.create_rectangle(px - bezel, py - bezel, px + pw + bezel, py + ph + bezel,
                           fill="white", outline="", tags="static")
        c.create_rectangle(px, py, px + pw, py + ph, fill="black", outline="", tags="static")
        c.create_image(px, py, anchor="nw", tags="preview_img")
        c.create_text(px + pw / 2, py + ph / 2, text="", font=self.fonts["caption"],
                      fill="#9db7ee", anchor="center", justify="center", tags="preview_note")

        info = self.preview_info
        cap_y = py + ph + bezel + max(2, conf.pad // 3)
        if info:
            line_one = f"CH {str(info['channel_number']).zfill(3)}  {str(info['network_name']).upper()}"
            line_two = info.get("title") or ""
        else:
            line_one, line_two = "NO CHANNEL TUNED", "Select a channel to watch"
        self._text(px, cap_y, line_one, "caption", conf.accent, "static", anchor="nw", max_width=pw)
        self._text(px, cap_y + self.fonts["caption"].metrics("linespace"), line_two, "caption", "white",
                   "static", anchor="nw", max_width=pw)

    def _start_preview(self):
        info = self.preview_info
        self.stream = None
        note = "NO PREVIEW"
        if info and info.get("path"):
            stream = LivePreview(info["path"], info.get("start", 0), self.conf.preview_width, self.conf.preview_height)
            if stream.start():
                self.stream = stream
                note = ""
        elif not info:
            note = "NO SIGNAL"
        self.canvas.itemconfigure("preview_note", text=note)

    def update_preview(self):
        try:
            stream = self.stream
            if stream:
                frame = stream.latest_frame()
                if frame:
                    image = Image.frombytes("RGB", (self.conf.preview_width, self.conf.preview_height), frame)
                    self.preview_photo = ImageTk.PhotoImage(image)
                    self.canvas.itemconfigure("preview_img", image=self.preview_photo)
                    self.canvas.itemconfigure("preview_note", text="")
                elif stream.ended and not stream.received_frame:
                    self.canvas.itemconfigure("preview_note", text="NO PREVIEW")
        except Exception:
            traceback.print_exc()
        self.canvas.after(70, self.update_preview)

    def update_clock(self):
        try:
            now = datetime.datetime.now()
            time_format = StationManager().server_conf["time_format"]
            self.canvas.itemconfigure("clock", text=f"{now.strftime(time_format)}   {now.strftime('%a %d %b').upper()}")
        except Exception:
            traceback.print_exc()
        self.canvas.after(1000, self.update_clock)

    def rotate_message(self):
        messages = self.conf.messages
        if messages:
            text = " ".join(str(messages[self.message_index % len(messages)]).split())
            self.canvas.itemconfigure("message", text=text)
            self.message_index += 1
        self.canvas.after(self.conf._message_rotation_rate, self.rotate_message)

    # ----- grid ------------------------------------------------------------

    def refresh_schedule(self, first=False):
        try:
            view = GuideBuilder().build_view(normalize=self.conf.normalize_titles)
            previous = None
            if self.meta and self.selection.index < len(self.meta):
                previous = self.meta[self.selection.index]["channel_number"]
            elif first and self.preview_info:
                previous = self.preview_info["channel_number"]

            self.rows, self.meta, self.timings = view["rows"], view["meta"], view["timings"]
            self.selection.set_count(len(self.rows))
            if previous is not None:
                for index, meta in enumerate(self.meta):
                    if meta["channel_number"] == previous:
                        self.selection.select(index)
                        break
            self.draw_grid()
        except Exception:
            traceback.print_exc()
        self.canvas.after(60_000, self.refresh_schedule)

    def draw_grid(self):
        conf, c = self.conf, self.canvas
        c.delete("grid")
        gap = max(1, int(conf.scale_factor))
        x0 = conf.margin
        x1 = conf.width - conf.margin
        prog_x = x0 + conf.network_w
        prog_w = x1 - prog_x
        row_h = conf.sched_h
        pad = conf.pad

        # time header row
        y = conf.grid_top
        today = datetime.datetime.now().strftime("%a %d %b").upper()
        self._panel(x0, y, conf.network_w - gap, row_h - gap, conf.time_top, conf.time_bottom, "grid")
        self._text(x0 + pad, y + (row_h - gap) / 2, today, "network", conf.accent, "grid", max_width=conf.network_w - pad * 2)
        for col in range(conf.schedule_col_count):
            cx = prog_x + col * conf.sched_w
            self._panel(cx, y, conf.sched_w - gap, row_h - gap, conf.time_top, conf.time_bottom, "grid")
            label = self.timings[col] if col < len(self.timings) else ""
            self._text(cx + pad, y + (row_h - gap) / 2, label, "schedule", conf.accent, "grid", max_width=conf.sched_w - pad * 2)

        # channel rows (padded with empty rows so the grid always looks full)
        visible = list(self.selection.visible_rows())
        for slot in range(conf.slot_count):
            y = conf.grid_top + (slot + 1) * row_h
            if slot >= len(visible):
                self._panel(x0, y, conf.network_w - gap, row_h - gap, conf.empty_top, conf.empty_bottom, "grid")
                self._panel(prog_x, y, prog_w, row_h - gap, conf.empty_top, conf.empty_bottom, "grid")
                continue
            self._draw_row(visible[slot], y, x0, prog_x, prog_w, row_h, gap)

        self._draw_details()
        self._draw_footer()

    def _draw_row(self, index, y, x0, prog_x, prog_w, row_h, gap):
        conf, c = self.conf, self.canvas
        pad = conf.pad
        selected = index == self.selection.index
        meta, row = self.meta[index], self.rows[index]
        h = row_h - gap
        mid = y + h / 2

        if selected:
            ch_top, ch_bottom, ch_fg = conf.selected_top, conf.selected_bottom, conf.selected_fg
        else:
            ch_top, ch_bottom, ch_fg = conf.channel_top, conf.channel_bottom, conf.schedule_fg
        self._panel(x0, y, conf.network_w - gap, h, ch_top, ch_bottom, "grid")
        number = str(meta["channel_number"]).zfill(3)
        self._text(x0 + pad, mid, number, "network", conf.selected_fg if selected else conf.accent, "grid")
        number_w = self.fonts["network"].measure("000") + pad * 2
        self._text(x0 + pad + number_w, mid, str(meta["network_name"]).upper(), "network", ch_fg, "grid",
                   max_width=conf.network_w - number_w - pad * 3)

        cell_x = prog_x
        limit = prog_x + prog_w
        for block in row:
            if block.width <= 0 or cell_x >= limit - 1:
                continue
            width = min(block.width / 5400 * prog_w, limit - cell_x)
            if width < 2:
                continue
            if selected:
                top, bottom, fg = conf.selected_top, conf.selected_bottom, conf.selected_fg
            else:
                top, bottom, fg = conf.program_top, conf.program_bottom, conf.schedule_fg
            self._panel(cell_x, y, width - gap, h, top, bottom, "grid")
            title = block.title + (" ▸" if block.ends_later else "")
            self._text(cell_x + pad, mid, title, "schedule", fg, "grid", max_width=width - gap - pad * 2)
            cell_x += width

        if selected:
            line = max(2, int(conf.scale_factor * 1.5))
            c.create_rectangle(x0 - line // 2, y - line // 2, x0 + (prog_x - x0) + prog_w + line // 2, y + h + line // 2,
                               outline="white", width=line, tags="grid")

    def _draw_details(self):
        conf = self.conf
        h = conf.detail_panel_height
        y = conf.height - conf.footer_height - h
        pad = conf.pad
        self._panel(0, y, conf.width, h, conf.header_top, conf.bottom_bg, "grid")
        if not self.rows:
            self._text(pad * 2, y + h / 2, "NO CHANNELS AVAILABLE", "detail_title", "white", "grid")
            return

        index = self.selection.index
        meta, row = self.meta[index], self.rows[index]
        left = pad * 2
        pill_w = int(self.fonts["detail_title"].measure("OK  WATCH") + pad * 3)
        text_w = conf.width - left - pill_w - pad * 5
        header = f"CH {str(meta['channel_number']).zfill(3)}  {str(meta['network_name']).upper()}"
        self._text(left, y + h * 0.18, header, "detail_small", conf.accent, "grid", max_width=text_w)
        now_title = row[0].title if row else ""
        self._text(left, y + h * 0.48, f"NOW  {now_title}", "detail_title", "white", "grid", max_width=text_w)
        if len(row) > 1:
            self._text(left, y + h * 0.82, f"NEXT  {row[1].title}", "detail_small", "#b8cdf5", "grid", max_width=text_w)

        pill_h = int(h * 0.56)
        px0 = conf.width - left - pill_w
        py0 = y + (h - pill_h) / 2
        self._panel(px0, py0, pill_w, pill_h, conf.selected_top, conf.selected_bottom, "grid", outline="white")
        self._text(px0 + pill_w / 2, py0 + pill_h / 2, "OK  WATCH", "detail_title", conf.selected_fg, "grid", anchor="center")

    def _draw_footer(self):
        conf = self.conf
        y = conf.height - conf.footer_height
        self._panel(0, y, conf.width, conf.footer_height, conf.header_top, conf.bottom_bg, "grid")
        self.canvas.create_rectangle(0, y, conf.width, y + max(1, int(conf.scale_factor)),
                                     fill=conf.accent, outline="", tags="grid")
        text = "NAV ▲ ▼  BROWSE   •   OK  WATCH   •   CH ▲ ▼  CHANGE CHANNEL"
        self._text(conf.width / 2, y + conf.footer_height / 2 + 1, text, "footer", "white", "grid",
                   anchor="center", max_width=conf.width - conf.pad * 2)

    # ----- input -----------------------------------------------------------

    def handle_command(self, command):
        if self.tuning:
            return
        if command == GuideCommands.nav_up:
            self.selection.move(-1)
            self.draw_grid()
        elif command == GuideCommands.nav_down:
            self.selection.move(1)
            self.draw_grid()
        elif command == GuideCommands.nav_select:
            self.select_channel()

    def select_channel(self):
        if not self.meta:
            return
        channel = self.meta[self.selection.index]["channel_number"]
        self.tuning = True
        if self.events:
            self.events.put({"event": "tune", "channel": channel})
        else:
            print(f"Guide selected channel {channel}")
            self.tuning = False

    def close(self):
        if self.stream:
            self.stream.stop()
            self.stream = None


class GuideApp(tk.Tk):
    def __init__(self, user_conf, queue=None):
        super().__init__()

        print("======The guide channel has the following beliefs:======")
        print(f"1. Your screen is {self.winfo_screenwidth()} pixels wide")
        print(f"2. Your screen is {self.winfo_screenheight()} pixels tall")
        print("3. All humans should be treated with dignity.")

        self.title("FieldStation42 Guide")
        self.view = None

        # set defaults, just in case
        if "width" not in user_conf:
            user_conf["width"] = 720
        if "height" not in user_conf:
            user_conf["height"] = 480

        fullscreen = user_conf.get("fullscreen", True)
        if fullscreen:
            user_conf["width"] = self.winfo_screenwidth()
            user_conf["height"] = self.winfo_screenheight()

        if "window_decorations" not in user_conf or not user_conf["window_decorations"]:
            self.overrideredirect(True)

        if fullscreen:
            self.attributes("-fullscreen", True)
            print("Setting final geometry: ", f"{user_conf['width']}x{user_conf['height']}+0+0")
            self.geometry(f"{user_conf['width']}x{user_conf['height']}+0+0")
        else:
            x = (self.winfo_screenwidth() - user_conf['width']) // 2
            y = (self.winfo_screenheight() - user_conf['height']) // 2
            print("Setting final geometry: ", f"{user_conf['width']}x{user_conf['height']}+{x}+{y}")
            self.geometry(f"{user_conf['width']}x{user_conf['height']}+{x}+{y}")

        # Make cursor invisible
        self.config(cursor="none")

        merge_conf = GuideWindowConf(w=user_conf["width"], h=user_conf["height"])

        if user_conf:
            merge_conf.merge_config(user_conf)

        visible_station_count = sum(
            1 for station in StationManager().stations if not station.get("hidden", False)
        )
        merge_conf.schedule_row_count = max(1, visible_station_count)
        merge_conf._calc_internals()

        self.conf = merge_conf

        self.config(bg=merge_conf.bottom_bg)

        # self.resizable(False, False)
        self.after(1000, self.tick)
        self.queue = queue

    def get_conf(self):
        return self.conf

    def tick(self):
        if self.queue:
            # Drain everything waiting so fast remote presses are never dropped.
            while True:
                try:
                    msg = self.queue.get_nowait()
                except Empty:
                    break
                if msg == GuideCommands.hide_window:
                    print("Guide window is shutting down now.")
                    view = getattr(self, "view", None)
                    if view:
                        view.close()
                    self.destroy()
                    return
                view = getattr(self, "view", None)
                if view and msg:
                    # An error here must not stop the polling loop, or the guide could never close.
                    try:
                        view.handle_command(msg)
                    except Exception:
                        traceback.print_exc()

        self.after(100, self.tick)


def guide_channel_runner(user_conf, queue, events=None, preview=None):
    app = GuideApp(user_conf, queue)
    app.view = GuideView(app, app.get_conf(), events=events, preview=preview)
    for key, command in (
        ("<Up>", GuideCommands.nav_up),
        ("<Down>", GuideCommands.nav_down),
        ("<Return>", GuideCommands.nav_select),
    ):
        app.bind(key, lambda _event, command=command: app.view.handle_command(command))

    app.mainloop()


if __name__ == "__main__":
    conf = StationManager().station_by_name("Guide")
    guide_channel_runner(conf, None)
