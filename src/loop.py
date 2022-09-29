import ctypes
import glob
import math
import os
import time
import traceback
from io import BytesIO

import numpy as np
import sdl2
import OpenGL.GL as GL

import imgui

from pathlib import Path

from PIL import Image
from pydub import AudioSegment
from pydub.playback import _play_with_simpleaudio

from src.level import Level

with Image.open("assets/nocover.png") as im:
    NO_COVER = im.copy()
DIFFICULTIES: tuple = ("Unspecified", "Easy", "Medium", "Hard", "LOGIC?", "Tasukete")
TIMELINE_HEIGHT: int = 50
HITSOUND = AudioSegment.from_file("assets/hit.wav").set_sample_width(2)


def play_at_position(audio, position):
    audio = audio.set_sample_width(2)
    data = np.array(audio.get_array_of_samples())
    data = data[int(position * audio.frame_rate // 2) * 4:]
    cut_audio = audio._spawn(data=data.tobytes())
    return _play_with_simpleaudio(cut_audio)


def adjust(x, s): return (((round(((x) / 2) * (s - 1)) / (s - 1)) * 2)) if s != 0 else x


class Editor:
    def __init__(self):
        self.hitsounds = True
        self.bpm_markers = True
        self.io = None
        self.bpm = 120
        self.offset = 0
        self.approach_rate = 500
        self.approach_distance = 10
        self.snapping = None
        self.level_window_size = (200, 200)
        self.filename = None
        self.temp_filename = "out.sspm"
        self.files = None
        self.file_choice = -1
        self.current_folder = str(Path.resolve(Path(__file__).parent))
        self.level = None
        self.time = 0
        self.playing = False
        self.last_saved_hash = None
        self.playback = None
        self.error = None
        self.time_signature = (4, 4)
        self.note_snapping = 3, 3
        self.cover_id = None
        self.draw_notes = True
        self.draw_audio = True
        self.fps_cap = 100
        self.vsync = False
        self.rects_drawn = 0
        self.volume = 0

    def file_display(self, extensions):
        """Create a file select window."""
        changed = False
        folder_changed, self.current_folder = imgui.input_text("Directory", self.current_folder, 65536)
        if folder_changed or not self.files:
            # If the directory isn't what it was last time, go to the new directory
            try:
                os.chdir(
                    Path.resolve(Path(self.current_folder))
                )
            except Exception:
                os.chdir(Path.resolve(Path(__file__).parent))
            self.current_folder = os.getcwd()
        # Create list of selectable files and directories
        self.files = ['..']  # Add parent directory to self.files to allow going to it
        for extension in extensions:
            self.files.extend(sorted([f[2:] for f in glob.glob("./*" + extension)]))  # Get files
        self.files.extend(sorted(
            [f[2:] for f in glob.glob(
                "./*" + os.sep)]))  # Get directories
        clicked, self.file_choice = imgui.listbox("Levels", self.file_choice,
                                                  [path for path in self.files])
        return clicked

    def load_image(self, im: Image.Image):
        width, height = im.size
        texture_data = im.tobytes()  # Get the image's raw data for GL
        self.cover_id = self.cover_id if self.cover_id is not None else GL.glGenTextures(
            1)  # Generate the cover id if it doesn't exist, otherwise replace the texture at said id
        # Bind and set the texture at the id
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.cover_id)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, width, height, 0, GL.GL_RGBA,
                        GL.GL_UNSIGNED_BYTE, texture_data)

    def open_file_dialog(self, extensions: list[str]):
        clicked = self.file_display(extensions)  # Display a file list
        if clicked:
            # Check if the selection is a file or not
            if Path(self.files[self.file_choice]).is_file():
                imgui.close_current_popup()
                return (True, self.files[self.file_choice])  # Return the filename
            # If the selection is a directory, go to the selected directory
            self.current_folder = str(Path(os.path.join(self.current_folder, self.files[self.file_choice])).resolve())
            self.file_choice = 0
            os.chdir(os.path.expanduser(self.current_folder))
        return False, None

    def save_file_dialog(self):
        clicked = self.file_display(["*.sspm"])  # Display a file list
        if clicked:
            path = Path(os.path.join(self.current_folder,
                                     self.files[self.file_choice])).resolve()  # Get the absolute path of the file
            # Check if the selection is a file or not
            if path.is_file():
                self.temp_filename = path.stem + path.suffix  # Set the filename in the file display to the clicked file's name
            else:
                self.current_folder = str(path)  # Move to the clicked folder
            self.file_choice = 0
            os.chdir(os.path.expanduser(self.current_folder))
        # Add the filename selector
        changed, value = imgui.input_text("Filename", self.temp_filename, 128)
        if changed:
            self.temp_filename = value
        # Return the filepath if the save button has been clicked, return a fail case otherwise
        if imgui.button("Save"):
            self.filename = self.temp_filename
            self.temp_filename = None
            return True, os.path.join(self.current_folder, self.filename)
        return False, None

    def keys(self):
        return tuple(self.io.keys_down)

    def time_scroll(self, y, keys):
        if self.level is not None:
            # Check modifier keys
            use_bpm = not (keys[sdl2.SDL_SCANCODE_LALT] or keys[sdl2.SDL_SCANCODE_RALT]) and (
                self.bpm_markers and self.bpm)  # If either alt key is pressed, or there's no bpm markers to base it off of
            if not use_bpm:
                # Don't base scrolling on the current BPM and time signature
                increment = 0.1
            else:
                increment = (60 / self.bpm) * (4 / self.time_signature[1])  # Step one beat
            if keys[sdl2.SDL_SCANCODE_LSHIFT] or keys[
                    sdl2.SDL_SCANCODE_RSHIFT]:
                increment *= self.time_signature[0] if use_bpm else 10  # Step one measure
            elif keys[sdl2.SDL_SCANCODE_LCTRL] or keys[
                    sdl2.SDL_SCANCODE_RCTRL]:
                increment *= 0.25  # Step a quarter beat
            delta = increment * 1000 * y
            old_time = self.time
            self.time = max(self.time + delta, 0)
            # Set the playback and position
            if self.playback is not None:
                self.playback.stop()
                self.playback = play_at_position(self.level.audio + self.volume, self.time / 1000)
            if self.playing:
                self.starting_position += self.time - old_time

    def start(self, window, impl, font, *_):
        self.io = imgui.get_io()
        self.io.config_resize_windows_from_edges = True

        event = sdl2.SDL_Event()

        running = True
        old_audio = None
        audio_data = None
        space_last = False
        was_playing = False
        level_was_hovered = False
        last_notes = np.zeros((0), dtype=np.int64)
        old_mouse = (0, 0, 0, 0, 0)
        self.load_image(NO_COVER)
        while running:
            self.rects_drawn = 0
            dt = time.perf_counter_ns()
            # Check if the audio data needs to be updated
            if self.level is not None:
                if self.level.audio is not None:
                    if hash(self.level.audio) != old_audio:
                        audio_data = np.array(self.level.audio.get_array_of_samples(), dtype=np.int16)
                        old_audio = hash(self.level.audio)
            impl.process_inputs()
            imgui.new_frame()
            keys = self.keys()
            # Check if the song needs to be paused/played
            if keys[sdl2.SDLK_SPACE] and self.level is not None:
                if not space_last:
                    self.playing = not self.playing
                space_last = True
            elif space_last:
                space_last = False
            if self.playing and not was_playing:
                self.starting_time = time.perf_counter_ns()
                self.starting_position = self.time
                if self.level.audio is not None:
                    self.playback = play_at_position(self.level.audio + self.volume, self.time / 1000)
            elif not self.playing and was_playing:
                if self.playback is not None:
                    del self.starting_time  # Deleting these variables when they're not needed makes it easier to figure out that
                    del self.starting_position  # these are being accessed when they shouldn't be.
                    self.playback.stop()
                    self.playback = None
                if self.bpm:
                    # Snap the current time to the nearest quarter of a beat, for easier scrolling through
                    ms_per_beat = (60000 / self.bpm) * (4 / self.time_signature[1])
                    step = (ms_per_beat) / 4
                    self.time = (self.time // step) * (step) + self.offset
            was_playing = self.playing
            # Set the window name
            if self.level is None:  # Is a level open?
                sdl2.SDL_SetWindowTitle(window, "SSPy".encode("utf-8"))
            elif self.filename is None:  # Does the level exist as a file?
                sdl2.SDL_SetWindowTitle(window, "*Unnamed - SSPy".encode("utf-8"))
            elif self.last_saved_hash != hash(self.level):  # Has the level been saved?
                sdl2.SDL_SetWindowTitle(window, f"*{self.filename} - SSPy".encode("utf-8"))
            else:
                sdl2.SDL_SetWindowTitle(window, f"{self.filename} - SSPy".encode("utf-8"))
            with imgui.font(font):
                while sdl2.SDL_PollEvent(ctypes.byref(event)) != 0:
                    # Handle quitting the app
                    if event.type == sdl2.SDL_QUIT:
                        self.playing = False
                        if self.last_saved_hash == hash(self.level):
                            running = False
                        else:
                            imgui.open_popup("quit.ensure")
                    if event.type == sdl2.SDL_MOUSEWHEEL and level_was_hovered:
                        self.time_scroll(event.wheel.y, keys)
                    impl.process_event(event)
                menu_choice = None
                # Handle file keybinds
                if self.io.key_ctrl:
                    if keys[sdl2.SDLK_n]:
                        # CTRL + N : New
                        self.level = Level()
                        self.filename = None
                        self.playing = False
                        self.last_saved_hash = None
                        self.time = 0
                    if keys[sdl2.SDLK_o]:
                        # CTRL + O : Open...
                        menu_choice = "file.open"
                    if keys[sdl2.SDLK_s]:
                        # CTRL + S : Save / CTRL + SHIFT + S : Save As...
                        if self.filename is not None and not keys[sdl2.SDL_SCANCODE_LSHIFT]:
                            with open(self.filename, "wb+") as f:
                                f.write(self.level.save())
                            self.last_saved_hash = hash(self.level)
                        else:
                            menu_choice = "file.saveas"
                    if keys[sdl2.SDLK_q]:
                        # CTRL + Q : Quit
                        self.playing = False
                        if self.last_saved_hash == hash(self.level) or (
                                self.filename is not None and self.last_saved_hash is None):
                            running = False
                        else:
                            menu_choice = "quit.ensure"
                if imgui.begin_main_menu_bar():
                    if imgui.begin_menu("File"):
                        if imgui.menu_item("New", "ctrl + n")[0]:
                            self.level = Level()
                            self.filename = None
                            self.playing = False
                            self.last_saved_hash = None
                            self.time = 0
                        if imgui.menu_item("Open...", "ctrl + o")[0]:
                            menu_choice = "file.open"
                        if imgui.menu_item("Save", "ctrl + s",
                                           enabled=(self.level is not None and self.filename is not None))[0]:
                            if self.filename is not None:
                                with open(self.filename, "wb+") as f:
                                    f.write(self.level.save())
                                self.last_saved_hash = hash(self.level)
                            else:
                                menu_choice = "file.saveas"
                        if imgui.menu_item("Save As...", "ctrl + shift + s", enabled=self.level is not None)[0]:
                            if self.filename is not None:
                                self.temp_filename = self.filename
                            menu_choice = "file.saveas"
                        imgui.separator()
                        if imgui.menu_item("Quit", "ctrl + q")[0]:
                            self.playing = False
                            if self.last_saved_hash == hash(self.level) or (
                                    self.filename is not None and self.last_saved_hash is None):
                                running = False
                            else:
                                menu_choice = "quit.ensure"  # The quit menu won't open if I don't do this from here
                        imgui.end_menu()
                    if imgui.begin_menu("Edit", self.level is not None):
                        imgui.push_item_width(240)
                        # Difficulty picker
                        changed, value = imgui.combo("Difficulty", self.level.difficulty + 1,
                                                     list(DIFFICULTIES))
                        if changed:
                            self.level.difficulty = value - 1
                        imgui.separator()
                        imgui.push_style_color(imgui.COLOR_TEXT, 0.7, 0.7, 0.7, 1)
                        _, _ = imgui.input_text("ID", self.level.id, 128,
                                                imgui.INPUT_TEXT_READ_ONLY)
                        imgui.pop_style_color()
                        # Display song data
                        if changed:
                            self.level.difficulty = value - 1
                        changed_a, value = imgui.input_text("Name", self.level.name, 128,
                                                            imgui.INPUT_TEXT_AUTO_SELECT_ALL)
                        if changed_a:
                            self.level.name = value
                        changed_b, value = imgui.input_text("Author", self.level.author, 64,
                                                            imgui.INPUT_TEXT_AUTO_SELECT_ALL)
                        if changed_b:
                            self.level.author = value
                        # Change the level ID if needed
                        if changed_a or changed_b:
                            self.level.id = (self.level.author.lower() + " " + self.level.name.lower()).replace(" ",
                                                                                                                "_")
                        imgui.separator()
                        clicked = imgui.image_button(self.cover_id, 150, 150)
                        if clicked:
                            menu_choice = "edit.cover"
                        if imgui.is_item_hovered():
                            imgui.set_tooltip("Click to set a cover.")
                        clicked = imgui.button("Remove Cover")
                        if clicked:
                            self.load_image(NO_COVER)  # Remove the cover
                        imgui.separator()
                        if self.level.audio is None:
                            imgui.text("/!\\ Map has no audio")
                        clicked = imgui.button("Change song")
                        if clicked:
                            menu_choice = "edit.song"
                        imgui.pop_item_width()
                        imgui.end_menu()
                    if imgui.begin_menu("Preferences and Tools", self.level is not None):
                        imgui.push_item_width(120)
                        changed, value = imgui.checkbox("Vsync?", self.vsync)
                        if changed:
                            sdl2.SDL_GL_SetSwapInterval(int(value))  # Turn on/off VSync
                            self.vsync = value
                        if not self.vsync:
                            imgui.indent()
                            changed, value = imgui.slider_float("FPS Cap", float(self.fps_cap), 15, 360, "%.0f", 3)
                            if changed:
                                self.fps_cap = int(value)
                            imgui.unindent()
                        changed, value = imgui.checkbox("Draw notes on timeline?", self.draw_notes)
                        if changed:
                            self.draw_notes = value
                        changed, value = imgui.checkbox("Draw audio on timeline?", self.draw_audio)
                        if changed:
                            self.draw_audio = value
                        imgui.separator()
                        changed, value = imgui.checkbox("BPM markers?", self.bpm_markers)
                        if changed:
                            self.bpm_markers = value
                        if self.bpm_markers:
                            imgui.indent()
                            changed, value = imgui.input_int("Marker Offset (ms)", self.offset, 0)
                            if changed:
                                self.offset = value
                            changed, value = imgui.input_float("BPM", self.bpm, 0)
                            if changed:
                                self.bpm = value
                            imgui.push_item_width(49)
                            # Display time signature
                            changed, value = imgui.input_int("", self.time_signature[0], 0)
                            if changed:
                                self.time_signature = (value, self.time_signature[1])
                            imgui.same_line()
                            imgui.text("/")
                            imgui.same_line()
                            changed, value = imgui.input_int("Time Signature", self.time_signature[1], 0)
                            if changed:
                                self.time_signature = (
                                    self.time_signature[0], min(max(1 << (value - 1).bit_length(), 1), 256))
                            imgui.unindent()
                        else:
                            imgui.push_item_width(49)
                        imgui.separator()
                        # Display note snapping
                        changed, value = imgui.input_int("##", self.note_snapping[0], 0)
                        if changed:
                            self.note_snapping = (min(16, max(value, 0)) if value != 1 else 0, self.note_snapping[1])
                        if imgui.is_item_hovered():
                            imgui.set_tooltip("Set to 0 to turn off snapping.")
                        imgui.same_line()
                        imgui.text("/")
                        imgui.same_line()
                        changed, value = imgui.input_int("Note snapping", self.note_snapping[1], 0)
                        if changed:
                            self.note_snapping = (self.note_snapping[0], min(16, max(value, 0)) if value != 1 else 0)
                        if imgui.is_item_hovered():
                            imgui.set_tooltip("Set to 0 to turn off snapping.")
                        imgui.pop_item_width()
                        changed, value = imgui.slider_int("Approach Rate (ms)", self.approach_rate, 50, 2000)
                        if changed:
                            self.approach_rate = value
                        changed, value = imgui.slider_int("Spawn Distance (units)", self.approach_distance, 1,
                                                          100)
                        if changed:
                            self.approach_distance = value
                        imgui.separator()
                        if not self.playing:
                            changed, value = imgui.input_int("Position (ms)", self.time, 0)
                            if changed:
                                self.time = value
                        if self.level.audio is not None:
                            changed, value = imgui.slider_float("Volume (db)", self.volume, -100, 0.001, "%.1f", 3)
                            if changed:
                                self.volume = value
                                # Change the volume of the song if it's playing
                                if self.playback is not None:
                                    self.playback.stop()
                                    self.playback = play_at_position(self.level.audio + value, self.time / 1000)
                        changed, value = imgui.checkbox("Play hitsounds?", self.hitsounds)
                        if changed:
                            self.hitsounds = value
                        imgui.pop_item_width()
                        imgui.end_menu()
                    imgui.end_main_menu_bar()
                if menu_choice == "file.open":
                    imgui.open_popup("file.open")
                    self.file_choice = 0
                if imgui.begin_popup("file.open"):
                    # Open a file dialog
                    changed, value = self.open_file_dialog([".sspm"])
                    if changed:
                        self.filename = value
                        try:
                            with open(value, "rb") as file:
                                # Read the level from the file and load it
                                self.level = Level.from_sspm(file)
                            # Initialize song variables
                            self.load_image(self.level.cover if self.level.cover is not None else NO_COVER)
                            self.time = 0
                            self.playing = False
                        except Exception as e:
                            self.error = e
                    imgui.end_popup()
                if menu_choice == "file.saveas":
                    imgui.open_popup("file.saveas")
                if imgui.begin_popup("file.saveas"):
                    changed, value = self.save_file_dialog()
                    if changed:
                        with open(value, "wb+") as file:
                            file.write(self.level.save())
                        self.last_saved_hash = hash(self.level)
                        imgui.close_current_popup()
                    imgui.end_popup()
                if menu_choice == "edit.cover":
                    imgui.open_popup("edit.cover")
                if imgui.begin_popup(
                        "edit.cover"):
                    # Load the selected image
                    changed, value = self.open_file_dialog([".png"])
                    if changed:
                        with Image.open(value) as im:
                            self.level.cover = im.copy()
                            self.load_image(self.level.cover)
                    imgui.end_popup()
                if menu_choice == "edit.song":
                    imgui.open_popup("edit.song")
                if imgui.begin_popup(
                        "edit.song"):
                    # Load the selected audio
                    changed, value = self.open_file_dialog([".mp3", ".ogg", ".wav", ".flac", ".opus"])
                    if changed:
                        if Path(value).suffix == ".ogg":
                            self.level.audio = AudioSegment.from_file(value)
                        else:
                            # Convert audio to .ogg
                            audio_temp = AudioSegment.from_file(value)
                            audio_buf = BytesIO()
                            audio_temp.export(audio_buf, format="ogg")
                            audio_buf.seek(0)
                            self.level.audio = AudioSegment.from_file(audio_buf)
                    imgui.end_popup()
                if menu_choice == "quit.ensure":
                    imgui.open_popup("quit.ensure")
                if imgui.begin_popup(
                        "quit.ensure"
                ):
                    imgui.text("You have unsaved changes!")
                    imgui.text("Are you sure you want to exit?")
                    if imgui.button("Quit"):
                        return False
                    imgui.same_line(spacing=10)
                    if imgui.button("Cancel"):
                        imgui.close_current_popup()
                    imgui.end_popup()
                if self.level is not None:
                    size = self.io.display_size
                    imgui.set_next_window_size(size[0], size[1] - 26)
                    imgui.set_next_window_position(0, 26)
                    if imgui.core.begin("Level",
                                        flags=imgui.WINDOW_NO_MOVE | imgui.WINDOW_NO_COLLAPSE | imgui.WINDOW_NO_TITLE_BAR | imgui.WINDOW_NO_RESIZE | imgui.WINDOW_NO_BRING_TO_FRONT_ON_FOCUS):
                        if imgui.begin_child("nodrag", 0, 0, False, ):
                            draw_list = imgui.get_window_draw_list()
                            x, y = imgui.get_window_position()
                            w, h = imgui.get_content_region_available()
                            # Draw the main UI background
                            square_side = min(w - TIMELINE_HEIGHT, h - TIMELINE_HEIGHT)
                            draw_list.add_rect_filled(x, y, x + w, y + h, 0xff080808)
                            adjusted_x = (((x + w) / 2) - (square_side / 2))
                            draw_list.add_rect_filled(adjusted_x, y, adjusted_x + square_side, y + square_side,
                                                      0xff000000)
                            draw_list.add_rect_filled(x, (y + h) - 50, x + w, (y + h), 0x20ffffff)
                            self.rects_drawn += 3
                            times_to_display = np.array(tuple(self.level.notes.keys()), dtype=np.uint32)
                            ending_time = self.level.get_end()
                            if self.level.audio is not None and audio_data is not None and self.draw_audio:
                                center = (y + h) - (TIMELINE_HEIGHT / 2)
                                length = int(self.level.audio.frame_rate * (max(ending_time + 1000, self.time) / 1000))
                                extent = np.max(np.abs(audio_data))
                                waveform_width = int(
                                    size[0])
                                # Draw waveform
                                for n in range(waveform_width):
                                    index = math.floor((n / waveform_width) * length * 2)
                                    try:
                                        sample = audio_data[index]
                                        draw_list.add_rect_filled(x + int((w / waveform_width) * n),
                                                                  center - int((sample / extent) * 25),
                                                                  x + int((w / waveform_width) * n) + 1,
                                                                  center + int((sample / extent) * 25), 0x20ffffff)
                                        self.rects_drawn += 1
                                    except IndexError:
                                        break
                            if self.draw_notes:
                                # Draw notes
                                for note in times_to_display:
                                    progress = note / max(ending_time + 1000, self.time + self.approach_rate, 1)
                                    progress = progress if not math.isnan(progress) else 1
                                    draw_list.add_rect_filled(x + int(w * progress), (y + h) - 50,
                                                              x + int(w * progress) + 1, (y + h), 0x40ffffff)
                                    self.rects_drawn += 1
                            # Draw currently visible area on timeline
                            start = (self.time) / max(ending_time + 1000, self.time + self.approach_rate, 1)
                            end = (self.time + self.approach_rate) / max(ending_time + 1000,
                                                                         self.time + self.approach_rate, 1)
                            draw_list.add_rect(x + int(w * start), (y + h) - 50, x + int(w * end) + 1,
                                               (y + h), 0x80ffffff, thickness=3)
                            self.rects_drawn += 1

                            def center_of_view(text):
                                text_width = imgui.calc_text_size(text).x
                                return max(
                                    min((((x + int(w * start)) + (x + int(w * end) + 1)) / 2) - (text_width / 2),
                                        w - text_width), text_width / 2)

                            # Draw the current time above the visible area
                            draw_list.add_text(
                                center_of_view(f"{self.time / 1000:.3f}"),
                                y + h - 70, 0x80FFFFFF, f"{self.time / 1000:.3f}")
                            if self.bpm_markers and self.bpm:
                                # Draw the current measure and beat
                                ms_per_beat = (60000 / self.bpm) * (4 / self.time_signature[1])
                                current_beat = (self.time - self.offset) / (ms_per_beat)
                                m_text = f"Measure {current_beat // self.time_signature[0]:.0f}"
                                draw_list.add_text(
                                    center_of_view(m_text),
                                    y + h - 110, 0x80FFFFFF, m_text)
                                b_text = f"Beat {f'{current_beat % self.time_signature[0]:.2f}'.rstrip('0').rstrip('.')}"
                                draw_list.add_text(
                                    center_of_view(b_text),
                                    y + h - 90, 0x80FFFFFF, b_text)

                                # Draw beat markers in note space
                                closest_beat = ((self.time) // (ms_per_beat)) * (ms_per_beat) + self.offset
                                for n in np.arange(closest_beat, (closest_beat + self.approach_rate + 1), ms_per_beat):
                                    i = int(n // ms_per_beat)  # Current beat
                                    beat_time = (n + ((self.offset / ms_per_beat) % ms_per_beat))
                                    line_prog = max(1 - (((beat_time - (self.time)) / (self.approach_rate))), 0)
                                    if line_prog <= 1:
                                        position = (adjusted_x + adjusted_x + square_side) // 2, (
                                            y + y + square_side) // 2
                                        draw_list.add_rect(
                                            self.adjust_pos(position[0] - (square_side // 2), position[0], line_prog),
                                            self.adjust_pos(position[1] - (square_side // 2), position[1], line_prog),
                                            self.adjust_pos(position[0] + (square_side // 2), position[0], line_prog),
                                            self.adjust_pos(position[1] + (square_side // 2), position[1], line_prog),
                                            (0xff000000 if i % self.time_signature[0] == 0 else
                                             0x80000000) | int(0xFF * line_prog),
                                            thickness=int((4 if i % self.time_signature[0] == 0 else 2) * line_prog))
                                        self.rects_drawn += 1

                            # Draw notes on note space
                            times_to_display = times_to_display[np.logical_and(times_to_display >= self.time - 1,
                                                                               (times_to_display) < (
                                                                                   self.time + self.approach_rate))].flatten()
                            for note_time in times_to_display[::-1]:
                                for note in self.level.notes[note_time]:
                                    progress = 1 - ((note_time - self.time) / self.approach_rate)
                                    self.draw_note(draw_list, note,
                                                   (adjusted_x, y, adjusted_x + square_side, y + square_side), progress)
                                    self.rects_drawn += 1

                            # Play note hit sound
                            if self.playing:
                                if last_notes.size and times_to_display.size and np.min(last_notes) < np.min(
                                        times_to_display):
                                    _play_with_simpleaudio(HITSOUND)
                            last_notes = times_to_display

                            mouse_pos = tuple(self.io.mouse_pos)
                            level_was_hovered = imgui.is_window_hovered()
                            if ((adjusted_x <= mouse_pos[0] < adjusted_x + square_side) and
                                    (y <= mouse_pos[1] < y + square_side)) and level_was_hovered:
                                note_pos = ((((mouse_pos[0] - (adjusted_x + 10)) / (square_side - 10)) * 3) - 0.5,
                                            (((mouse_pos[1] - (y + 10)) / (square_side - 10)) * 3) - 0.5)
                                time_arr = np.array(tuple(self.level.notes.keys()))
                                time_arr = time_arr[
                                    np.logical_and(time_arr - self.time >= -1, time_arr - self.time < 10)]
                                closest_time = np.min(time_arr) if time_arr.size > 0 else self.time
                                closest_index = None
                                closest_dist = None
                                if tuple(self.io.mouse_down)[1] and not old_mouse[1]:
                                    for i, note in enumerate(self.level.notes.get(closest_time, ())):
                                        if abs(note[0] - note_pos[0]) < 0.5 and abs(note[1] - note_pos[1]) < 0.5:
                                            if closest_dist is None:
                                                closest_index = i
                                                closest_dist = math.sqrt((abs(note[0] - note_pos[0]) ** 2) + (
                                                    abs(note[1] - note_pos[1]) ** 2))
                                            elif closest_dist > (d := math.sqrt((abs(note[0] - note_pos[0]) ** 2) + (
                                                    abs(note[1] - note_pos[1]) ** 2))):
                                                closest_dist = d
                                                closest_index = i
                                    if closest_index is not None:
                                        del self.level.notes[int(closest_time)][closest_index]
                                        if len(self.level.notes[int(closest_time)]) == 0:
                                            del self.level.notes[int(closest_time)]
                                # Draw the note under the cursor
                                if not self.playing:
                                    np_x = adjust(note_pos[0], self.note_snapping[0])
                                    np_y = adjust(note_pos[1], self.note_snapping[1])
                                    note_pos = (np_x, np_y)
                                    self.draw_note(draw_list, note_pos,
                                                   (adjusted_x, y, adjusted_x + square_side, y + square_side), 1.0,
                                                   color=0xffff00, alpha=0x40)
                                    self.rects_drawn += 1
                                    if tuple(self.io.mouse_down)[0] and not old_mouse[0]:
                                        if int(self.time) in self.level.notes:
                                            self.level.notes[int(self.time)].append(note_pos)
                                        else:
                                            self.level.notes[int(self.time)] = [note_pos]
                            # Draw current statistics
                            fps_text = f"{int(self.io.framerate)}{f'/{self.fps_cap}' if not self.vsync else ''} FPS"
                            fps_size = imgui.calc_text_size(fps_text)
                            draw_list.add_text(w - fps_size.x, y, 0x80FFFFFF, fps_text)
                            rdtf_size = imgui.calc_text_size(f"{self.rects_drawn} rects drawn")
                            draw_list.add_text(w - rdtf_size.x, y + fps_size.y, 0x80FFFFFF,
                                               f"{self.rects_drawn} rects drawn")
                            self.rects_drawn = 0
                        imgui.end_child()
                        imgui.end()

            old_mouse = tuple(self.io.mouse_down)
            if self.error is not None:
                imgui.open_popup(self.error.__class__.__name__)
            if imgui.begin_popup(self.error.__class__.__name__):
                imgui.text_ansi("\n".join(traceback.format_exception(self.error)))
                clicked = imgui.button("Close")
                if clicked:
                    imgui.close_current_popup()
                    self.error = None
                imgui.end_popup()
            GL.glClearColor(0., 0., 0., 1)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)
            imgui.render()
            impl.render(imgui.get_draw_data())
            sdl2.SDL_GL_SwapWindow(window)

            if self.playing:
                self.time = ((time.perf_counter_ns() - self.starting_time) / 1000000) + self.starting_position

            if not self.vsync:
                dt = (time.perf_counter_ns() - dt) / 1000000000
                time.sleep(max((1 / self.fps_cap) - dt, 0))

    def adjust_pos(self, cen, pos, progress):
        visual_size = 1 / (1 + ((1 - progress) * self.approach_distance))
        return (cen * visual_size) + (pos * (1 - visual_size))

    def draw_note(self, draw_list, note_pos, box, progress, color=0xFFFFFF, alpha=0xff):
        center = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        spacing = ((box[2] - box[0]) / 3)
        note_size = spacing / 1.25
        position = (center[0] + ((note_pos[0] - 1) * spacing), center[1] + ((note_pos[1] - 1) * spacing))
        v = 1 / (1 + ((1 - progress) * self.approach_distance))
        color_part = int(0xFF * progress)
        draw_list.add_rect(self.adjust_pos(position[0] - (note_size // 2), center[0], progress),
                           self.adjust_pos(position[1] - (note_size // 2), center[1], progress),
                           self.adjust_pos(position[0] + (note_size // 2), center[0], progress),
                           self.adjust_pos(position[1] + (note_size // 2), center[1], progress),
                           (alpha << 24) | (int(color_part * (((color & 0xFF0000) >> 16) / 0xFF)) << 16) |
                           (int((color_part * (((color & 0xFF00) >> 8)) / 0xFF)) << 8) |
                           int((color_part * (color & 0xFF)) / 0xFF), thickness=(note_size // 8) * v)
