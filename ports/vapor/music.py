# -*- coding: utf-8 -*-
"""Musica de fondo: reproduce en orden aleatorio las canciones del usuario.

Carpetas que se buscan (todas las que existan):
  - ports/vapor/music/          (la propia de Vapor)
  - ~/.emulationstation/music   (la de EmulationStation)
  - /roms/bgmusic, /roms2/bgmusic
  - MusicDirectory / UserMusicDirectory de es_settings.cfg
"""
import os
import random

import sdl

EXTS = (".mp3", ".ogg", ".wav", ".flac", ".mod", ".xm", ".s3m", ".it", ".opus")


def music_dirs(app_dir, home, es_settings):
    dirs = [os.path.join(app_dir, "music"),
            os.path.join(home, ".emulationstation", "music"),
            "/roms/bgmusic", "/roms2/bgmusic"]
    for key in ("MusicDirectory", "UserMusicDirectory"):
        v = (es_settings or {}).get(key)
        if v:
            dirs.append(v)
    out = []
    for d in dirs:
        d = os.path.abspath(d)
        if d not in out:
            out.append(d)
    return out


def find_songs(dirs):
    songs = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, subdirs, names in os.walk(d):
            subdirs[:] = [x for x in subdirs if not x.startswith(".")]
            for n in names:
                if not n.startswith(".") and os.path.splitext(n)[1].lower() in EXTS:
                    songs.append(os.path.join(root, n))
    return sorted(set(songs))


class MusicPlayer(object):
    FADE_MS = 800

    def __init__(self, dirs):
        self.dirs = dirs
        self.songs = find_songs(dirs)
        self.queue = []
        self.current = None
        self.music = None
        self.ok = False
        self.enabled = False
        self.volume = 70
        self.last_check = 0
        self.error = ""
        self.started = False

    @property
    def available(self):
        return sdl.MIX is not None

    def _open(self):
        if self.ok or not self.available:
            return self.ok
        try:
            sdl.Mix_Init(sdl.MIX_INIT_MP3 | sdl.MIX_INIT_OGG | sdl.MIX_INIT_FLAC |
                         sdl.MIX_INIT_MOD)
            if sdl.Mix_OpenAudio(44100, sdl.AUDIO_S16SYS, 2, 4096) != 0:
                self.error = sdl.error()
                return False
            self.ok = True
            sdl.Mix_VolumeMusic(self._mix_volume())
        except Exception as e:  # pragma: no cover - depende del sistema
            self.error = str(e)
        return self.ok

    def _mix_volume(self):
        return int(round(128 * max(0, min(100, self.volume)) / 100.0))

    def _next_path(self):
        if not self.songs:
            return None
        if not self.queue:
            self.queue = list(self.songs)
            random.shuffle(self.queue)
            # que no se repita la misma cancion dos veces seguidas
            if len(self.queue) > 1 and self.queue[0] == self.current:
                self.queue.append(self.queue.pop(0))
        return self.queue.pop(0)

    def start(self, enabled=True, volume=70):
        self.enabled = enabled
        self.volume = volume
        if enabled and self.songs:
            self.play_next(fade=True)

    def play_next(self, fade=False):
        if not self.songs or not self._open():
            return None
        self._free()
        for _ in range(min(5, len(self.songs))):
            path = self._next_path()
            mus = sdl.Mix_LoadMUS(os.fsencode(path))
            if not mus:
                self.error = sdl.error()
                continue
            self.music = mus
            self.current = path
            sdl.Mix_VolumeMusic(self._mix_volume())
            if fade:
                sdl.Mix_FadeInMusic(mus, 1, self.FADE_MS)
            else:
                sdl.Mix_PlayMusic(mus, 1)
            self.started = True
            return path
        return None

    def set_enabled(self, on):
        self.enabled = on
        if on:
            if not self.ok or not sdl.Mix_PlayingMusic():
                self.play_next(fade=True)
        elif self.ok:
            sdl.Mix_HaltMusic()
            self._free()

    def set_volume(self, v):
        self.volume = max(0, min(100, int(v)))
        if self.ok:
            sdl.Mix_VolumeMusic(self._mix_volume())

    def tick(self, now):
        """Llamar a menudo: cuando acaba una cancion pone otra al azar."""
        if not self.enabled or not self.ok or now - self.last_check < 700:
            return False
        self.last_check = now
        if not sdl.Mix_PlayingMusic():
            return self.play_next() is not None
        return False

    def current_name(self):
        if not self.current:
            return ""
        return os.path.splitext(os.path.basename(self.current))[0]

    def _free(self):
        if self.music:
            sdl.Mix_HaltMusic()
            sdl.Mix_FreeMusic(self.music)
            self.music = None

    def stop(self, fade_ms=0):
        if not self.ok:
            return
        if fade_ms and sdl.Mix_PlayingMusic():
            sdl.Mix_FadeOutMusic(fade_ms)
            sdl.SDL_Delay(fade_ms)
        self._free()
        sdl.Mix_CloseAudio()
        sdl.Mix_Quit()
        self.ok = False
