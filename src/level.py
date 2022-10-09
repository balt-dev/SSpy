from functools import lru_cache
from io import BytesIO
from itertools import chain

import numpy as np
from PIL import Image
from pydub import AudioSegment
import struct

import math


def read_line(file):
    out = bytearray(b"")
    while (f := file.read(1)) != b"\n":
        out.append(int.from_bytes(f, "little"))
    return out.decode("utf-8")


class Level:
    def __init__(self,
                 name: str = "Unnamed",
                 author: str = "Unknown Author",
                 notes: dict[int, list[tuple[int, int]]] = None,
                 cover: Image.Image = None,
                 audio: AudioSegment = None,
                 difficulty: int = -1):
        self.id = (author.lower() + " " + name.lower()).replace(" ", "_")
        self.name = name
        self.author = author
        self.notes = notes if notes is not None else {}
        self.cover = cover
        self.audio = audio
        self.difficulty = difficulty

    def __str__(self):
        return f"Level(author: {self.author}, cover: {self.cover}, difficulty: {self.difficulty}, id: {self.id}, name: {self.name}, notes: ({len(self.notes)} notes))"

    def __hash__(self):
        return hash((self.id, tuple(self.notes.keys()), str(self.notes.values()), self.cover.tobytes() if self.cover is not None else None, self.audio, self.difficulty))

    @lru_cache
    def get_end(self):
        times_to_display = self.get_notes()
        return (np.max(times_to_display) if times_to_display.shape[0] > 0 else 1000)

    @lru_cache
    def get_notes(self):
        return np.sort(np.array(tuple(self.notes.keys()), dtype=np.int32))

    @classmethod
    def from_sspm(cls, file):
        assert file.read(4) == b"SS+m", "Invalid file signature! Your level might be corrupted, or in the wrong format."
        assert file.read(2) == b"\x01\x00", \
            "Sorry, this doesn't support SSPM v2. Use the in-game editor."
        assert file.read(2) == b"\x00\x00", \
            "Reserved bits aren't 0. Is this a modchart?"
        read_line(file)
        song_name = read_line(file)
        song_author = read_line(file)
        file.read(4)  # MS length, not needed
        note_count = int.from_bytes(file.read(4), "little")
        difficulty = int.from_bytes(file.read(1), "little") - 1
        cover = None
        if file.read(1) == b"\x02":
            data_length = int.from_bytes(file.read(8), "little")
            image_data = file.read(data_length)
            with BytesIO(image_data) as io:
                with Image.open(io) as im:
                    cover = im.copy()
        audio = None
        if file.read(1) == b"\x01":
            data_length = int.from_bytes(file.read(8), "little")
            audio_data = file.read(data_length)
            with BytesIO(audio_data) as io:
                audio = AudioSegment.from_file(io).set_sample_width(2)  # HACK: if i don't do this, it plays horribly clipped and way too loud. it's a simpleaudio bug :/
        notes = {}
        for _ in range(note_count):
            timing = int.from_bytes(file.read(4), "little")
            if file.read(1) == b"\x00":
                x = int.from_bytes(file.read(1), "little")
                y = int.from_bytes(file.read(1), "little")
            else:
                x, y = struct.unpack("ff", file.read(8))  # nice
            if timing in notes:
                notes[timing].append((x, y))
            else:
                notes[timing] = [(x, y)]
        return Level(song_name, song_author, notes, cover, audio, difficulty)

    def save(self):
        with BytesIO() as output:
            print("Writing metadata...")
            output.write(b"SS+m\x01\x00\x00\x00")
            output.write(bytes(self.id + "\n", "utf-8"))
            output.write(bytes(self.name + "\n", "utf-8"))
            output.write(bytes(self.author + "\n", "utf-8"))
            output.write(
                (max(self.notes.keys()) if len(self.notes) else 0).to_bytes(4, "little")
            )
            output.write(
                len(tuple(chain(*self.notes.values()))).to_bytes(4, "little")
            )
            output.write(
                (self.difficulty + 1).to_bytes(1, "little")
            )
            if self.cover is None:
                output.write(b"\x00")
            else:
                print(f"Writing cover...")
                output.write(b"\x02")
                with BytesIO() as im_data:
                    self.cover.save(im_data, format="PNG")
                    output.write(
                        im_data.seek(0, 2).to_bytes(8, "little")
                    )
                    output.write(im_data.getvalue())
            if self.audio is None:
                output.write(b"\x00")
            else:
                print(f"Writing song...")
                output.write(b"\x01")
                with BytesIO() as audio_data:
                    # XXX: this leads to compression rot over multiple saves, after 50 saves or so the music isn't really listenable anymore
                    self.audio.export(audio_data, format="ogg")
                    output.write(
                        audio_data.seek(0, 2).to_bytes(8, "little")
                    )
                    output.write(audio_data.getvalue())
            for i, (timing, notes) in enumerate(self.notes.items()):
                print(f"\rWriting notes... ({i+1: >{(len(str(len(self.notes))))}}/{len(self.notes)})", end="")
                for position in notes:
                    output.write(
                        timing.to_bytes(4, "little")
                    )
                    if all([isinstance(n, int) for n in position]):
                        output.write(b"\x00")
                        output.write(position[0].to_bytes(1, "little"))
                        output.write(position[1].to_bytes(1, "little"))
                    else:
                        output.write(b"\x01")
                        output.write(struct.pack("<ff", *position))
            print()
            return output.getvalue()
