import sdl2
import ctypes
import OpenGL.GL as GL

import imgui
import glfw
from imgui.integrations.glfw import GlfwRenderer
import src.loop as loop

import src.style as imgui_style


def main():
    window = init()
    imgui.create_context()
    style = imgui.get_style()
    font = imgui_style.set(style)
    impl = GlfwRenderer(window)
    impl.refresh_font_texture()
    editor = loop.Editor()
    editor.start(window, impl, font)
    impl.shutdown()
    glfw.terminate()


def init():
    if not glfw.init():
        print("Could not initialize OpenGL context")
        exit(1)

    # OS X supports only forward-compatible core profiles from 3.2
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)

    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, GL.GL_TRUE)

    # Create a windowed mode window and its OpenGL context
    window = glfw.create_window(500, 500, "SSpy", None, None)
    glfw.make_context_current(window)

    if not window:
        glfw.terminate()
        print("Could not initialize Window")
        exit(1)

    return window


if __name__ == '__main__':
    main()
