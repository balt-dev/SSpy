# SSPy - A python-based level editor for SS+ (or Sound Space)



---
## Roadmap
- [x] Basic functionality
  - [x] Loading/Saving
  - [x] Timeline
  - [x] Note display
- [x] Note placing and removing
- [x] Audio playing
  - [x] BPM markers
- [x] Waveform on timeline
- [x] .txt map save/load support
- [x] Optimizations for low-end devices
- [ ] Vulnus .zip support

## FAQ:

> Why is Vulnus support at the back of the roadmap?

To put it bluntly: I don't like Vulnus. 

> What platforms does this run on?

Almost any platform that supports OpenGL and Python. Windows, MacOS, and most Linux distributions should work.

> What do I do if it crashes?

Report it! My discord tag is in the crash message, but if you can't reach me from there, feel free to open an issue.

> How do I run it?

Install `git`, `git-lfs`, `python`, and `ffmpeg` if you haven't, then
```
git clone [url] sspy
cd sspy
pip install wheel
pip install -r requirements.txt
python main.py
```
## Troubleshooting

> It's crashing and complaining about a file not found when loading a map!

Check if you've added `ffmpeg` to your system PATH.

> It's giving me a divide by zero error!

You probably did something that doesn't make sense. Report the crash.

## Notes:

The code behind the file picker was taken from https://github.com/Zygahedron/Parabox-Editor, with [explicit permission from the repository owner.][1]


[1]: https://i.imgur.com/7JyRsjb.png (Permission proof)
