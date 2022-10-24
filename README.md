# SSPy - A python-based level editor for [SS+](https://chedski.itch.io/sound-space-plus) (or [Sound Space](https://www.roblox.com/games/2677609345/FREE-Sound-Space-Music-Rhythm))



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

To put it bluntly: I don't like it. I have my reasons why.

> What platforms does this run on?

Almost any platform that supports OpenGL and Python. Windows, MacOS, and most Linux distributions should work.

> What do I do if it crashes?

Report it! My discord tag is in the crash message, but if you can't reach me from there, feel free to open an issue.

> How do I run it?

Install `git`, `git-lfs`, `python`, and `ffmpeg` if you haven't, then
```
git clone https://github.com/balt-dev/SSpy/ sspy
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

> My song file is corrupted! What do I do?

This usually happens when the level is interrupted during saving. It's good practice to make backups often.

## Notes

The code behind the file picker was taken from https://github.com/Zygahedron/Parabox-Editor, with [explicit permission from the repository owner.][1]


[1]: https://i.imgur.com/7JyRsjb.png (Permission proof)

## Gallery
![Screenshot_2022-10-12_19-52-11](https://user-images.githubusercontent.com/59123926/195474222-8ba3a165-2e4d-4bd2-820a-be3030b87f91.png)
![Screenshot_2022-10-12_19-50-23](https://user-images.githubusercontent.com/59123926/195474223-afc23cc3-d870-45e6-902e-eda1d004826e.png)
![Screenshot_2022-10-12_19-50-13](https://user-images.githubusercontent.com/59123926/195474224-f43697fe-108e-4e56-bf78-96bbc33d405b.png)
![Screenshot_2022-10-12_19-49-52](https://user-images.githubusercontent.com/59123926/195474225-78400263-58f2-42e2-8b3e-45f2254a56e0.png)
![Screenshot_2022-10-12_19-49-47](https://user-images.githubusercontent.com/59123926/195474226-8ac4c514-8c5f-44b9-9f20-72d3b43446e2.png)
