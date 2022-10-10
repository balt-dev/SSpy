import ctypes
from functools import lru_cache
import glob
import math
from multiprocessing.sharedctypes import Value
import os
import time
from timeit import timeit
import traceback
from io import BytesIO
import webbrowser
import cProfile
import pstats

import numpy as np
import sdl2
import OpenGL.GL as GL

import imgui

from pathlib import Path

from PIL import Image
from pydub import AudioSegment
from pydub.playback import _play_with_simpleaudio
from pydub.exceptions import TooManyMissingFrames

from src.level import Level

"""
In case you aren't aware:
Codetags are a way of commenting that shows what the developer was doing at the time.
Here's a list of the ones supported by VSCode:
    NOTE: Description of how the code works (when it isn't self evident).
    XXX: Warning about possible pitfalls.
    HACK: Not very well written or malformed code to circumvent a problem/bug.
    FIXME: This works, sort of, but it could be done better. (usually code written in a hurry that needs rewriting).
    BUG: There's a problem here.
    TODO: No problem, but additional code needs to be written, usually used when skipping something.
"""
# Initialize constants

DIFFICULTIES: tuple = ("Unspecified", "Easy", "Medium", "Hard", "LOGIC?", "Tasukete")
HITSOUND = AudioSegment.from_file("assets/hit.wav").set_sample_width(2)
METRONOME_M = AudioSegment.from_file("assets/metronome_measure.wav").set_sample_width(2)
METRONOME_B = AudioSegment.from_file("assets/metronome_beat.wav").set_sample_width(2)


def speed_change(sound, speed=1.0):
    if speed < 0:
        sound = sound.reverse()
    sound_with_altered_frame_rate = sound._spawn(sound.raw_data, overrides={
        "frame_rate": int(sound.frame_rate * abs(speed))
    })
    return sound_with_altered_frame_rate.set_frame_rate(sound.frame_rate)


def play_at_position(audio, position):
    try:
        cut_audio = audio[int(position * 1000):]
    except TooManyMissingFrames:
        return None
    return _play_with_simpleaudio(cut_audio)


def adjust(x, s): return (((round(((x) / 2) * (s - 1)) / (s - 1)) * 2)) if s != 0 else x

# NOTE: https://www.desmos.com/calculator/8akx7lcdxq


def adjust_swing(beat, s):
    b = (beat % 2)
    if b < (2 * s):
        return (beat - b) + (((2 - 2 * s) / (2 * s)) * b)
    else:
        return (beat - b) + (((2 * s) / (2 - 2 * s)) * (b - 2 * s) + 2 - 2 * s)


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
        self.time_signature = (4, 4)
        self.note_snapping = 3, 3
        self.cover_id = None
        self.draw_notes = True
        self.draw_audio = True
        self.fps_cap = 100
        self.vsync = False
        self.rects_drawn = 0
        self.volume = 0
        self.waveform_res = 4
        self.timeline_height = 50
        self.hitsound_offset = 0
        self.metronome = False
        self.cursor = True
        self.colors = []
        # Read colors from file
        if os.path.exists("colors.txt"):
            with open("colors.txt", "r") as f:
                for line in f.read().splitlines():
                    color = int(line[1:], base=16)
                    if color <= 0xFFFFFF:
                        color = color | 0xFF000000
                    # ARGB -> ABGR
                    r, g, b, a = (color & 0xFF), ((color >> 8) & 0xFF), ((color >> 16) & 0xFF), ((color >> 24) & 0xFF)
                    color = a << 24 | r << 16 | g << 8 | b
                    self.colors.append(color)
        else:
            with open("colors.txt", "w") as f:
                f.write("#FFFFFFFF")
            self.colors = [0xFFFFFFFF]
        self.swing = 0.5
        self.hitsound_panning = 1.0
        self.vis_map_size = 3
        self.audio_speed = 1

    def file_display(self, extensions):
        """Create a file select window."""
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
            self.temp_filename = "out.sspm"
            return True, os.path.join(self.current_folder, self.filename)
        return False, None

    def keys(self):
        return tuple(self.io.keys_down)

    def time_scroll(self, y, keys):
        if self.level is not None:
            # Check modifier keys
            use_bpm = not (keys[sdl2.SDL_SCANCODE_LALT] or keys[sdl2.SDL_SCANCODE_RALT]) and (
                self.bpm != 0)  # If either alt key is pressed, or there's no bpm markers to base it off of
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
                self.playback = play_at_position(speed_change(self.level.audio + self.volume, self.audio_speed), (self.time) / 1000)
            if self.playing:
                self.starting_position += self.time - old_time

    def create_image(self, im, tex_id) -> int:
        texture_data = im.convert("RGBA").tobytes()  # Get the image's raw data for GL
        # Bind and set the texture at the id
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex_id)
        GL.glClearColor(0, 0, 0, 0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, im.size[0], im.size[1], 0, GL.GL_RGBA,
                        GL.GL_UNSIGNED_BYTE, texture_data)
        return tex_id  # NOTE: returning it makes things easier

    def start(self, window, impl, font, *_):
        self.io = imgui.get_io()

        event = sdl2.SDL_Event()

        # Initialize variables
        running = True
        old_audio = None
        audio_data = None
        space_last = False
        was_playing = False
        level_was_hovered = False
        source_code_was_open = False
        was_resizing_timeline = False
        last_hitsound_times = np.zeros((0), dtype=np.int64)
        old_mouse = (0, 0, 0, 0, 0)
        old_beat = 0
        tex_ids = GL.glGenTextures(3)  # NOTE: Update this when you add more images
        self.cover_id = int(tex_ids[0])
        note_offset = None
        old_keys = self.keys()
        cursor_positions = [[0, 0]]
        # Load constant textures
        with Image.open("assets/nocover.png") as im:
            NO_COVER = im.copy()
            COVER_ID = self.create_image(NO_COVER, int(tex_ids[0]))
        with Image.open("assets/github.png") as im:
            GITHUB_ICON_ID = self.create_image(im, int(tex_ids[1]))
        while running:
            self.rects_drawn = 0
            dt = time.perf_counter_ns()
            # Check if the audio data needs to be updated
            if self.level is not None:
                if self.level.audio is not None:
                    if hash(self.level.audio) != old_audio:
                        audio_data = np.array(self.level.audio.get_array_of_samples())
                        old_audio = hash(self.level.audio)
            impl.process_inputs()
            imgui.new_frame()
            keys = self.keys()
            mouse = tuple(self.io.mouse_down)
            # Check if the song needs to be paused/played
            if keys[sdl2.SDLK_SPACE] and self.level is not None:
                if not old_keys[sdl2.SDLK_SPACE]:
                    self.playing = not self.playing
                space_last = True
            elif space_last:
                space_last = False
            if self.playing and not was_playing:
                if self.level.audio is not None:
                    self.playback = play_at_position(speed_change(self.level.audio + self.volume, self.audio_speed), ((self.time) / 1000) / self.audio_speed)
                self.starting_time = time.perf_counter_ns()
                self.starting_position = self.time
            elif not self.playing and was_playing:
                if self.playback is not None:
                    del self.starting_time  # NOTE: Deleting these variables when they're not needed makes it easier to figure out that
                    del self.starting_position  # these are being accessed when they shouldn't be.
                    self.playback.stop()
                    self.playback = None
                if self.bpm:
                    # Snap the current time to the nearest quarter of a beat, for easier scrolling through
                    # TODO: make this snap with swing
                    ms_per_beat = (60000 / self.bpm) * (4 / self.time_signature[1])
                    step = (ms_per_beat) / 4
                    self.time = ((self.time // step) * (step)) + self.offset
            # Fix playback not working when playing in reverse (speed < 0)
            # This keeps going until it's being played
            if (self.playing
                and self.playback is None
                and self.level.audio is not None
                    and self.time / 1000 <= self.level.audio.duration_seconds):
                self.playback = play_at_position(speed_change(self.level.audio + self.volume, self.audio_speed), ((self.time) / 1000) / self.audio_speed)
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
                    if event.type == sdl2.SDL_MOUSEWHEEL and level_was_hovered and not self.playing:
                        self.time_scroll(event.wheel.y, keys)
                    impl.process_event(event)
                menu_choice = None
                # Handle file keybinds
                if keys[sdl2.SDL_SCANCODE_LCTRL] or keys[sdl2.SDL_SCANCODE_RCTRL]:
                    if keys[sdl2.SDLK_n] and not old_keys[sdl2.SDLK_n]:
                        # CTRL + N : New
                        self.level = Level()
                        self.filename = None
                        self.playing = False
                        self.last_saved_hash = None
                        self.time = 0
                    if keys[sdl2.SDLK_o] and not old_keys[sdl2.SDLK_o]:
                        # CTRL + O : Open...
                        menu_choice = "file.open"
                    if keys[sdl2.SDLK_s] and not old_keys[sdl2.SDLK_s]:
                        # CTRL + S : Save / CTRL + SHIFT + S : Save As...
                        if self.filename is not None and not keys[sdl2.SDL_SCANCODE_LSHIFT]:
                            buf = self.level.save()
                            with open(self.filename, "wb+") as file:
                                file.write(buf)
                            # Check for corruption
                            with open(self.filename, "rb") as file:
                                if file.read() != buf:
                                    print("!!!!!!! FILE DID NOT SAVE CORRECTLY.")
                                else:
                                    print("Saved!")
                                    self.last_saved_hash = hash(self.level)
                        else:
                            menu_choice = "file.saveas"
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
                                buf = self.level.save()
                                with open(self.filename, "wb+") as file:
                                    file.write(buf)
                                # Check for corruption
                                with open(self.filename, "rb") as file:
                                    if file.read() != buf:
                                        print("!!!!!!! FILE DID NOT SAVE CORRECTLY.")
                                    else:
                                        print("Saved!")
                                        self.last_saved_hash = hash(self.level)
                            else:
                                menu_choice = "file.saveas"
                        if imgui.menu_item("Save As...", "ctrl + shift + s", enabled=self.level is not None)[0]:
                            if self.filename is not None:
                                self.temp_filename = self.filename
                            menu_choice = "file.saveas"
                        imgui.separator()
                        if imgui.menu_item("Quit", "alt + f4")[0]:
                            self.playing = False
                            if self.last_saved_hash == hash(self.level) or (
                                    self.filename is not None and self.last_saved_hash is None):
                                running = False
                            else:
                                menu_choice = "quit.ensure"  # NOTE: The quit menu won't open if I don't do this from here
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
                        clicked = imgui.image_button(self.cover_id, 192, 192, frame_padding=0)
                        if clicked:
                            menu_choice = "edit.cover"
                        if imgui.is_item_hovered():
                            imgui.set_tooltip("Click to set a cover.")
                        clicked = imgui.button("Remove Cover")
                        if clicked:
                            self.create_image(NO_COVER, COVER_ID)  # Remove the cover
                        imgui.separator()
                        if self.level.audio is None:
                            imgui.text("/!\\ Map has no audio")
                        clicked = imgui.button("Change song")
                        if clicked:
                            menu_choice = "edit.song"
                        imgui.pop_item_width()
                        imgui.end_menu()
                    if imgui.begin_menu("Preferences", self.level is not None):
                        imgui.push_item_width(120)
                        changed, value = imgui.checkbox("Vsync?", self.vsync)
                        if changed:
                            sdl2.SDL_GL_SetSwapInterval(int(value))  # Turn on/off VSync
                            self.vsync = value
                        if not self.vsync:
                            imgui.indent()
                            changed, value = imgui.slider_int("FPS Cap", self.fps_cap, 15, 360)
                            if changed:
                                self.fps_cap = value
                            imgui.unindent()
                        changed, value = imgui.checkbox("Draw notes on timeline?", self.draw_notes)
                        if changed:
                            self.draw_notes = value
                        changed, value = imgui.checkbox("Draw audio on timeline?", self.draw_audio)
                        if changed:
                            self.draw_audio = value
                        if self.draw_audio:
                            imgui.indent()
                            changed, value = imgui.slider_int("Waveform resolution (px)", self.waveform_res, 1, 20)
                            if changed:
                                self.waveform_res = value
                            imgui.unindent()
                        imgui.separator()
                        changed, value = imgui.input_float("BPM", self.bpm, 0)
                        if changed:
                            self.bpm = value
                        if imgui.is_item_hovered():
                            imgui.set_tooltip("Set to 0 to turn off beat snapping.")
                        if self.bpm != 0:
                            imgui.indent()
                            changed, value = imgui.input_int("Offset (ms)", self.offset, 0)
                            if changed:
                                self.offset = value
                            changed, value = imgui.checkbox("BPM markers?", self.bpm_markers)
                            if changed:
                                self.bpm_markers = value
                            changed, value = imgui.checkbox("Metronome?", self.metronome)
                            if changed:
                                self.metronome = value
                            changed, value = imgui.input_float("Swing", self.swing, 0)
                            if changed:
                                self.swing = min(max(0.001, value), 0.999)
                            imgui.unindent()
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
                        else:
                            imgui.push_item_width(49)
                        imgui.separator()
                        # Display note snapping
                        changed, value = imgui.input_int("##", self.note_snapping[0], 0)
                        if changed:
                            self.note_snapping = (min(96, max(value, 0)) if value != 1 else 0, self.note_snapping[1])
                        if imgui.is_item_hovered():
                            imgui.set_tooltip("Set to 0 to turn off snapping.")
                        imgui.same_line()
                        imgui.text("/")
                        imgui.same_line()
                        changed, value = imgui.input_int("Note snapping", self.note_snapping[1], 0)
                        if changed:
                            self.note_snapping = (self.note_snapping[0], min(96, max(value, 0)) if value != 1 else 0)
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
                            changed, value = imgui.slider_float("Volume (db)", self.volume, -100, 10, "%.1f", 1.2)
                            if changed:
                                self.volume = value
                                # Change the volume of the song if it's playing
                                if self.playback is not None:
                                    self.playback.stop()
                                    self.playback = play_at_position(speed_change(self.level.audio + self.volume, self.audio_speed), (self.time) / 1000)
                        if not self.playing:  # NOTE: If I don't stop it from being changed while playing, wacky shit happens and self.time gets set to NaN somehow. No thanks.
                            changed, value = imgui.input_float("Playback Speed", self.audio_speed, 0, format="%.2f")
                            if changed:
                                self.audio_speed = value if value != 0 else 1
                        changed, value = imgui.checkbox("Play hitsounds?", self.hitsounds)
                        if changed:
                            self.hitsounds = value
                        if self.hitsounds:
                            imgui.indent()
                            changed, value = imgui.input_int("Hitsound offset (ms)", self.hitsound_offset, 0)
                            if changed:
                                self.hitsound_offset = value
                            changed, value = imgui.slider_float("Hitsound panning", self.hitsound_panning, -1, 1, "%.2f")
                            if changed:
                                self.hitsound_panning = value
                            imgui.unindent()
                        imgui.separator()
                        changed, value = imgui.checkbox("Show cursor?", self.cursor)
                        if changed:
                            self.cursor = value
                        changed, value = imgui.input_int("Map Size", self.vis_map_size, 0)
                        if changed:
                            self.vis_map_size = value
                        imgui.pop_item_width()
                        imgui.end_menu()
                    if imgui.begin_menu("Tools", self.level is not None):
                        clicked = imgui.button("Offset Notes")
                        if clicked:
                            menu_choice = "tools.offset_notes"
                        imgui.end_menu()
                    source_code_was_open = imgui.core.image_button(GITHUB_ICON_ID, 26, 26, frame_padding=0)
                    if source_code_was_open:
                        webbrowser.open("https://github.com/balt-is-you-and-shift/SSpy", 2, autoraise=True)
                        source_code_was_open = False
                    imgui.end_main_menu_bar()
                # Handle popups
                if menu_choice is not None:
                    imgui.open_popup(menu_choice)
                    if menu_choice == "file.open":
                        self.file_choice = 0
                if imgui.begin_popup("file.open"):
                    # Open a file dialog
                    changed, value = self.open_file_dialog([".sspm"])
                    if changed:
                        self.filename = value
                        with open(value, "rb") as file:
                            # Read the level from the file and load it
                            self.level = Level.from_sspm(file)
                        # Initialize song variables
                        self.create_image(NO_COVER if self.level.cover is None else self.level.cover.resize((192, 192), Image.NEAREST), COVER_ID)
                        self.time = 0
                        self.playing = False
                        self.playback = None
                    imgui.end_popup()
                if imgui.begin_popup("file.saveas"):
                    changed, value = self.save_file_dialog()
                    if changed:
                        buf = self.level.save()
                        with open(value, "wb+") as file:
                            file.write(buf)
                        # Check for corruption
                        with open(value, "rb") as file:
                            if file.read() != buf:
                                print("!!!!!!! FILE DID NOT SAVE CORRECTLY. DO NOT CLOSE THE APP YET.")
                            else:
                                print("Saved!")
                                self.last_saved_hash = hash(self.level)
                        imgui.close_current_popup()
                    imgui.end_popup()
                if imgui.begin_popup("edit.cover"):
                    # Load the selected image
                    changed, value = self.open_file_dialog([".png", ".jpg", ".bmp", ".gif"])
                    if changed:
                        with Image.open(value) as im:
                            self.level.cover = im.copy()
                            self.create_image(self.level.cover, COVER_ID)
                    imgui.end_popup()
                if imgui.begin_popup("edit.song"):
                    # Load the selected audio
                    changed, value = self.open_file_dialog([".mp3", ".ogg", ".wav", ".flac", ".opus"])
                    if changed:
                        self.level.audio = AudioSegment.from_file(value).set_sample_width(2)
                    imgui.end_popup()
                if imgui.begin_popup("quit.ensure"):
                    imgui.text("You have unsaved changes!")
                    imgui.text("Are you sure you want to exit?")
                    if imgui.button("Quit"):
                        return False
                    imgui.same_line(spacing=10)
                    if imgui.button("Cancel"):
                        imgui.close_current_popup()
                    imgui.end_popup()
                if imgui.begin_popup("tools.offset_notes"):
                    imgui.text("Offset all notes by a specified value.")
                    imgui.text("Current Time - Offset = New Time")
                    if note_offset is None:
                        note_offset = 0
                    changed, value = imgui.input_int("Offset", note_offset, 0)
                    if changed:
                        note_offset = value
                    if imgui.button("Cancel"):
                        imgui.close_current_popup()
                    imgui.same_line(spacing=10)
                    if imgui.button("Confirm"):
                        imgui.text("Working...")
                        # FIXME: this code kinda sucks
                        new_notes = {}
                        for timing, pos in self.level.notes.items():
                            new_notes[timing - note_offset] = pos
                        self.level.notes = new_notes
                        note_offset = None
                        imgui.close_current_popup()
                    imgui.end_popup()

                if self.level is not None:
                    size = self.io.display_size
                    imgui.set_next_window_size(size[0], size[1] - 26)
                    imgui.set_next_window_position(0, 26)
                    mouse_pos = tuple(self.io.mouse_pos)
                    imgui.push_style_var(imgui.STYLE_WINDOW_PADDING, (0, 0))
                    if imgui.core.begin("Level",
                                        flags=imgui.WINDOW_NO_MOVE | imgui.WINDOW_NO_COLLAPSE | imgui.WINDOW_NO_TITLE_BAR | imgui.WINDOW_NO_RESIZE | imgui.WINDOW_NO_BRING_TO_FRONT_ON_FOCUS):
                        x, y = imgui.get_window_position()
                        w, h = imgui.get_content_region_available()
                        if imgui.begin_child("nodrag", 0, 0, False, ):
                            draw_list = imgui.get_window_draw_list()
                            timeline_width = max(self.level.get_end() + 1000, self.time + self.approach_rate, 1)
                            # Draw the main UI background
                            square_side = min(w - self.timeline_height, h - self.timeline_height)
                            draw_list.add_rect_filled(x, y, x + w, y + h, 0xff080808)
                            adjusted_x = (((x + w) / 2) - (square_side / 2))
                            draw_list.add_rect_filled(adjusted_x, y, adjusted_x + square_side, y + square_side,
                                                      0xff000000)
                            draw_list.add_rect_filled(x, (y + h) - self.timeline_height, x + w, (y + h), 0x20ffffff)
                            self.rects_drawn += 3

                            times_to_display = self.level.get_notes()
                            if (self.level.audio is not None and audio_data is not None
                                    and self.draw_audio and self.timeline_height > 20):
                                center = (y + h) - (self.timeline_height / 2)
                                length = int(self.level.audio.frame_rate * timeline_width / 1000)
                                extent = np.max(np.abs(audio_data))
                                waveform_width = int(
                                    size[0])
                                # Draw waveform
                                # FIXME: it'd be nice if this wasn't a python loop
                                for n in range(0, waveform_width, self.waveform_res):
                                    try:
                                        # Slice a segment of audio
                                        sample = audio_data[math.floor((n / waveform_width) * length * 2): math.floor(((n + 1) / waveform_width) * length * 2)]
                                        if (np.max(sample) != np.min(sample)):
                                            draw_list.add_rect_filled(x + int((w / waveform_width) * n),
                                                                      center + int((np.max(sample) / extent) * (self.timeline_height // 2)),
                                                                      x + int((w / waveform_width) * n) + self.waveform_res,
                                                                      center + int((np.min(sample) / extent) * (self.timeline_height // 2)), 0x20ffffff)
                                            self.rects_drawn += 1
                                    except (IndexError, ValueError):
                                        break
                            if self.draw_notes:
                                # Draw notes
                                for i, note in enumerate(times_to_display):
                                    color = (self.colors[i % len(self.colors)] & 0xFFFFFF) | 0x40000000
                                    progress = note / timeline_width
                                    progress = progress if not math.isnan(progress) else 1
                                    draw_list.add_rect_filled(x + int(w * progress), (y + h) - self.timeline_height,
                                                              x + int(w * progress) + 1, (y + h),
                                                              color)
                                    self.rects_drawn += 1
                            # Draw currently visible area on timeline
                            start = (self.time) / timeline_width
                            end = (self.time + self.approach_rate) / timeline_width
                            draw_list.add_rect(x + int(w * start), (y + h) - self.timeline_height, x + int(w * end) + 1,
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
                                y + h - (self.timeline_height + 20), 0x80FFFFFF, f"{self.time / 1000:.3f}")
                            if self.bpm:
                                # Draw the current measure and beat
                                ms_per_beat = (60000 / self.bpm) * (4 / self.time_signature[1])
                                raw_current_beat = (self.time - self.offset) / (ms_per_beat)
                                current_beat = adjust_swing(raw_current_beat, self.swing)
                                m_text = f"Measure {current_beat // self.time_signature[0]:.0f}"
                                draw_list.add_text(
                                    center_of_view(m_text),
                                    y + h - (self.timeline_height + 60), 0x80FFFFFF, m_text)
                                b_text = f"Beat {f'{current_beat % self.time_signature[0]:.2f}'.rstrip('0').rstrip('.')}"
                                draw_list.add_text(
                                    center_of_view(b_text),
                                    y + h - (self.timeline_height + 40), 0x80FFFFFF, b_text)

                                floor_beat = math.floor(raw_current_beat)
                                # Play the metronome
                                if self.metronome and self.playing:
                                    beat_skipped = floor_beat - math.floor(old_beat)
                                    if beat_skipped:
                                        if old_beat // self.time_signature[0] != current_beat // self.time_signature[0]:  # If a measure has passed
                                            _play_with_simpleaudio(METRONOME_M)
                                        else:
                                            _play_with_simpleaudio(METRONOME_B)
                                old_beat = current_beat

                                if self.bpm_markers:
                                    # Draw beat markers in note space
                                    position = (adjusted_x + adjusted_x + square_side) // 2, (
                                        y + y + square_side) // 2
                                    offset_time = self.time + self.offset
                                    line_prog = 0
                                    index = -1
                                    if self.bpm > 0:
                                        while line_prog < 1:  # NOTE: This used to be a for loop, but it wasn't going far enough. I decided to just keep going until it hit the camera.
                                            representing_beat = floor_beat - (index) + math.ceil(self.approach_rate / ms_per_beat)  # What beat this marker represents (NOTE: took me a week to figure out how to find this ._.)
                                            decimal_beat = ((index) + ((offset_time % ms_per_beat) / ms_per_beat))
                                            if self.swing != 0.5:
                                                decimal_beat += adjust_swing(representing_beat, self.swing) - representing_beat
                                            line_prog = ((decimal_beat * ms_per_beat) / (self.approach_rate))  # Distance betweeen the edge of view and the camera
                                            if line_prog > 1:
                                                break
                                            draw_list.add_rect(
                                                self.adjust_pos(position[0] - (square_side // 2), position[0], line_prog),
                                                self.adjust_pos(position[1] - (square_side // 2), position[1], line_prog),
                                                self.adjust_pos(position[0] + (square_side // 2), position[0], line_prog),
                                                self.adjust_pos(position[1] + (square_side // 2), position[1], line_prog),
                                                0xFF000000 | int(0xFF * max(0, line_prog) / (2 if representing_beat % self.time_signature[0] else 1)),
                                                thickness=2 * max(0, line_prog) * (2 if not representing_beat % self.time_signature[0] else 1)
                                            )
                                            self.rects_drawn += 1
                                            index += 1

                                    # Draw beat markers on timeline
                                    for beat in range(min(math.ceil(timeline_width / ms_per_beat), 10000)):
                                        on_measure = beat % self.time_signature[0] == 0
                                        beat = adjust_swing(beat, 1 - self.swing)
                                        beat_time = (beat * ms_per_beat) + self.offset
                                        progress = beat_time / timeline_width
                                        progress = progress if not math.isnan(progress) else 1
                                        draw_list.add_rect_filled(x + int(w * progress), (y + h) - self.timeline_height,
                                                                  x + int(w * progress) + 1, (y + h),
                                                                  0xff0000ff if on_measure else 0x800000ff)
                                        self.rects_drawn += 1

                            # FIXME: Copy the times display for hitsound offsets
                            hitsound_times = times_to_display[np.logical_and(times_to_display >= self.time + self.hitsound_offset - 1,
                                                                             (times_to_display) < (
                                                                                 self.time + self.approach_rate + self.hitsound_offset))].flatten()

                            note_times = times_to_display[np.logical_and(times_to_display >= self.time - 1,
                                                                         (times_to_display) < (
                                                                             self.time + self.approach_rate))].flatten()
                            for note_time in note_times[::-1]:
                                i = np.where(times_to_display == note_time)[0][0]
                                for note in self.level.notes[note_time]:
                                    rgba = self.colors[i % len(self.colors)]
                                    rgb, a = rgba & 0xFFFFFF, (rgba & 0xFF000000) >> 24
                                    progress = 1 - ((note_time - self.time) / self.approach_rate)
                                    self.draw_note(draw_list, note,
                                                   (adjusted_x, y, adjusted_x + square_side, y + square_side), progress,
                                                   color=rgb, alpha=a)
                                    self.rects_drawn += 1

                            # Play note hit sound
                            if self.playing and self.hitsounds:
                                if ((last_hitsound_times.size and
                                        np.min(last_hitsound_times) < self.time + self.hitsound_offset - 1)):
                                    notes = self.level.notes[np.min(last_hitsound_times)]
                                    for note in notes[:8]:
                                        pos = note[0] - 1
                                        panning = pos * self.hitsound_panning
                                        _play_with_simpleaudio(HITSOUND.pan(min(max(panning, -1), 1)))
                            last_hitsound_times = hitsound_times

                            level_was_hovered = imgui.is_window_hovered()
                            if ((adjusted_x <= mouse_pos[0] < adjusted_x + square_side) and
                                    (y <= mouse_pos[1] < y + square_side)) and level_was_hovered:
                                # Note placing and deleting
                                note_pos = ((((mouse_pos[0] - (adjusted_x)) / (square_side)) * self.vis_map_size) - (self.vis_map_size / 2) + 1,
                                            (((mouse_pos[1] - (y)) / (square_side)) * self.vis_map_size) - (self.vis_map_size / 2) + 1)
                                time_arr = np.array(tuple(self.level.notes.keys()))
                                time_arr = time_arr[
                                    np.logical_and(time_arr - self.time >= -1, time_arr - self.time < 10)]
                                closest_time = np.min(time_arr) if time_arr.size > 0 else self.time
                                closest_index = None
                                closest_dist = None
                                # Note deletion
                                if mouse[1] and not old_mouse[1]:
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
                                    if mouse[0] and not old_mouse[0]:
                                        if int(self.time) in self.level.notes:
                                            self.level.notes[int(self.time)].append(note_pos)
                                        else:
                                            self.level.notes[int(self.time)] = [note_pos]
                            # Draw cursor
                            if self.cursor and len(self.level.notes) > 0:
                                notes = self.level.get_notes()
                                start = np.max(notes[notes - max(int(self.time), np.min(notes)) <= 0])
                                try:
                                    end = np.min(notes[notes - int(self.time) > 0])
                                except ValueError:
                                    end = start
                                if (end - start):
                                    progress = (self.time - start) / (end - start)
                                    start_pos = np.array(self.level.notes[start]).reshape(-1, 2).mean(0)
                                    end_pos = np.array(self.level.notes[end]).reshape(-1, 2).mean(0)
                                    # FIXME: this is copied from draw_note and kinda sucks ass
                                    box = (adjusted_x, y, adjusted_x + square_side, y + square_side)
                                    center = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                                    spacing = ((box[2] - box[0]) / self.vis_map_size)
                                    def position(pos): return [center[0] + ((pos[0] - 1) * spacing), center[1] + ((pos[1] - 1) * spacing)]

                                    def ease_out_cubic(a, b, t):
                                        return (a * (((1 - t) ** 3))) + (b * (1 - ((1 - t) ** 3)))

                                    def ease_in_cubic(a, b, t):
                                        return ease_out_cubic(b, a, 1 - t)

                                    def ease(a, b, t):
                                        return ease_out_cubic(a, b, t) if self.audio_speed > 0 else ease_in_cubic(a, b, t)
                                    cursor_positions = [position((ease_out_cubic(start_pos[0], end_pos[0], progress), ease_out_cubic(start_pos[1], end_pos[1], progress)))] + cursor_positions[:5]
                                    draw_list.add_circle_filled(*cursor_positions[0], spacing / 20, 0xFFFFFFFF, num_segments=32)
                                else:
                                    cursor_positions = cursor_positions[1:]
                                if len(cursor_positions) > 1:
                                    draw_list.add_polyline(cursor_positions[1:], 0x40FFFFFF, thickness=spacing / 20)

                            # Draw current statistics
                            fps_text = f"{int(self.io.framerate)}{f'/{self.fps_cap}' if not self.vsync else ''} FPS"
                            fps_size = imgui.calc_text_size(fps_text)
                            draw_list.add_text(w - fps_size.x - 4, y + 2, 0x80FFFFFF, fps_text)
                            rdtf_size = imgui.calc_text_size(f"{self.rects_drawn} rects drawn")
                            draw_list.add_text(w - rdtf_size.x - 4, y + fps_size.y + 2, 0x80FFFFFF,
                                               f"{self.rects_drawn} rects drawn")
                            self.rects_drawn = 0
                            imgui.end_child()
                        imgui.end()
                    imgui.pop_style_var(imgui.STYLE_WINDOW_PADDING)
                    # Resize the timeline when needed
                    if abs(((y + h) - mouse_pos[1]) - self.timeline_height) <= 5 or was_resizing_timeline:
                        draw_list.add_rect_filled(x, (y + h - 3) - self.timeline_height, x + w, (y + h + 2) - self.timeline_height, 0xffff8040)
                        was_resizing_timeline = False
                        if mouse[0]:
                            was_resizing_timeline = True
                            self.timeline_height = max(5, (y + h) - mouse_pos[1])

            old_mouse = mouse
            old_keys = keys
            GL.glClearColor(0., 0., 0., 1)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)
            imgui.render()
            impl.render(imgui.get_draw_data())
            sdl2.SDL_GL_SwapWindow(window)
            if self.playing:
                self.time = max(((time.perf_counter_ns() - self.starting_time) / (1000000 / self.audio_speed)) + self.starting_position, 0)
            was_playing = self.playing

            if not self.vsync:
                dt = (time.perf_counter_ns() - dt) / 1000000000
                time.sleep(max((1 / self.fps_cap) - dt, 0))

    def adjust_pos(self, cen, pos, progress):
        visual_size = 1 / (1 + ((1 - progress) * self.approach_distance))
        return (cen * visual_size) + (pos * (1 - visual_size))

    def draw_note(self, draw_list, note_pos, box, progress, color=0xFFFFFF, alpha=0xff):
        center = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        spacing = ((box[2] - box[0]) / self.vis_map_size)
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
