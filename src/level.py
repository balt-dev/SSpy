from io import BytesIO

import cv2
import numpy as np
from PIL import Image
from pydub import AudioSegment
import struct


def read_line(file):
    out = bytearray(b"")
    while (f := file.read(1)) != b"\n":
        out.append(int.from_bytes(f, "little"))
    return out.decode("utf-8")


class Level:
    def __init__(self,
                 song_id="",
                 name: str = "Unnamed",
                 author: str = "Unknown Author",
                 notes: dict[tuple[int, int]] = None,
                 cover: np.ndarray = None,
                 audio: AudioSegment = None,
                 difficulty: int = -1):
        self.id = song_id
        self.name = name
        self.author = author
        self.notes = notes if notes is not None else {}
        self.cover = cover
        self.audio = audio
        self.difficulty = difficulty

    def __str__(self):
        return f"Level(author: {self.author}, cover: {self.cover}, difficulty: {self.difficulty}, id: {self.id}, name: {self.name}, notes: ({len(self.notes)} notes))"

    @classmethod
    def from_sspm(cls, file):
        assert file.read(4) == b"SS+m", "Invalid file signature! Did you choose a .sspm?"
        assert file.read(2) == b"\x01\x00", \
            "Sorry, this doesn't support SSPM v2. Use the in-game editor."
        assert file.read(2) == b"\x00\x00", \
            "Reserved bits aren't 0. Is this a modchart?"
        song_id = read_line(file)
        song_name = read_line(file)
        song_author = read_line(file)
        file.read(4)  # MS length, not needed
        note_count = int.from_bytes(file.read(4), "little")
        difficulty = int.from_bytes(file.read(1), "little") - 1
        cover = None
        if file.read(1) == b"\x02":
            data_length = int.from_bytes(file.read(8), "little")
            image_data = file.read(data_length)
            io = BytesIO(image_data)
            with Image.open(io) as im:
                cover = cv2.cvtColor(np.array(im.convert("RGBA"), dtype=np.uint8), cv2.COLOR_RGB2BGR)
        audio = None
        if file.read(1) == b"\x01":
            data_length = int.from_bytes(file.read(8), "little")
            image_data = file.read(data_length)
            io = BytesIO(image_data)
            audio = AudioSegment.from_file(io)
        notes = {}
        for _ in range(note_count):
            timing = int.from_bytes(file.read(4), "little")
            if file.read(1) == b"\x00":
                x = int.from_bytes(file.read(1), "little")
                y = int.from_bytes(file.read(1), "little")
            else:
                x = struct.unpack("f", file.read(4))
                y = struct.unpack("f", file.read(4))
            notes[timing] = x, y
        return Level(song_id, song_name, song_author, notes, cover, audio, difficulty)

    def save(self):
        with BytesIO(b"SS+m\x01\x00\x00\x00") as output:
            output.write(bytes(self.id + "\n","utf-8"))
            output.write(bytes(self.name + "\n","utf-8"))
            output.write(bytes(self.author + "\n","utf-8"))
            output.write(
                max(self.notes.keys()).to_bytes(4,"little")
            )
