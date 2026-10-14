import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "ports", "vapor"))

try:
    import inputmap
    import sdl
except OSError:  # sin SDL2 en el sistema
    inputmap = None

ES_INPUT = """<?xml version="1.0"?>
<inputList>
  <inputConfig type="joystick" deviceName="GO-Super Gamepad" deviceGUID="ABC">
    <input name="hotkeyenable" type="button" id="12" value="1"/>
    <input name="select" type="button" id="12" value="1"/>
    <input name="a" type="button" id="1" value="1"/>
    <input name="up" type="hat" id="0" value="1"/>
    <input name="leftanalogleft" type="axis" id="0" value="-1"/>
    <input name="pageup" type="button" id="4" value="1"/>
  </inputConfig>
</inputList>
"""


class Ev(object):
    def __init__(self, type, which=0, index=0, value=0, key=0):
        self.type = type
        self.which = which
        self.index = index
        self.value = value
        self.key = key
        self.repeat = 0


@unittest.skipIf(inputmap is None, "SDL2 no disponible")
class InputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "es_input.cfg")
        with open(self.path, "w") as f:
            f.write(ES_INPUT)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_parse_and_hotkey_does_not_steal_select(self):
        cfgs = inputmap.load_es_input([self.path])
        self.assertEqual(len(cfgs), 1)
        name, guid, b = cfgs[0]
        self.assertEqual(guid, "abc")
        self.assertEqual(b.buttons[12], "select")
        self.assertEqual(b.buttons[1], "a")
        self.assertEqual(b.buttons[4], "l1")
        self.assertEqual(b.hats[(0, 1)], "up")
        self.assertEqual(b.axes[(0, -1)], "left")

    def test_events_and_repeat(self):
        inp = inputmap.Input([self.path])
        inp.joys[7] = (None, inp._binding_for("GO-Super Gamepad", "abc"))
        acts = inp.handle(Ev(sdl.SDL_JOYBUTTONDOWN, 7, 12), 0)
        self.assertEqual(acts, ["select"])
        acts = inp.handle(Ev(sdl.SDL_JOYHATMOTION, 7, 0, sdl.SDL_HAT_UP), 0)
        self.assertEqual(acts, ["up"])
        self.assertEqual(inp.repeats(100), [])
        self.assertEqual(inp.repeats(inp.REPEAT_DELAY + 1), ["up"])
        inp.handle(Ev(sdl.SDL_JOYHATMOTION, 7, 0, 0), 500)
        self.assertEqual(inp.repeats(5000), [])
        acts = inp.handle(Ev(sdl.SDL_JOYAXISMOTION, 7, 1, value=30000), 0)
        self.assertEqual(acts, ["down"])

    def test_swap_ab_like_emulationstation(self):
        inp = inputmap.Input([self.path], swap_ab=True)
        inp.joys[1] = (None, inp._binding_for("GO-Super Gamepad", "abc"))
        self.assertEqual(inp.handle(Ev(sdl.SDL_JOYBUTTONDOWN, 1, 1), 0), ["b"])

    def test_known_default_for_r36s(self):
        b = inputmap._default_binding("GO-Super Gamepad")
        self.assertEqual(b.buttons[13], "start")
        self.assertEqual(b.buttons[8], "up")


if __name__ == "__main__":
    unittest.main()
