"""Musica de fondo con el driver de audio 'dummy' de SDL."""
import os
import shutil
import struct
import sys
import tempfile
import time
import unittest
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "ports", "vapor"))
os.environ["SDL_AUDIODRIVER"] = "dummy"

try:
    import sdl
    import music
except OSError:
    sdl = None


def make_wav(path, secs=0.3):
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(struct.pack("<h", 0) * int(22050 * secs))


@unittest.skipIf(sdl is None or sdl.MIX is None, "SDL2_mixer no disponible")
class MusicTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dir = os.path.join(self.tmp, "music")
        os.makedirs(os.path.join(self.dir, "sub"))
        for n in ("uno.wav", "dos.wav", "sub/tres.wav"):
            make_wav(os.path.join(self.dir, n))
        open(os.path.join(self.dir, "LEEME.txt"), "w").close()
        open(os.path.join(self.dir, ".oculta.wav"), "w").close()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_find_songs_and_dirs(self):
        songs = music.find_songs([self.dir, "/no/existe"])
        self.assertEqual(sorted(os.path.basename(s) for s in songs),
                         ["dos.wav", "tres.wav", "uno.wav"])
        dirs = music.music_dirs("/app", "/home/ark", {"MusicDirectory": "/roms/mis"})
        self.assertEqual(dirs[0], "/app/music")
        self.assertIn("/home/ark/.emulationstation/music", dirs)
        self.assertIn("/roms/mis", dirs)

    def test_shuffle_play_next_volume(self):
        p = music.MusicPlayer([self.dir])
        try:
            p.start(True, 50)
            self.assertTrue(p.ok, p.error)
            first = p.current
            self.assertIsNotNone(first)
            self.assertEqual(sdl.Mix_VolumeMusic(-1), 64)
            # cuando acaba la cancion, tick() pone otra distinta
            time.sleep(0.6)
            seen = {first}
            for _ in range(3):
                sdl.Mix_HaltMusic()
                self.assertTrue(p.tick(p.last_check + 1000))
                self.assertNotEqual(p.current, None)
                seen.add(p.current)
            self.assertGreaterEqual(len(seen), 2)
            p.set_enabled(False)
            self.assertFalse(sdl.Mix_PlayingMusic())
            self.assertFalse(p.tick(10 ** 9))
        finally:
            p.stop()

    def test_no_songs_is_quiet(self):
        p = music.MusicPlayer([os.path.join(self.tmp, "vacia")])
        p.start(True, 70)
        self.assertIsNone(p.current)
        self.assertFalse(p.tick(10 ** 9))
        p.stop()


if __name__ == "__main__":
    unittest.main()
