# -*- coding: utf-8 -*-
"""Bindings ctypes minimos para SDL2, SDL2_ttf y SDL2_image.

Solo se usan funciones disponibles desde SDL 2.0.8 / SDL_ttf 2.0.14 /
SDL_image 2.0.4, que son las versiones (o mas nuevas) que trae ArkOS.
No hace falta compilar nada ni instalar pygame.
"""
import ctypes
import ctypes.util
import os
import struct

c_int = ctypes.c_int
c_uint8 = ctypes.c_uint8
c_uint16 = ctypes.c_uint16
c_uint32 = ctypes.c_uint32
c_char_p = ctypes.c_char_p
c_void_p = ctypes.c_void_p
POINTER = ctypes.POINTER
byref = ctypes.byref

# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------
SDL_INIT_VIDEO = 0x00000020
SDL_INIT_JOYSTICK = 0x00000200
SDL_INIT_EVENTS = 0x00004000

SDL_WINDOWPOS_UNDEFINED = 0x1FFF0000
SDL_WINDOW_FULLSCREEN = 0x00000001
SDL_WINDOW_SHOWN = 0x00000004
SDL_WINDOW_FULLSCREEN_DESKTOP = SDL_WINDOW_FULLSCREEN | 0x00001000

SDL_RENDERER_SOFTWARE = 0x00000001
SDL_RENDERER_ACCELERATED = 0x00000002
SDL_RENDERER_PRESENTVSYNC = 0x00000004
SDL_RENDERER_TARGETTEXTURE = 0x00000008

SDL_FLIP_VERTICAL = 2

SDL_BLENDMODE_NONE = 0
SDL_BLENDMODE_BLEND = 1

SDL_TEXTUREACCESS_STATIC = 0
SDL_TEXTUREACCESS_TARGET = 2

SDL_PIXELFORMAT_ARGB8888 = 0x16362004
SDL_PIXELFORMAT_ABGR8888 = 0x16762004  # bytes R,G,B,A en little-endian

# Eventos
SDL_QUIT = 0x100
SDL_WINDOWEVENT = 0x200
SDL_KEYDOWN = 0x300
SDL_KEYUP = 0x301
SDL_JOYAXISMOTION = 0x600
SDL_JOYHATMOTION = 0x602
SDL_JOYBUTTONDOWN = 0x603
SDL_JOYBUTTONUP = 0x604
SDL_JOYDEVICEADDED = 0x605
SDL_JOYDEVICEREMOVED = 0x606
SDL_RENDER_TARGETS_RESET = 0x2000
SDL_RENDER_DEVICE_RESET = 0x2001

SDL_HAT_UP = 0x01
SDL_HAT_RIGHT = 0x02
SDL_HAT_DOWN = 0x04
SDL_HAT_LEFT = 0x08

# Teclas
SDLK_RETURN = 13
SDLK_ESCAPE = 27
SDLK_BACKSPACE = 8
SDLK_TAB = 9
SDLK_SPACE = 32
SDLK_RIGHT = 0x4000004F
SDLK_LEFT = 0x40000050
SDLK_DOWN = 0x40000051
SDLK_UP = 0x40000052
SDLK_PAGEUP = 0x4000004B
SDLK_PAGEDOWN = 0x4000004E
SDLK_HOME = 0x4000004A
SDLK_END = 0x4000004D
SDLK_F1 = 0x4000003A
SDLK_F12 = 0x40000045
SDLK_KP_ENTER = 0x40000058

IMG_INIT_JPG = 1
IMG_INIT_PNG = 2

TTF_STYLE_NORMAL = 0
TTF_STYLE_BOLD = 1


# --------------------------------------------------------------------------
# Estructuras
# --------------------------------------------------------------------------
class SDL_Rect(ctypes.Structure):
    _fields_ = [("x", c_int), ("y", c_int), ("w", c_int), ("h", c_int)]


class SDL_Color(ctypes.Structure):
    _fields_ = [("r", c_uint8), ("g", c_uint8), ("b", c_uint8), ("a", c_uint8)]


class SDL_Surface(ctypes.Structure):
    _fields_ = [
        ("flags", c_uint32),
        ("format", c_void_p),
        ("w", c_int),
        ("h", c_int),
        ("pitch", c_int),
        ("pixels", c_void_p),
    ]


class SDL_DisplayMode(ctypes.Structure):
    _fields_ = [
        ("format", c_uint32),
        ("w", c_int),
        ("h", c_int),
        ("refresh_rate", c_int),
        ("driverdata", c_void_p),
    ]


class SDL_JoystickGUID(ctypes.Structure):
    _fields_ = [("data", c_uint8 * 16)]


SurfaceP = POINTER(SDL_Surface)

# --------------------------------------------------------------------------
# Carga de librerias
# --------------------------------------------------------------------------
_LIB_DIRS = [
    "",
    "/usr/lib/aarch64-linux-gnu/",
    "/usr/lib/arm-linux-gnueabihf/",
    "/usr/lib/",
    "/usr/local/lib/",
    "/lib/x86_64-linux-gnu/",
    "/usr/lib/x86_64-linux-gnu/",
]


def _load(names, required=True):
    errors = []
    # Permite forzar una ruta concreta, por ejemplo VAPOR_SDL2_TTF=/opt/x/libSDL2_ttf.so
    for name in names:
        for d in _LIB_DIRS:
            path = d + name
            if d and not os.path.exists(path):
                continue
            try:
                return ctypes.CDLL(path)
            except OSError as e:
                errors.append(str(e))
    found = ctypes.util.find_library(names[0].split(".so")[0].replace("lib", "", 1))
    if found:
        try:
            return ctypes.CDLL(found)
        except OSError as e:
            errors.append(str(e))
    if required:
        raise OSError("No se pudo cargar %s: %s" % (names[0], "; ".join(errors[-3:])))
    return None


def _env_first(var, names):
    v = os.environ.get(var)
    return [v] + names if v else names


SDL = _load(_env_first("VAPOR_SDL2", ["libSDL2-2.0.so.0", "libSDL2.so"]))
TTF = _load(_env_first("VAPOR_SDL2_TTF", ["libSDL2_ttf-2.0.so.0", "libSDL2_ttf.so"]))
IMG = _load(_env_first("VAPOR_SDL2_IMAGE", ["libSDL2_image-2.0.so.0", "libSDL2_image.so"]),
            required=False)


def _fn(lib, name, res, args):
    f = getattr(lib, name)
    f.restype = res
    f.argtypes = args
    return f


# --------------------------------------------------------------------------
# SDL2
# --------------------------------------------------------------------------
SDL_Init = _fn(SDL, "SDL_Init", c_int, [c_uint32])
SDL_InitSubSystem = _fn(SDL, "SDL_InitSubSystem", c_int, [c_uint32])
SDL_Quit = _fn(SDL, "SDL_Quit", None, [])
SDL_GetError = _fn(SDL, "SDL_GetError", c_char_p, [])
SDL_SetHint = _fn(SDL, "SDL_SetHint", c_int, [c_char_p, c_char_p])
SDL_GetTicks = _fn(SDL, "SDL_GetTicks", c_uint32, [])
SDL_Delay = _fn(SDL, "SDL_Delay", None, [c_uint32])
SDL_ShowCursor = _fn(SDL, "SDL_ShowCursor", c_int, [c_int])
SDL_GetDesktopDisplayMode = _fn(SDL, "SDL_GetDesktopDisplayMode", c_int,
                                [c_int, POINTER(SDL_DisplayMode)])

SDL_CreateWindow = _fn(SDL, "SDL_CreateWindow", c_void_p,
                       [c_char_p, c_int, c_int, c_int, c_int, c_uint32])
SDL_DestroyWindow = _fn(SDL, "SDL_DestroyWindow", None, [c_void_p])
SDL_CreateRenderer = _fn(SDL, "SDL_CreateRenderer", c_void_p, [c_void_p, c_int, c_uint32])
SDL_DestroyRenderer = _fn(SDL, "SDL_DestroyRenderer", None, [c_void_p])
SDL_GetRendererOutputSize = _fn(SDL, "SDL_GetRendererOutputSize", c_int,
                                [c_void_p, POINTER(c_int), POINTER(c_int)])
SDL_RenderTargetSupported = _fn(SDL, "SDL_RenderTargetSupported", c_int, [c_void_p])
SDL_SetRenderTarget = _fn(SDL, "SDL_SetRenderTarget", c_int, [c_void_p, c_void_p])
SDL_SetRenderDrawColor = _fn(SDL, "SDL_SetRenderDrawColor", c_int,
                             [c_void_p, c_uint8, c_uint8, c_uint8, c_uint8])
SDL_SetRenderDrawBlendMode = _fn(SDL, "SDL_SetRenderDrawBlendMode", c_int, [c_void_p, c_int])
SDL_RenderClear = _fn(SDL, "SDL_RenderClear", c_int, [c_void_p])
SDL_RenderFillRect = _fn(SDL, "SDL_RenderFillRect", c_int, [c_void_p, POINTER(SDL_Rect)])
SDL_RenderDrawRect = _fn(SDL, "SDL_RenderDrawRect", c_int, [c_void_p, POINTER(SDL_Rect)])
SDL_RenderDrawLine = _fn(SDL, "SDL_RenderDrawLine", c_int, [c_void_p, c_int, c_int, c_int, c_int])
SDL_RenderCopy = _fn(SDL, "SDL_RenderCopy", c_int,
                     [c_void_p, c_void_p, POINTER(SDL_Rect), POINTER(SDL_Rect)])
SDL_RenderCopyEx = _fn(SDL, "SDL_RenderCopyEx", c_int,
                       [c_void_p, c_void_p, POINTER(SDL_Rect), POINTER(SDL_Rect), ctypes.c_double,
                        c_void_p, c_int])
SDL_RenderSetClipRect = _fn(SDL, "SDL_RenderSetClipRect", c_int, [c_void_p, POINTER(SDL_Rect)])
SDL_RenderPresent = _fn(SDL, "SDL_RenderPresent", None, [c_void_p])
SDL_RenderReadPixels = _fn(SDL, "SDL_RenderReadPixels", c_int,
                           [c_void_p, POINTER(SDL_Rect), c_uint32, c_void_p, c_int])

SDL_CreateTexture = _fn(SDL, "SDL_CreateTexture", c_void_p,
                        [c_void_p, c_uint32, c_int, c_int, c_int])
SDL_CreateTextureFromSurface = _fn(SDL, "SDL_CreateTextureFromSurface", c_void_p,
                                   [c_void_p, SurfaceP])
SDL_DestroyTexture = _fn(SDL, "SDL_DestroyTexture", None, [c_void_p])
SDL_UpdateTexture = _fn(SDL, "SDL_UpdateTexture", c_int,
                        [c_void_p, POINTER(SDL_Rect), c_void_p, c_int])
SDL_QueryTexture = _fn(SDL, "SDL_QueryTexture", c_int,
                       [c_void_p, POINTER(c_uint32), POINTER(c_int), POINTER(c_int), POINTER(c_int)])
SDL_SetTextureColorMod = _fn(SDL, "SDL_SetTextureColorMod", c_int,
                             [c_void_p, c_uint8, c_uint8, c_uint8])
SDL_SetTextureAlphaMod = _fn(SDL, "SDL_SetTextureAlphaMod", c_int, [c_void_p, c_uint8])
SDL_SetTextureBlendMode = _fn(SDL, "SDL_SetTextureBlendMode", c_int, [c_void_p, c_int])

SDL_FreeSurface = _fn(SDL, "SDL_FreeSurface", None, [SurfaceP])
SDL_ConvertSurfaceFormat = _fn(SDL, "SDL_ConvertSurfaceFormat", SurfaceP,
                               [SurfaceP, c_uint32, c_uint32])
SDL_CreateRGBSurfaceWithFormat = _fn(SDL, "SDL_CreateRGBSurfaceWithFormat", SurfaceP,
                                     [c_uint32, c_int, c_int, c_int, c_uint32])
SDL_UpperBlitScaled = _fn(SDL, "SDL_UpperBlitScaled", c_int,
                          [SurfaceP, POINTER(SDL_Rect), SurfaceP, POINTER(SDL_Rect)])
SDL_SetSurfaceBlendMode = _fn(SDL, "SDL_SetSurfaceBlendMode", c_int, [SurfaceP, c_int])

SDL_PollEvent = _fn(SDL, "SDL_PollEvent", c_int, [c_void_p])
SDL_WaitEventTimeout = _fn(SDL, "SDL_WaitEventTimeout", c_int, [c_void_p, c_int])
SDL_PushEvent = _fn(SDL, "SDL_PushEvent", c_int, [c_void_p])

SDL_NumJoysticks = _fn(SDL, "SDL_NumJoysticks", c_int, [])
SDL_JoystickOpen = _fn(SDL, "SDL_JoystickOpen", c_void_p, [c_int])
SDL_JoystickGetDeviceInstanceID = _fn(SDL, "SDL_JoystickGetDeviceInstanceID", c_int, [c_int])
SDL_JoystickClose = _fn(SDL, "SDL_JoystickClose", None, [c_void_p])
SDL_JoystickName = _fn(SDL, "SDL_JoystickName", c_char_p, [c_void_p])
SDL_JoystickInstanceID = _fn(SDL, "SDL_JoystickInstanceID", c_int, [c_void_p])
SDL_JoystickGetGUID = _fn(SDL, "SDL_JoystickGetGUID", SDL_JoystickGUID, [c_void_p])
SDL_JoystickGetGUIDString = _fn(SDL, "SDL_JoystickGetGUIDString", None,
                                [SDL_JoystickGUID, c_char_p, c_int])

# --------------------------------------------------------------------------
# SDL2_ttf
# --------------------------------------------------------------------------
TTF_Init = _fn(TTF, "TTF_Init", c_int, [])
TTF_Quit = _fn(TTF, "TTF_Quit", None, [])
TTF_OpenFont = _fn(TTF, "TTF_OpenFont", c_void_p, [c_char_p, c_int])
TTF_CloseFont = _fn(TTF, "TTF_CloseFont", None, [c_void_p])
TTF_FontHeight = _fn(TTF, "TTF_FontHeight", c_int, [c_void_p])
TTF_FontAscent = _fn(TTF, "TTF_FontAscent", c_int, [c_void_p])
TTF_SetFontStyle = _fn(TTF, "TTF_SetFontStyle", None, [c_void_p, c_int])
TTF_SizeUTF8 = _fn(TTF, "TTF_SizeUTF8", c_int,
                   [c_void_p, c_char_p, POINTER(c_int), POINTER(c_int)])
TTF_RenderUTF8_Blended = _fn(TTF, "TTF_RenderUTF8_Blended", SurfaceP,
                             [c_void_p, c_char_p, SDL_Color])

# --------------------------------------------------------------------------
# SDL2_image (opcional: sin ella no hay caratulas, pero la app funciona)
# --------------------------------------------------------------------------
if IMG is not None:
    IMG_Init = _fn(IMG, "IMG_Init", c_int, [c_int])
    IMG_Load = _fn(IMG, "IMG_Load", SurfaceP, [c_char_p])
else:  # pragma: no cover - depende del sistema
    IMG_Init = None
    IMG_Load = None


# --------------------------------------------------------------------------
# Eventos: se leen desde un buffer de 56 bytes (tamano de SDL_Event)
# --------------------------------------------------------------------------
EVENT_SIZE = 56


class Event(object):
    __slots__ = ("type", "key", "repeat", "which", "index", "value")

    def __init__(self):
        self.type = 0
        self.key = 0
        self.repeat = 0
        self.which = 0
        self.index = 0
        self.value = 0


def new_event_buffer():
    return ctypes.create_string_buffer(EVENT_SIZE)


def decode_event(buf):
    raw = buf.raw
    ev = Event()
    ev.type = struct.unpack_from("<I", raw, 0)[0]
    t = ev.type
    if t in (SDL_KEYDOWN, SDL_KEYUP):
        ev.repeat = raw[13] if isinstance(raw[13], int) else ord(raw[13])
        ev.key = struct.unpack_from("<i", raw, 20)[0]
    elif t in (SDL_JOYBUTTONDOWN, SDL_JOYBUTTONUP):
        ev.which = struct.unpack_from("<i", raw, 8)[0]
        ev.index = struct.unpack_from("<B", raw, 12)[0]
    elif t == SDL_JOYHATMOTION:
        ev.which = struct.unpack_from("<i", raw, 8)[0]
        ev.index = struct.unpack_from("<B", raw, 12)[0]
        ev.value = struct.unpack_from("<B", raw, 13)[0]
    elif t == SDL_JOYAXISMOTION:
        ev.which = struct.unpack_from("<i", raw, 8)[0]
        ev.index = struct.unpack_from("<B", raw, 12)[0]
        ev.value = struct.unpack_from("<h", raw, 16)[0]
    elif t in (SDL_JOYDEVICEADDED, SDL_JOYDEVICEREMOVED):
        ev.which = struct.unpack_from("<i", raw, 8)[0]
    return ev


def push_quit():
    buf = ctypes.create_string_buffer(EVENT_SIZE)
    struct.pack_into("<I", buf, 0, SDL_QUIT)
    SDL_PushEvent(buf)


def error():
    e = SDL_GetError()
    return e.decode("utf-8", "replace") if e else ""


def rect(x, y, w, h):
    return SDL_Rect(int(x), int(y), int(w), int(h))


def texture_size(tex):
    w = c_int()
    h = c_int()
    SDL_QueryTexture(tex, None, None, byref(w), byref(h))
    return w.value, h.value
