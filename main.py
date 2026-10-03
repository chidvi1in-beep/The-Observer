"""THE OBSERVER 3D: 30 levels, procedural sound, jump scares.

Keep entity.jpg and scream.mp3 in the same folder as this script: they are used for the capture jump scare.

Controls: WASD move, SHIFT sprint, MOUSE look (or arrow keys), hold LMB/SPACE
for flashlight, Q beam focus (uncertainty), hold G amplitude amplification, E interference pulse, R restart level, ESC back/quit.
Wear headphones.
"""
import array
import asyncio
import json
import math
import os
import random
import sys
import types
from collections import deque

import pygame

pygame.mixer.pre_init(22050, -16, 2, 512)
pygame.init()

WEB = sys.platform == "emscripten"      # running in the browser through pygbag
WIDTH, HEIGHT = 1100, 700
# the browser runs Python slower, so render the 3D view at a lower internal resolution there
IW, IH = (256, 163) if WEB else (352, 224)
FOV = math.radians(70)
MAX_LEVEL = 30

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("THE OBSERVER 3D: it moves when you don't look")
clock = pygame.time.Clock()

FONT = pygame.font.SysFont("consolas", 24)
BIG = pygame.font.SysFont("consolas", 52, bold=True)
HUGE = pygame.font.SysFont("consolas", 84, bold=True)
SMALL = pygame.font.SysFont("consolas", 18)
TINY = pygame.font.SysFont("consolas", 13, bold=True)

WHITE = (235, 235, 235)
RED = (210, 55, 55)
GREEN = (70, 210, 130)
BLUE = (80, 150, 230)
GOLD = (240, 200, 80)
GRAY = (95, 95, 110)

# ================================================================= AUDIO
AUDIO = False
SR, MCH = 22050, 2
_mi = pygame.mixer.get_init()
if _mi and _mi[1] == -16:
    SR, _, MCH = _mi
    AUDIO = True
    pygame.mixer.set_num_channels(24)
    pygame.mixer.set_reserved(2)

try:
    ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    ASSET_DIR = os.getcwd()


def find_asset(name):
    """Look for the exact file name first, then any file of the same type (e.g. the original
    WhatsApp photo name or freesound mp3 name) in the script folder and the current folder."""
    import glob
    exts = {"entity.jpg": ("jpg", "jpeg", "jfif", "png", "webp", "bmp", "gif"), "scream.mp3": ("ogg", "mp3", "wav")}.get(name, ())
    for d in (ASSET_DIR, os.getcwd()):
        fp = os.path.join(d, name)
        if os.path.isfile(fp):
            return fp
    for d in (ASSET_DIR, os.getcwd()):
        for e in exts:
            hits = sorted(glob.glob(os.path.join(d, "*." + e)) + glob.glob(os.path.join(d, "*." + e.upper())))
            if hits:
                return hits[0]
    return None


SND = {}


def make_sound(samples, gain=1.0):
    buf = array.array("h")
    for s in samples:
        v = int(max(-1.0, min(1.0, s * gain)) * 30000)
        for _ in range(MCH):
            buf.append(v)
    return pygame.mixer.Sound(buffer=buf.tobytes())


def lowpass(x, a):
    y = 0.0
    out = []
    for v in x:
        y += a * (v - y)
        out.append(y)
    return out


def gen_drone():
    n = SR * 4
    lp = 0.0
    out = []
    for i in range(n):
        t = i / SR
        trem = 0.75 + 0.25 * math.sin(2 * math.pi * 0.25 * t)
        v = (0.5 * math.sin(2 * math.pi * 55 * t) + 0.3 * math.sin(2 * math.pi * 82.5 * t + 1)
             + 0.12 * math.sin(2 * math.pi * 164.5 * t + 2))
        lp += 0.02 * (random.uniform(-1, 1) - lp)
        out.append((v * trem + lp * 1.4) * 0.55)
    return out


def gen_growl():
    n = SR * 3
    lp = 0.0
    out = []
    for i in range(n):
        t = i / SR
        lp += 0.03 * (random.uniform(-1, 1) - lp)
        am = 0.6 + 0.4 * math.sin(2 * math.pi * 6 * t)
        out.append((lp * 5 * am + 0.5 * math.sin(2 * math.pi * 42 * t)) * 0.6)
    return out


def gen_heart():
    n = int(SR * 0.6)
    out = [0.0] * n
    for start, amp in ((0.0, 1.0), (0.19, 0.7)):
        s = int(start * SR)
        for i in range(int(SR * 0.25)):
            t = i / SR
            if s + i < n:
                out[s + i] += amp * math.sin(2 * math.pi * (60 * t - 40 * t * t)) * math.exp(-t * 20)
    return out


def gen_step(seed, heavy):
    rnd = random.Random(seed)
    n = int(SR * (0.28 if heavy else 0.14))
    a = 0.25 if heavy else 0.5
    y = 0.0
    out = []
    for i in range(n):
        t = i / SR
        y += a * (rnd.uniform(-1, 1) - y)
        env = math.exp(-t * (14 if heavy else 32))
        thud = math.sin(2 * math.pi * (70 if heavy else 110) * t) * math.exp(-t * (16 if heavy else 40))
        out.append(y * 0.8 * env + thud * 0.9)
    return out


def gen_click():
    n = int(SR * 0.04)
    return [(random.uniform(-1, 1) * 0.6 + math.sin(2 * math.pi * 1800 * i / SR) * 0.4)
            * math.exp(-i / SR * 120) for i in range(n)]


def gen_chime(freqs, step, dur, decay):
    n = int(SR * (dur + step * len(freqs)))
    out = [0.0] * n
    for k, f in enumerate(freqs):
        s = int(k * step * SR)
        for i in range(int(SR * dur)):
            if s + i < n:
                t = i / SR
                out[s + i] += 0.35 * math.sin(2 * math.pi * f * t) * math.exp(-decay * t)
    return out


def gen_pulse():
    n = int(SR * 0.9)
    ph = 0.0
    out = []
    for i in range(n):
        t = i / SR
        ph += 2 * math.pi * (500 * math.exp(-t * 3.5) + 40) / SR
        out.append(math.sin(ph) * math.exp(-t * 3) + random.uniform(-1, 1) * 0.2 * math.exp(-t * 6))
    return out


def gen_scream():
    n = int(SR * 1.8)
    ph = ph2 = 0.0
    out = []
    for i in range(n):
        t = i / SR
        f = 600 + 900 * min(1.0, t / 0.4) + 80 * math.sin(2 * math.pi * 9 * t)
        ph += 2 * math.pi * f / SR
        ph2 += 2 * math.pi * f * 1.51 / SR
        saw = (ph / (2 * math.pi)) % 1 * 2 - 1
        sq = 1.0 if math.sin(ph2) > 0 else -1.0
        env = min(1.0, t / 0.02) * (1.0 if t < 1.3 else max(0.0, (1.8 - t) / 0.5))
        v = (0.55 * saw + 0.25 * sq + 0.45 * random.uniform(-1, 1)) * env
        boom = math.sin(2 * math.pi * 45 * t) * math.exp(-t * 4) * 0.9
        out.append(math.tanh((v + boom) * 2.2) * 0.9)
    return out


def gen_sting():
    n = int(SR * 0.9)
    out = []
    for i in range(n):
        t = i / SR
        v = sum(math.sin(2 * math.pi * f * t) for f in (311.1, 329.6, 466.2)) / 3
        out.append(v * 0.7 * math.exp(-t * 4) + (random.uniform(-1, 1) * 0.6 * math.exp(-t * 40)))
    return out


def gen_whisper():
    rnd = random.Random(7)
    n = int(SR * 1.4)
    env = [0.0] * n
    for _ in range(5):
        c, w, amp = rnd.uniform(0.1, 1.2), rnd.uniform(0.05, 0.12), rnd.uniform(0.5, 1.0)
        for i in range(max(0, int((c - 3 * w) * SR)), min(n, int((c + 3 * w) * SR))):
            env[i] += amp * math.exp(-(((i / SR) - c) / w) ** 2)
    noise = [rnd.uniform(-1, 1) for _ in range(n)]
    lp1 = lowpass(noise, 0.12)
    hp = [a - b for a, b in zip(noise, lp1)]
    lp2 = lowpass(hp, 0.5)
    return [lp2[i] * env[i] * 2.2 for i in range(n)]


def gen_bang():
    n = int(SR * 1.4)
    y = 0.0
    out = []
    for i in range(n):
        t = i / SR
        y += 0.1 * (random.uniform(-1, 1) - y)
        out.append(y * 2.5 * math.exp(-t * 5) + math.sin(2 * math.pi * 50 * t) * math.exp(-t * 7))
    d = int(0.17 * SR)
    for i in range(d, n):
        out[i] += 0.45 * out[i - d]
    return out


def gen_buzz():
    n = int(SR * 0.5)
    out = []
    on = True
    for i in range(n):
        if i % 700 == 0:
            on = random.random() < 0.7
        sq = 1.0 if math.sin(2 * math.pi * 60 * i / SR) > 0 else -1.0
        out.append((sq * 0.5 + random.uniform(-1, 1) * 0.3) * (1 if on else 0.1) * (1 - i / n))
    return out


def gen_boom():
    n = int(SR * 1.6)
    return [math.sin(2 * math.pi * 45 * (i / SR)) * math.exp(-(i / SR) * 3) for i in range(n)]


def load_sounds():
    if not AUDIO:
        return
    SND["drone"] = make_sound(gen_drone(), 1.0)
    SND["growl"] = make_sound(gen_growl(), 1.0)
    SND["heart"] = make_sound(gen_heart(), 1.0)
    SND["step0"] = make_sound(gen_step(1, False), 1.0)
    SND["step1"] = make_sound(gen_step(2, False), 1.0)
    SND["mstep"] = make_sound(gen_step(3, True), 1.0)
    SND["click"] = make_sound(gen_click(), 1.0)
    SND["core"] = make_sound(gen_chime((660, 880, 1320), 0.09, 0.5, 6), 1.0)
    SND["win"] = make_sound(gen_chime((523, 659, 784, 1047), 0.14, 1.2, 3), 1.0)
    SND["pulse"] = make_sound(gen_pulse(), 1.0)
    SND["scream"] = make_sound(gen_scream(), 1.0)
    SND["sting"] = make_sound(gen_sting(), 1.0)
    SND["whisper"] = make_sound(gen_whisper(), 1.0)
    SND["bang"] = make_sound(gen_bang(), 1.0)
    SND["buzz"] = make_sound(gen_buzz(), 1.0)
    SND["boom"] = make_sound(gen_boom(), 1.0)
    # custom scream used when the entity catches the player (falls back to the generated one)
    try:
        SND["scream"] = pygame.mixer.Sound(find_asset("scream.mp3"))
        g.scream_ok = True
    except Exception as e:
        print("Could not load scream.mp3, using generated scream:", e)


def play(name, vol=1.0, pan=0.0):
    s = SND.get(name)
    if not AUDIO or s is None:
        return
    ch = pygame.mixer.find_channel()
    if ch is None:
        return
    ch.set_volume(max(0.0, min(1.0, vol * (1 - pan))), max(0.0, min(1.0, vol * (1 + pan))))
    ch.play(s)


def start_loops():
    if AUDIO and "drone" in SND:
        pygame.mixer.Channel(0).play(SND["drone"], loops=-1)
        pygame.mixer.Channel(0).set_volume(0.35)
        pygame.mixer.Channel(1).play(SND["growl"], loops=-1)
        pygame.mixer.Channel(1).set_volume(0.0)


def set_loop_volumes(drone, growl):
    if AUDIO and "drone" in SND:
        pygame.mixer.Channel(0).set_volume(drone)
        pygame.mixer.Channel(1).set_volume(growl)


# ---- monster sprite start
def draw_monster(surf, x, y, t, s=1.0):
    """A pale, bald, starved humanoid with long arms, hollow eyes and a wide grin."""

    def P(dx, dy):
        return (x + dx * s, y + dy * s)

    def R(dx, dy, w, h):
        return pygame.Rect(x + dx * s, y + dy * s, w * s, h * s)

    sway = math.sin(t * 2.0) * 2
    tr = math.sin(t * 31) * 0.8
    skin = (176, 180, 182)
    skin_mid = (130, 134, 138)
    skin_dark = (92, 96, 100)
    blood = (100, 20, 22)

    pygame.draw.ellipse(surf, (0, 0, 0), R(-36, 64, 72, 13))

    # legs
    for sx in (-1, 1):
        pts = [P(sx * 12, 20), P(sx * 14, 46), P(sx * 16, 66)]
        pygame.draw.lines(surf, skin_dark, False, pts, max(2, int(11 * s)))
        for p in pts:
            pygame.draw.circle(surf, skin_dark, p, max(1, int(5 * s)))
        pygame.draw.ellipse(surf, skin_dark, R(sx * 16 - 9, 63, 18, 8))

    # torso
    torso = [P(-14, -52), P(14, -52), P(40, -40), P(30, -10), P(21, 24), P(-21, 24), P(-30, -10), P(-40, -40)]
    pygame.draw.polygon(surf, skin_mid, torso)
    pygame.draw.ellipse(surf, skin_dark, R(-15, 4, 30, 22))
    for k in range(5):
        pygame.draw.arc(surf, (74, 78, 82), R(-27, -30 + k * 9, 54, 16), 3.4, 6.0, 2)
    pygame.draw.line(surf, (84, 88, 92), P(0, -44), P(0, 4), 2)
    pygame.draw.line(surf, (190, 194, 196), P(-4, -47), P(-35, -41), 2)
    pygame.draw.line(surf, (190, 194, 196), P(4, -47), P(35, -41), 2)

    # long arms hanging down
    for sx in (-1, 1):
        pts = [P(sx * 38, -40), P(sx * 52, -2), P(sx * 46 + tr, 44)]
        pygame.draw.lines(surf, skin_mid, False, pts, max(2, int(8 * s)))
        for p in pts:
            pygame.draw.circle(surf, skin_mid, p, max(1, int(4 * s)))
        hand = pts[-1]
        for a in (72, 84, 96, 108):
            ang = math.radians(a)
            end = (hand[0] + math.cos(ang) * 15 * s, hand[1] + math.sin(ang) * 15 * s)
            pygame.draw.line(surf, skin, hand, end, 2)

    # chest blood
    for bx, by, br in ((-8, -22, 3), (6, -14, 2), (-3, -6, 2), (12, -28, 2)):
        pygame.draw.circle(surf, blood, P(bx, by), max(1, int(br * s)))

    # head
    hx = sway * 0.5
    pygame.draw.rect(surf, skin_mid, R(hx - 5, -52, 10, 10))
    pygame.draw.ellipse(surf, skin_mid, R(hx - 20, -76, 5, 12))
    pygame.draw.ellipse(surf, skin_mid, R(hx + 15, -76, 5, 12))
    pygame.draw.ellipse(surf, skin, R(hx - 17, -92, 34, 46))
    pygame.draw.ellipse(surf, (48, 38, 42), R(hx - 14, -77, 12, 10))
    pygame.draw.ellipse(surf, (48, 38, 42), R(hx + 2, -77, 12, 10))
    for ex in (-8, 8):
        pygame.draw.circle(surf, (150, 120, 110), P(hx + ex, -72), max(2, int(4.5 * s)), 1)
        pygame.draw.circle(surf, (245, 235, 205), P(hx + ex, -72), max(1, int(2.6 * s)))
    pygame.draw.line(surf, (128, 132, 134), P(hx, -69), P(hx - 2, -60), 2)

    # wide grin, teeth, blood on the chin
    mouth = [P(hx - 11, -58), P(hx, -55), P(hx + 11, -58), P(hx + 8, -51), P(hx, -48), P(hx - 8, -51)]
    pygame.draw.polygon(surf, (62, 12, 14), mouth)
    for k in range(5):
        tx = hx - 8 + k * 4
        pygame.draw.line(surf, (232, 228, 214), P(tx, -55), P(tx, -52), 1)
    pygame.draw.ellipse(surf, blood, R(hx - 6, -49, 12, 9))
# ---- monster sprite end

# ================================================================= TUNING
PLAYER_SPEED = 3.0
SPRINT_SPEED = 4.4
TURN_SPEED = 2.2
MOUSE_SENS = 0.0025
LIGHT_RANGE = 9.0
LIGHT_HALF = math.radians(24)
PULSE_COST = 30

LEVEL_NAMES = [
    "Arrival Wing", "Containment Corridor", "Records Archive", "Maintenance Tunnels", "Observation Deck",
    "Cold Storage", "Specimen Hall", "The Vents", "Flooded Basement", "Quarantine Ward",
    "Boiler Room", "Dormitory", "The Morgue", "Server Catacombs", "Black Site Gamma",
    "Isolation Cells", "Autopsy Theatre", "The Long Dark", "Chapel of Static", "Sublevel Twenty",
    "The Quiet Floor", "Mirror Hall", "Reactor Core", "Lost Archives", "The Pit",
    "Echo Chambers", "Last Checkpoint", "Collapse Zone", "The Witness", "The Observer's Eye",
]

DIRS4 = [(1, 0), (-1, 0), (0, 1), (0, -1)]
SAVE_PATH = os.path.join(ASSET_DIR, "observer_save.json")


def load_save():
    try:
        with open(SAVE_PATH) as f:
            return max(1, min(MAX_LEVEL, int(json.load(f).get("unlocked", 1))))
    except Exception:
        return 1


def write_save(unlocked):
    try:
        with open(SAVE_PATH, "w") as f:
            json.dump({"unlocked": unlocked}, f)
    except Exception:
        pass


# ================================================================= LEVEL GENERATION
def bfs_grid(sol, W, H, cell):
    dist = [[999] * W for _ in range(H)]
    sx, sy = cell
    dist[sy][sx] = 0
    q = deque([cell])
    while q:
        x, y = q.popleft()
        d = dist[y][x] + 1
        for dx, dy in DIRS4:
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H and not sol[ny][nx] and dist[ny][nx] == 999:
                dist[ny][nx] = d
                q.append((nx, ny))
    return dist


def gen_level(level):
    """Rooms joined by corridors. Bigger every few levels. Deterministic per level."""
    rnd = random.Random(level * 7919 + 13)
    gx = min(7, 3 + level // 7)
    gy = min(5, 2 + level // 8)
    B = 8
    W, H = gx * B + 1, gy * B + 1
    sol = [[True] * W for _ in range(H)]
    rooms = {}
    for j in range(gy):
        for i in range(gx):
            rw, rh = rnd.randint(4, 6), rnd.randint(4, 6)
            ox = i * B + 1 + rnd.randint(0, 7 - rw)
            oy = j * B + 1 + rnd.randint(0, 7 - rh)
            for y in range(oy, oy + rh):
                for x in range(ox, ox + rw):
                    sol[y][x] = False
            rooms[(i, j)] = (ox, oy, rw, rh, (ox + rw // 2, oy + rh // 2))

    visited = {(0, 0)}
    stack = [(0, 0)]
    edges = []
    while stack:
        i, j = stack[-1]
        nb = [(i + dx, j + dy) for dx, dy in DIRS4
              if 0 <= i + dx < gx and 0 <= j + dy < gy and (i + dx, j + dy) not in visited]
        if nb:
            n = rnd.choice(nb)
            visited.add(n)
            edges.append(((i, j), n))
            stack.append(n)
        else:
            stack.pop()
    for _ in range(int(gx * gy * 0.4)):
        i, j = rnd.randrange(gx), rnd.randrange(gy)
        dx, dy = rnd.choice(DIRS4)
        n = (i + dx, j + dy)
        if 0 <= n[0] < gx and 0 <= n[1] < gy:
            edges.append(((i, j), n))
    for a, b in edges:
        ax, ay = rooms[a][4]
        bx, by = rooms[b][4]
        for x in range(min(ax, bx), max(ax, bx) + 1):
            sol[ay][x] = False
        for y in range(min(ay, by), max(ay, by) + 1):
            sol[y][bx] = False

    start = rooms[(0, 0)][4]
    floor = sum(1 for row in sol for v in row if not v)
    for (i, j), (ox, oy, rw, rh, c) in rooms.items():
        if rnd.random() < 0.55:
            for _ in range(rnd.randint(1, 3)):
                x, y = rnd.randrange(ox, ox + rw), rnd.randrange(oy, oy + rh)
                if sol[y][x] or (x, y) == c or (x, y) == start:
                    continue
                sol[y][x] = True
                d = bfs_grid(sol, W, H, start)
                if sum(1 for row in d for v in row if v != 999) != floor - 1:
                    sol[y][x] = False
                else:
                    floor -= 1

    d = bfs_grid(sol, W, H, start)
    far = max(rooms.values(), key=lambda r: d[r[4][1]][r[4][0]])
    return sol, W, H, start, far[4]


def level_params(level):
    return dict(
        cores=3 + level // 8,
        monsters=1 if level < 15 else 2 if level < 25 else 3,
        mspeed=1.45 + 0.045 * level,
        tunnel_chance=min(0.5, 0.15 + 0.012 * level),
        tunnel_every=max(1.0, 1.6 - 0.02 * level),
        drain=16 + 0.3 * level,
        recharge=max(3.0, 7 - 0.1 * level),
        event_scale=max(0.45, 1 - 0.015 * level),
    )


solid = [[True]]
MW, MH = 1, 1
START = (1.5, 1.5)
EXIT_CELL = (1, 1)
EXIT_POS = (1.5, 1.5)


def bfs(cell):
    return bfs_grid(solid, MW, MH, cell)


def free(x, y):
    return not solid[int(y)][int(x)]


def los(x0, y0, x1, y1):
    d = math.hypot(x1 - x0, y1 - y0)
    steps = int(d / 0.1) + 1
    for i in range(1, steps):
        t = i / steps
        if solid[int(y0 + (y1 - y0) * t)][int(x0 + (x1 - x0) * t)]:
            return False
    return True


def cast(px, py, ang):
    dx, dy = math.cos(ang), math.sin(ang)
    mapx, mapy = int(px), int(py)
    ddx = abs(1 / dx) if dx else 1e30
    ddy = abs(1 / dy) if dy else 1e30
    if dx < 0:
        stepx, sidex = -1, (px - mapx) * ddx
    else:
        stepx, sidex = 1, (mapx + 1 - px) * ddx
    if dy < 0:
        stepy, sidey = -1, (py - mapy) * ddy
    else:
        stepy, sidey = 1, (mapy + 1 - py) * ddy
    side = 0
    while True:
        if sidex < sidey:
            sidex += ddx
            mapx += stepx
            side = 0
        else:
            sidey += ddy
            mapy += stepy
            side = 1
        if solid[mapy][mapx]:
            break
    if side == 0:
        dist = sidex - ddx
        wx = py + dist * dy
    else:
        dist = sidey - ddy
        wx = px + dist * dx
    return dist, side, mapx, mapy, wx - math.floor(wx)


# ================================================================= ASSETS
TS = 64
SHADES = 16


def _clamp(c):
    return tuple(max(0, min(255, int(v))) for v in c)


def make_textures():
    out = []
    for kind in range(3):
        rnd = random.Random(100 + kind)
        t = pygame.Surface((TS, TS))
        for y in range(TS):
            for x in range(TS):
                n = rnd.randint(-9, 9)
                if kind == 0:
                    c = (108 + n, 112 + n, 116 + n)
                    if x % 32 == 0 or y in (0, 31):
                        c = (c[0] - 38, c[1] - 38, c[2] - 38)
                    if y >= 54:
                        c = (c[0] - 26, c[1] - 26, c[2] - 22)
                elif kind == 1:
                    row = y // 8
                    off = (row % 2) * 8
                    bx = (x + off) % 16
                    if y % 8 == 0 or bx == 0:
                        c = (64 + n // 2, 58 + n // 2, 56 + n // 2)
                    else:
                        var = ((row * 31 + (x + off) // 16 * 17) % 21) - 10
                        c = (128 + n + var, 84 + n + var // 2, 70 + n)
                else:
                    c = (96 + n, 118 + n, 112 + n)
                    if x % 16 == 0 or y % 16 == 0:
                        c = (58, 68, 66)
                    if y >= 52:
                        c = (c[0] - 24, c[1] - 24, c[2] - 20)
                t.set_at((x, y), _clamp(c))
        for _ in range(6):
            x0 = rnd.randrange(TS)
            for yy in range(rnd.randint(10, 44)):
                for xx, dk in ((x0, 28), (x0 + 1, 16)):
                    if xx < TS:
                        r, g_, b = t.get_at((xx, yy))[:3]
                        t.set_at((xx, yy), _clamp((r - dk, g_ - dk, b - dk)))
        for _ in range(4):
            bx, by = rnd.randrange(TS - 4), rnd.randrange(TS - 4)
            for yy in range(by, by + rnd.randint(2, 4)):
                for xx in range(bx, bx + rnd.randint(2, 4)):
                    t.set_at((xx, yy), (88 + rnd.randint(-8, 8), 16, 18))
        out.append(t)
    shaded = []
    for t in out:
        sides = []
        for sidef in (1.0, 0.78):
            row = []
            for i in range(SHADES):
                v = int(255 * (i / (SHADES - 1)) * sidef)
                s = t.copy()
                s.fill((v, v, v), special_flags=pygame.BLEND_RGB_MULT)
                row.append(s)
            sides.append(row)
        shaded.append(sides)
    return shaded


WALL_TEX = make_textures()

scene = pygame.Surface((IW, IH))
frame = pygame.Surface((WIDTH, HEIGHT))
zbuf = [1e9] * IW

bg = pygame.Surface((IW, IH))
for _y in range(IH):
    if _y < IH // 2:
        _t = _y / (IH / 2)
        _c = (int(16 * (1 - _t) + 7 * _t), int(16 * (1 - _t) + 7 * _t), int(20 * (1 - _t) + 9 * _t))
    else:
        _t = (_y - IH / 2) / (IH / 2)
        _c = (int(20 + 38 * _t), int(20 + 34 * _t), int(24 + 32 * _t))
    pygame.draw.line(bg, _c, (0, _y), (IW, _y))


def make_lit_mask(ambient=0.07, widen=1.0):
    m = pygame.Surface((IW, IH))
    rx, ry = IW * 0.42 * widen, IH * 0.62 * (0.55 + 0.45 * widen)
    for y in range(IH):
        for x in range(IW):
            ux = (x - IW / 2) / rx
            uy = (y - IH * 0.52) / ry
            f = max(0.0, 1.0 - (ux * ux + uy * uy))
            v = ambient + (1 - ambient) * f ** 1.4
            m.set_at((x, y), (int(255 * v), int(246 * v), int(220 * v)))
    return m


MASK_LIT = make_lit_mask()
MASK_NARROW = make_lit_mask(widen=0.55)
MASK_DIM = pygame.Surface((IW, IH))
MASK_DIM.fill((17, 17, 20))
MASK_BLACK = pygame.Surface((IW, IH))
MASK_BLACK.fill((6, 6, 8))

_grain_small = []
for _k in range(6):
    _s = pygame.Surface((176, 112))
    _r = random.Random(500 + _k)
    for _y in range(112):
        for _x in range(176):
            if _r.random() < 0.35:
                _v = _r.randint(4, 18)
                _s.set_at((_x, _y), (_v, _v, _v))
    _grain_small.append(_s)
GRAIN_SCENE = [pygame.transform.scale(s, (IW, IH)) for s in _grain_small]
GRAIN_SCREEN = [pygame.transform.scale(s, (WIDTH, HEIGHT)) for s in _grain_small]

_vs = pygame.Surface((110, 70), pygame.SRCALPHA)
for _y in range(70):
    for _x in range(110):
        _r2 = math.hypot((_x - 55) / 55, (_y - 35) / 35)
        _vs.set_at((_x, _y), (0, 0, 0, int(255 * max(0.0, min(1.0, (_r2 - 0.45) / 0.75)) ** 1.5)))
VIGNETTE = pygame.transform.smoothscale(_vs, (WIDTH, HEIGHT))

MON_FRAMES = []
for _tt in (0.05, 0.15):
    _s = pygame.Surface((120, 175), pygame.SRCALPHA)
    draw_monster(_s, 60, 95, _tt, 1.0)
    MON_FRAMES.append(_s)

CORE_IMG = pygame.Surface((48, 48), pygame.SRCALPHA)
for _rr in range(24, 0, -1):
    pygame.draw.circle(CORE_IMG, (255, 205, 90, int(255 * (1 - _rr / 24) ** 1.3)), (24, 24), _rr)
pygame.draw.circle(CORE_IMG, (255, 250, 210, 255), (24, 24), 4)


ENTITY_EMBED_SIZE = (241, 348)
ENTITY_EMBED = """
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
3oXT/+jixf8P3NgnJg==
"""


def load_entity_image():
    """Use entity.jpg next to the script if pygame can read it; otherwise use the copy of the
    photo built into this file (raw pixels, so it works even if pygame lacks JPEG support)."""
    import base64
    import zlib
    note = ""
    for d in (ASSET_DIR, os.getcwd()):
        fp = os.path.join(d, "entity.jpg")
        if os.path.isfile(fp):
            try:
                return pygame.image.load(fp).convert(), "entity.jpg (file)"
            except Exception as ex:
                note = "entity.jpg unreadable (%s); " % ex
                break
    raw = zlib.decompress(base64.b64decode(ENTITY_EMBED.replace("\n", "")))
    surf = pygame.image.frombuffer(raw, ENTITY_EMBED_SIZE, "RGB").convert()
    return surf, note + "built-in photo"


ENTITY_IMG = None
IMG_STATUS = ""
try:
    ENTITY_IMG, IMG_STATUS = load_entity_image()
except Exception as _e:
    IMG_STATUS = "load error: " + str(_e)
    print("Could not load entity image, using drawn face:", _e)


def make_photo_sprite(img, bright):
    """Whole entity photo as a sprite, with only the outer edges softly feathered."""
    w, h = img.get_size()
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    out.blit(img, (0, 0))
    f = 8.0
    for y in range(h):
        for x in range(w):
            e = min(x, y, w - 1 - x, h - 1 - y)
            a = max(0.0, min(1.0, e / f))
            r, gg, b = out.get_at((x, y))[:3]
            out.set_at((x, y), (min(255, int(r * bright)), min(255, int(gg * bright)),
                                min(255, int(b * bright)), int(255 * a)))
    return out


USE_PHOTO_MONSTER = False
if ENTITY_IMG is not None:
    try:
        _small = pygame.transform.smoothscale(ENTITY_IMG, (120, int(120 * ENTITY_IMG.get_height() / ENTITY_IMG.get_width())))
        MON_FRAMES = [make_photo_sprite(_small, 1.0), make_photo_sprite(_small, 0.8)]
        USE_PHOTO_MONSTER = True
    except Exception as _e:
        print("Could not build photo monster sprite:", _e)
_entity_cache = {}


def entity_scaled(h):
    """Smooth-scaled copy of the entity photo at height h (cached in 24px steps)."""
    h = max(24, int(h // 8 * 8))
    img = _entity_cache.get(h)
    if img is None:
        w = int(h * ENTITY_IMG.get_width() / ENTITY_IMG.get_height())
        img = pygame.transform.smoothscale(ENTITY_IMG, (w, h))
        if len(_entity_cache) > 40:
            _entity_cache.clear()
        _entity_cache[h] = img
    return img


def draw_entity_photo(surf, T):
    """Jump scare: the whole photo, uncropped, fitted to the screen height with a slow creep."""
    surf.blit(entity_backdrop(), (0, 0))
    h = HEIGHT * (0.92 + min(T, 2.6) * 0.03) * (1.0 + 0.06 * max(0.0, 1 - T * 8))
    img = entity_scaled(h)
    shake = max(2.0, 14 - T * 6)
    cx = WIDTH / 2 + random.uniform(-shake, shake)
    cy = HEIGHT / 2 + random.uniform(-shake, shake)
    surf.blit(img, (cx - img.get_width() / 2, cy - img.get_height() / 2))
    ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    ov.fill((150, 0, 0, 30 + (50 if int(T * 30) % 5 == 0 else 0)))
    surf.blit(ov, (0, 0))


_backdrop = None


def entity_backdrop():
    global _backdrop
    if _backdrop is None:
        _backdrop = pygame.transform.smoothscale(ENTITY_IMG, (WIDTH, HEIGHT))
        _backdrop.fill((70, 40, 40), special_flags=pygame.BLEND_RGB_MULT)
    return _backdrop


def make_exit(unlocked):
    s = pygame.Surface((44, 80), pygame.SRCALPHA)
    fill = (20, 90, 50) if unlocked else (30, 30, 36)
    edge = (70, 210, 130) if unlocked else (110, 110, 120)
    pygame.draw.rect(s, fill, (0, 0, 44, 80))
    pygame.draw.rect(s, edge, (0, 0, 44, 80), 3)
    label = TINY.render("EXIT" if unlocked else "LOCK", True, edge)
    s.blit(label, (22 - label.get_width() // 2, 30))
    return s


EXIT_OPEN, EXIT_LOCKED = make_exit(True), make_exit(False)

# ================================================================= GAME STATE
g = types.SimpleNamespace()
g.state = "title"
g.unlocked = 1
g.sel = 1
g.t = 0.0
g.deaths = 0
g.level = 1
g.mons = []
g.cores = []
g.decoy = None
g.message = ""
g.flash = 0.0
g.shake_t = 0.0
g.horizon = IH / 2
g.focus = False
g.grover = False
g.gmark = set()
g.gP = g.gpeak = 0.0
g.lh = LIGHT_HALF
g.lr = LIGHT_RANGE


def set_mouse(play):
    try:
        pygame.event.set_grab(play)
        pygame.mouse.set_visible(not play)
        pygame.mouse.get_rel()
    except Exception:
        pass


def set_state(s):
    g.state = s
    set_mouse(s in ("card", "play", "dead", "levelwin"))


def new_monster(x, y):
    # psi is the monster's wavefunction: probability of being found in each floor cell.
    # collapsed=True means a measurement (your light) pinned it to the definite spot (x, y).
    return dict(x=x, y=y, observed=False, seen=False, unobs=0.0, tunnel_t=0.0,
                step_t=0.0, last=(x, y), moving=False,
                psi={(int(x), int(y)): 1.0}, collapsed=False, ent=None,
                meas_t=0.0, evo_t=0.0, ex=x, ey=y, pd=20.0)


def spawn_cores(n):
    d = g.dist_map
    ed = bfs(EXIT_CELL)
    cells = [(x, y) for y in range(MH) for x in range(MW) if not solid[y][x] and d[y][x] < 999]
    pts = []
    for attempt in range(8):
        pts = []
        for _ in range(500):
            x, y = random.choice(cells)
            c = (x + 0.5, y + 0.5)
            if d[y][x] < 8 - attempt or ed[y][x] < max(2, 5 - attempt // 2):
                continue
            if any(math.dist(c, p) < 6 - attempt * 0.5 for p in pts):
                continue
            pts.append(c)
            if len(pts) == n:
                return pts
    return pts


def spawn_monsters(n):
    d = g.dist_map
    maxd = max(v for row in d for v in row if v != 999)
    cells = [(x, y) for y in range(MH) for x in range(MW)
             if not solid[y][x] and d[y][x] != 999 and d[y][x] >= max(12, int(maxd * 0.5))]
    if not cells:
        cells = [(x, y) for y in range(MH) for x in range(MW) if not solid[y][x] and 6 <= d[y][x] < 999]
    mons = []
    for _ in range(n):
        x, y = random.choice(cells)
        for _t in range(100):
            x, y = random.choice(cells)
            if all(math.dist((x, y), (int(m["x"]), int(m["y"]))) >= 8 for m in mons):
                break
        mons.append(new_monster(x + 0.5, y + 0.5))
    # entangle monsters in pairs: measuring one collapses its partner to the mirror point
    for i in range(0, len(mons) - 1, 2):
        mons[i]["ent"], mons[i + 1]["ent"] = i + 1, i
    return mons


def schedule_event():
    g.event_t = random.uniform(14, 30) * g.p["event_scale"]


def start_level(level):
    global solid, MW, MH, START, EXIT_CELL, EXIT_POS
    solid, MW, MH, sc, ec = gen_level(level)
    START = (sc[0] + 0.5, sc[1] + 0.5)
    EXIT_CELL = ec
    EXIT_POS = (ec[0] + 0.5, ec[1] + 0.5)
    g.level = level
    g.p = level_params(level)
    g.px, g.py = START
    g.pa = math.atan2(EXIT_POS[1] - START[1], EXIT_POS[0] - START[0])
    g.dist_map = bfs((int(g.px), int(g.py)))
    g.cores = spawn_cores(g.p["cores"])
    g.mons = spawn_monsters(g.p["monsters"])
    g.taken = 0
    g.battery = 100.0
    g.stamina = 100.0
    g.tired = False
    g.light_on = False
    g.locked = False
    g.blackout_t = 0.0
    g.decoy = None
    g.focus = False
    g.grover = False
    g.gmark = set()
    g.gP = g.gpeak = 0.0
    apply_focus()
    g.message = f"FIND {g.p['cores']} CORES. KEEP YOUR LIGHT ON IT."
    g.elapsed = 0.0
    g.map_t = 0.0
    g.walk = 0.0
    g.moving = False
    g.sprinting = False
    g.step_t = 0.0
    g.hb_t = 0.0
    g.pulse_t = 0.0
    g.flash = 0.0
    g.shake_t = 0.0
    g.dead_t = 0.0
    g.win_t = 0.0
    g.card_t = 0.0
    g.cs = max(2, min(8, 220 // MW, 160 // MH))
    g.mini = pygame.Surface((MW * g.cs, MH * g.cs))
    g.mini.fill((6, 6, 10))
    g.explored = [[False] * MW for _ in range(MH)]
    schedule_event()
    g.event_t += 8
    set_state("card")
    play("boom", 0.6)
    start_loops()


# ================================================================= GAMEPLAY
def monster_observed(m):
    dx, dy = m["x"] - g.px, m["y"] - g.py
    d = math.hypot(dx, dy)
    if d < 0.001:
        return True
    rel = (math.atan2(dy, dx) - g.pa + math.pi) % (2 * math.pi) - math.pi
    if abs(rel) > FOV / 2 or not los(g.px, g.py, m["x"], m["y"]):
        return False
    return g.light_on and d < g.lr and abs(rel) < g.lh


def try_move(dx, dy):
    r = 0.22
    nx = g.px + dx
    if all(free(nx + sx * r, g.py + sy * r) for sx in (-1, 1) for sy in (-1, 1)):
        g.px = nx
    ny = g.py + dy
    if all(free(g.px + sx * r, ny + sy * r) for sx in (-1, 1) for sy in (-1, 1)):
        g.py = ny


def move_monster(m, dt):
    speed = g.p["mspeed"] + 0.1 * g.taken
    cx, cy = int(m["x"]), int(m["y"])
    if (cx, cy) == (int(g.px), int(g.py)):
        tx, ty = g.px, g.py
    else:
        best, bd = None, g.dist_map[cy][cx]
        for dx, dy in DIRS4:
            nx, ny = cx + dx, cy + dy
            if not solid[ny][nx] and g.dist_map[ny][nx] < bd:
                best, bd = (nx, ny), g.dist_map[ny][nx]
        if best is None:
            m["moving"] = False
            return
        tx, ty = best[0] + 0.5, best[1] + 0.5
    ddx, ddy = tx - m["x"], ty - m["y"]
    d = math.hypot(ddx, ddy)
    if d < 1e-6:
        m["moving"] = False
        return
    step = min(d, speed * dt)
    m["x"] += ddx / d * step
    m["y"] += ddy / d * step
    m["moving"] = True


def tunnel(m):
    cx, cy = int(m["x"]), int(m["y"])
    for _ in range(2):
        best, bd = None, g.dist_map[cy][cx]
        for dx, dy in DIRS4:
            nx, ny = cx + dx, cy + dy
            if not solid[ny][nx] and g.dist_map[ny][nx] < bd:
                best, bd = (nx, ny), g.dist_map[ny][nx]
        if best is None:
            break
        cx, cy = best
    if g.dist_map[cy][cx] >= 3:
        m["x"], m["y"] = cx + 0.5, cy + 0.5


def rel_pan(wx, wy):
    a = math.atan2(wy - g.py, wx - g.px) - g.pa
    return math.sin(a)


def pulse():
    if g.battery < PULSE_COST:
        g.message = "NOT ENOUGH BATTERY FOR A PULSE."
        return
    g.battery -= PULSE_COST
    cands = [(x, y) for y in range(MH) for x in range(MW) if not solid[y][x] and 9 <= g.dist_map[y][x] < 999]
    for m in g.mons:
        if cands:
            # maximum uncertainty: the wavefunction is smeared evenly across the far facility
            m["psi"] = {c: 1.0 / len(cands) for c in cands}
            m["collapsed"] = False
            m.pop("amp", None)
            x, y = random.choice(cands)
            m["x"], m["y"] = x + 0.5, y + 0.5
        m["unobs"] = 8.0
        m["last"] = (MW / 2, MH / 2)
    g.pulse_t = 0.5
    g.message = "PULSE SMEARED ITS WAVEFUNCTION ACROSS THE FACILITY."
    play("pulse", 0.9)


def presence():
    best = 0.0
    for m in g.mons:
        pd = m["pd"]
        best = max(best, max(0.0, min(1.0, 1 - pd / 14)) ** 1.2)
    return best


def spawn_decoy():
    for _ in range(10):
        a = g.pa + random.uniform(-0.6, 0.6)
        d = random.uniform(5, 9)
        x, y = g.px + math.cos(a) * d, g.py + math.sin(a) * d
        if 0 < x < MW and 0 < y < MH and free(x, y) and los(g.px, g.py, x, y):
            g.decoy = dict(x=x, y=y, t=1.8)
            play("whisper", 0.7, math.sin(a - g.pa))
            return


def trigger_event():
    kinds = ["whisper", "bang", "blackout", "eyes"]
    if g.level >= 5:
        kinds += ["blackout", "eyes"]
    k = random.choice(kinds)
    if k == "whisper":
        play("whisper", 0.9, random.choice([-0.9, 0.9]))
        g.message = "SOMETHING WHISPERED YOUR NAME."
    elif k == "bang":
        play("bang", 1.0, random.uniform(-0.8, 0.8))
        g.shake_t = 0.5
        g.message = "A DOOR SLAMMED SOMEWHERE."
    elif k == "blackout":
        play("buzz", 0.9)
        g.blackout_t = 2.5
        g.message = "THE LIGHTS DIED."
    else:
        spawn_decoy()


def mark_explored():
    cx, cy = int(g.px), int(g.py)
    for yy in range(max(0, cy - 3), min(MH, cy + 4)):
        for xx in range(max(0, cx - 3), min(MW, cx + 4)):
            if not g.explored[yy][xx]:
                g.explored[yy][xx] = True
                pygame.draw.rect(g.mini, (70, 72, 84) if solid[yy][xx] else (22, 22, 30),
                                 (xx * g.cs, yy * g.cs, g.cs, g.cs))


# ---------------------------------------------------------------- QUANTUM RULES
# 1. SUPERPOSITION  : an unwatched monster has no position, only a wavefunction psi over cells.
# 2. MEASUREMENT    : light on a cell either finds it (Born rule: chance = probability inside the
#                     beam) and collapses psi to one cell, or finds nothing, which also collapses
#                     psi (that area is now ruled out and the rest is renormalised).
# 3. TUNNELLING     : mass can leak through a 1-cell wall; chance falls off as exp(-2*kappa*width).
# 4. ENTANGLEMENT   : monsters come in pairs; collapsing one collapses the other to the mirror point.
# 5. UNCERTAINTY    : narrow beam = sharp aim and long reach, but the lit field is tiny and drains more.
def nearest_free(cx, cy, maxr=6):
    for r in range(maxr + 1):
        ring = [(x, y) for y in range(cy - r, cy + r + 1) for x in range(cx - r, cx + r + 1)
                if max(abs(x - cx), abs(y - cy)) == r and 0 <= x < MW and 0 <= y < MH
                and not solid[y][x] and g.dist_map[y][x] < 999]
        if ring:
            return random.choice(ring)
    return None


def collapse_entangled(m):
    j = m.get("ent")
    if j is None or j >= len(g.mons):
        return
    o = g.mons[j]
    if o is m or o["collapsed"]:
        return
    cell = nearest_free(MW - 1 - int(m["x"]), MH - 1 - int(m["y"]))
    if cell is None or math.hypot(cell[0] + 0.5 - g.px, cell[1] + 0.5 - g.py) < 4:
        return
    o["psi"] = {cell: 1.0}
    o["x"], o["y"] = cell[0] + 0.5, cell[1] + 0.5
    g.message = "ENTANGLED PAIR: ITS PARTNER COLLAPSED AT THE MIRROR POINT."


def qmeasure(m, dt):
    """Returns True while the monster is collapsed inside the beam (observed)."""
    if m["collapsed"]:
        if monster_observed(m):
            return True
        m["collapsed"] = False                  # decoherence: it dissolves back into a wavefunction
        m["psi"] = {(int(m["x"]), int(m["y"])): 1.0}
        return False
    m["meas_t"] += dt
    if not g.light_on or m["meas_t"] < 0.1:
        return False
    m["meas_t"] = 0.0
    vis, tot = [], 0.0
    for c, p in m["psi"].items():
        cx, cy = c[0] + 0.5, c[1] + 0.5
        dx, dy = cx - g.px, cy - g.py
        if math.hypot(dx, dy) > g.lr:
            continue
        rel = (math.atan2(dy, dx) - g.pa + math.pi) % (2 * math.pi) - math.pi
        if abs(rel) > g.lh or not los(g.px, g.py, cx, cy):
            continue
        vis.append((c, p))
        tot += p
    if not vis:
        return False
    if random.random() < tot:                   # Born rule: found it, wavefunction collapses
        r, acc, pick = random.random() * tot, 0.0, vis[-1][0]
        for c, p in vis:
            acc += p
            if acc >= r:
                pick = c
                break
        m["x"], m["y"] = pick[0] + 0.5, pick[1] + 0.5
        m["collapsed"] = True
        m["psi"] = {pick: 1.0}
        collapse_entangled(m)
        return True
    for c, _ in vis:                            # null result: it is NOT in the lit area
        del m["psi"][c]
    s = sum(m["psi"].values())
    if s <= 1e-9:
        m["psi"] = {vis[0][0]: 1.0}
    else:
        m["psi"] = {c: p / s for c, p in m["psi"].items()}
    return False


def qevolve_step(m, step):
    speed = g.p["mspeed"] + 0.1 * g.taken
    f = min(0.9, speed * step * 1.2)
    dm = g.dist_map
    pc = (int(g.px), int(g.py))
    tun = min(0.6, g.p["tunnel_chance"] * 2.0) * math.exp(-2 * 0.7 * 1)   # width-1 barrier
    new = {}
    for c, p in m["psi"].items():
        if c == pc:
            new[c] = new.get(c, 0.0) + p
            continue
        x, y = c
        here = dm[y][x]
        move = p * f
        new[c] = new.get(c, 0.0) + p - move
        nbrs, best, bd = [], None, here
        for dx, dy in DIRS4:
            nx, ny = x + dx, y + dy
            if not solid[ny][nx]:
                nbrs.append((nx, ny))
                if dm[ny][nx] < bd:
                    best, bd = (nx, ny), dm[ny][nx]
        tdest, td = None, here - 3
        for dx, dy in DIRS4:
            tx, ty = x + 2 * dx, y + 2 * dy
            if 0 <= tx < MW and 0 <= ty < MH and solid[y + dy][x + dx] and not solid[ty][tx] \
                    and dm[ty][tx] <= td:
                tdest, td = (tx, ty), dm[ty][tx]
        if tdest:
            share = move * tun
            new[tdest] = new.get(tdest, 0.0) + share
            move -= share
        if not nbrs:
            new[c] += move
            continue
        if best:
            new[best] = new.get(best, 0.0) + move * 0.8
            rest = move * 0.2
        else:
            rest = move
        for n in nbrs:
            new[n] = new.get(n, 0.0) + rest / len(nbrs)
    tot = sum(new.values())
    new = {c: p for c, p in new.items() if p > 2e-5 * tot}
    tot = sum(new.values())
    m["psi"] = {c: p / tot for c, p in new.items()}


def qevolve(m, dt):
    m["evo_t"] += dt
    while m["evo_t"] >= 0.12:
        m["evo_t"] -= 0.12
        qevolve_step(m, 0.12)


def qstats(m):
    dm = g.dist_map
    if m["collapsed"]:
        m["ex"], m["ey"] = m["x"], m["y"]
        m["pd"] = dm[int(m["y"])][int(m["x"])]
        return
    ex = ey = pd = 0.0
    for (x, y), p in m["psi"].items():
        ex += p * (x + 0.5)
        ey += p * (y + 0.5)
        pd += p * dm[y][x]
    m["ex"], m["ey"], m["pd"] = ex, ey, pd


# 6. AMPLITUDE AMPLIFICATION (Grover search), hold G.
#    Probability is the SQUARE of an amplitude, and amplitudes can be negative. Each iteration does
#    two reflections: (a) the ORACLE flips the sign of every amplitude inside the beam you locked,
#    (b) DIFFUSION reflects all amplitudes about their mean. Together they rotate amplitude INTO the
#    marked cells, so P(in beam) rises like sin^2((2k+1)*theta). Keep going past the peak and it
#    rotates back out again, so you must release at the top. Best after a pulse (uniform cloud).
def grover_start():
    M = set()
    r = int(g.lr) + 1
    for y in range(int(g.py) - r, int(g.py) + r + 1):
        for x in range(int(g.px) - r, int(g.px) + r + 1):
            if not (0 <= x < MW and 0 <= y < MH) or solid[y][x]:
                continue
            cx, cy = x + 0.5, y + 0.5
            dx, dy = cx - g.px, cy - g.py
            if math.hypot(dx, dy) > g.lr:
                continue
            rel = (math.atan2(dy, dx) - g.pa + math.pi) % (2 * math.pi) - math.pi
            if abs(rel) <= g.lh and los(g.px, g.py, cx, cy):
                M.add((x, y))
    if not M:
        g.message = "AIM AT OPEN FLOOR TO MARK CELLS, THEN HOLD G."
        return
    g.gmark, g.gacc, g.gtime, g.gpeak, g.gP = M, 0.0, 0.0, 0.0, 0.0
    for m in g.mons:
        if not m["collapsed"]:
            m["amp"] = {c: math.sqrt(m["psi"].get(c, 0.0)) for c in (set(m["psi"]) | M)}
    g.grover = True
    g.message = "AMPLIFYING: RELEASE G AT THE PEAK."


def grover_iterate():
    best = 0.0
    for m in g.mons:
        amp = m.get("amp")
        if not amp:
            continue
        for c in g.gmark:
            amp[c] = -amp[c]                              # oracle: phase flip on marked cells
        mean = sum(amp.values()) / len(amp)
        for c in amp:
            amp[c] = 2 * mean - amp[c]                    # diffusion: inversion about the mean
        pm = sum(amp[c] ** 2 for c in g.gmark if c in amp)
        m["psi"] = {c: a * a for c, a in amp.items() if a * a > 2e-5}
        tot = sum(m["psi"].values())
        m["psi"] = {c: p / tot for c, p in m["psi"].items()}
        best = max(best, pm)
    g.gP = best
    g.gpeak = max(g.gpeak, best)


def grover_end():
    for m in g.mons:
        if "amp" in m:
            del m["amp"]
            m["meas_t"] = 0.1                             # measure right away if your light is on
    g.grover = False
    g.gmark = set()
    g.message = f"AMPLIFICATION RELEASED. PEAK P(IN BEAM) WAS {g.gpeak * 100:.0f}%."


def apply_focus():
    g.lh = math.radians(9) if g.focus else LIGHT_HALF
    g.lr = 15.0 if g.focus else LIGHT_RANGE


def caught_by(m):
    g.deaths += 1
    g.pa = math.atan2(m["y"] - g.py, m["x"] - g.px)
    g.dead_t = 0.0
    set_state("dead")
    play("scream", 1.0)
    set_loop_volumes(0.05, 0.0)


def finish_level():
    g.unlocked = max(g.unlocked, min(MAX_LEVEL, g.level + 1))
    write_save(g.unlocked)
    g.win_t = 0.0
    set_state("levelwin")
    play("win", 0.9)
    set_loop_volumes(0.2, 0.0)


def update(dt):
    keys = pygame.key.get_pressed()
    try:
        rel = pygame.mouse.get_rel()
    except Exception:
        rel = (0, 0)
    g.t += dt
    g.flash = max(0.0, g.flash - dt)
    g.shake_t = max(0.0, g.shake_t - dt)

    if g.state == "card":
        g.card_t += dt
        if g.card_t > 3.0:
            set_state("play")
        return
    if g.state == "dead":
        g.dead_t += dt
        return
    if g.state == "levelwin":
        g.win_t += dt
        if g.win_t > 4.0:
            if g.level >= MAX_LEVEL:
                set_state("ending")
            else:
                start_level(g.level + 1)
        return
    if g.state != "play":
        return

    p = g.p
    g.elapsed += dt
    g.pulse_t = max(0.0, g.pulse_t - dt)
    g.blackout_t = max(0.0, g.blackout_t - dt)
    g.pa += rel[0] * MOUSE_SENS + (keys[pygame.K_RIGHT] - keys[pygame.K_LEFT]) * TURN_SPEED * dt

    # movement and stamina
    fwd = keys[pygame.K_w] - keys[pygame.K_s]
    strafe = keys[pygame.K_d] - keys[pygame.K_a]
    vx = math.cos(g.pa) * fwd - math.sin(g.pa) * strafe
    vy = math.sin(g.pa) * fwd + math.cos(g.pa) * strafe
    n = math.hypot(vx, vy)
    g.moving = n > 0
    want_sprint = (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]) and g.moving
    if g.tired and g.stamina >= 25:
        g.tired = False
    g.sprinting = bool(want_sprint) and g.stamina > 0 and not g.tired
    if g.sprinting:
        g.stamina = max(0.0, g.stamina - 38 * dt)
        if g.stamina <= 0:
            g.tired = True
    else:
        g.stamina = min(100.0, g.stamina + 18 * dt)
    if g.moving:
        sp = SPRINT_SPEED if g.sprinting else PLAYER_SPEED
        try_move(vx / n * sp * dt, vy / n * sp * dt)
        g.walk += dt * (1.4 if g.sprinting else 1.0)
        g.step_t -= dt
        if g.step_t <= 0:
            play("step0" if int(g.walk * 3) % 2 else "step1", 0.55 if g.sprinting else 0.3)
            g.step_t = 0.3 if g.sprinting else 0.45
    mark_explored()

    # flashlight
    was_on = g.light_on
    wants = pygame.mouse.get_pressed()[0] or keys[pygame.K_SPACE]
    if g.locked and g.battery >= 15:
        g.locked = False
    g.light_on = bool(wants) and g.battery > 0 and not g.locked and g.blackout_t <= 0
    if g.light_on:
        g.battery = max(0.0, g.battery - p["drain"] * (1.35 if g.focus else 1.0) * dt)
        if g.battery <= 0:
            g.locked = True
            g.light_on = False
            g.message = "BATTERY DEAD. THE DARK IS LISTENING."
    else:
        g.battery = min(100.0, g.battery + p["recharge"] * dt)
    if g.light_on != was_on:
        play("click", 0.5)

    # cores
    for c in g.cores[:]:
        if math.dist((g.px, g.py), c) < 0.6:
            g.cores.remove(c)
            g.taken += 1
            play("core", 0.8)
            g.message = ("ALL CORES SECURED. FIND THE EXIT."
                         if g.taken == p["cores"] else f"CORE SECURED ({g.taken}/{p['cores']}).")

    # path map
    g.map_t += dt
    if g.map_t >= 0.2:
        g.map_t = 0.0
        g.dist_map = bfs((int(g.px), int(g.py)))

    # amplitude amplification (hold G)
    holding = keys[pygame.K_g]
    if holding and not g.grover and g.battery > 10 and not g.locked:
        grover_start()
    if g.grover:
        g.gacc += dt
        g.gtime += dt
        g.battery = max(0.0, g.battery - 12.0 * dt)
        while g.gacc >= 0.18:      # one Grover iteration every 0.18 s so you can time the release
            g.gacc -= 0.18
            grover_iterate()
        if not holding or g.battery <= 0 or g.gtime > 4.0:
            grover_end()

    # the observer effect, per monster (wavefunction measurement / evolution)
    pc = (int(g.px), int(g.py))
    for m in g.mons:
        if "amp" in m:
            m["observed"] = False
            m["moving"] = False
            qstats(m)
            continue
        m["observed"] = qmeasure(m, dt)
        if m["observed"]:
            if not m["seen"]:
                m["seen"] = True
                play("sting", 0.9, rel_pan(m["x"], m["y"]))
                g.flash = 0.18
            m["unobs"] = 0.0
            m["moving"] = False
        else:
            m["unobs"] += dt
            if m["unobs"] > 8:
                m["seen"] = False
            qevolve(m, dt)
            m["moving"] = True
            m["step_t"] -= dt
            if m["step_t"] <= 0:
                d = math.hypot(m["ex"] - g.px, m["ey"] - g.py)
                play("mstep", max(0.0, 1 - d / 14) ** 1.4 * 0.9, rel_pan(m["ex"], m["ey"]))
                m["step_t"] = 0.5
        qstats(m)
        if m["collapsed"]:
            hit = math.dist((g.px, g.py), (m["x"], m["y"])) < 0.6
        else:
            hit = random.random() < min(1.0, m["psi"].get(pc, 0.0) * dt * 6)
            if hit:
                m["x"], m["y"] = g.px + math.cos(g.pa) * 0.4, g.py + math.sin(g.pa) * 0.4
        if hit:
            caught_by(m)
            return

    # decoy eyes: vanish if lit
    if g.decoy:
        g.decoy["t"] -= dt
        dxx, dyy = g.decoy["x"] - g.px, g.decoy["y"] - g.py
        rl = (math.atan2(dyy, dxx) - g.pa + math.pi) % (2 * math.pi) - math.pi
        if g.decoy["t"] <= 0 or (g.light_on and abs(rl) < g.lh):
            g.decoy = None

    # scare events
    g.event_t -= dt
    if g.event_t <= 0:
        trigger_event()
        schedule_event()

    # ambience reacts to danger
    pres = presence()
    set_loop_volumes(0.35, pres ** 1.5 * 0.7 if pres > 0.2 else 0.0)
    g.hb_t -= dt
    if pres > 0.12 and g.hb_t <= 0:
        play("heart", 0.25 + 0.75 * pres)
        g.hb_t = 1.1 - 0.65 * pres

    # exit
    if g.taken >= p["cores"] and math.dist((g.px, g.py), EXIT_POS) < 0.9:
        g.message = "YOU ESCAPED THE OBSERVED REALITY."
        finish_level()


# ================================================================= RENDERING
def project(wx, wy):
    dx, dy = wx - g.px, wy - g.py
    dist = math.hypot(dx, dy)
    if dist < 0.15:
        return None
    rel = (math.atan2(dy, dx) - g.pa + math.pi) % (2 * math.pi) - math.pi
    if abs(rel) > FOV / 2 + 0.5:
        return None
    return (rel / FOV + 0.5) * IW, max(0.2, dist * math.cos(rel))


def draw_sprite(img, wx, wy, world_h, zc):
    pr = project(wx, wy)
    if not pr:
        return None
    sx, perp = pr
    lh = IH / perp
    sh = int(world_h * lh)
    if sh < 2:
        return None
    sw = max(1, int(sh * img.get_width() / img.get_height()))
    top = int(g.horizon + (0.5 - zc) * lh - sh / 2)
    x0 = int(sx - sw / 2)
    scaled = pygame.transform.scale(img, (sw, sh))
    for cx in range(max(0, x0), min(IW, x0 + sw)):
        if perp < zbuf[cx]:
            scene.blit(scaled, (cx, top), (cx - x0, 0, 1, sh))
    return x0, top, sw, sh, perp


def draw_eyes_at(sx, perp, eye_y, rad):
    for off in (-1, 1):
        ex = int(sx + off * rad * 2.2)
        if 0 <= ex < IW and perp < zbuf[ex]:
            pygame.draw.circle(scene, (255, 250, 230), (ex, int(eye_y)), max(1, int(rad)))


def render_world():
    g.moving_vis = g.moving and g.state == "play"
    g.horizon = IH / 2 + math.sin(g.t * 1.3) * 0.8 + (math.sin(g.walk * 9) * 1.5 if g.moving_vis else 0)
    horizon = g.horizon
    scene.blit(bg, (0, 0))
    tex_region = g.level // 5

    for x in range(IW):
        ang = g.pa + (x / IW - 0.5) * FOV
        dist, side, mapx, mapy, u = cast(g.px, g.py, ang)
        perp = max(0.05, dist * math.cos(ang - g.pa))
        zbuf[x] = perp
        lh = IH / perp
        y0f = horizon - lh / 2
        ya = max(0, int(y0f))
        yb = min(IH, int(y0f + lh) + 1)
        if yb <= ya:
            continue
        shade = max(0.0, 1 - perp / 12) ** 1.2
        kind = (mapx // 4 + mapy // 4 + tex_region) % 3
        tex = WALL_TEX[kind][side][int(shade * (SHADES - 1))]
        tx = min(TS - 1, int(u * TS))
        r0 = max(0, int((ya - y0f) / lh * TS))
        r1 = min(TS, max(r0 + 1, int(math.ceil((yb - y0f) / lh * TS))))
        strip = tex.subsurface((tx, r0, 1, r1 - r0))
        scene.blit(pygame.transform.scale(strip, (1, yb - ya)), (x, ya))

    # monsters, far to near
    rects = {}
    order = sorted([m for m in g.mons if m["collapsed"]], key=lambda m: -math.hypot(m["x"] - g.px, m["y"] - g.py))
    for m in order:
        rects[id(m)] = draw_sprite(MON_FRAMES[int(g.t * 8) % 2], m["x"], m["y"], 1.1 if USE_PHOTO_MONSTER else 0.95, 0.5 if USE_PHOTO_MONSTER else 0.475)

    pres = presence() if g.mons else 0.0
    lit = g.light_on or g.state == "dead"
    if g.light_on and g.battery < 20 and random.random() < 0.15:
        lit = False
    if g.state == "play" and random.random() < pres * 0.05:
        lit = False
    if g.blackout_t > 0:
        lit = False
    mask = (MASK_NARROW if g.focus else MASK_LIT) if lit else (MASK_BLACK if g.blackout_t > 0 else MASK_DIM)
    scene.blit(mask, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    for c in g.cores:
        draw_sprite(CORE_IMG, c[0], c[1], 0.22, 0.5 + 0.04 * math.sin(g.t * 3))
    draw_sprite(EXIT_OPEN if g.taken >= g.p["cores"] else EXIT_LOCKED, EXIT_POS[0], EXIT_POS[1], 0.9, 0.45)

    for m in g.mons:
        r = rects.get(id(m))
        if r and not USE_PHOTO_MONSTER and not m["observed"] and los(g.px, g.py, m["x"], m["y"]) \
                and math.hypot(m["x"] - g.px, m["y"] - g.py) < 14:
            x0, top, sw, sh, perp = r
            ey = top + sh * 0.131
            rad = max(1, sh * 0.02)
            draw_eyes_at(x0 + sw * 0.5, perp, ey, rad)

    for m in g.mons:
        if m["collapsed"] or not m["psi"]:
            continue
        keys = list(m["psi"].keys())
        for c in random.choices(keys, [m["psi"][k] for k in keys], k=2):
            if random.random() > min(1.0, m["psi"][c] * 6):
                continue
            cx, cy = c[0] + 0.5, c[1] + 0.5
            if math.hypot(cx - g.px, cy - g.py) > 14 or not los(g.px, g.py, cx, cy):
                continue
            pr = project(cx, cy)
            if pr:
                sx, perp = pr
                lh_ = IH / perp
                draw_eyes_at(sx, perp, g.horizon + (0.5 - 0.78) * lh_, max(1, 0.02 * lh_ * 0.95))

    if g.decoy:
        pr = project(g.decoy["x"], g.decoy["y"])
        if pr:
            sx, perp = pr
            lh = IH / perp
            draw_eyes_at(sx, perp, g.horizon + (0.5 - 0.78) * lh, max(1, 0.02 * lh * 0.95))

    scene.blit(GRAIN_SCENE[int(g.t * 24) % 6], (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    shake = int(pres * 5) + int(g.shake_t * 14)
    if g.state not in ("play", "card"):
        shake = 0
    ox = random.randint(-shake, shake) if shake else 0
    oy = random.randint(-shake, shake) if shake else 0
    pygame.transform.scale(scene, (WIDTH, HEIGHT), frame)

    if g.state == "play" and (pres > 0.55 or g.shake_t > 0) and random.random() < 0.25:
        y = random.randint(0, HEIGHT - 60)
        h = random.randint(8, 50)
        sl = frame.subsurface((0, y, WIDTH, h)).copy()
        frame.blit(sl, (random.randint(-30, 30), y))

    screen.fill((0, 0, 0))
    screen.blit(frame, (ox, oy))
    if g.flash > 0:
        ov = pygame.Surface((WIDTH, HEIGHT))
        ov.fill((255, 255, 255))
        ov.set_alpha(int(255 * min(1.0, g.flash / 0.18)))
        screen.blit(ov, (0, 0))
    return pres


def bar(x, y, w, h, frac, color):
    pygame.draw.rect(screen, (45, 45, 58), (x, y, w, h))
    pygame.draw.rect(screen, color, (x, y, int(w * max(0, min(1, frac))), h))
    pygame.draw.rect(screen, GRAY, (x, y, w, h), 1)


def draw_hud(pres):
    pygame.draw.circle(screen, (200, 200, 200), (WIDTH // 2, HEIGHT // 2), 2)
    screen.blit(SMALL.render(f"LEVEL {g.level}/{MAX_LEVEL}: {LEVEL_NAMES[g.level - 1].upper()}", True, WHITE), (20, 14))
    screen.blit(SMALL.render("BATTERY", True, WHITE), (20, 40))
    bar(120, 42, 200, 14, g.battery / 100, GOLD if not g.locked else RED)
    screen.blit(SMALL.render("STAMINA", True, WHITE), (20, 62))
    bar(120, 64, 200, 14, g.stamina / 100, BLUE if not g.tired else RED)
    screen.blit(SMALL.render("PRESENCE", True, WHITE), (20, 84))
    bar(120, 86, 200, 14, pres, RED)
    screen.blit(SMALL.render(f"CORES {g.taken}/{g.p['cores']}", True, GOLD), (20, 106))
    screen.blit(SMALL.render(f"TIME {g.elapsed:5.1f}s", True, GRAY), (170, 106))

    obs = sum(1 for m in g.mons if m["observed"])
    tot = len(g.mons)
    if obs == tot:
        state, scol = "OBSERVED: ALL FROZEN", GREEN
    elif obs > 0:
        state, scol = f"OBSERVED: {obs}/{tot} FROZEN", GOLD
    else:
        state, scol = f"UNOBSERVED: {tot} MOVING" if tot > 1 else "UNOBSERVED: SUPERPOSED, MOVING", RED
    screen.blit(SMALL.render(state, True, scol), (20, 130))
    spread = sum(len(m["psi"]) for m in g.mons if not m["collapsed"])
    screen.blit(SMALL.render(f"BEAM: {'NARROW' if g.focus else 'WIDE'} (Q)   psi spread: {spread} cells",
                             True, BLUE), (20, 152))
    if any(m["ent"] is not None for m in g.mons):
        screen.blit(SMALL.render("ENTANGLED PAIR: watch one, the other jumps to its mirror point", True, BLUE), (20, 174))
    if g.grover:
        screen.blit(SMALL.render(f"AMPLIFYING  P(in beam) {g.gP * 100:3.0f}%   peak {g.gpeak * 100:3.0f}%", True, GOLD), (20, 196))
        bar(20, 218, 300, 12, g.gP, GOLD)
        pygame.draw.rect(screen, WHITE, (20 + int(300 * g.gpeak) - 1, 214, 3, 20))
        screen.blit(TINY.render("release G at the top: past the peak the probability rotates back out", True, GRAY), (20, 236))
    else:
        screen.blit(TINY.render("hold G: amplitude amplification (aim first, best after a pulse)", True, GRAY), (20, 196))

    cs = g.cs
    mx0, my0 = WIDTH - MW * cs - 20, 16
    pygame.draw.rect(screen, (10, 10, 14), (mx0 - 3, my0 - 3, MW * cs + 6, MH * cs + 6))
    screen.blit(g.mini, (mx0, my0))
    heat = pygame.Surface((MW * cs, MH * cs), pygame.SRCALPHA)
    for (hx, hy) in g.gmark:
        pygame.draw.rect(heat, (90, 150, 255, 90), (hx * cs, hy * cs, cs, cs))
    for m in g.mons:
        if m["collapsed"]:
            pygame.draw.circle(heat, (255, 70, 70, 255), (int(m["x"] * cs), int(m["y"] * cs)), max(2, cs // 2 + 1))
        else:
            pm = max(m["psi"].values())
            for (hx, hy), pr_ in m["psi"].items():
                a_ = int(40 + 215 * min(1.0, pr_ / pm) ** 0.6)
                pygame.draw.rect(heat, (215, 55, 55, a_), (hx * cs, hy * cs, cs, cs))
    screen.blit(heat, (mx0, my0))
    for c in g.cores:
        if g.explored[int(c[1])][int(c[0])]:
            pygame.draw.circle(screen, GOLD, (mx0 + int(c[0] * cs), my0 + int(c[1] * cs)), max(2, cs // 2))
    if g.explored[EXIT_CELL[1]][EXIT_CELL[0]]:
        pygame.draw.rect(screen, GREEN if g.taken >= g.p["cores"] else GRAY,
                         (mx0 + EXIT_CELL[0] * cs, my0 + EXIT_CELL[1] * cs, cs, cs), 2)
    pp = (mx0 + g.px * cs, my0 + g.py * cs)
    pygame.draw.circle(screen, WHITE, pp, max(2, cs // 2))
    pygame.draw.line(screen, WHITE, pp, (pp[0] + math.cos(g.pa) * cs * 1.5, pp[1] + math.sin(g.pa) * cs * 1.5), 2)

    m = FONT.render(g.message, True, WHITE)
    screen.blit(m, (WIDTH // 2 - m.get_width() // 2, HEIGHT - 70))
    c = SMALL.render("WASD move  SHIFT sprint  MOUSE look  hold LMB/SPACE light  Q focus  G amplify  E pulse  R restart  ESC menu",
                     True, GRAY)
    screen.blit(c, (WIDTH // 2 - c.get_width() // 2, HEIGHT - 32))


# ================================================================= JUMP SCARE
_cr = random.Random(11)
CRACKS = []
for _ in range(16):
    _x, _y = _cr.uniform(-230, 230), _cr.uniform(-300, 120)
    _pts = [(_x, _y)]
    for _k in range(3):
        _x += _cr.uniform(-30, 30)
        _y += _cr.uniform(10, 40)
        _pts.append((_x, _y))
    CRACKS.append(_pts)


def draw_scare_face(surf, T):
    u = 0.85 + min(T, 2.6) * 0.11
    shake = max(3.0, 18 - T * 7)
    cx = WIDTH / 2 + random.uniform(-shake, shake)
    cy = HEIGHT / 2 + 30 + random.uniform(-shake, shake)

    def P(dx, dy):
        return (cx + dx * u, cy + dy * u)

    def E(dx, dy, w, h):
        return pygame.Rect(cx + (dx - w / 2) * u, cy + (dy - h / 2) * u, w * u, h * u)

    jaw = 0.5 + 0.5 * math.sin(T * 15)
    mh = 170 + 80 * jaw

    pygame.draw.polygon(surf, (62, 64, 68), [P(-460, 420), P(-170, 240), P(170, 240), P(460, 420)])
    pygame.draw.polygon(surf, (112, 116, 118), [P(-120, 180), P(120, 180), P(160, 300), P(-160, 300)])
    for sx in (-1, 1):
        pygame.draw.line(surf, (80, 84, 86), P(sx * 60, 200), P(sx * 80, 300), max(2, int(5 * u)))
    pygame.draw.ellipse(surf, (52, 54, 58), E(0, -30, 640, 800))
    pygame.draw.ellipse(surf, (110, 114, 118), E(0, -30, 600, 760))
    pygame.draw.ellipse(surf, (170, 174, 176), E(0, -40, 540, 700))
    pygame.draw.ellipse(surf, (192, 195, 196), E(0, -90, 420, 500))
    for pts in CRACKS:
        pygame.draw.lines(surf, (118, 122, 124), False, [P(*p) for p in pts], 2)

    for sx in (-1, 1):
        ex = sx * 125
        pygame.draw.ellipse(surf, (34, 24, 28), E(ex, -70, 175, 125))
        pygame.draw.ellipse(surf, (238, 228, 198), E(ex, -70, 128, 84))
        for k in range(10):
            ang = k * 0.63 + sx
            pygame.draw.line(surf, (190, 40, 40),
                             P(ex + math.cos(ang) * 60, -70 + math.sin(ang) * 38),
                             P(ex + math.cos(ang) * 22, -70 + math.sin(ang) * 14), 2)
        pygame.draw.circle(surf, (14, 8, 8), P(ex + sx * 4, -70), max(2, int(11 * u)))
        pygame.draw.circle(surf, (255, 255, 255), P(ex + sx * 4 - 3, -73), max(1, int(3 * u)))
        pygame.draw.arc(surf, (30, 20, 22), E(ex, -84, 150, 80), 0.2, 2.9, 5)

    pygame.draw.line(surf, (128, 132, 134), P(-14, -30), P(-24, 50), max(2, int(4 * u)))
    pygame.draw.line(surf, (128, 132, 134), P(14, -30), P(24, 50), max(2, int(4 * u)))
    for sx in (-1, 1):
        pygame.draw.ellipse(surf, (40, 30, 32), E(sx * 24, 62, 22, 30))

    my = 190
    mw = 300
    pygame.draw.ellipse(surf, (64, 8, 10), E(0, my, mw + 40, mh + 30))
    pygame.draw.ellipse(surf, (16, 0, 2), E(0, my, mw, mh))
    pygame.draw.ellipse(surf, (150, 44, 52), E(0, my + mh * 0.25, mw * 0.6, mh * 0.45))
    for k in range(9):
        tx = -mw / 2 * 0.85 + k * (mw * 0.85 / 8)
        edge = (mh / 2) * math.sqrt(max(0.0, 1 - (tx / (mw / 2)) ** 2))
        by = my - edge + 2
        pygame.draw.polygon(surf, (228, 224, 206), [P(tx - 14, by), P(tx + 14, by), P(tx, by + 44 + (k % 2) * 14)])
    for k in range(8):
        tx = -mw / 2 * 0.8 + k * (mw * 0.8 / 7)
        edge = (mh / 2) * math.sqrt(max(0.0, 1 - (tx / (mw / 2)) ** 2))
        by = my + edge - 2
        pygame.draw.polygon(surf, (222, 218, 200), [P(tx - 12, by), P(tx + 12, by), P(tx, by - 36 - (k % 2) * 12)])
    for sx in (-1, 1):
        pygame.draw.line(surf, (112, 16, 18), P(sx * 150, my + 10), P(sx * 166, my + mh / 2 + 150), max(3, int(9 * u)))
    pygame.draw.ellipse(surf, (112, 16, 18), E(0, my + mh / 2 + 40, 120, 80))

    for sx in (-1, 1):
        arm = [P(sx * 560, 460), P(sx * 470, 240), P(sx * 400 + random.uniform(-4, 4), 40)]
        pygame.draw.lines(surf, (128, 132, 134), False, arm, max(4, int(34 * u)))
        for pt in arm:
            pygame.draw.circle(surf, (128, 132, 134), pt, max(2, int(17 * u)))
        hand = arm[-1]
        for a in (-125, -105, -85, -65, -45):
            ang = math.radians(a if sx < 0 else 180 - a)
            mid = (hand[0] + math.cos(ang) * 70 * u, hand[1] + math.sin(ang) * 70 * u)
            ang2 = ang + (0.5 if sx < 0 else -0.5)
            end = (mid[0] + math.cos(ang2) * 55 * u, mid[1] + math.sin(ang2) * 55 * u)
            pygame.draw.line(surf, (176, 180, 176), hand, mid, max(2, int(10 * u)))
            pygame.draw.line(surf, (228, 224, 208), mid, end, max(2, int(7 * u)))


def render_dead():
    T = g.dead_t
    if T < 0.10:
        render_world()
        return
    screen.fill((10, 0, 0))
    # white then black cut, then the face
    if T < 0.16:
        screen.fill((255, 255, 255) if int(T * 100) % 2 == 0 else (0, 0, 0))
        return
    t2 = T - 0.16
    if ENTITY_IMG is not None:
        draw_entity_photo(screen, t2)
    else:
        draw_scare_face(screen, t2)
    screen.blit(VIGNETTE, (0, 0))
    screen.blit(GRAIN_SCREEN[int(g.t * 24) % 6], (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    screen.blit(GRAIN_SCREEN[int(g.t * 24 + 3) % 6], (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    if random.random() < 0.3:
        ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        ov.fill((200, 0, 0, random.randint(20, 90)))
        screen.blit(ov, (0, 0))
    if t2 > 2.2:
        ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 0, 0, min(150, int((t2 - 2.2) * 200))))
        screen.blit(ov, (0, 0))
        t = BIG.render("YOU WERE OBSERVED.", True, RED)
        screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 250))
        t = FONT.render("Press ENTER to try again   ESC for menu", True, WHITE)
        screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 330))


# ================================================================= SCREENS
def render_title():
    screen.fill((4, 4, 6))
    pulse_a = 0.5 + 0.5 * math.sin(g.t * 2)
    for ex in (WIDTH // 2 - 70, WIDTH // 2 + 70):
        pygame.draw.circle(screen, (int(40 + 150 * pulse_a), 10, 10), (ex, 190), 34)
        pygame.draw.circle(screen, (235, 225, 195), (ex, 190), 14)
        pygame.draw.circle(screen, (10, 6, 6), (ex, 190), 5)
    t = HUGE.render("THE OBSERVER", True, WHITE)
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 250))
    t = FONT.render("it moves when you don't look", True, GRAY)
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 350))
    t = FONT.render(f"<  LEVEL {g.sel}: {LEVEL_NAMES[g.sel - 1].upper()}  >", True, GOLD)
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 430))
    t = SMALL.render(f"unlocked {g.unlocked}/{MAX_LEVEL}   LEFT/RIGHT choose level", True, GRAY)
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 465))
    t = FONT.render("ENTER to begin", True, WHITE if int(g.t * 2) % 2 == 0 else GRAY)
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 520))
    ok_img = "OK" if ENTITY_IMG is not None else "NOT FOUND"
    ok_snd = "OK" if getattr(g, "scream_ok", False) else "NOT FOUND"
    t = SMALL.render(f"entity.jpg: {ok_img}    scream.mp3: {ok_snd}", True, GREEN if ok_img == ok_snd == "OK" else RED)
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 580))
    t = TINY.render("build 4 | image: " + IMG_STATUS[:100], True, GRAY)
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 600))
    t = SMALL.render("Wear headphones. Hold LMB/SPACE to shine your light on it. Unwatched, it moves.", True, GRAY)
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 620))
    screen.blit(GRAIN_SCREEN[int(g.t * 24) % 6], (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def render_card():
    screen.fill((0, 0, 0))
    t = HUGE.render(f"LEVEL {g.level}", True, WHITE)
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 220))
    t = BIG.render(LEVEL_NAMES[g.level - 1].upper(), True, RED)
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 330))
    n = len(g.mons)
    t = FONT.render(f"Collect {g.p['cores']} cores.   {n} {'entity' if n == 1 else 'entities'} loose.", True, GRAY)
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 420))
    t = SMALL.render("QUANTUM RULES: superposition  collapse  tunnelling  entanglement  uncertainty (Q)  amplification (G)", True, BLUE)
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 480))
    screen.blit(GRAIN_SCREEN[int(g.t * 24) % 6], (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def render_levelwin():
    pres = render_world()
    ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    ov.fill((0, 80, 40, 90))
    screen.blit(ov, (0, 0))
    final = g.level >= MAX_LEVEL
    t = BIG.render("FINAL LEVEL COMPLETE." if final else "LEVEL COMPLETE.", True, GREEN)
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 250))
    t = FONT.render(f"Escaped in {g.elapsed:.1f}s", True, WHITE)
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 320))


def render_ending():
    screen.fill((0, 0, 0))
    t = BIG.render("YOU ESCAPED THE OBSERVER.", True, GREEN)
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 230))
    t = FONT.render(f"All {MAX_LEVEL} levels cleared. Times caught: {g.deaths}", True, WHITE)
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 320))
    t = SMALL.render("Press ENTER for the menu", True, GRAY)
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, 400))
    screen.blit(GRAIN_SCREEN[int(g.t * 24) % 6], (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def render():
    s = g.state
    if s == "title":
        render_title()
    elif s == "card":
        render_card()
    elif s == "play":
        pres = render_world()
        draw_hud(pres)
    elif s == "dead":
        render_dead()
    elif s == "levelwin":
        render_levelwin()
    elif s == "ending":
        render_ending()


def to_title():
    g.sel = min(g.unlocked, max(1, g.level))
    set_state("title")
    set_loop_volumes(0.25, 0.0)


async def main():
    screen.fill((0, 0, 0))
    screen.blit(FONT.render("LOADING...", True, WHITE), (WIDTH // 2 - 60, HEIGHT // 2))
    pygame.display.flip()
    await asyncio.sleep(0)
    load_sounds()
    g.unlocked = load_save()
    g.sel = g.unlocked
    start_loops()
    set_loop_volumes(0.25, 0.0)
    set_state("title")
    running = True
    while running:
        dt = min(clock.tick(60) / 1000, 0.05)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type != pygame.KEYDOWN:
                continue
            k = event.key
            s = g.state
            if s == "title":
                if k == pygame.K_ESCAPE:
                    running = False
                elif k in (pygame.K_LEFT, pygame.K_a, pygame.K_DOWN):
                    g.sel = max(1, g.sel - 1)
                elif k in (pygame.K_RIGHT, pygame.K_d, pygame.K_UP):
                    g.sel = min(g.unlocked, g.sel + 1)
                elif k in (pygame.K_RETURN, pygame.K_SPACE):
                    start_level(g.sel)
            elif s == "card":
                if k == pygame.K_ESCAPE:
                    to_title()
                elif k in (pygame.K_RETURN, pygame.K_SPACE):
                    set_state("play")
            elif s == "play":
                if k == pygame.K_ESCAPE:
                    to_title()
                elif k == pygame.K_r:
                    start_level(g.level)
                elif k == pygame.K_e:
                    pulse()
                elif k == pygame.K_q:
                    g.focus = not g.focus
                    apply_focus()
                    g.message = "NARROW BEAM: SHARP AIM, LONG REACH, SMALL FIELD." if g.focus else "WIDE BEAM: BROAD FIELD, SHORT REACH."
                    play("click", 0.5)
            elif s == "dead":
                if k == pygame.K_ESCAPE:
                    to_title()
                elif k in (pygame.K_RETURN, pygame.K_r) and g.dead_t > 2.4:
                    start_level(g.level)
            elif s == "levelwin":
                if k in (pygame.K_RETURN, pygame.K_SPACE):
                    g.win_t = 4.1
            elif s == "ending":
                if k in (pygame.K_RETURN, pygame.K_ESCAPE):
                    g.unlocked = MAX_LEVEL
                    to_title()
        update(dt)
        render()
        pygame.display.flip()
        await asyncio.sleep(0)          # lets the browser breathe every frame (required by pygbag)
    pygame.quit()


asyncio.run(main())
