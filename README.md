# THE OBSERVER

A 3D horror game where the monster has no position until you look at it. It moves when you don't look.

**Play in your browser: https://chidvi1in-beep.itch.io/the-observer**

Wear headphones. Click inside the game, then press Enter to begin.

## Controls

WASD move, SHIFT sprint, MOUSE look (or arrow keys), hold LMB/SPACE for flashlight, Q beam focus, hold G amplitude amplification, E interference pulse, R restart level, ESC back/quit.

## Run locally

```
pip install pygame
python main.py
```

## Build for the browser (pygbag)

Run from the folder that contains this one (the folder must contain main.py):

```
pip install pygbag
pygbag the-observer          # test at http://localhost:8000
pygbag --build the-observer  # makes build/web.zip for itch.io
```

---

THE OBSERVER - browser build (pygbag)

MAIN

I added amplitude amplification (Grover search) to observer.py. It's the sixth quantum rule, on the G key. I couldn't run the game window here, but I tested the algorithm on its own and it behaves like the textbook version.

1. pip install pygbag
2. From the folder that CONTAINS this folder (the parent), run:
      pygbag observer_web
   Open http://localhost:8000 and click to start. Test it works here first.
3. To publish: run   pygbag --build observer_web
   Upload  observer_web/build/web.zip  to itch.io (Kind of project: HTML,
   tick "played in the browser") and set the page to Public. Share that link.
4. Main idea: when you're not looking, the monster isn't hiding somewhere. It has no position at all. The game tracks a "probability 	cloud": how likely it is to be in each spot. Your flashlight is what forces it to pick a spot.

	Superposition: the monster is a fuzzy cloud, not one spot. The cloud drifts toward you and spreads out the longer you don't look. 	The red glow on the minimap is this cloud.
	Collapse (observer effect): your light "checks" the area it covers.
	If the monster is there, the cloud collapses to one spot and it freezes.
	If it's not there, that area is crossed off and the cloud shifts elsewhere.
	When you look away, it turns back into a cloud.
	Tunnelling: some of the cloud can leak through thin walls, so the monster sometimes takes shortcuts.
	Entanglement (level 15+): monsters come in linked pairs. When you see one, the other jumps to the mirror spot on the map.
	Uncertainty (Q key): you can't have everything at once.
	Narrow beam: long reach, tiny area, uses more battery.
	Wide beam: big area, short reach.
	Pulse (E) spreads the cloud across the whole map. Getting caught is a chance: the more of the cloud sitting on your spot, the more 	likely it gets you, even if you can't see it.

	In one line: keep checking, because the monster only becomes solid when you look.