import ctypes
import sys
import traceback
import imgui
import sdl2
from imgui.integrations.sdl2 import SDL2Renderer
import OpenGL.GL as gl
import src.loop as loop

import src.style as imgui_style


def main():
    window, gl_ctx = init()
    imgui.create_context()
    style = imgui.get_style()
    font = imgui_style.set(style)
    impl = SDL2Renderer(window)
    impl.refresh_font_texture()
    editor = loop.Editor()
    try:
        editor.start(window, impl, font, gl_ctx)
    except:
        exc = traceback.format_exc()
        print("If you're seeing this, the app encountered a fatal error and had to close.")
        print("Please send this traceback to @balt#6423 on Discord, and tell him what you were doing that caused the crash.")
        print("---------")
        print(exc, end="")
        print("---------")

    impl.shutdown()
    sdl2.SDL_GL_DeleteContext(gl_ctx)
    sdl2.SDL_DestroyWindow(window)
    sdl2.SDL_Quit()


def init():
    width, height = 800, 600
    window_name = "If you see this as a window name, something's wrong."
    if sdl2.SDL_Init(sdl2.SDL_INIT_EVERYTHING) < 0:
        print("Error: SDL could not initialize! SDL Error: " + sdl2.SDL_GetError().decode("utf-8"))
        exit(1)

    sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_DOUBLEBUFFER, 1)
    sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_DEPTH_SIZE, 24)
    sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_STENCIL_SIZE, 8)
    sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_ACCELERATED_VISUAL, 1)
    sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_MULTISAMPLEBUFFERS, 1)
    sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_MULTISAMPLESAMPLES, 16)
    sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_FLAGS, sdl2.SDL_GL_CONTEXT_FORWARD_COMPATIBLE_FLAG)
    sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_MAJOR_VERSION, 4)
    sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_MINOR_VERSION, 1)
    sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_PROFILE_MASK, sdl2.SDL_GL_CONTEXT_PROFILE_CORE)

    sdl2.SDL_SetHint(sdl2.SDL_HINT_MAC_CTRL_CLICK_EMULATE_RIGHT_CLICK, b"1")
    sdl2.SDL_SetHint(sdl2.SDL_HINT_VIDEO_HIGHDPI_DISABLED, b"1")

    window = sdl2.SDL_CreateWindow(window_name.encode('utf-8'),
                                   sdl2.SDL_WINDOWPOS_CENTERED, sdl2.SDL_WINDOWPOS_CENTERED,
                                   width, height,
                                   sdl2.SDL_WINDOW_OPENGL | sdl2.SDL_WINDOW_RESIZABLE)

    if window is None:
        print("Error: Window could not be created! SDL Error: " + sdl2.SDL_GetError().decode("utf-8"))
        exit(1)

    gl_context = sdl2.SDL_GL_CreateContext(window)
    if gl_context is None:
        print("Error: Cannot create OpenGL Context! SDL Error: " + sdl2.SDL_GetError().decode("utf-8"))
        exit(1)

    sdl2.SDL_GL_MakeCurrent(window, gl_context)
    if sdl2.SDL_GL_SetSwapInterval(0) < 0:
        print("Warning: Unable to set VSync! SDL Error: " + sdl2.SDL_GetError().decode("utf-8"))
        exit(1)

    return window, gl_context


if __name__ == '__main__':
    main()
