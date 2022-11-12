import json
import re
from pathlib import Path

import chparse


def import_timings(filepath, game) -> list[int]:
    timings = set()
    if game == 0:  # A Dance of Fire and Ice
        assert Path(filepath).suffix == ".adofai", "Unsupported file format! Required: .adofai"
        with open(filepath, "r") as f:
            file = f.read()
            # Fix JSON since ADOFAI doesn't quite get it right all of the time
            file = re.sub(r', *([}\]])', r"\1", file)
            file = re.sub(r'([}\]\"])([ \r\n\t]*[{["])', r"\1,\2", file)
            level = json.loads(file.encode("utf-8"))
        # Initialize variables
        twirled = False
        bpm = level["settings"]["bpm"]
        time = level["settings"]["offset"]
        multi_planet = False
        actions = {}
        for action in level["actions"]:
            if action["floor"] in actions:
                actions[action["floor"]].append({k: v for k, v in action.items() if k != "floor"})
            else:
                actions[action["floor"]] = [{k: v for k, v in action.items() if k != "floor"}]
        old_angle = 0
        for i, angle in enumerate(level["angleData"]):
            angle_delta = (angle % 360) - (old_angle % 360) % 360
            angle_delta = (angle_delta * (1 if twirled else -1)) % 360
            angle_delta += 180
            if multi_planet:
                angle_delta = (angle_delta - 60)
            angle_delta %= 360
            old_angle = angle
            time += (60000 / bpm) * (angle_delta / 180)
            timings.add(int(time))
            for action in actions.get(i, []):
                if action["eventType"] == "Twirl":
                    twirled = not twirled
                if action["eventType"] == "MultiPlanet":
                    multi_planet = action["planets"] == "ThreePlanets"
                if action["eventType"] == "SetSpeed":
                    if action["speedType"] == "Multiplier":
                        bpm *= action["bpmMultiplier"]
                    else:
                        bpm = action["beatsPerMinute"]
                if action["eventType"] in ["Hold", "Pause"]:
                    time += int(action["duration"] * (60000 / bpm))
                if action["eventType"] == "FreeRoam":
                    time += int(action["duration"] * (60000 / bpm))
    elif game == 1:  # osu!
        assert Path(filepath).suffix == ".osu", "Unsupported file format! Required: .osu"
        with open(filepath, "r") as f:
            file = f.read()
        lines = file.splitlines()
        assert "[HitObjects]" in lines, "HitObjects weren't found!"
        i = lines.index("[HitObjects]") + 1
        while i < len(lines):
            timings.add(int(lines[i].split(",")[2]))
            i += 1
    elif game == 2:  # Clone Hero
        assert Path(filepath).suffix == ".chart", "Unsupported file format! Required: .chart"
        with open(filepath, "r") as f:
            chart = chparse.load(f)
        for difficulty in [chparse.EXPERT, chparse.HARD, chparse.MEDIUM, chparse.EASY, chparse.NA]:
            if chparse.GUITAR in chart.instruments[difficulty]:
                track = chart.instruments[chparse.EXPERT][chparse.GUITAR]
                break
        else:
            raise AssertionError("Couldn't find a guitar chart!")
        for note in track:
            timings.add(note.time)
    return sorted(timings)
