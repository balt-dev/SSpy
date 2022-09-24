import glob
import os
import traceback

import cv2
import imgui_datascience.imgui_cv as imgui_cv
import numpy as np
import glfw
import OpenGL.GL as GL

import imgui

from pathlib import Path

from PIL import Image
from pydub import AudioSegment

from src.level import Level

with Image.open("assets/nocover.png") as im:
    NO_COVER = cv2.cvtColor(np.array(im.convert("RGBA")), cv2.COLOR_RGB2BGR)


class Editor:
    def __init__(self):
        self.level_window_size = (200, 200)
        self.filename = None
        self.temp_filename = "out.sspm"
        self.files = None
        self.file_choice = -1
        self.current_folder = str(Path.resolve(Path(__file__).parent))
        self.level = None
        self.time = 0

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

    def start(self, window, impl, font):
        running = True
        while running:
            glfw.poll_events()

            impl.process_inputs()
            imgui.new_frame()

            overlay_draw_list = imgui.get_overlay_draw_list()
            io = imgui.get_io()
            io.config_resize_windows_from_edges = True
            with imgui.font(font):
                menu_choice = None
                if imgui.begin_main_menu_bar():
                    if imgui.begin_menu("File"):
                        if imgui.menu_item("New")[0]:
                            self.level = Level()
                            self.filename = None
                        if imgui.menu_item("Open...")[0]:
                            menu_choice = "file.open"
                        if imgui.menu_item("Save", enabled=(self.level is not None))[0]:
                            if self.filename is not None:
                                with open(self.filename, "wb+") as f:
                                    f.write(self.level.save())
                            else:
                                menu_choice = "file.saveas"
                        if imgui.menu_item("Save As...", enabled=self.level is not None)[0]:
                            if self.filename is not None:
                                self.temp_filename = self.filename
                            menu_choice = "file.saveas"
                        imgui.separator()
                        if imgui.menu_item("Quit")[0]:
                            return False
                        imgui.end_menu()
                    if imgui.begin_menu("Edit", self.level is not None):
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
                            self.level.id = (self.level.author.lower() + " " + self.level.name.lower()).replace(" ", "_")
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
                        imgui.end_menu()

                    imgui.end_main_menu_bar()
                if menu_choice == "file.open":
                    imgui.open_popup("file.open")
                    self.file_choice = 0
                if imgui.begin_popup("file.open"):
                    changed, value = self.open_file_dialog([".sspm"])
                    if changed:
                        self.filename = value
                        with open(value, "rb") as file:
                            self.level = Level.from_sspm(file)
                    imgui.end_popup()
                if menu_choice == "file.saveas":
                    imgui.open_popup("file.saveas")
                if imgui.begin_popup("file.saveas"):
                    changed, value = self.save_file_dialog()
                    if changed:
                        with open(value, "wb+") as file:
                            file.write(self.level.save())
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
                if self.level is not None:
                    size = io.display_size
                    imgui.set_next_window_size(size[0], size[1] - 26)
                    imgui.set_next_window_position(0, 26)
                    if imgui.core.begin("Level",
                                        flags=imgui.WINDOW_NO_MOVE | imgui.WINDOW_NO_COLLAPSE | imgui.WINDOW_NO_TITLE_BAR | imgui.WINDOW_NO_RESIZE):
                        if imgui.begin_child("nodrag", 0, 0, False, ):
                            draw_list = imgui.get_window_draw_list()
                            x, y = imgui.get_window_position()
                            w, h = imgui.get_content_region_available()
                            draw_list.add_rect_filled(x, y, x + w, y + h, 0xff000000)
                            # square_x =
                            draw_list.add_rect_filled(x, y, x + w, y + h, 0xff000000)
                        imgui.end_child()
                        size = min(imgui.get_window_width(), imgui.get_window_height() - 26)
                        imgui.end()
                keys = tuple(io.keys_down)  # this could've been a bitfield!
                try:
                    print(keys.index(1))
                except:
                    pass

            GL.glClearColor(0., 0., 0., 1)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)

            imgui.render()
            impl.render(imgui.get_draw_data())
            glfw.swap_buffers(window)

            if glfw.window_should_close(window):
                return False
