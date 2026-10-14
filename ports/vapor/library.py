# -*- coding: utf-8 -*-
"""Lee la configuracion de EmulationStation (la de ArkOS: EmulationStation-fcamod)
y construye la lista de juegos y los comandos de lanzamiento exactamente como
lo hace EmulationStation (FileData::launchGame)."""
import os
import pickle
import re
import time
import unicodedata
import xml.etree.ElementTree as ET

try:
    from html import unescape as _html_unescape
except ImportError:  # pragma: no cover
    _html_unescape = None

CACHE_VERSION = 3

# Carpetas que EmulationStation ignora al buscar juegos
_SKIP_DIRS = ("media", "images", "videos", "ppsspp")

# BIOS habituales de MAME/FBNeo que ES no muestra como juegos
_BIOS = set("""neogeo pgm skns stvbios cpzn1 cpzn2 coh1000c coh1001l coh1002e coh1002m coh3002c
decocass hng64 isgsm konamigx megaplay megatech naomi naomi2 naomigd awbios nss playch10
qsound sys246 sys256 taitofx1 tps cvs ym2608 bubsys""".split())


def _unescape(s):
    if s is None:
        return ""
    if _html_unescape is not None:
        return _html_unescape(s)
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"') \
        .replace("&apos;", "'").replace("&amp;", "&")


def generic_path(p):
    """Equivalente a Utils::FileSystem::getGenericPath de ES."""
    if not p:
        return p
    p = p.replace("\\", "/")
    while "//" in p:
        p = p.replace("//", "/")
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p


def es_escape(path):
    """Replica exacta de Utils::FileSystem::getEscapedPath (Linux) de ES."""
    path = generic_path(path)
    for ch in "\\ '\"!$^&*(){}[]?;<>":
        start = 0
        while True:
            off = path.find(ch, start)
            if off < 0:
                break
            start = off + 1
            if off == 0 or path[off - 1] != "\\":
                path = path[:off] + "\\" + path[off:]
                start += 1
    return path


def sort_key(text):
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.lower().strip()


def parse_es_time(s):
    """'20240115T153000' -> epoch (hora local). 0 si no es valido."""
    if not s or s in ("0", "not-a-date-time"):
        return 0
    try:
        return int(time.mktime(time.strptime(s[:15], "%Y%m%dT%H%M%S")))
    except (ValueError, OverflowError):
        return 0


def release_year(s):
    if s and len(s) >= 4 and s[:4].isdigit() and s[:4] not in ("0000", "1970"):
        return s[:4]
    return ""


# --------------------------------------------------------------------------
# es_settings.cfg
# --------------------------------------------------------------------------
_SETTING_RE = re.compile(r'<(bool|int|float|string)\s+name="([^"]*)"\s+value="([^"]*)"\s*/>')


def load_es_settings(path):
    out = {}
    try:
        with open(path, "rb") as f:
            txt = f.read().decode("utf-8", "replace")
    except (IOError, OSError):
        return out
    for _typ, name, value in _SETTING_RE.findall(txt):
        out[_unescape(name)] = _unescape(value)
    return out


# --------------------------------------------------------------------------
# es_systems.cfg
# --------------------------------------------------------------------------
class Emulator(object):
    __slots__ = ("name", "command", "cores", "governors")

    def __init__(self, name, command="", cores=None, governors=None):
        self.name = name
        self.command = command
        self.cores = cores or []
        # igual que EmulatorData de ES: lista por defecto + las del cfg
        self.governors = ["performance", "ondemand", "powersave"] + (governors or [])


class System(object):
    def __init__(self):
        self.name = ""
        self.fullname = ""
        self.path = ""
        self.extensions = set()
        self.command = ""
        self.emulators = []
        self.platforms = []
        self.theme = ""
        self.group = ""
        self.order = 0
        self.games = []

    @property
    def is_arcade(self):
        return any(p in ("arcade", "neogeo", "mame", "fba", "fbneo") for p in self.platforms) or \
            self.name in ("arcade", "mame", "mame2003", "mame2010", "fbneo", "fba", "neogeo", "cps1",
                          "cps2", "cps3")

    # --- misma logica que SystemEnvironmentData (SystemData.h de ES) ---
    def default_emulator(self, settings):
        cur = settings.get(self.name + ".emulator", "")
        for e in self.emulators:
            if e.name == cur:
                return e.name
        return self.emulators[0].name if self.emulators else ""

    def default_core(self, emulator, settings):
        cur = settings.get(self.name + ".core", "")
        for e in self.emulators:
            if e.name == emulator:
                if cur in e.cores:
                    return cur
                return e.cores[0] if e.cores else ""
        return ""

    def default_governor(self, emulator, settings):
        cur = settings.get(self.name + ".governor", "")
        for e in self.emulators:
            if e.name == emulator and cur in e.governors:
                return cur
        return ""

    def emulator_command(self, emulator):
        for e in self.emulators:
            if e.name == emulator:
                return e.command
        return ""


def _text(node, tag):
    ch = node.find(tag)
    if ch is None or ch.text is None:
        return ""
    return ch.text.strip()


# '&' que no forma parte de una entidad XML valida (p. ej. el "2>&1" que ArkOS
# pone en el comando del menu de Opciones)
_BARE_AMP = re.compile(r"&(?!(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#x[0-9A-Fa-f]+);)")
_TAG_RE = re.compile(r"<(\w+)(?:\s[^>]*)?>(.*?)</\1\s*>", re.S)
_ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


def parse_xml_lenient(path):
    """Lee un XML con la misma tolerancia que pugixml (el lector de EmulationStation).

    1) XML estricto; 2) escapando los '&' sueltos; 3) si aun falla, se reconstruye
    el arbol con expresiones regulares (sirve para es_systems.cfg y es_input.cfg).
    Lanza IOError/OSError si el fichero no se puede leer."""
    with open(path, "rb") as f:
        data = f.read()
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        pass
    text = data.decode("utf-8", "replace")
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
    try:
        return ET.fromstring(_BARE_AMP.sub("&amp;", text).encode("utf-8"))
    except ET.ParseError:
        pass
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return _regex_tree(text)


def _regex_tree(text):
    """Arbol minimo a partir de etiquetas con expresiones regulares."""
    root = ET.Element("root")

    def fill(parent, body, depth):
        for m in _TAG_RE.finditer(body):
            tag, inner = m.group(1), m.group(2)
            el = ET.SubElement(parent, tag)
            head = body[m.start():body.index(">", m.start()) + 1]
            for k, v in _ATTR_RE.findall(head):
                el.set(k, _unescape(v))
            if depth < 6 and "<" in inner:
                fill(el, inner, depth + 1)
            if not len(el):
                el.text = _unescape(inner)
        # etiquetas sin cierre: <input name="a" type="button" id="1" value="1"/>
        for m in re.finditer(r"<(\w+)(\s[^<>]*?)/>", body):
            el = ET.SubElement(parent, m.group(1))
            for k, v in _ATTR_RE.findall(m.group(2)):
                el.set(k, _unescape(v))

    fill(root, text, 0)
    return root


def load_es_systems(path, home):
    root = parse_xml_lenient(path)
    systems = []
    for i, sn in enumerate(root.iter("system")):
        s = System()
        s.order = i
        s.name = _text(sn, "name")
        s.fullname = _text(sn, "fullname") or s.name
        p = _text(sn, "path")
        if p.startswith("~"):
            p = home + p[1:]
        s.path = generic_path(p)
        s.extensions = set(e.lower() for e in _text(sn, "extension").replace(",", " ").split())
        s.command = _text(sn, "command")
        s.platforms = [x.strip() for x in _text(sn, "platform").replace(",", " ").split()]
        s.theme = _text(sn, "theme") or s.name
        s.group = _text(sn, "group")
        emus = sn.find("emulators")
        if emus is not None:
            for en in emus:
                cores = []
                govs = []
                cn = en.find("cores")
                if cn is not None:
                    cores = [(c.text or "").strip() for c in cn if (c.text or "").strip()]
                gn = en.find("governors")
                if gn is not None:
                    govs = [(g.text or "").strip() for g in gn if (g.text or "").strip()]
                s.emulators.append(Emulator(en.get("name", ""), en.get("command", "") or "",
                                            cores, govs))
        if not s.name or not s.path or not s.extensions or not s.command:
            continue
        systems.append(s)
    return systems


# --------------------------------------------------------------------------
# Juegos
# --------------------------------------------------------------------------
GAME_FIELDS = ("name", "desc", "image", "thumbnail", "marquee", "fanart", "video", "rating",
               "releasedate", "developer", "publisher", "genre", "players", "favorite", "hidden",
               "playcount", "lastplayed", "emulator", "core", "governor")


class Game(object):
    __slots__ = ("path", "system", "name", "sortname", "desc", "image", "thumbnail", "marquee",
                 "fanart", "rating", "year", "developer", "publisher", "genre", "players",
                 "es_favorite", "es_playcount", "es_lastplayed", "emulator", "core", "governor",
                 "has_meta")

    def __init__(self, path, system):
        self.path = path
        self.system = system
        self.name = ""
        self.sortname = ""
        self.desc = ""
        self.image = ""
        self.thumbnail = ""
        self.marquee = ""
        self.fanart = ""
        self.rating = 0.0
        self.year = ""
        self.developer = ""
        self.publisher = ""
        self.genre = ""
        self.players = ""
        self.es_favorite = False
        self.es_playcount = 0
        self.es_lastplayed = 0
        self.emulator = ""
        self.core = ""
        self.governor = ""
        self.has_meta = False

    @property
    def stem(self):
        base = os.path.basename(self.path)
        root, _ext = os.path.splitext(base)
        return root

    def cover(self):
        """Imagen para la cuadricula (caratula si existe)."""
        return self.thumbnail or self.image or self.marquee or self.fanart

    def hero(self):
        """Imagen grande para la ficha del juego."""
        return self.fanart or self.image or self.thumbnail or self.marquee

    def poster(self):
        return self.thumbnail or self.image or self.marquee

    def genres(self):
        g = (self.genre or "").strip()
        if not g or g.lower() == "unknown":
            return []
        parts = re.split(r"\s*[/,;]\s*|\s+-\s+", g)
        out = []
        for p in parts:
            p = p.strip()
            if p and p not in out:
                out.append(p[:1].upper() + p[1:])
        return out[:1]  # el genero principal


def _resolve(value, base, home):
    """resolveRelativePath de ES: './x' relativo a la carpeta del sistema, '~/' a HOME."""
    if not value:
        return ""
    value = value.strip()
    if value == ".":
        return base
    if value.startswith("./") or value.startswith(".\\"):
        return generic_path(base + value[1:])
    if value.startswith("~/"):
        return generic_path(home + value[1:])
    if not value.startswith("/"):
        return generic_path(base + "/" + value)
    return generic_path(value)


def _parse_gamelist_xml(path):
    """Devuelve lista de dicts con los campos de cada <game>. Tolerante a XML roto."""
    entries = []
    try:
        for _ev, el in ET.iterparse(path, events=("end",)):
            if el.tag == "game":
                d = {}
                for ch in el:
                    if ch.tag in GAME_FIELDS or ch.tag == "path":
                        d[ch.tag] = (ch.text or "").strip()
                entries.append(d)
                el.clear()
            elif el.tag == "folder":
                el.clear()
        return entries
    except ET.ParseError:
        pass
    except (IOError, OSError):
        return entries
    # Plan B: XML mal formado (p.ej. '&' sin escapar). Lectura con expresiones regulares.
    entries = []
    try:
        with open(path, "rb") as f:
            txt = f.read().decode("utf-8", "replace")
    except (IOError, OSError):
        return entries
    for block in re.findall(r"<game(?:\s[^>]*)?>(.*?)</game>", txt, re.S):
        d = {}
        for tag, val in re.findall(r"<(\w+)>(.*?)</\1>", block, re.S):
            if tag in GAME_FIELDS or tag == "path":
                d[tag] = _unescape(val.strip())
        entries.append(d)
    return entries


def _gamelist_path(system, home):
    p = system.path + "/gamelist.xml"
    if os.path.isfile(p):
        return p
    p = home + "/.emulationstation/gamelists/" + system.name + "/gamelist.xml"
    if os.path.isfile(p):
        return p
    p = "/etc/emulationstation/gamelists/" + system.name + "/gamelist.xml"
    if os.path.isfile(p):
        return p
    return ""


class MameNames(object):
    """Nombres reales de juegos arcade (sf2.zip -> Street Fighter II) usando los
    mismos ficheros que EmulationStation, si existen."""

    DIRS = ["/usr/bin/emulationstation/resources", "/etc/emulationstation/resources",
            "/opt/emulationstation/resources"]

    def __init__(self, home):
        self.names = None
        self.bios = None
        self.dirs = [home + "/.emulationstation/resources"] + self.DIRS

    def _find(self, fn):
        for d in self.dirs:
            p = os.path.join(d, fn)
            if os.path.isfile(p):
                return p
        return None

    def _load(self):
        self.names = {}
        self.bios = set(_BIOS)
        p = self._find("mamenames.xml")
        if p:
            try:
                for _ev, el in ET.iterparse(p):
                    if el.tag == "game":
                        mn = (el.findtext("mamename") or "").strip()
                        rn = (el.findtext("realname") or "").strip()
                        if mn and rn:
                            self.names[mn] = rn
                        el.clear()
            except (ET.ParseError, IOError, OSError):
                pass
        for fn in ("mamebioses.xml", "mamedevices.xml"):
            p = self._find(fn)
            if not p:
                continue
            try:
                for _ev, el in ET.iterparse(p):
                    if el.tag in ("bios", "device") and el.text:
                        self.bios.add(el.text.strip())
            except (ET.ParseError, IOError, OSError):
                pass

    def real_name(self, stem):
        if self.names is None:
            self._load()
        return self.names.get(stem, stem)

    def is_bios(self, stem):
        if self.bios is None:
            self._load()
        return stem in self.bios


class Library(object):
    def __init__(self, es_dir="/etc/emulationstation", home=None, cache_path=None,
                 exclude=None):
        self.home = home or os.path.expanduser("~")
        self.es_dir = es_dir
        self.cache_path = cache_path
        self.exclude = set(generic_path(os.path.abspath(p)) for p in (exclude or []) if p)
        self.systems = []
        self.games = []
        self.by_path = {}
        self.settings = {}
        self.errors = []
        self.cfg_used = ""
        self.report = []  # (sistema, carpeta, n juegos o motivo) para el log
        self.mame = MameNames(self.home)

    # ------------------------------------------------------------------
    def systems_cfg_path(self):
        p = self.home + "/.emulationstation/es_systems.cfg"
        if os.path.isfile(p):
            return p
        return os.path.join(self.es_dir, "es_systems.cfg")

    def settings_path(self):
        return self.home + "/.emulationstation/es_settings.cfg"

    def input_cfg_paths(self):
        return [self.home + "/.emulationstation/es_input.cfg",
                os.path.join(self.es_dir, "es_input.cfg")]

    def collections_dir(self):
        return self.home + "/.emulationstation/collections"

    # ------------------------------------------------------------------
    def load(self, progress=None, use_cache=True):
        self.errors = []
        self.settings = load_es_settings(self.settings_path())
        cfg = self.systems_cfg_path()
        try:
            systems = load_es_systems(cfg, self.home)
        except (ET.ParseError, IOError, OSError) as e:
            self.errors.append("%s: %s" % (cfg, e))
            systems = []
        self.cfg_used = cfg
        if not systems and not self.errors:
            self.errors.append("%s: 0 sistemas" % cfg)
        hidden = set(x for x in self.settings.get("HiddenSystems", "").split(";") if x)
        cache = self._load_cache() if use_cache else {}
        new_cache = {}
        seen = set()
        self.systems = []
        self.games = []
        self.by_path = {}
        show_hidden = self.settings.get("ShowHiddenFiles", "false") == "true"
        scan_ports = self.settings.get("ScanPorts", "false") == "true"
        total = len(systems)
        self.report = []
        for i, s in enumerate(systems):
            if progress:
                progress(i, total, s.fullname)
            # "retropie" = menu de Opciones/herramientas de ArkOS, no son juegos
            if s.name == "retropie" or s.path.startswith("/opt/system") or s.name in hidden:
                continue
            if not os.path.isdir(s.path):
                self.report.append((s.name, s.path, "no existe la carpeta"))
                continue
            files = self._scan(s, show_hidden, scan_ports)
            meta = self._gamelist(s, cache, new_cache)
            games = []
            for path in files:
                if path in seen or path in self.exclude:
                    continue
                g = Game(path, s)
                m = meta.get(path)
                if m is not None:
                    if m.get("hidden") == "true":
                        continue
                    self._apply_meta(g, m, s)
                stem = g.stem
                if s.is_arcade and os.path.splitext(path)[1].lower() == ".zip" and \
                        self.mame.is_bios(stem):
                    continue
                if not g.name:
                    g.name = self.mame.real_name(stem) if s.is_arcade else stem
                g.sortname = sort_key(g.name)
                seen.add(path)
                games.append(g)
            self.report.append((s.name, s.path, "%d juegos" % len(games)))
            if not games:
                continue
            self._local_art(s, games)
            games.sort(key=lambda x: x.sortname)
            s.games = games
            self.systems.append(s)
            self.games.extend(games)
        for g in self.games:
            self.by_path[g.path] = g
        self.games.sort(key=lambda x: x.sortname)
        if use_cache:
            self._save_cache(new_cache)
        if progress:
            progress(total, total, "")
        return self

    # ------------------------------------------------------------------
    def _scan(self, s, show_hidden, scan_ports):
        out = []

        def walk(folder, depth):
            try:
                it = os.scandir(folder)
                try:
                    entries = list(it)
                finally:
                    if hasattr(it, "close"):
                        it.close()
            except OSError:
                return
            for e in entries:
                name = e.name
                if not show_hidden and name.startswith("."):
                    continue
                ext = os.path.splitext(name)[1].lower()
                full = generic_path(folder + "/" + name)
                is_dir = False
                try:
                    is_dir = e.is_dir()
                except OSError:
                    pass
                if ext and ext in s.extensions:
                    if name.lower() == "gamelist.xml":
                        continue
                    out.append(full)
                    continue
                if is_dir and depth < 6:
                    low = name.lower()
                    if low.startswith("downloaded_") or low in _SKIP_DIRS or low.startswith("."):
                        continue
                    if not scan_ports and "/ports" in full:
                        continue
                    walk(full, depth + 1)

        walk(s.path, 0)
        return out

    def _gamelist(self, s, cache, new_cache):
        gl = _gamelist_path(s, self.home)
        if not gl:
            return {}
        try:
            st = os.stat(gl)
            sig = (gl, int(st.st_mtime), st.st_size, s.path)
        except OSError:
            return {}
        key = s.name + "|" + s.path
        ent = cache.get(key)
        if ent is not None and ent[0] == sig:
            new_cache[key] = ent
            return ent[1]
        meta = {}
        # ES resuelve las rutas "./" relativas a la carpeta del sistema
        base = s.path
        for d in _parse_gamelist_xml(gl):
            p = d.get("path")
            if not p:
                continue
            full = _resolve(p, s.path, self.home)
            for k in ("image", "thumbnail", "marquee", "fanart", "video"):
                if d.get(k):
                    d[k] = _resolve(d[k], base, self.home)
            meta[full] = d
        new_cache[key] = (sig, meta)
        return meta

    def _apply_meta(self, g, m, s):
        g.has_meta = True
        g.name = m.get("name", "")
        g.desc = m.get("desc", "")
        g.image = m.get("image", "")
        g.thumbnail = m.get("thumbnail", "")
        g.marquee = m.get("marquee", "")
        g.fanart = m.get("fanart", "")
        try:
            g.rating = float(m.get("rating") or 0)
        except ValueError:
            g.rating = 0.0
        g.year = release_year(m.get("releasedate", ""))
        dev = m.get("developer", "")
        pub = m.get("publisher", "")
        g.developer = "" if dev.lower() == "unknown" else dev
        g.publisher = "" if pub.lower() == "unknown" else pub
        g.genre = m.get("genre", "")
        g.players = m.get("players", "")
        g.es_favorite = m.get("favorite", "") == "true"
        try:
            g.es_playcount = int(m.get("playcount") or 0)
        except ValueError:
            g.es_playcount = 0
        g.es_lastplayed = parse_es_time(m.get("lastplayed", ""))
        g.emulator = m.get("emulator", "")
        g.core = m.get("core", "")
        g.governor = m.get("governor", "")

    def _local_art(self, s, games):
        """Si el gamelist no trae imagenes, busca arte en las carpetas habituales
        (images/ de ES, media/ de Skraper, boxart/, snap/...). Se lista cada
        carpeta una sola vez para no hacer miles de 'stat' en la SD."""
        need = [g for g in games if not g.cover()]
        if not need:
            return
        candidates = [
            ("images", ("%s-thumb", "%s-image", "%s", "%s-marquee")),
            ("media/box2dfront", ("%s",)), ("media/covers", ("%s",)), ("media/boxart", ("%s",)),
            ("media/images", ("%s",)), ("media/screenshots", ("%s",)), ("media/snaps", ("%s",)),
            ("boxart", ("%s",)), ("covers", ("%s",)), ("box", ("%s",)), ("snap", ("%s",)),
            ("snaps", ("%s",)), ("screenshots", ("%s",)), ("media/wheel", ("%s",)),
        ]
        listings = []
        for sub, patterns in candidates:
            d = s.path + "/" + sub
            try:
                names = {}
                for fn in os.listdir(d):
                    root, ext = os.path.splitext(fn)
                    if ext.lower() in (".png", ".jpg", ".jpeg"):
                        names.setdefault(root, fn)
                if names:
                    listings.append((d, patterns, names))
            except OSError:
                continue
        # PNG/p8 que son la propia imagen (pico-8)
        for g in need:
            ext = os.path.splitext(g.path)[1].lower()
            if ext == ".png":
                g.thumbnail = g.path
                continue
            stem = g.stem
            disp = g.name
            found = ""
            for d, patterns, names in listings:
                for pat in patterns:
                    for base in (stem, disp):
                        fn = names.get(pat % base)
                        if fn:
                            found = d + "/" + fn
                            break
                    if found:
                        break
                if found:
                    break
            if found:
                g.thumbnail = found

    # ------------------------------------------------------------------
    def _load_cache(self):
        if not self.cache_path:
            return {}
        try:
            with open(self.cache_path, "rb") as f:
                data = pickle.load(f)
            if isinstance(data, dict) and data.get("v") == CACHE_VERSION:
                return data.get("systems", {})
        except Exception:
            pass
        return {}

    def _save_cache(self, systems):
        if not self.cache_path:
            return
        try:
            tmp = self.cache_path + ".tmp"
            with open(tmp, "wb") as f:
                pickle.dump({"v": CACHE_VERSION, "systems": systems}, f, protocol=2)
            os.replace(tmp, self.cache_path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def launch_command(self, game):
        """Construye el comando igual que FileData::launchGame de ES (ArkOS)."""
        s = game.system
        st = self.settings
        command = s.command
        rom = es_escape(game.path)
        basename = game.stem
        rom_raw = generic_path(game.path)

        emulator = game.emulator or s.default_emulator(st)
        core = game.core or s.default_core(emulator, st)
        governor = game.governor
        if not governor:
            governor = s.default_governor(emulator, st)
        if not governor:
            governor = st.get(game.name + ".governor", "")
        if not governor:
            governor = st.get(s.name + ".governor", "")
        if not governor:
            governor = s.default_governor(s.default_emulator(st), st)
        if not governor:
            governor = st.get("GlobalPerformanceGovernor", "performance") or "performance"

        custom = s.emulator_command(emulator)
        if custom:
            command = custom

        command = command.replace("%GOVERNOR%", governor)
        command = command.replace("%EMULATOR%", emulator)
        command = command.replace("%CORE%", core)
        command = command.replace("%ROM%", rom)
        command = command.replace("%BASENAME%", basename)
        command = command.replace("%ROM_RAW%", rom_raw)
        command = command.replace("%SYSTEM%", s.name)
        command = command.replace("%HOME%", self.home)
        return command
