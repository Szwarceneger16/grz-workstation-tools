#!/usr/bin/env python3
import argparse
import json
import math
import os
import subprocess
import sys
import threading
import time
import fcntl
from pathlib import Path

import gi
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from Xlib import X, display, error as XError


APP_NAME = "mx_dpi_wheel"

DEFAULT_CONFIG = {
    "device_name": "MX Master 3S",
    "dpis": [1200, 1600, 1800, 2200, 2800],
    "mod_keycode": 202,
    "scroll_up_button": 4,
    "scroll_down_button": 5,
    "radius": 140,
    "window_size": 360,
    "anim_fps": 45,
    "anim_ease": 0.08,
    "scroll_debounce_ms": 60,
    "mod_timeout_ms": 250,
}

CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / APP_NAME / "config.json"
STATE_PATH = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / f"{APP_NAME}_state.json"
LOCK_PATH = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / APP_NAME / "wheel.lock"
_RUN_LOCK_HANDLE = None


def config_dir() -> Path:
    return CONFIG_PATH.parent


def state_dir() -> Path:
    return STATE_PATH.parent


def notify(title: str, body: str):
    subprocess.Popen(["notify-send", "--expire-time=1800", title, body])


def ensure_config_exists():
    config_dir().mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2))


def normalize_dpis(value):
    out = []
    if isinstance(value, list):
        for item in value:
            try:
                n = int(item)
                if n > 0:
                    out.append(n)
            except Exception:
                pass
    return out


def load_config():
    ensure_config_exists()
    cfg = dict(DEFAULT_CONFIG)

    try:
        raw = json.loads(CONFIG_PATH.read_text())
        if isinstance(raw, dict):
            cfg.update(raw)
    except Exception:
        pass

    cfg["device_name"] = str(cfg.get("device_name", DEFAULT_CONFIG["device_name"])).strip() or DEFAULT_CONFIG["device_name"]
    cfg["dpis"] = normalize_dpis(cfg.get("dpis")) or list(DEFAULT_CONFIG["dpis"])

    for key in (
        "mod_keycode",
        "scroll_up_button",
        "scroll_down_button",
        "radius",
        "window_size",
        "anim_fps",
        "mod_timeout_ms",
        "scroll_debounce_ms",
    ):
        try:
            cfg[key] = int(cfg.get(key, DEFAULT_CONFIG[key]))
        except Exception:
            cfg[key] = DEFAULT_CONFIG[key]

    try:
        cfg["anim_ease"] = float(cfg.get("anim_ease", DEFAULT_CONFIG["anim_ease"]))
    except Exception:
        cfg["anim_ease"] = DEFAULT_CONFIG["anim_ease"]

    cfg["radius"] = max(40, cfg["radius"])
    cfg["window_size"] = max(180, cfg["window_size"])
    cfg["anim_fps"] = max(10, cfg["anim_fps"])
    cfg["anim_ease"] = min(max(0.01, cfg["anim_ease"]), 1.0)
    cfg["mod_timeout_ms"] = max(50, cfg["mod_timeout_ms"])
    cfg["scroll_debounce_ms"] = max(0, cfg["scroll_debounce_ms"])

    return cfg


def save_config(cfg):
    config_dir().mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def load_state():
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {"i": 0}


def save_state(i: int):
    state_dir().mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"i": i}))




def acquire_run_lock():
    global _RUN_LOCK_HANDLE
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fh = LOCK_PATH.open("w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        raise RuntimeError(
            "Inna instancja runtime już działa albo trzyma lock. "
            "Zatrzymaj usługę / drugi proces przed uruchomieniem kolejnego."
        )
    fh.write(str(os.getpid()))
    fh.flush()
    _RUN_LOCK_HANDLE = fh
    return fh

def set_dpi_blocking(device_name: str, dpi: int) -> bool:
    cp = subprocess.run(
        ["solaar", "config", device_name, "dpi", str(dpi)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return cp.returncode == 0


class WheelOverlay(Gtk.Window):
    def __init__(self, cfg):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.cfg = cfg

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_app_paintable(True)
        self.set_accept_focus(False)
        self.stick()
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        self.set_size_request(self.cfg["window_size"], self.cfg["window_size"])

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        self.connect("draw", self.on_draw)

        self.i = load_state().get("i", 0) % len(self.cfg["dpis"])
        self.angle = 0.0
        self.target_angle = 0.0
        self.visible_now = False

        self.set_target_for_index(self.i, snap=True)
        GLib.timeout_add(int(1000 / self.cfg["anim_fps"]), self.on_tick)

    def show_at(self, x, y):
        window_size = self.cfg["window_size"]
        nx = int(x - window_size // 2)
        ny = int(y - window_size // 2)

        scr = Gdk.Screen.get_default()
        w = scr.get_width()
        h = scr.get_height()
        nx = max(0, min(nx, w - window_size))
        ny = max(0, min(ny, h - window_size))

        self.move(nx, ny)
        self.show_all()
        self.present()
        self.queue_draw()

        while Gtk.events_pending():
            Gtk.main_iteration_do(False)

        self.visible_now = True

    def hide_overlay(self):
        self.hide()
        self.visible_now = False

    def set_target_for_index(self, i: int, snap=False):
        n = len(self.cfg["dpis"])
        step = 2 * math.pi / n
        self.target_angle = -i * step
        if snap:
            self.angle = self.target_angle

    def on_tick(self):
        if abs(self.target_angle - self.angle) > 1e-4:
            self.angle += (self.target_angle - self.angle) * self.cfg["anim_ease"]
            self.queue_draw()
        return True

    def on_draw(self, widget, cr):
        cr.set_operator(0)
        cr.paint()
        cr.set_operator(2)

        window_size = self.cfg["window_size"]
        radius = self.cfg["radius"]
        cx = window_size / 2
        cy = window_size / 2

        cr.set_source_rgba(0, 0, 0, 0.70)
        cr.arc(cx, cy, radius + 70, 0, 2 * math.pi)
        cr.fill()

        cr.set_source_rgba(1, 1, 1, 0.16)
        cr.set_line_width(2)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()

        cr.set_source_rgba(1, 1, 1, 0.85)
        cr.set_line_width(3)
        cr.move_to(cx, cy - radius - 18)
        cr.line_to(cx, cy - radius + 18)
        cr.stroke()

        dpis = self.cfg["dpis"]
        n = len(dpis)
        step = 2 * math.pi / n

        for idx, dpi in enumerate(dpis):
            a = (idx * step) + self.angle - math.pi / 2
            x = cx + math.cos(a) * radius
            y = cy + math.sin(a) * radius
            is_selected = (idx == self.i)

            if is_selected:
                cr.set_source_rgba(1, 1, 1, 0.97)
                cr.select_font_face("Sans", 0, 1)
                cr.set_font_size(22)
            else:
                cr.set_source_rgba(1, 1, 1, 0.70)
                cr.select_font_face("Sans", 0, 0)
                cr.set_font_size(16)

            txt = str(dpi)
            _xb, _yb, w, h, _xa, _ya = cr.text_extents(txt)
            cr.move_to(x - w / 2, y + h / 2)
            cr.show_text(txt)

        cr.set_source_rgba(1, 1, 1, 0.92)
        cr.select_font_face("Sans", 0, 1)
        cr.set_font_size(26)
        center = f"{dpis[self.i]} DPI"
        _xb, _yb, w, h, _xa, _ya = cr.text_extents(center)
        cr.move_to(cx - w / 2, cy + h / 2)
        cr.show_text(center)

        return False


class Controller:
    def __init__(self, cfg):
        self.cfg = cfg
        self.d = display.Display()
        self.root = self.d.screen().root

        self.root.change_attributes(
            event_mask=X.KeyPressMask | X.KeyReleaseMask
        )

        try:
            self.root.grab_key(
                self.cfg["mod_keycode"],
                X.AnyModifier,
                False,
                X.GrabModeAsync,
                X.GrabModeAsync,
            )
            self.d.sync()
        except XError.BadAccess as exc:
            try:
                self.d.close()
            except Exception:
                pass
            raise RuntimeError(
                f'Nie udało się przejąć keycode {self.cfg["mod_keycode"]} na X11. '
                "Najczęściej oznacza to, że inna instancja wheel już działa "
                "albo ten sam grab przejął inny program."
            ) from exc

        self.overlay = WheelOverlay(self.cfg)

        self.mod_down = False
        self.pending = False
        self.active = False
        self.pointer_grabbed = False

        self.anchor_x = 0
        self.anchor_y = 0
        self.start_i = self.overlay.i
        self.used_scroll = False

        self.last_mod_ms = 0
        self.last_scroll_ms = 0

        GLib.timeout_add(5, self.poll_x)
        GLib.timeout_add(30, self.check_mod_timeout)

    def grab_pointer(self):
        self.root.grab_pointer(
            owner_events=False,
            event_mask=X.ButtonPressMask | X.ButtonReleaseMask,
            pointer_mode=X.GrabModeAsync,
            keyboard_mode=X.GrabModeAsync,
            confine_to=X.NONE,
            cursor=X.NONE,
            time=X.CurrentTime,
        )
        self.d.sync()

    def ungrab_pointer(self):
        self.d.ungrab_pointer(X.CurrentTime)
        self.d.sync()

    def snapshot_pointer_pos(self):
        p = self.root.query_pointer()
        x, y = int(p.root_x), int(p.root_y)
        if x == 0 and y == 0:
            scr = Gdk.Screen.get_default()
            x = scr.get_width() // 2
            y = scr.get_height() // 2
        self.anchor_x, self.anchor_y = x, y

    def show_overlay(self):
        if self.active:
            return
        self.active = True
        self.overlay.show_at(self.anchor_x, self.anchor_y)

    def commit_if_needed(self):
        if not self.active:
            return

        self.active = False
        self.overlay.hide_overlay()

        dpi = self.cfg["dpis"][self.overlay.i]
        save_state(self.overlay.i)

        if not self.used_scroll or self.overlay.i == self.start_i:
            return

        def worker():
            ok = set_dpi_blocking(self.cfg["device_name"], dpi)
            if ok:
                notify("MX Master – DPI", f"Ustawiono: {dpi} DPI")
            else:
                notify("MX Master – DPI", f'Błąd: nie udało się ustawić DPI dla "{self.cfg["device_name"]}".')

        threading.Thread(target=worker, daemon=True).start()

    def step(self, direction: int, force: bool = False):
        now = int(time.time() * 1000)
        if not force and now - self.last_scroll_ms < self.cfg["scroll_debounce_ms"]:
            return
        self.last_scroll_ms = now

        n = len(self.cfg["dpis"])
        self.overlay.i = (self.overlay.i + direction) % n
        self.overlay.set_target_for_index(self.overlay.i)
        self.overlay.queue_draw()

    def is_mod_key_still_down(self) -> bool:
        keymap = self.d.query_keymap()
        keycode = self.cfg["mod_keycode"]
        return bool(keymap[keycode // 8] & (1 << (keycode % 8)))

    def check_mod_timeout(self):
        if self.mod_down:
            now = int(time.time() * 1000)
            if now - self.last_mod_ms > self.cfg["mod_timeout_ms"]:
                if self.is_mod_key_still_down():
                    # Modifier is still physically held (e.g. no autorepeat
                    # KeyPress arrived in time) - keep waiting for KeyRelease.
                    self.last_mod_ms = now
                    return True

                # No KeyRelease event ever arrived for this press - fall back
                # to releasing state as if it had.
                self.mod_down = False
                self.pending = False

                if self.pointer_grabbed:
                    self.ungrab_pointer()
                    self.pointer_grabbed = False

                self.commit_if_needed()

        return True

    def poll_x(self):
        try:
            while self.d.pending_events():
                e = self.d.next_event()

                if e.type == X.KeyPress and e.detail == self.cfg["mod_keycode"]:
                    now = int(time.time() * 1000)
                    self.last_mod_ms = now

                    if not self.mod_down:
                        self.mod_down = True
                        self.pending = True
                        self.used_scroll = False
                        self.start_i = self.overlay.i
                        self.last_scroll_ms = 0
                        self.snapshot_pointer_pos()

                        if not self.pointer_grabbed:
                            self.grab_pointer()
                            self.pointer_grabbed = True

                elif e.type == X.ButtonPress and self.mod_down:
                    if e.detail == self.cfg["scroll_up_button"]:
                        self.used_scroll = True
                        if self.pending:
                            self.pending = False
                            self.show_overlay()
                            self.step(+1, force=True)
                        else:
                            self.step(+1)

                    elif e.detail == self.cfg["scroll_down_button"]:
                        self.used_scroll = True
                        if self.pending:
                            self.pending = False
                            self.show_overlay()
                            self.step(-1, force=True)
                        else:
                            self.step(-1)

                elif e.type == X.KeyRelease and e.detail == self.cfg["mod_keycode"]:
                    if self.mod_down and not self.is_mod_key_still_down():
                        self.mod_down = False
                        self.pending = False

                        if self.pointer_grabbed:
                            self.ungrab_pointer()
                            self.pointer_grabbed = False

                        self.commit_if_needed()

        except Exception as ex:
            try:
                if self.pointer_grabbed:
                    self.ungrab_pointer()
                    self.pointer_grabbed = False
                self.overlay.hide_overlay()
            except Exception:
                pass
            notify("MX DPI Wheel – błąd", str(ex))

        return True


class KeycodeCaptureDialog(Gtk.Dialog):
    def __init__(self, parent, on_captured):
        super().__init__(title="Wykrywanie keycode", transient_for=parent, flags=0)
        self.set_modal(True)
        self.set_default_size(460, 140)
        self.add_button("Anuluj", Gtk.ResponseType.CANCEL)
        self.connect("response", self.on_response)

        box = self.get_content_area()
        box.set_spacing(10)
        box.set_border_width(12)

        label = Gtk.Label(
            label="Naciśnij teraz docelowy przycisk / klawisz.\nPo wykryciu keycode okno zamknie się samo.",
            xalign=0,
        )
        label.set_line_wrap(True)
        box.add(label)

        self.status = Gtk.Label(label="Czekam na pierwszy KeyPress…", xalign=0)
        box.add(self.status)

        self.on_captured = on_captured
        self.xd = None
        self.root = None
        self._active = False
        self._timer_id = None

        self.start_capture()
        self.show_all()

    def start_capture(self):
        try:
            self.xd = display.Display()
            self.root = self.xd.screen().root
            self.root.change_attributes(event_mask=X.KeyPressMask | X.KeyReleaseMask)
            self.root.grab_keyboard(False, X.GrabModeAsync, X.GrabModeAsync, X.CurrentTime)
            self._active = True
            self._timer_id = GLib.timeout_add(10, self.poll)
        except Exception as exc:
            self.status.set_text(f"Błąd startu nasłuchu: {exc}")

    def stop_capture(self):
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

        try:
            if self.xd is not None:
                self.xd.ungrab_keyboard(X.CurrentTime)
                self.xd.sync()
                self.xd.close()
        except Exception:
            pass

        self._active = False
        self.xd = None
        self.root = None

    def poll(self):
        if not self._active or self.xd is None:
            return False

        try:
            while self.xd.pending_events():
                event = self.xd.next_event()
                if event.type == X.KeyPress:
                    keycode = int(event.detail)
                    self.on_captured(keycode)
                    self.stop_capture()
                    self.response(Gtk.ResponseType.OK)
                    return False
        except Exception as exc:
            self.status.set_text(f"Błąd nasłuchu: {exc}")
            self.stop_capture()
            return False

        return True

    def on_response(self, *_args):
        self.stop_capture()
        self.destroy()


class DpiRow(Gtk.Box):
    def __init__(self, value, on_changed):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.on_changed = on_changed

        self.spin = Gtk.SpinButton()
        self.spin.set_numeric(True)
        self.spin.set_range(50, 20000)
        self.spin.set_increments(50, 100)
        self.spin.set_value(int(value))
        self.spin.connect("value-changed", lambda *_: self.on_changed())

        self.btn_up = Gtk.Button.new_with_label("↑")
        self.btn_down = Gtk.Button.new_with_label("↓")
        self.btn_remove = Gtk.Button.new_with_label("Usuń")

        self.pack_start(Gtk.Label(label="DPI:", xalign=0), False, False, 0)
        self.pack_start(self.spin, False, False, 0)
        self.pack_start(self.btn_up, False, False, 0)
        self.pack_start(self.btn_down, False, False, 0)
        self.pack_start(self.btn_remove, False, False, 0)

    def get_value(self):
        return int(self.spin.get_value())


class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="MX DPI Wheel – konfiguracja")
        self.set_default_size(700, 560)
        self.set_border_width(12)

        self.cfg = load_config()
        self.rows = []

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(root)

        intro = Gtk.Label(
            label=(
                "Ten sam plik działa w dwóch trybach:\n"
                "• bez argumentów → GUI konfiguracji\n"
                "• z --run → overlay DPI"
            ),
            xalign=0,
        )
        intro.set_line_wrap(True)
        root.pack_start(intro, False, False, 0)

        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        root.pack_start(grid, False, False, 0)

        row = 0

        grid.attach(Gtk.Label(label="Nazwa urządzenia Solaar:", xalign=0), 0, row, 1, 1)
        self.device_entry = Gtk.Entry()
        self.device_entry.set_text(str(self.cfg["device_name"]))
        self.device_entry.connect("changed", lambda *_: self.on_changed())
        grid.attach(self.device_entry, 1, row, 2, 1)
        row += 1

        grid.attach(Gtk.Label(label="Keycode przycisku modyfikującego:", xalign=0), 0, row, 1, 1)
        self.mod_keycode_spin = Gtk.SpinButton()
        self.mod_keycode_spin.set_numeric(True)
        self.mod_keycode_spin.set_range(8, 255)
        self.mod_keycode_spin.set_value(int(self.cfg["mod_keycode"]))
        self.mod_keycode_spin.connect("value-changed", lambda *_: self.on_changed())
        grid.attach(self.mod_keycode_spin, 1, row, 1, 1)

        detect_btn = Gtk.Button.new_with_label("Wykryj keycode")
        detect_btn.connect("clicked", self.on_detect_keycode)
        grid.attach(detect_btn, 2, row, 1, 1)
        row += 1

        grid.attach(Gtk.Label(label="Button scroll w górę:", xalign=0), 0, row, 1, 1)
        self.scroll_up_spin = Gtk.SpinButton()
        self.scroll_up_spin.set_numeric(True)
        self.scroll_up_spin.set_range(1, 24)
        self.scroll_up_spin.set_value(int(self.cfg["scroll_up_button"]))
        self.scroll_up_spin.connect("value-changed", lambda *_: self.on_changed())
        grid.attach(self.scroll_up_spin, 1, row, 1, 1)
        row += 1

        grid.attach(Gtk.Label(label="Button scroll w dół:", xalign=0), 0, row, 1, 1)
        self.scroll_down_spin = Gtk.SpinButton()
        self.scroll_down_spin.set_numeric(True)
        self.scroll_down_spin.set_range(1, 24)
        self.scroll_down_spin.set_value(int(self.cfg["scroll_down_button"]))
        self.scroll_down_spin.connect("value-changed", lambda *_: self.on_changed())
        grid.attach(self.scroll_down_spin, 1, row, 1, 1)
        row += 1

        info = Gtk.Label(
            label="Lista DPI w kolejności przełączania. Możesz dodawać, usuwać i zmieniać kolejność pozycji.",
            xalign=0
        )
        info.set_line_wrap(True)
        root.pack_start(info, False, False, 0)

        frame = Gtk.Frame(label="Lista DPI")
        root.pack_start(frame, True, True, 0)

        frame_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        frame_box.set_border_width(8)
        frame.add(frame_box)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)
        frame_box.pack_start(scrolled, True, True, 0)

        self.rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scrolled.add(self.rows_box)

        for dpi in self.cfg["dpis"]:
            self.add_dpi_row(dpi, mark_changed=False)

        add_btn = Gtk.Button.new_with_label("Dodaj DPI")
        add_btn.connect("clicked", self.on_add_dpi)
        frame_box.pack_start(add_btn, False, False, 0)

        adv = Gtk.Expander(label="Ustawienia zaawansowane")
        root.pack_start(adv, False, False, 0)

        adv_grid = Gtk.Grid(column_spacing=12, row_spacing=10, margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)
        adv.add(adv_grid)

        adv_row = 0

        self.radius_spin = Gtk.SpinButton()
        self.radius_spin.set_numeric(True)
        self.radius_spin.set_range(40, 500)
        self.radius_spin.set_value(int(self.cfg["radius"]))
        self.radius_spin.connect("value-changed", lambda *_: self.on_changed())
        adv_grid.attach(Gtk.Label(label="Radius:", xalign=0), 0, adv_row, 1, 1)
        adv_grid.attach(self.radius_spin, 1, adv_row, 1, 1)
        adv_row += 1

        self.window_size_spin = Gtk.SpinButton()
        self.window_size_spin.set_numeric(True)
        self.window_size_spin.set_range(180, 1000)
        self.window_size_spin.set_value(int(self.cfg["window_size"]))
        self.window_size_spin.connect("value-changed", lambda *_: self.on_changed())
        adv_grid.attach(Gtk.Label(label="Window size:", xalign=0), 0, adv_row, 1, 1)
        adv_grid.attach(self.window_size_spin, 1, adv_row, 1, 1)
        adv_row += 1

        self.anim_fps_spin = Gtk.SpinButton()
        self.anim_fps_spin.set_numeric(True)
        self.anim_fps_spin.set_range(10, 240)
        self.anim_fps_spin.set_value(int(self.cfg["anim_fps"]))
        self.anim_fps_spin.connect("value-changed", lambda *_: self.on_changed())
        adv_grid.attach(Gtk.Label(label="FPS animacji:", xalign=0), 0, adv_row, 1, 1)
        adv_grid.attach(self.anim_fps_spin, 1, adv_row, 1, 1)
        adv_row += 1

        self.anim_ease_spin = Gtk.SpinButton()
        self.anim_ease_spin.set_digits(2)
        self.anim_ease_spin.set_numeric(True)
        self.anim_ease_spin.set_range(0.01, 1.0)
        self.anim_ease_spin.set_increments(0.01, 0.05)
        self.anim_ease_spin.set_value(float(self.cfg["anim_ease"]))
        self.anim_ease_spin.connect("value-changed", lambda *_: self.on_changed())
        adv_grid.attach(Gtk.Label(label="Ease animacji:", xalign=0), 0, adv_row, 1, 1)
        adv_grid.attach(self.anim_ease_spin, 1, adv_row, 1, 1)
        adv_row += 1

        self.debounce_spin = Gtk.SpinButton()
        self.debounce_spin.set_numeric(True)
        self.debounce_spin.set_range(0, 1000)
        self.debounce_spin.set_value(int(self.cfg["scroll_debounce_ms"]))
        self.debounce_spin.connect("value-changed", lambda *_: self.on_changed())
        adv_grid.attach(Gtk.Label(label="Scroll debounce [ms]:", xalign=0), 0, adv_row, 1, 1)
        adv_grid.attach(self.debounce_spin, 1, adv_row, 1, 1)
        adv_row += 1

        self.mod_timeout_spin = Gtk.SpinButton()
        self.mod_timeout_spin.set_numeric(True)
        self.mod_timeout_spin.set_range(50, 3000)
        self.mod_timeout_spin.set_value(int(self.cfg["mod_timeout_ms"]))
        self.mod_timeout_spin.connect("value-changed", lambda *_: self.on_changed())
        adv_grid.attach(Gtk.Label(label="Mod timeout [ms]:", xalign=0), 0, adv_row, 1, 1)
        adv_grid.attach(self.mod_timeout_spin, 1, adv_row, 1, 1)
        adv_row += 1

        self.status = Gtk.Label(label="", xalign=0)
        root.pack_start(self.status, False, False, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        root.pack_start(actions, False, False, 0)

        btn_reload = Gtk.Button.new_with_label("Wczytaj z pliku")
        btn_reload.connect("clicked", self.on_reload)

        btn_save = Gtk.Button.new_with_label("Zapisz")
        btn_save.connect("clicked", self.on_save)

        btn_open_cfg = Gtk.Button.new_with_label("Otwórz config.json")
        btn_open_cfg.connect("clicked", self.on_open_config)

        btn_run = Gtk.Button.new_with_label("Uruchom wheel (--run)")
        btn_run.connect("clicked", self.on_run_wheel)

        btn_close = Gtk.Button.new_with_label("Zamknij")
        btn_close.connect("clicked", lambda *_: Gtk.main_quit())

        actions.pack_start(btn_reload, False, False, 0)
        actions.pack_start(btn_open_cfg, False, False, 0)
        actions.pack_start(btn_run, False, False, 0)
        actions.pack_end(btn_close, False, False, 0)
        actions.pack_end(btn_save, False, False, 0)

        self.set_status(f"Config: {CONFIG_PATH}")

    def set_status(self, text):
        self.status.set_text(text)

    def on_changed(self):
        self.set_status("Masz niezapisane zmiany.")

    def clear_rows(self):
        for row in self.rows:
            self.rows_box.remove(row)
        self.rows = []

    def add_dpi_row(self, value=1200, position=None, mark_changed=True):
        row = DpiRow(value, self.on_changed)
        row.btn_remove.connect("clicked", self.on_remove_row, row)
        row.btn_up.connect("clicked", self.on_move_row, row, -1)
        row.btn_down.connect("clicked", self.on_move_row, row, +1)

        if position is None or position >= len(self.rows):
            self.rows.append(row)
            self.rows_box.pack_start(row, False, False, 0)
        else:
            self.rows.insert(position, row)
            self.refresh_row_order()

        self.rows_box.show_all()
        if mark_changed:
            self.on_changed()

    def refresh_row_order(self):
        for child in list(self.rows_box.get_children()):
            self.rows_box.remove(child)
        for row in self.rows:
            self.rows_box.pack_start(row, False, False, 0)
        self.rows_box.show_all()

    def on_add_dpi(self, *_):
        last = self.rows[-1].get_value() if self.rows else 1200
        self.add_dpi_row(last)

    def on_remove_row(self, _btn, row):
        if len(self.rows) <= 1:
            self.set_status("Musi zostać przynajmniej jedna wartość DPI.")
            return
        self.rows.remove(row)
        self.rows_box.remove(row)
        self.rows_box.show_all()
        self.on_changed()

    def on_move_row(self, _btn, row, direction):
        idx = self.rows.index(row)
        new_idx = idx + direction
        if 0 <= new_idx < len(self.rows):
            self.rows[idx], self.rows[new_idx] = self.rows[new_idx], self.rows[idx]
            self.refresh_row_order()
            self.on_changed()

    def on_detect_keycode(self, *_):
        self.set_status("Nasłuch keycode… naciśnij docelowy przycisk.")
        KeycodeCaptureDialog(self, self.on_keycode_captured)

    def on_keycode_captured(self, keycode):
        self.mod_keycode_spin.set_value(int(keycode))
        self.set_status(f"Wykryto keycode: {keycode}")

    def collect_config(self):
        dpis = [row.get_value() for row in self.rows]
        dpis = [dpi for dpi in dpis if dpi > 0]
        if not dpis:
            raise ValueError("Lista DPI nie może być pusta.")

        device_name = self.device_entry.get_text().strip()
        if not device_name:
            raise ValueError("Nazwa urządzenia Solaar nie może być pusta.")

        cfg = dict(DEFAULT_CONFIG)
        cfg["device_name"] = device_name
        cfg["mod_keycode"] = int(self.mod_keycode_spin.get_value())
        cfg["scroll_up_button"] = int(self.scroll_up_spin.get_value())
        cfg["scroll_down_button"] = int(self.scroll_down_spin.get_value())
        cfg["dpis"] = dpis
        cfg["radius"] = int(self.radius_spin.get_value())
        cfg["window_size"] = int(self.window_size_spin.get_value())
        cfg["anim_fps"] = int(self.anim_fps_spin.get_value())
        cfg["anim_ease"] = float(self.anim_ease_spin.get_value())
        cfg["scroll_debounce_ms"] = int(self.debounce_spin.get_value())
        cfg["mod_timeout_ms"] = int(self.mod_timeout_spin.get_value())
        return cfg

    def on_save(self, *_):
        try:
            cfg = self.collect_config()
            save_config(cfg)
            self.set_status(f"Zapisano: {CONFIG_PATH}")
        except Exception as exc:
            self.set_status(f"Błąd zapisu: {exc}")

    def on_reload(self, *_):
        self.cfg = load_config()
        self.device_entry.set_text(str(self.cfg["device_name"]))
        self.mod_keycode_spin.set_value(int(self.cfg["mod_keycode"]))
        self.scroll_up_spin.set_value(int(self.cfg["scroll_up_button"]))
        self.scroll_down_spin.set_value(int(self.cfg["scroll_down_button"]))
        self.radius_spin.set_value(int(self.cfg["radius"]))
        self.window_size_spin.set_value(int(self.cfg["window_size"]))
        self.anim_fps_spin.set_value(int(self.cfg["anim_fps"]))
        self.anim_ease_spin.set_value(float(self.cfg["anim_ease"]))
        self.debounce_spin.set_value(int(self.cfg["scroll_debounce_ms"]))
        self.mod_timeout_spin.set_value(int(self.cfg["mod_timeout_ms"]))

        self.clear_rows()
        for dpi in self.cfg["dpis"]:
            self.add_dpi_row(dpi, mark_changed=False)
        self.set_status(f"Wczytano: {CONFIG_PATH}")

    def on_open_config(self, *_):
        ensure_config_exists()
        try:
            subprocess.Popen(["xdg-open", str(CONFIG_PATH)])
            self.set_status("Otwieram config.json…")
        except Exception as exc:
            self.set_status(f"Nie udało się otworzyć configu: {exc}")

    def on_run_wheel(self, *_):
        script_path = Path(__file__).resolve()
        try:
            subprocess.Popen([sys.executable, str(script_path), "--run"])
            self.set_status("Uruchomiono tryb wheel (--run).")
        except Exception as exc:
            self.set_status(f"Nie udało się uruchomić wheel: {exc}")


def launch_gui():
    ensure_config_exists()
    win = MainWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


def run_wheel():
    ensure_config_exists()
    acquire_run_lock()
    cfg = load_config()
    try:
        Controller(cfg)
    except Exception as exc:
        notify("MX DPI Wheel", str(exc))
        print(f"MX DPI Wheel: {exc}", file=sys.stderr)
        return 1
    Gtk.main()
    return 0


def print_help_and_exit(parser, exit_code=0):
    parser.print_help()
    sys.exit(exit_code)


def build_parser():
    parser = argparse.ArgumentParser(
        description="MX DPI Wheel: bez argumentów uruchamia GUI, z --run uruchamia overlay DPI."
    )
    parser.add_argument("--run", action="store_true", help="Uruchom właściwy wheel / overlay DPI.")
    parser.add_argument("--gui", action="store_true", help="Jawnie uruchom GUI konfiguracji.")
    parser.add_argument("--print-config-path", action="store_true", help="Wypisz ścieżkę do config.json i zakończ.")
    parser.add_argument("--reset-config", action="store_true", help="Nadpisz config.json wartościami domyślnymi i zakończ.")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.print_config_path:
        print(CONFIG_PATH)
        return 0

    if args.reset_config:
        save_config(dict(DEFAULT_CONFIG))
        print(f"Zresetowano config: {CONFIG_PATH}")
        return 0

    if args.run:
        return run_wheel()

    if args.gui or len(sys.argv) == 1:
        launch_gui()
        return 0

    print_help_and_exit(parser, 1)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
