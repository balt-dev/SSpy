import glob
import os
import traceback

import cv2
import imgui_datascience.imgui_cv as imgui_cv
import numpy as np
import sdl2
import ctypes
import OpenGL.GL as GL

import imgui

from pathlib import Path

from PIL import Image

from src.level import Level


class Editor:
    def __init__(self):
        self.filename = None
        self.files = None
        self.file_choice = -1
        self.current_folder = str(Path.resolve(Path(__file__).parent))
        self.level = None

    def file_dialog(self, extensions: list[str]):
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
            self.files.extend(sorted([f[2:] for f in glob.glob("./*." + extension)]))
        self.files.extend(sorted(
            [f[2:] for f in glob.glob(
                "./*" + os.sep)]))
        clicked, self.file_choice = imgui.listbox("Levels", self.file_choice,
                                                  [path for path in self.files])
        if clicked:
            for extension in extensions:
                if self.files[self.file_choice].endswith("." + extension):
                    imgui.close_current_popup()
                    return (True, self.files[self.file_choice])
            self.current_folder = str(Path(os.path.join(self.current_folder, self.files[self.file_choice])).resolve())
            self.file_choice = 0
            os.chdir(os.path.expanduser(self.current_folder))
        return False, None

    def start(self, window, gl_ctx, impl):
        running = True
        event = sdl2.SDL_Event()
        while running:
            while sdl2.SDL_PollEvent(ctypes.byref(event)) != 0:
                if event.type == sdl2.SDL_QUIT:
                    running = False
                    break
                impl.process_event(event)
            impl.process_inputs()
            imgui.new_frame()

            overlay_draw_list = imgui.get_overlay_draw_list()
            io = imgui.get_io()

            menu_choice = None
            if imgui.begin_main_menu_bar():
                if imgui.begin_menu("File"):
                    if imgui.menu_item("New", "ctrl+n")[0]:
                        self.level = Level()
                        self.filename = None
                    if imgui.menu_item("Open...", "ctrl+o")[0]:
                        menu_choice = "file.open"
                    if imgui.menu_item("Save", "ctrl+s", enabled=(self.level is not None)):
                        ...
                    if imgui.menu_item("Save As...", "ctrl+shift+s", enabled=self.level is not None)[0]:
                        menu_choice = "file.saveas"
                    imgui.separator()
                    if imgui.menu_item("Quit")[0]:
                        return False
                    imgui.end_menu()
                if imgui.begin_menu("Edit", self.level is not None):
                    changed, value = imgui.combo("Difficulty", self.level.difficulty + 1,
                                                 ["Unspecified", "Easy", "Medium", "Hard", "LOGIC?", "Tasukete"])
                    if changed:
                        self.level.difficulty = value - 1
                    changed, value = imgui.input_text("Name", self.level.name, 128, imgui.INPUT_TEXT_AUTO_SELECT_ALL)
                    if changed:
                        self.level.name = value
                    changed, value = imgui.input_text("Author", self.level.author, 64, imgui.INPUT_TEXT_AUTO_SELECT_ALL)
                    if changed:
                        self.level.author = value
                    imgui.separator()
                    if self.level.cover is not None:
                        imgui_cv.image(self.level.cover, width=150, height=150)
                    else:
                        imgui_cv.image(np.full((200, 200, 3), 255, dtype=np.uint8), width=150, height=150,
                                       title="/!\\ No cover selected!")
                    clicked = imgui.button("Cover (click button to change)")
                    if clicked:
                        menu_choice = "edit.cover"
                    imgui.end_menu()
                imgui.end_main_menu_bar()
            if menu_choice == "file.open":
                imgui.open_popup("file.open")
                self.file_choice = 0
            if imgui.begin_popup("file.open"):
                changed, value = self.file_dialog(["sspm"])
                if changed:
                    with open(value, "rb") as file:
                        self.level = Level.from_sspm(file)
                    print(self.level)
                imgui.end_popup()
            if menu_choice == "edit.cover":
                imgui.open_popup("edit.cover")
            if imgui.begin_popup(
                    "edit.cover"):  # i tried to cut some code repetition but i couldn't get rid of all of it
                changed, value = self.file_dialog(["png"])
                if changed:
                    with Image.open(value) as im:
                        self.level.cover = cv2.cvtColor(np.array(im.convert("RGBA"), dtype=np.uint8), cv2.COLOR_RGB2BGR)
                imgui.end_popup()

            imgui.set_next_window_size(300, 90)
            imgui.set_next_window_position(0, 19)
            if imgui.begin("...", False,
                           imgui.WINDOW_NO_TITLE_BAR |
                           imgui.WINDOW_NO_COLLAPSE):
                imgui.text("Bar")
                imgui.end()

            GL.glClearColor(0., 0., 0., 1)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)

            imgui.render()
            impl.render(imgui.get_draw_data())
            sdl2.SDL_GL_SwapWindow(window)
