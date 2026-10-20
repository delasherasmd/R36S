# -*- coding: utf-8 -*-
"""Datos propios de Vapor: categorias, favoritos, ajustes e historial de juego.

Todo se guarda en ports/vapor/data/ (en la tarjeta SD), asi que se puede copiar
o editar desde el PC. library.json es JSON legible."""
import io
import json
import os
import re
import time

DEFAULT_SETTINGS = {
    "view": "grid",          # grid | list
    "sort": "name",          # name | system | recent | playtime | playcount
    "sort_list": "priority",  # orden dentro de listas y favoritos (priority = el tuyo)
    "tab": "all",
    "lang": "es",
    "show_genres": True,
    # personalizacion
    "theme": "vapor",
    "accent": "auto",
    "tile_size": "normal",
    "brightness": None,      # None = no tocar el brillo del sistema
    "music": True,
    "music_volume": 70,
    "clock_24h": True,
    "clock_autosync": True,  # poner en hora por internet al abrir Vapor
}


def _atomic_write(path, text):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)


def safe_filename(name):
    n = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "-", name).strip(" .")
    return n or "categoria"


class Stats(object):
    __slots__ = ("playtime", "last", "count")

    def __init__(self):
        self.playtime = 0
        self.last = 0
        self.count = 0


class Store(object):
    def __init__(self, data_dir):
        self.data_dir = data_dir
        if not os.path.isdir(data_dir):
            os.makedirs(data_dir)
        self.path = os.path.join(data_dir, "library.json")
        self.history_path = os.path.join(data_dir, "history.log")
        self.data = {
            "version": 1,
            "categories": [],
            "favorites": {},
            "fav_order": [],
            "settings": dict(DEFAULT_SETTINGS),
            "es_imported": False,
        }
        self.stats = {}
        self.dirty = False
        self.load()
        self.load_history()

    # --------------------------------------------------------------- disco
    def load(self):
        d = None
        for path in (self.path, self.path + ".bak"):
            if not os.path.isfile(path):
                continue
            try:
                with io.open(path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                break
            except (IOError, OSError, ValueError):
                # se guarda el fichero roto aparte y se prueba con la copia
                try:
                    os.replace(path, path + ".roto")
                except OSError:
                    pass
                d = None
        if d is None:
            return
        if not isinstance(d, dict):
            return
        cats = []
        for c in d.get("categories", []):
            if isinstance(c, dict) and c.get("name"):
                games = []
                for g in c.get("games", []):
                    if isinstance(g, str) and g not in games:
                        games.append(g)
                cats.append({"name": str(c["name"]), "games": games,
                             "pinned": bool(c.get("pinned", False))})
        self.data["categories"] = cats
        fav = d.get("favorites", {})
        if isinstance(fav, dict):
            self.data["favorites"] = dict((k, bool(v)) for k, v in fav.items())
        order = d.get("fav_order", [])
        if isinstance(order, list):
            self.data["fav_order"] = [p for p in order if isinstance(p, str)]
        st = d.get("settings", {})
        if isinstance(st, dict):
            self.data["settings"].update(st)
        self.data["es_imported"] = bool(d.get("es_imported", False))
        self.data["es_import_ok"] = bool(d.get("es_import_ok", False))

    def save(self):
        if not self.dirty:
            return True
        try:
            # se conserva la version anterior como copia de seguridad
            if os.path.isfile(self.path):
                try:
                    with io.open(self.path, "rb") as f:
                        old = f.read()
                    with io.open(self.path + ".bak", "wb") as f:
                        f.write(old)
                except (IOError, OSError):
                    pass
            _atomic_write(self.path, json.dumps(self.data, ensure_ascii=False, indent=1))
            self.dirty = False
            return True
        except (IOError, OSError):
            return False

    def _touch(self):
        self.dirty = True

    # ------------------------------------------------------------ ajustes
    def get(self, key):
        return self.data["settings"].get(key, DEFAULT_SETTINGS.get(key))

    def set(self, key, value):
        if self.data["settings"].get(key) != value:
            self.data["settings"][key] = value
            self._touch()

    # ---------------------------------------------------------- categorias
    def categories(self):
        return self.data["categories"]

    def category_names(self):
        return [c["name"] for c in self.data["categories"]]

    def find(self, name):
        low = name.strip().lower()
        for c in self.data["categories"]:
            if c["name"].lower() == low:
                return c
        return None

    def create(self, name, pinned=False):
        name = name.strip()
        if not name or self.find(name) is not None:
            return False
        self.data["categories"].append({"name": name, "games": [], "pinned": bool(pinned)})
        self._touch()
        return True

    def priority(self, name):
        """Posicion de la lista (1 = mas prioritaria)."""
        c = self.find(name)
        return self.data["categories"].index(c) + 1 if c is not None else 0

    def move_to(self, name, index):
        cats = self.data["categories"]
        c = self.find(name)
        if c is None:
            return False
        i = cats.index(c)
        j = max(0, min(len(cats) - 1, index))
        if i == j:
            return False
        cats.insert(j, cats.pop(i))
        self._touch()
        return True

    def is_pinned(self, name):
        c = self.find(name)
        return bool(c and c.get("pinned"))

    def set_pinned(self, name, value):
        c = self.find(name)
        if c is None or bool(c.get("pinned")) == bool(value):
            return False
        c["pinned"] = bool(value)
        self._touch()
        return True

    def pinned_names(self):
        return [c["name"] for c in self.data["categories"] if c.get("pinned")]

    @staticmethod
    def _reorder(order, visible, path, delta, index):
        """Mueve 'path' dentro de la lista visible; los juegos que no estan
        en la tarjeta ahora mismo se conservan al final."""
        if path not in visible:
            return None
        vis = list(visible)
        i = vis.index(path)
        j = index if index is not None else i + (delta or 0)
        j = max(0, min(len(vis) - 1, j))
        if i == j:
            return None
        vis.insert(j, vis.pop(i))
        seen = set(vis)
        return vis + [p for p in order if p not in seen]

    def move_game(self, name, visible, path, delta=None, index=None):
        """Cambia la prioridad de un juego dentro de una lista."""
        c = self.find(name)
        if c is None:
            return False
        new = self._reorder(c["games"], visible, path, delta, index)
        if new is None:
            return False
        c["games"] = new
        self._touch()
        return True

    def rename(self, old, new):
        new = new.strip()
        c = self.find(old)
        if c is None or not new:
            return False
        other = self.find(new)
        if other is not None and other is not c:
            return False
        c["name"] = new
        self._touch()
        return True

    def delete(self, name):
        c = self.find(name)
        if c is None:
            return False
        self.data["categories"].remove(c)
        self._touch()
        return True

    def move(self, name, delta):
        """Sube (delta<0) o baja (delta>0) la prioridad de una lista."""
        c = self.find(name)
        if c is None:
            return False
        return self.move_to(name, self.data["categories"].index(c) + delta)

    def games_in(self, name):
        c = self.find(name)
        return list(c["games"]) if c else []

    def contains(self, name, path):
        c = self.find(name)
        return bool(c) and path in c["games"]

    def add(self, name, path):
        c = self.find(name)
        if c is None or path in c["games"]:
            return False
        c["games"].append(path)
        self._touch()
        return True

    def remove(self, name, path):
        c = self.find(name)
        if c is None or path not in c["games"]:
            return False
        c["games"].remove(path)
        self._touch()
        return True

    def toggle(self, name, path):
        if self.contains(name, path):
            self.remove(name, path)
            return False
        self.add(name, path)
        return True

    def categories_of(self, path):
        return [c["name"] for c in self.data["categories"] if path in c["games"]]

    # ----------------------------------------------------------- favoritos
    def is_favorite(self, game):
        return self.data["favorites"].get(game.path, game.es_favorite)

    def toggle_favorite(self, game):
        new = not self.is_favorite(game)
        if new == game.es_favorite:
            self.data["favorites"].pop(game.path, None)
        else:
            self.data["favorites"][game.path] = new
        order = self.data["fav_order"]
        if new and game.path not in order:
            order.append(game.path)
        elif not new and game.path in order:
            order.remove(game.path)
        self._touch()
        return new

    def favorites_ordered(self, games):
        """Favoritos en el orden de prioridad guardado. Los que aun no tienen
        posicion (p. ej. marcados en EmulationStation) se anaden al final."""
        favs = [g for g in games if self.is_favorite(g)]
        by_path = dict((g.path, g) for g in favs)
        order = self.data["fav_order"]
        out = [by_path[p] for p in order if p in by_path]
        known = set(order)
        extra = [g for g in favs if g.path not in known]
        if extra:
            extra.sort(key=lambda g: g.sortname)
            for g in extra:
                order.append(g.path)
            self._touch()
            out.extend(extra)
        return out

    def move_favorite(self, visible, path, delta=None, index=None):
        new = self._reorder(self.data["fav_order"], visible, path, delta, index)
        if new is None:
            return False
        self.data["fav_order"] = new
        self._touch()
        return True

    # ----------------------------------------------------------- historial
    def load_history(self):
        """history.log lo escribe Vapor.sh: 'inicio<TAB>segundos<TAB>ruta' por partida."""
        self.stats = {}
        try:
            with io.open(self.history_path, "r", encoding="utf-8", errors="surrogateescape") as f:
                for line in f:
                    parts = line.rstrip("\n").split("\t", 2)
                    if len(parts) != 3:
                        continue
                    try:
                        start = int(parts[0])
                        secs = int(parts[1])
                    except ValueError:
                        continue
                    st = self.stats.get(parts[2])
                    if st is None:
                        st = self.stats[parts[2]] = Stats()
                    # partidas de menos de 5 s suelen ser errores al lanzar
                    if secs >= 5:
                        st.playtime += min(secs, 24 * 3600)
                        st.count += 1
                    st.last = max(st.last, start)
        except (IOError, OSError):
            pass

    def playtime(self, game):
        st = self.stats.get(game.path)
        return st.playtime if st else 0

    def last_played(self, game):
        st = self.stats.get(game.path)
        return max(st.last if st else 0, game.es_lastplayed)

    def play_count(self, game):
        st = self.stats.get(game.path)
        return (st.count if st else 0) + game.es_playcount

    def mark_launch(self, game):
        """Marca el juego como jugado ahora mismo (para 'Recientes' al volver)."""
        st = self.stats.get(game.path)
        if st is None:
            st = self.stats[game.path] = Stats()
        st.last = int(time.time())

    # ------------------------------------------------- rutas de los juegos
    def fix_paths(self, by_path):
        """Si las ROMs cambian de sitio (p. ej. de /roms a /roms2 al usar la
        segunda SD) se recolocan las listas buscando la misma carpeta/archivo."""
        index = {}
        for p in by_path:
            parts = p.strip("/").split("/")
            if len(parts) >= 2:
                index.setdefault("/".join(parts[-2:]), p)

        def fix(p):
            if p in by_path:
                return p
            parts = p.strip("/").split("/")
            if len(parts) >= 2:
                return index.get("/".join(parts[-2:]), p)
            return p

        changed = False
        for c in self.data["categories"]:
            new = []
            for p in c["games"]:
                q = fix(p)
                if q not in new:
                    new.append(q)
            if new != c["games"]:
                c["games"] = new
                changed = True
        order = []
        for p in self.data["fav_order"]:
            q = fix(p)
            if q not in order:
                order.append(q)
        if order != self.data["fav_order"]:
            self.data["fav_order"] = order
            changed = True
        favs = {}
        for p, v in self.data["favorites"].items():
            favs[fix(p)] = v
        if favs != self.data["favorites"]:
            self.data["favorites"] = favs
            changed = True
        if changed:
            self._touch()
        return changed

    # -------------------------------------------- integracion con ES (colecciones)
    def export_to_es(self, collections_dir):
        """Escribe cada categoria como coleccion personalizada de EmulationStation
        (~/.emulationstation/collections/custom-<nombre>.cfg)."""
        if not os.path.isdir(collections_dir):
            os.makedirs(collections_dir)
        n = 0
        for c in self.data["categories"]:
            fn = os.path.join(collections_dir, "custom-%s.cfg" % safe_filename(c["name"]))
            lines = "".join(p + "\n" for p in c["games"])
            with io.open(fn, "w", encoding="utf-8", errors="surrogateescape") as f:
                f.write(lines)
            n += 1
        return n

    def import_from_es(self, collections_dir, home, known_paths=None):
        """Importa las colecciones personalizadas de ES como categorias.
        Devuelve el numero de juegos anadidos."""
        added = 0
        try:
            names = sorted(os.listdir(collections_dir))
        except OSError:
            names = []
        for fn in names:
            if not (fn.startswith("custom-") and fn.endswith(".cfg")) or fn == "custom-.cfg":
                continue
            cname = fn[7:-4]
            try:
                with io.open(os.path.join(collections_dir, fn), "r", encoding="utf-8",
                             errors="surrogateescape") as f:
                    lines = [l.strip() for l in f]
            except (IOError, OSError):
                continue
            if self.find(cname) is None:
                self.create(cname)
            for p in lines:
                if not p:
                    continue
                if p.startswith("~/"):
                    p = home + p[1:]
                if known_paths is not None and p not in known_paths:
                    continue
                if self.add(cname, p):
                    added += 1
        self.data["es_imported"] = True
        self._touch()
        return added
