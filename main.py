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
        try:
            try:
                imgui.core.pop_font()
            except:
                pass
            imgui.end_frame()
            with open("log.txt", "w+") as log:
                sys.stdout = log
                traceback.print_exc()
                sys.stdout = sys.__stdout__
            impl.shutdown()
            sdl2.SDL_GL_DeleteContext(gl_ctx)
            sdl2.SDL_DestroyWindow(window)
            sdl2.SDL_Quit()
            window, gl_ctx = init()
            impl = SDL2Renderer(window)
            event = sdl2.SDL_Event()
            run = True
            while run:
                while sdl2.SDL_PollEvent(ctypes.byref(event)) != 0:
                    if event.type == sdl2.SDL_QUIT:
                        run = False
                    impl.process_event(event)
                size = imgui.get_io().display_size
                impl.process_inputs()
                imgui.new_frame()
                imgui.set_next_window_size(size[0], size[1])
                imgui.set_next_window_position(0, 0)
                imgui.begin("A fatal error occurred.", True)
                imgui.text(f"""Sorry, but an error occurred and the program was stopped.
    Please report this to @balt#6423 on Discord.
    """)

                imgui.core.input_text_multiline("", exc, len(exc), imgui.INPUT_TEXT_READ_ONLY)
                gl.glClearColor(0., 0., 0., 1)
                gl.glClear(gl.GL_COLOR_BUFFER_BIT)
                imgui.end()
                imgui.render()
                impl.render(imgui.get_draw_data())
                sdl2.SDL_GL_SwapWindow(window)
        except:
            print("If you're seeing this, both the app and the error handler threw an error. Not great.")
            print("Please send this traceback to @balt#6423 on Discord, and tell him what you were doing that caused the crash.")
            print("---------")
            print(exc)
            print("---------")

    impl.shutdown()
    sdl2.SDL_GL_DeleteContext(gl_ctx)
    sdl2.SDL_DestroyWindow(window)
    sdl2.SDL_Quit()


def init():
    width, height = 800, 600
    window_name = "FATAL ERROR"
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
