# -*- coding: utf-8 -*-
"""Mando y teclado -> acciones de la interfaz.

El mapeo del mando se lee de es_input.cfg (el mismo que usa EmulationStation),
asi los botones coinciden siempre con los de ArkOS en cualquier R36S/clon.
Si no se encuentra, se usan valores conocidos para los mandos de ArkOS."""
import os
import xml.etree.ElementTree as ET

import sdl
from library import parse_xml_lenient

ACTIONS = ("up", "down", "left", "right", "a", "b", "x", "y", "l1", "r1", "l2", "r2",
           "start", "select", "hotkey")
REPEATABLE = ("up", "down", "left", "right", "l1", "r1", "l2", "r2")

# nombre en es_input.cfg -> accion
_ES_NAMES = {
    "up": "up", "down": "down", "left": "left", "right": "right",
    "a": "a", "b": "b", "x": "x", "y": "y",
    "start": "start", "select": "select",
    "leftshoulder": "l1", "pageup": "l1",
    "rightshoulder": "r1", "pagedown": "r1",
    "lefttrigger": "l2", "l2": "l2",
    "righttrigger": "r2", "r2": "r2",
    "hotkeyenable": "hotkey",
    "leftanalogup": "up", "leftanalogdown": "down",
    "leftanalogleft": "left", "leftanalogright": "right",
    "joystick1up": "up", "joystick1left": "left",
}

# Mandos integrados conocidos (gamecontrollerdb de ArkOS / PortMaster)
_KNOWN = {
    # R36S, RG351MP y compatibles
    "GO-Super Gamepad": dict(a=1, b=0, x=2, y=3, l1=4, r1=5, l2=6, r2=7, up=8, down=9, left=10,
                             right=11, select=12, start=13, hotkey=16),
    "GO-Advance Gamepad (rev 1.1)": dict(a=1, b=0, x=2, y=3, l1=4, r1=5, l2=14, r2=15, up=8,
                                         down=9, left=10, right=11, select=12, start=17),
    "GO-Advance Gamepad": dict(a=1, b=0, x=2, y=3, l1=4, r1=5, l2=12, r2=13, up=6, down=7,
                               left=8, right=9, select=10, start=15),
    "GO-Ultra Gamepad": dict(a=1, b=0, x=2, y=3, l1=4, r1=5, l2=6, r2=7, up=8, down=9, left=10,
                             right=11, select=12, start=17, hotkey=13),
}

_KEYS = {
    sdl.SDLK_UP: "up", sdl.SDLK_DOWN: "down", sdl.SDLK_LEFT: "left", sdl.SDLK_RIGHT: "right",
    sdl.SDLK_RETURN: "a", sdl.SDLK_KP_ENTER: "a", ord("z"): "a", sdl.SDLK_SPACE: "a",
    sdl.SDLK_ESCAPE: "b", sdl.SDLK_BACKSPACE: "b", ord("x"): "b",
    ord("c"): "x", ord("v"): "y",
    ord("q"): "l1", sdl.SDLK_PAGEUP: "l1", ord("e"): "r1", sdl.SDLK_PAGEDOWN: "r1",
    sdl.SDLK_HOME: "l2", sdl.SDLK_END: "r2",
    ord("s"): "start", sdl.SDLK_F1: "start", sdl.SDLK_TAB: "select", ord("a"): "select",
}


class Binding(object):
    def __init__(self):
        self.buttons = {}  # boton -> accion
        self.hats = {}     # (hat, valor) -> accion
        self.axes = {}     # (eje, signo) -> accion

    def empty(self):
        return not (self.buttons or self.hats or self.axes)


def load_es_input(paths):
    """Devuelve lista de (deviceName, deviceGUID, Binding) leidas de es_input.cfg."""
    out = []
    for p in paths:
        if not os.path.isfile(p):
            continue
        try:
            root = parse_xml_lenient(p)
        except (ET.ParseError, IOError, OSError):
            continue
        for ic in root.iter("inputConfig"):
            if ic.get("type") != "joystick":
                continue
            b = Binding()
            # 'hotkeyenable' suele compartir boton con SELECT: se asigna al final
            # y solo si ese boton esta libre, para no perder SELECT.
            inputs = sorted(ic.iter("input"),
                            key=lambda n: (n.get("name") or "").lower() == "hotkeyenable")
            for inp in inputs:
                act = _ES_NAMES.get((inp.get("name") or "").lower())
                if not act:
                    continue
                typ = inp.get("type")
                try:
                    iid = int(inp.get("id", "-1"))
                    val = int(inp.get("value", "1"))
                except ValueError:
                    continue
                if typ == "button":
                    b.buttons.setdefault(iid, act)
                elif typ == "hat":
                    b.hats.setdefault((iid, val), act)
                elif typ == "axis":
                    b.axes.setdefault((iid, 1 if val > 0 else -1), act)
            if not b.empty():
                out.append((ic.get("deviceName", ""), (ic.get("deviceGUID") or "").lower(), b))
    return out


def _default_binding(name):
    b = Binding()
    known = _KNOWN.get(name)
    if known is None:
        for k, v in _KNOWN.items():
            if name and k.lower() in name.lower():
                known = v
                break
    if known is None:
        # mando generico (disposicion SDL/Xbox)
        known = dict(a=0, b=1, x=2, y=3, l1=4, r1=5, select=6, start=7, hotkey=8)
    for act, btn in known.items():
        b.buttons[btn] = act
    return b


def _complete(binding, name):
    """Si en es_input.cfg faltan botones (p. ej. L2/R2 sin configurar) y el mando es
    uno conocido, se completan con sus valores de fabrica sin pisar nada."""
    known = None
    for k, v in _KNOWN.items():
        if name == k or (name and k.lower() in name.lower()):
            known = v
            break
    if known is None:
        return binding
    mapped = set(binding.buttons.values()) | set(binding.hats.values()) | \
        set(binding.axes.values())
    for act, btn in known.items():
        if act not in mapped and btn not in binding.buttons:
            binding.buttons[btn] = act
    return binding


class Input(object):
    REPEAT_DELAY = 360
    REPEAT_RATE = 70
    REPEAT_FAST = 35
    AXIS_DEAD = 16000

    def __init__(self, es_input_paths, swap_ab=False):
        self.configs = load_es_input(es_input_paths)
        # "SWITCH A/B BUTTONS IN EMULATIONSTATION" activado en ES
        self.swap_ab = swap_ab
        self.joys = {}  # instance id -> (ptr, Binding)
        self.held = {}  # accion -> (t_pulsado, t_proxima_repeticion)
        self.axis_state = {}
        self.hat_state = {}
        self.pressed = set()

    def open_all(self):
        for i in range(sdl.SDL_NumJoysticks()):
            self.open(i)

    def open(self, index):
        if sdl.SDL_JoystickGetDeviceInstanceID(index) in self.joys:
            return
        js = sdl.SDL_JoystickOpen(index)
        if not js:
            return
        iid = sdl.SDL_JoystickInstanceID(js)
        if iid in self.joys:
            return
        raw = sdl.SDL_JoystickName(js)
        name = raw.decode("utf-8", "replace") if raw else ""
        buf = ctypes_buf(64)
        try:
            sdl.SDL_JoystickGetGUIDString(sdl.SDL_JoystickGetGUID(js), buf, 64)
            guid = buf.value.decode("ascii", "replace").lower()
        except Exception:
            guid = ""
        self.joys[iid] = (js, self._binding_for(name, guid))

    def _binding_for(self, name, guid):
        for n, g, b in self.configs:
            if guid and g == guid:
                return _complete(b, name)
        for n, g, b in self.configs:
            if n and n == name:
                return _complete(b, name)
        if name in _KNOWN or any(k.lower() in (name or "").lower() for k in _KNOWN):
            return _default_binding(name)
        if self.configs:
            return self.configs[0][2]
        return _default_binding(name)

    def close(self, iid):
        ent = self.joys.pop(iid, None)
        if ent:
            sdl.SDL_JoystickClose(ent[0])

    # -------------------------------------------------------------------
    def _down(self, act, now, out):
        if act in self.pressed:
            return
        self.pressed.add(act)
        out.append(act)
        if act in REPEATABLE:
            self.held[act] = (now, now + self.REPEAT_DELAY)

    def _up(self, act):
        self.pressed.discard(act)
        self.held.pop(act, None)

    def handle(self, ev, now):
        """Traduce un evento SDL a una lista de acciones."""
        out = []
        t = ev.type
        if t == sdl.SDL_KEYDOWN:
            if ev.repeat:
                return out
            act = _KEYS.get(ev.key)
            if act:
                self._down(act, now, out)
        elif t == sdl.SDL_KEYUP:
            act = _KEYS.get(ev.key)
            if act:
                self._up(act)
        elif t in (sdl.SDL_JOYBUTTONDOWN, sdl.SDL_JOYBUTTONUP):
            ent = self.joys.get(ev.which)
            if ent:
                act = ent[1].buttons.get(ev.index)
                if self.swap_ab and act in ("a", "b"):
                    act = "b" if act == "a" else "a"
                if act:
                    if t == sdl.SDL_JOYBUTTONDOWN:
                        self._down(act, now, out)
                    else:
                        self._up(act)
        elif t == sdl.SDL_JOYHATMOTION:
            ent = self.joys.get(ev.which)
            b = ent[1] if ent else None
            prev = self.hat_state.get((ev.which, ev.index), 0)
            self.hat_state[(ev.which, ev.index)] = ev.value
            for bit, default in ((sdl.SDL_HAT_UP, "up"), (sdl.SDL_HAT_DOWN, "down"),
                                 (sdl.SDL_HAT_LEFT, "left"), (sdl.SDL_HAT_RIGHT, "right")):
                act = (b.hats.get((ev.index, bit)) if b else None) or default
                if ev.value & bit and not prev & bit:
                    self._down(act, now, out)
                elif prev & bit and not ev.value & bit:
                    self._up(act)
        elif t == sdl.SDL_JOYAXISMOTION:
            ent = self.joys.get(ev.which)
            b = ent[1] if ent else None
            sign = 0
            if ev.value > self.AXIS_DEAD:
                sign = 1
            elif ev.value < -self.AXIS_DEAD:
                sign = -1
            key = (ev.which, ev.index)
            prev = self.axis_state.get(key, 0)
            if sign == prev:
                return out
            self.axis_state[key] = sign

            def axis_act(s):
                if b is not None:
                    a = b.axes.get((ev.index, s))
                    if a:
                        return a
                if ev.index == 0:
                    return "left" if s < 0 else "right"
                if ev.index == 1:
                    return "up" if s < 0 else "down"
                return None

            if prev:
                a = axis_act(prev)
                if a:
                    self._up(a)
            if sign:
                a = axis_act(sign)
                if a:
                    self._down(a, now, out)
        elif t == sdl.SDL_JOYDEVICEADDED:
            self.open(ev.which)
        elif t == sdl.SDL_JOYDEVICEREMOVED:
            self.close(ev.which)
        return out

    def repeats(self, now):
        out = []
        for act, (t0, tnext) in list(self.held.items()):
            if now >= tnext:
                rate = self.REPEAT_FAST if now - t0 > 1500 else self.REPEAT_RATE
                self.held[act] = (t0, now + rate)
                out.append(act)
        return out

    def next_repeat_ms(self, now):
        if not self.held:
            return None
        return max(0, min(t for _a, (_t0, t) in self.held.items()) - now)

    def reset(self):
        self.held.clear()
        self.pressed.clear()

    def close_all(self):
        for iid in list(self.joys):
            self.close(iid)


def ctypes_buf(n):
    import ctypes
    return ctypes.create_string_buffer(n)
