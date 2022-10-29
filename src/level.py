import glob
import json
import os
import struct
from abc import ABC, abstractmethod
from io import BytesIO
from itertools import chain
from pathlib import Path

import numpy as np
from PIL import Image
from pydub import AudioSegment


def read_line(file):
    out = bytearray(b"")
    while (f := file.read(1)) != b"\n":
        out.append(int.from_bytes(f, "little"))
    return out.decode("utf-8")


class Level(ABC):
    def __init__(self,
                 name: str = "Unnamed",
                 author: str = "Unknown Author",
                 notes: dict[int, list[tuple[int, int]]] = None,
                 cover: Image.Image = None,
                 audio: AudioSegment = None,
                 difficulty: int | str = -1,
                 id: str = None):
        self.id = id if id is not None else (author.lower() + " " + name.lower()).replace(" ", "_")
        self.name = name
        self.author = author
        self.notes = notes if notes is not None else {}
        self.cover = cover
        self.audio = audio
        self.difficulty = difficulty

    def __str__(self):
        return f"{self.__class__.__name__}(author: {self.author}, cover: {self.cover}, difficulty: {self.difficulty}, id: {self.id}, name: {self.name}, notes: ({len(self.notes)} notes), level_name: {self.level_name})"

    def get_end(self):
        times_to_display = self.get_notes()
        return (np.max(times_to_display) if times_to_display.shape[0] > 0 else 1000)

    def get_notes(self):
        return np.sort(np.array(tuple(self.notes.keys()), dtype=np.int32))

    @classmethod
    @abstractmethod
    def load(cls, file):
        raise NotImplementedError

    @abstractmethod
    def save(self, *_):
        raise NotImplementedError


class SSPMLevel(Level):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def load(cls, file):
        with open(file, "rb") as f:
            assert f.read(
                4) == b"SS+m", "Invalid f signature! Your level might be corrupted, or in the wrong format."
            assert f.read(2) == b"\x01\x00", \
                "Sorry, this doesn't support SSPM v2. Use the in-game editor."
            assert f.read(2) == b"\x00\x00", \
                "Reserved bits aren't 0. Is this a modchart?"
            read_line(f)
            song_name = read_line(f)
            song_author = read_line(f)
            f.read(4)  # MS length, not needed
            note_count = int.from_bytes(f.read(4), "little")
            difficulty = int.from_bytes(f.read(1), "little") - 1
            cover = None
            if f.read(1) == b"\x02":
                data_length = int.from_bytes(f.read(8), "little")
                image_data = f.read(data_length)
                with BytesIO(image_data) as io:
                    with Image.open(io) as im:
                        cover = im.copy()
            audio = None
            if f.read(1) == b"\x01":
                data_length = int.from_bytes(f.read(8), "little")
                audio_data = f.read(data_length)
                with BytesIO(audio_data) as io:
                    audio = AudioSegment.from_file(io).set_sample_width(
                        2)  # HACK: if i don't do this, it plays horribly clipped and way too loud. it's a simpleaudio bug :/
            notes = {}
            for _ in range(note_count):
                timing = int.from_bytes(f.read(4), "little")
                if f.read(1) == b"\x00":
                    x = int.from_bytes(f.read(1), "little")
                    y = int.from_bytes(f.read(1), "little")
                else:
                    x, y = struct.unpack("ff", f.read(8))  # nice
                if timing in notes:
                    notes[timing].append((x, y))
                else:
                    notes[timing] = [(x, y)]
            metadata = True
            try:
                assert f.read(4) == b"SSPy"
                bpm = struct.unpack("d", f.read(8))[0]
                offset = int.from_bytes(f.read(4), "little")
                time_signature = struct.unpack("HH", f.read(4))
                swing = struct.unpack("d", f.read(8))[0]
            except (EOFError, AssertionError):
                metadata = False
            return cls(song_name, song_author, notes, cover, audio, difficulty, None), \
                (bpm, offset, time_signature, swing) if metadata else None

    def save(self, filename, bpm, offset, time_signature, swing):
        with open(filename, "wb+") as output:
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
                    self.audio.export(audio_data)
                    output.write(
                        audio_data.seek(0, 2).to_bytes(8, "little")
                    )
                    output.write(audio_data.getvalue())
            for i, (timing, notes) in enumerate(dict(sorted(self.notes.items())).items()):
                print(f"\rWriting notes... ({i + 1: >{(len(str(len(self.notes))))}}/{len(self.notes)})", end="")
                for position in notes:
                    output.write(
                        timing.to_bytes(4, "little")
                    )
                    if all([n == int(n) for n in position]):
                        output.write(b"\x00")
                        output.write(int(position[0]).to_bytes(1, "little"))
                        output.write(int(position[1]).to_bytes(1, "little"))
                    else:
                        output.write(b"\x01")
                        output.write(struct.pack("<ff", *position))
            # Write metadata past the notes, SS+ allows this
            output.write(b"SSPy")
            output.write(struct.pack("d", bpm))
            output.write(offset.to_bytes(4, "little"))
            output.write(struct.pack("<HH", *time_signature))
            output.write(struct.pack("d", swing))
            print()


class RawDataLevel(Level):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def load(cls, file):
        with open(file) as f:
            notes = {}
            data_string = f.read()
            for note in data_string.split(",")[1:]:
                try:
                    x, y, timing = note.split("|")
                    x, y = float(x), float(y)
                    try:
                        notes[int(timing)].append((x, y))
                    except KeyError:
                        notes[int(timing)] = [(x, y)]
                except ValueError:
                    print(f"/!\\ Invalid note! {note}")
            return cls(notes=notes), None

    def save(self, filename, *_):
        with open(filename, "w+") as f:
            output = []
            for timing, notes in dict(sorted(self.notes.items())).items():
                for note in notes:
                    x = 2 - note[0]
                    y = 2 - note[1]
                    x = int(x) if int(x) == x else x
                    y = int(y) if int(y) == y else y
                    output.append(f"{2 - x}|{2 - y}|{timing}")
            f.write(self.id + "," + ",".join(output))


class VulnusLevel(Level):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def load(cls, file):
        assert Path("meta.json").exists(), "Metadata file not found!"
        with open("meta.json", "r") as meta:
            m_data = json.load(meta)  # Raises json.JSONDecodeError, caught outside
        try:
            assert m_data["_version"] == 1, "Unsupported version!"
            song_name = f'{m_data["_artist"]} - {m_data["_title"]}'
            song_author = ", ".join(m_data["_mappers"])
            audio = AudioSegment.from_file(m_data["_music"])
            cover = [Path(name).name for name in glob.glob("./cover*")]
            if len(cover):
                assert len(cover) < 2, "Multiple covers found! (?????)"
                with open(cover[0], "rb") as im:
                    with Image.open(im) as i:
                        cover = i.copy()
            else:
                cover = None
            with open(file, "r") as m:
                level = json.load(m)
            difficulty = level["_name"]
            notes = {}
            for note in level["_notes"]:
                timing = int(note["_time"] * 1000)
                position = (1 - note["_x"], note["_y"] + 1)
                if timing in notes:
                    notes[timing].append(position)
                else:
                    notes[timing] = [position]
            metadata = "_sspy" in m_data
            if metadata:
                bpm = m_data["_sspy"]["bpm"]
                offset = m_data["_sspy"]["offset"]
                time_signature = m_data["_sspy"]["time_signature"]
                swing = m_data["_sspy"]["swing"]
        except KeyError as e:
            raise KeyError(f"Error while loading: JSON key {e} not found!")
        return cls(song_name, song_author, notes, cover, audio, difficulty), (
            bpm, offset, time_signature, swing) if metadata else None

    def save(self, filename, bpm, offset, time_signature, swing):
        print("Exporting audio...")
        with open("audio.wav", "wb+") as f:
            self.audio.export(f, format="wav")
        print("Exporting metadata...")
        try:  # Load an existing metadata file
            with open("meta.json", "r") as f:
                metadata = json.load(f)
            metadata["_difficulties"].append(f"{filename}.json")
        except FileNotFoundError:
            metadata = {"_difficulties": [f"{filename}.json"]}
        metadata_temp = {"_artist": (self.name.split(" - "))[0], "_title": (self.name.split(" - "))[1],
                         "_mappers": self.author.split(", "), "_music": "audio.wav", "_version": 1, "_sspy": {
            "bpm": bpm,
            "time_signature": time_signature,
            "offset": offset,
            "swing": swing
        }}
        metadata |= metadata_temp
        with open("meta.json", "w+") as m:
            json.dump(metadata, m)
        print("Exporting cover...")
        for path in glob.glob("./cover*"):
            os.remove(path)
        self.cover.save("cover.png")
        print("Exporting notes...")
        level = {"_notes": [], "_name": self.difficulty}
        for time in self.notes:
            for note in self.notes[time]:
                level["_notes"].append({"_time": time / 1000, "_x": 1 - note[0], "_y": note[1] - 1})
        with open(f"{filename}", "w+") as level_file:
            json.dump(level, level_file)
