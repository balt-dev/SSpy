import ctypes
import glob
import math
import os
import time
import traceback

import cv2
import imgui_datascience.imgui_cv as imgui_cv
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
    NO_COVER = cv2.cvtColor(np.array(im.convert("RGBA")), cv2.COLOR_RGB2BGR)


def play_at_position(audio, position):
    audio = audio.set_sample_width(2)
    data = np.array(audio.get_array_of_samples())
    data = data[int(position * audio.frame_rate // 2) * 4:]
    cut_audio = audio._spawn(data=data.tobytes())
    return _play_with_simpleaudio(cut_audio)


class Editor:
    def __init__(self):
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

    def file_display(self, extensions):
        changed = False
        folder_changed, self.current_folder = imgui.input_text("Directory", self.current_folder, 65536)
        if folder_changed or not self.files:
            try:
                os.chdir(
                    Path.resolve(Path(self.current_folder))
                )
            except Exception:
                traceback.print_exc()
                os.chdir(Path.resolve(Path(__file__).parent))
            self.current_folder = os.getcwd()
            changed = True
        if changed:
            pass
        self.files = ['..']
        for extension in extensions:
            self.files.extend(sorted([f[2:] for f in glob.glob("./*" + extension)]))
        self.files.extend(sorted(
            [f[2:] for f in glob.glob(
                "./*" + os.sep)]))
        clicked, self.file_choice = imgui.listbox("Levels", self.file_choice,
                                                  [path for path in self.files])
        return clicked

    def open_file_dialog(self, extensions: list[str]):
        clicked = self.file_display(extensions)
        if clicked:
            for extension in extensions:
                if self.files[self.file_choice].endswith(extension):
                    imgui.close_current_popup()
                    return (True, self.files[self.file_choice])
            self.current_folder = str(Path(os.path.join(self.current_folder, self.files[self.file_choice])).resolve())
            self.file_choice = 0
            os.chdir(os.path.expanduser(self.current_folder))
        return False, None

    def save_file_dialog(self):
        clicked = self.file_display(["*.sspm"])
        if clicked:
            path = Path(os.path.join(self.current_folder, self.files[self.file_choice])).resolve()
            if path.is_file():
                self.temp_filename = path.stem + path.suffix
            else:
                self.current_folder = str(path)
            self.file_choice = 0
            os.chdir(os.path.expanduser(self.current_folder))
        changed, value = imgui.input_text("Filename",
                                          self.temp_filename,
                                          128)
        if changed:
            self.temp_filename = value
        if imgui.button("Save"):
            self.filename = self.temp_filename
            self.temp_filename = None
            return True, os.path.join(self.current_folder, self.filename)
        return False, None

    def time_scroll(self, y):
        if self.level is not None:
            if tuple(self.io.keys_down)[sdl2.SDL_SCANCODE_LSHIFT] or tuple(self.io.keys_down)[sdl2.SDL_SCANCODE_RSHIFT]:
                distance = 1
            elif tuple(self.io.keys_down)[sdl2.SDL_SCANCODE_LCTRL] or tuple(self.io.keys_down)[sdl2.SDL_SCANCODE_RCTRL]:
                distance = 16
            else:
                distance = 4
            delta = int((60 / self.bpm) * 1000)
            old_time = self.time
            if tuple(self.io.keys_down)[sdl2.SDL_SCANCODE_LALT] or tuple(self.io.keys_down)[sdl2.SDL_SCANCODE_RALT]:
                self.time = max(self.time + ((y * 4) / distance), 0)
            else:
                self.time = max(self.time + (y * delta / distance), 0)
            if self.playback is not None:
                self.playback.stop()
                self.playback = play_at_position(self.level.audio, self.time / 1000)
            if self.playing:
                self.starting_position += self.time - old_time

    def start(self, window, impl, font, gl_ctx):
        self.io = imgui.get_io()
        self.io.config_resize_windows_from_edges = True

        event = sdl2.SDL_Event()

        running = True
        old_audio = None
        audio_data = None
        space_last = False
        was_playing = False
        old_mouse = (0, 0, 0, 0, 0)
        while running:
            old_time = self.time
            if self.level is not None:
                if self.level.audio is not None:
                    if hash(self.level.audio) != old_audio:
                        audio_data = np.array(self.level.audio.get_array_of_samples(), dtype=np.int16)
                        old_audio = hash(self.level.audio)
            impl.process_inputs()
            imgui.new_frame()
            keys = tuple(self.io.keys_down)
            if keys[32] and self.level is not None:  # Space
                if not space_last:
                    self.playing = not self.playing
                space_last = True
            elif space_last:
                space_last = False
            if self.playing and not was_playing:
                self.starting_time = time.perf_counter_ns()
                self.starting_position = self.time
                if self.level.audio is not None:
                    self.playback = play_at_position(self.level.audio, self.time / 1000)
            elif not self.playing and was_playing and self.playback is not None:
                del self.starting_time  # if these are accessed while self.playing is false then there's a problem anyways and this makes it easier to debug
                del self.starting_position
                self.playback.stop()
                self.playback = None
                if self.bpm != 0:
                    seconds_per_beat = 60 / self.bpm
                    self.time = int(self.time / (1000 * seconds_per_beat)) * (1000 * seconds_per_beat)  # snap to the nearest quarter step
                    # TODO: add irregular time support for bpm markers and scrolling
            was_playing = self.playing
            with imgui.font(font):
                while sdl2.SDL_PollEvent(ctypes.byref(event)) != 0:
                    if event.type == sdl2.SDL_QUIT:
                        self.playing = False
                        if self.last_saved_hash == hash(self.level):
                            running = False
                        else:
                            imgui.open_popup("quit.ensure")
                    if event.type == sdl2.SDL_MOUSEWHEEL:
                        self.time_scroll(event.wheel.y)
                    impl.process_event(event)
                menu_choice = None
                if imgui.begin_main_menu_bar():
                    if imgui.begin_menu("File"):
                        if imgui.menu_item("New")[0]:
                            self.level = Level()
                            self.filename = None
                            self.playing = False
                            self.last_saved_hash = None
                            self.time = 0
                        if imgui.menu_item("Open...")[0]:
                            menu_choice = "file.open"
                        if imgui.menu_item("Save", enabled=(self.level is not None))[0]:
                            if self.filename is not None:
                                with open(self.filename, "wb+") as f:
                                    f.write(self.level.save())
                                self.last_saved_hash = hash(self.level)
                            else:
                                menu_choice = "file.saveas"
                        if imgui.menu_item("Save As...", enabled=self.level is not None)[0]:
                            if self.filename is not None:
                                self.temp_filename = self.filename
                            menu_choice = "file.saveas"
                        imgui.separator()
                        if imgui.menu_item("Quit")[0]:
                            self.playing = False
                            if self.last_saved_hash == hash(self.level) or (self.filename is not None and self.last_saved_hash is None):
                                running = False
                            else:
                                menu_choice = "quit.ensure"  # won't open if i open it from here for whatever reason
                        imgui.end_menu()
                    if imgui.begin_menu("Edit", self.level is not None):
                        imgui.push_item_width(240)
                        changed, value = imgui.combo("Difficulty", self.level.difficulty + 1,
                                                     ["Unspecified", "Easy", "Medium", "Hard", "LOGIC?", "Tasukete"])
                        imgui.separator()
                        imgui.push_style_color(imgui.COLOR_TEXT, 0.7, 0.7, 0.7, 1)
                        _, _ = imgui.input_text("ID", self.level.id, 128,
                                                imgui.INPUT_TEXT_READ_ONLY)
                        imgui.pop_style_color()
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
                        if changed_a or changed_b:
                            self.level.id = (self.level.author.lower() + " " + self.level.name.lower()).replace(" ",
                                                                                                                "_")
                        imgui.separator()
                        if self.level.cover is not None:
                            imgui_cv.image(self.level.cover, width=150, height=150)
                        else:
                            imgui_cv.image(NO_COVER, width=150, height=150)
                        clicked = imgui.button("Cover (click to change)")
                        if clicked:
                            menu_choice = "edit.cover"
                        imgui.separator()
                        if self.level.audio is None:
                            imgui.text("/!\\ Map has no audio")
                        clicked = imgui.button("Change song")
                        if clicked:
                            menu_choice = "edit.song"
                        imgui.pop_item_width()
                        imgui.end_menu()
                    if imgui.begin_menu("Tools", self.level is not None):
                        changed, value = imgui.checkbox("BPM markers?", self.bpm_markers)
                        imgui.push_item_width(120)
                        if changed:
                            self.bpm_markers = value
                        if self.bpm_markers:
                            imgui.indent()
                            changed, value = imgui.input_int("Marker Offset (ms)", self.offset, 0)
                            if changed:
                                self.offset = value
                            imgui.unindent()
                        changed, value = imgui.input_int("BPM", self.bpm, 0)
                        if changed:
                            self.bpm = value
                        imgui.separator()
                        changed, value = imgui.slider_int("Approach Rate (ms)", self.approach_rate, 50, 2000)
                        if changed:
                            self.approach_rate = value
                        changed, value = imgui.slider_int("Spawn Distance (units)", self.approach_distance, 1, 100)  # , power=0.5) (can't do log on int sliders :P)
                        if changed:
                            self.approach_distance = value
                        imgui.separator()
                        if not self.playing:
                            changed, value = imgui.input_int("Position (ms)", self.time, 0)
                            if changed:
                                self.time = value
                        imgui.pop_item_width()
                        imgui.end_menu()
                    imgui.end_main_menu_bar()
                if menu_choice == "file.open":
                    imgui.open_popup("file.open")
                    self.file_choice = 0
                if imgui.begin_popup("file.open"):
                    changed, value = self.open_file_dialog([".sspm"])
                    if changed:
                        self.filename = value
                        try:
                            with open(value, "rb") as file:
                                self.level = Level.from_sspm(file)
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
                    changed, value = self.open_file_dialog([".png"])
                    if changed:
                        with Image.open(value) as im:
                            self.level.cover = cv2.cvtColor(np.array(im.convert("RGBA"), dtype=np.uint8),
                                                            cv2.COLOR_RGB2BGR)
                    imgui.end_popup()
                if menu_choice == "edit.song":
                    imgui.open_popup("edit.song")
                if imgui.begin_popup(
                        "edit.song"):  # i tried to cut some code repetition but i couldn't get rid of all of it
                    changed, value = self.open_file_dialog([".mp3", ".ogg"])
                    if changed:
                        self.level.audio = AudioSegment.from_file(value)
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
                            square_side = min(w - 50, h - 50)
                            draw_list.add_rect_filled(x, y, x + w, y + h, 0xff080808)
                            adjusted_x = (((x + w) / 2) - (square_side / 2))
                            draw_list.add_rect_filled(adjusted_x, y, adjusted_x + square_side, y + square_side,
                                                      0xff000000)
                            times_to_display = np.array(tuple(self.level.notes.keys()), dtype=np.uint32)
                            draw_list.add_rect_filled(x, (y + h) - 50, x + w, (y + h), 0x20ffffff)
                            ending_time = self.level.get_end()
                            if self.level.audio is not None and audio_data is not None:
                                center = (y + h) - 25
                                length = int(self.level.audio.frame_rate * (max(ending_time, self.time) / 1000))
                                extent = np.max(np.abs(audio_data))
                                waveform_width = int(size[0])  # somehow this isn't always an int???? idk it crashes when i remove it
                                for n in range(waveform_width):
                                    index = math.floor((n / waveform_width) * length * 2)
                                    try:
                                        sample = audio_data[index]
                                        draw_list.add_rect_filled(x + int((w / waveform_width) * n),
                                                                  center - int((sample / extent) * 25), x + int((w / waveform_width) * n) + 1,
                                                                  center + int((sample / extent) * 25), 0x20ffffff)
                                    except IndexError:
                                        break
                            for note in times_to_display:
                                progress = note / max(ending_time, self.time, 1)
                                progress = progress if not math.isnan(progress) else 1
                                draw_list.add_rect_filled(x + int(w * progress), (y + h) - 50,
                                                          x + int(w * progress) + 1, (y + h), 0x40ffffff)
                            start = (self.time) / max(ending_time, self.time, 1)
                            end = (self.time + self.approach_rate) / max(ending_time, self.time, 1)
                            draw_list.add_rect(x + int(w * start), (y + h) - 50, x + int(w * end) + 1,
                                               (y + h), 0x80ffffff, thickness=3)
                            if self.bpm_markers and self.bpm != 0:
                                # TODO: fix weirdness with short maps
                                seconds_per_beat = 60 / self.bpm
                                bpm_time = max(ending_time, self.time + (2000 * seconds_per_beat)) + int(self.offset % (1000 * seconds_per_beat))
                                beats = bpm_time / (1000 * seconds_per_beat)
                                for n in range(math.ceil(beats)):
                                    progress = (w / beats) * (n + ((self.offset / (1000 * seconds_per_beat)) % (1000 * seconds_per_beat)))
                                    draw_list.add_rect_filled(x + int(progress), (y + h) - 50,
                                                              x + int(progress) + 1, (y + h), 0x400000ff)
                                    beat_time = (n + ((self.offset / (1000 * seconds_per_beat)) % (1000 * seconds_per_beat))) * seconds_per_beat * 1000
                                    if beat_time >= self.time and beat_time < self.time + (self.approach_rate):
                                        line_prog = 1 - ((beat_time - self.time) / (self.approach_rate))
                                        position = (adjusted_x + adjusted_x + square_side) // 2, (y + y + square_side) // 2
                                        draw_list.add_rect(
                                            self.adjust_pos(position[0] - (square_side // 2), position[0], line_prog),
                                            self.adjust_pos(position[1] - (square_side // 2), position[1], line_prog),
                                            self.adjust_pos(position[0] + (square_side // 2), position[0], line_prog),
                                            self.adjust_pos(position[1] + (square_side // 2), position[1], line_prog),
                                            0xff000000 | int(0xFF * line_prog), thickness=int(4 * line_prog))

                            times_to_display = times_to_display[np.logical_and(times_to_display >= self.time,
                                                                               (times_to_display) < (
                                                                                   self.time + self.approach_rate))].flatten().tolist()
                            for note_time in times_to_display[::-1]:
                                for note in self.level.notes[note_time]:
                                    progress = 1 - ((note_time - self.time) / self.approach_rate)
                                    self.draw_note(draw_list, note,
                                                   (adjusted_x, y, adjusted_x + square_side, y + square_side), progress)
                            mouse_pos = tuple(self.io.mouse_pos)
                            if ((mouse_pos[0] >= adjusted_x and mouse_pos[0] < adjusted_x + square_side) and
                                    (mouse_pos[1] >= y and mouse_pos[1] < y + square_side)) and imgui.is_window_hovered():
                                note_pos = ((((mouse_pos[0] - adjusted_x) / square_side) * 3) - 0.5, (((mouse_pos[1] - y) / square_side) * 3) - 0.5)
                                time_arr = np.array(tuple(self.level.notes.keys()))
                                time_arr = time_arr[np.logical_and(time_arr - self.time >= 0, time_arr - self.time < 10)]
                                closest_time = np.min(time_arr) if time_arr.size > 0 else self.time
                                closest_index = None
                                closest_dist = None
                                if tuple(self.io.mouse_down)[1] and not old_mouse[1]:
                                    for i, note in enumerate(self.level.notes.get(closest_time, ())):
                                        if abs(note[0] - note_pos[0]) < 0.5 and abs(note[1] - note_pos[1]) < 0.5:
                                            if closest_dist is None:
                                                closest_index = i
                                                closest_dist = math.sqrt((abs(note[0] - note_pos[0])**2) + (abs(note[1] - note_pos[1])**2))
                                            elif closest_dist > (d := math.sqrt((abs(note[0] - note_pos[0])**2) + (abs(note[1] - note_pos[1])**2))):
                                                closest_dist = d
                                                closest_index = i
                                    if closest_index is not None:
                                        del self.level.notes[int(closest_time)][closest_index]
                                if closest_index is None:
                                    self.draw_note(draw_list, note_pos, (adjusted_x, y, adjusted_x + square_side, y + square_side), 1.0, color=0xffff00, alpha=0x40)
                                    if tuple(self.io.mouse_down)[0] and not old_mouse[0]:
                                        if int(self.time + 1) in self.level.notes:
                                            self.level.notes[int(self.time + 1)].append(note_pos)
                                        else:
                                            self.level.notes[int(self.time + 1)] = [note_pos]
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
