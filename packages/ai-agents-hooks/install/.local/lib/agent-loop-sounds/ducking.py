"""Coordinate temporary PipeWire mixing; never change saved channel volumes."""
import contextlib
import fcntl
import json
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time


def birth(pid):
    try:
        fields = Path(f"/proc/{int(pid)}/stat").read_text().rsplit(")", 1)[1].split()
        return None if fields[0] == "Z" else fields[19]
    except (OSError, ValueError, IndexError):
        return None


def same(left, right):
    return len(left) == len(right) and all(
        math.isclose(a, b, rel_tol=1e-5, abs_tol=1e-6) for a, b in zip(left, right))


def nodes_from_dump(raw):
    # pw-dump can append update documents even without --monitor.
    decoder = json.JSONDecoder()
    objects = {}
    while raw.strip():
        batch, end = decoder.raw_decode(raw.lstrip())
        raw = raw.lstrip()[end:]
        for obj in batch:
            if obj.get("info") is None:
                objects.pop(obj["id"], None)
            else:
                previous = objects.get(obj["id"], {})
                previous_info = previous.get("info", {})
                info = dict(previous_info, **obj["info"])
                for field in ("props", "params"):
                    if obj["info"].get(field) is not None:
                        info[field] = dict(previous_info.get(field, {}), **obj["info"][field])
                    elif field in previous_info:
                        info[field] = previous_info[field]
                objects[obj["id"]] = {**previous, **obj, "info": info}
    generation = objects.get(0, {}).get("info", {}).get("cookie")
    nodes = {}
    for obj in objects.values():
        info = obj.get("info", {})
        props = info.get("props", {})
        params = info.get("params", {}).get("Props", [])
        if (props.get("media.class") != "Stream/Output/Audio"
                or "object.serial" not in props or not params):
            continue
        values = params[0]
        channels = values.get("channelVolumes", [])
        soft = values.get("softVolumes", [])
        if (not channels or len(channels) != len(soft)
                or not all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0
                           for v in channels + soft)):
            continue
        nodes[str(props["object.serial"])] = {
            "id": obj["id"], "serial": props["object.serial"],
            "channels": channels, "soft": soft,
            "mute": values.get("mute", False),
            "soft_mute": values.get("softMute", False),
            "signal": props.get("application.name") == "agent-loop-sound",
        }
    return generation, nodes


class Audio:
    def snapshot(self):
        result = subprocess.run(["pw-dump"], capture_output=True, text=True,
                                timeout=3, check=True)
        return nodes_from_dump(result.stdout)

    def set_soft(self, generation, node, volumes, mute):
        # Recheck server and serial before using the reusable numeric node id.
        current_generation, current = self.snapshot()
        fresh = current.get(str(node["serial"]))
        if (generation != current_generation or fresh is None
                or fresh["id"] != node["id"]
                or not same(fresh["channels"], node["channels"])
                or not same(fresh["soft"], node["soft"])
                or fresh["mute"] != node["mute"]
                or fresh["soft_mute"] != node["soft_mute"]):
            return False
        # softVolumes select the software mixing path. Pair softMute with the
        # user's current mute so temporary mixing cannot unmute an application.
        result = subprocess.run(
            ["pw-cli", "set-param", str(node["id"]), "Props",
             json.dumps({"softVolumes": volumes, "softMute": mute})],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        if result.returncode != 0:
            return False
        after_generation, after_nodes = self.snapshot()
        after = after_nodes.get(str(node["serial"]))
        return (after_generation == generation and after is not None
                and after["id"] == node["id"] and same(after["soft"], volumes)
                and after["soft_mute"] == mute)


class Coordinator:
    def __init__(self, directory, audio=None, alive=None):
        self.directory = Path(directory)
        self.audio = audio or Audio()
        self.alive = alive or self.owner_alive

    @staticmethod
    def owner_alive(owner):
        return (birth(owner["parent"]) == owner["parent_birth"]
                and birth(owner["player"]) == owner["player_birth"])

    @contextlib.contextmanager
    def locked(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        metadata = self.directory.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise ValueError("unsafe audio runtime directory")
        os.chmod(self.directory, 0o700)
        fd = os.open(self.directory / "coordination.lock",
                     os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "r+") as lock:
            metadata = os.fstat(lock.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
                raise ValueError("unsafe audio coordination lock")
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = self.directory / "coordination.json"
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd) as saved:
                    metadata = os.fstat(saved.fileno())
                    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                            or metadata.st_size > 1024 * 1024):
                        raise ValueError("unsafe audio coordination state")
                    state = json.load(saved)
                if (state.get("version") != 1 or not isinstance(state.get("owners"), dict)
                        or not isinstance(state.get("nodes"), dict)):
                    raise ValueError("invalid audio coordination state")
            except FileNotFoundError:
                state = {"version": 1, "owners": {}, "nodes": {}, "generation": None}
            yield state
            self.save(state)

    def save(self, state):
        fd, path = tempfile.mkstemp(prefix=".coordination-", dir=self.directory)
        try:
            with os.fdopen(fd, "w") as saved:
                json.dump(state, saved)
                saved.flush()
                os.fsync(saved.fileno())
            os.replace(path, self.directory / "coordination.json")
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def step(self, owner_id, owner=None):
        with self.locked() as state:
            state["owners"] = {key: item for key, item in state["owners"].items()
                               if self.alive(item)}
            if owner is not None and self.alive(owner):
                state["owners"][owner_id] = owner
            else:
                state["owners"].pop(owner_id, None)
            generation, nodes = self.audio.snapshot()
            if generation is None:
                raise ValueError("missing PipeWire server identity")
            if state["generation"] != generation:
                # Serial numbers from a previous server are never authority.
                state["nodes"] = {}
                state["generation"] = generation
            active = bool(state["owners"])
            percent = min((o["percent"] for o in state["owners"].values()), default=100)
            # Pulse volume percentages are cubic; preserve the former audible
            # attenuation while keeping its stored/UI channelVolumes untouched.
            factor = (percent / 100) ** 3
            for serial in list(state["nodes"]):
                if serial not in nodes:
                    del state["nodes"][serial]
            for serial, node in nodes.items():
                if node["signal"]:
                    continue
                record = state["nodes"].get(serial)
                if record is None:
                    if not active:
                        continue
                    # Leave an existing third-party software effect alone.
                    if not (same(node["soft"], [1.0] * len(node["soft"]))
                            or same(node["soft"], node["channels"])):
                        continue
                    record = {"expected": node["soft"],
                              "expected_mute": node["soft_mute"], "released": False,
                              "idle": False}
                    state["nodes"][serial] = record
                if record["released"]:
                    continue
                if (not same(node["soft"], record["expected"])
                        or node["soft_mute"] != record["expected_mute"]):
                    # Another software mixer took ownership: do not undo it.
                    record["released"] = True
                    continue
                if active:
                    record["idle"] = False
                desired = [value * factor for value in node["channels"]]
                if not same(desired, node["soft"]) or node["soft_mute"] != node["mute"]:
                    previous = dict(record)
                    record["expected"] = desired
                    record["expected_mute"] = node["mute"]
                    # Journal intent before the audio write, for crash recovery.
                    self.save(state)
                    if not self.audio.set_soft(generation, node, desired, node["mute"]):
                        record.update(previous)
                if not active and same(record["expected"], node["channels"]):
                    # Keep provenance of our restored software parameters. A
                    # later user slider update clears PipeWire's software override
                    # but leaves these parameter values visible in Props.
                    record["idle"] = True
            if not active:
                state["nodes"] = {key: item for key, item in state["nodes"].items()
                                  if not item["released"]}
            return active, any(not record.get("idle", False) for record in state["nodes"].values())


def main():
    directory, parent_s, player_s, percent_s = sys.argv[1:5]
    parent, player = int(parent_s), int(player_s)
    try:
        percent = max(1, min(100, int(percent_s)))
    except ValueError:
        percent = 80
    owner = {"parent": parent, "parent_birth": birth(parent), "player": player,
             "player_birth": birth(player), "percent": percent}
    if owner["parent_birth"] is None or owner["player_birth"] is None:
        return
    owner_id = f"{parent}:{owner['parent_birth']}:{player}:{owner['player_birth']}"
    coordinator = Coordinator(directory)
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not stopping and coordinator.owner_alive(owner):
            coordinator.step(owner_id, owner)
            time.sleep(0.2)
    finally:
        # Retry temporary server/command errors on release without hanging the hook.
        for attempt in range(5):
            try:
                active, pending = coordinator.step(owner_id)
                if active or not pending:
                    break
            except (OSError, ValueError, subprocess.SubprocessError):
                if attempt == 4:
                    print("agent-loop-sound: temporary mixing recovery pending", file=sys.stderr)
            time.sleep(0.2)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print("agent-loop-sound: temporary ducking unavailable", file=sys.stderr)
