# -*- coding: utf-8 -*-
"""humanize.py -- anti-bot humanize helpers (§28, FDE Plan 4, Task 2). Three PURE, DETERMINISTIC
functions (no `random`, no live browser/network I/O -- they are called by the Playwright flow of
the `/dapphunt` skill, Task 9-10, which takes the OUTPUT of these functions as a sequence of
`mouse.move`/`keyboard.press`/`mouse.wheel` actions rather than executing them itself here). Determinism is a
deliberate brief requirement: control points/patterns are derived from the input (start/end/steps/text/index),
not from `random`, so behavior is reproducible and testable (`runtime_harness_replay.py`).

    bezier_path(start, end, steps=30) -> list[tuple]
    typo_type(text) -> list[dict]
    overshoot_scroll(target_y) -> list[int]
"""

import math


# ---------------------------------------------------------------------------
# bezier_path -- cubic Bezier, index-derived control points (§28)
# ---------------------------------------------------------------------------

def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def bezier_path(start, end, steps=30):
    """Cubic Bezier trajectory `start -> end` made of `steps` points (human mouse movement --
    not a straight line). Control points P1/P2 are DERIVED from `start`/`end`/`steps` (path fraction 0.25/0.75 +
    perpendicular offset, amplitude = `min(path_length, steps) / 6`) -- NOT `random`, determinism
    is guaranteed (same input -> same output).

    Guarantees (brief contract, enforced -- not just "usually the case"):
      - `len(result) == steps` (steps<=0 -> `[]`; steps==1 -> `[end]`).
      - the last point == `end` EXACTLY (a cubic Bezier at t=1 gives `end` by construction; see
        `out[-1] = (ex, ey)` -- explicit, guards against float noise).
      - distance to `end` is MONOTONICALLY NON-INCREASING by index: the raw Bezier points are computed
        normally (they may temporarily move farther from `end` due to perpendicular curvature -- that is
        the "humanness"), then every point whose distance to `end` EXCEEDS the distance of the
        previous (already accepted) point is SHRUNK along the point->`end` line down to the previous
        point's distance (see the loop below) -- this guarantees the property CONSTRUCTIVELY, not just "it
        usually works out for reasonable inputs".

    Non-numeric/broken input -> `steps` is coerced to `int` (failure -> defaults to 30); `start`/`end`
    are expected as `(x, y)` tuples of numbers (the brief contract does not require fail-open here -- the Playwright
    flow always passes valid coordinates)."""
    try:
        steps = int(steps)
    except Exception:
        steps = 30
    if steps <= 0:
        return []

    sx, sy = start
    ex, ey = end
    if steps == 1:
        return [(ex, ey)]

    dx, dy = ex - sx, ey - sy
    length = math.hypot(dx, dy)
    if length > 0:
        perp_x, perp_y = -dy / length, dx / length
    else:
        perp_x, perp_y = 0.0, 0.0

    amp = min(length, steps) / 6.0
    p1 = (sx + dx * 0.25 + perp_x * amp, sy + dy * 0.25 + perp_y * amp)
    p2 = (ex - dx * 0.25 - perp_x * amp * 0.5, ey - dy * 0.25 - perp_y * amp * 0.5)

    raw = []
    for i in range(steps):
        t = i / (steps - 1)
        mt = 1.0 - t
        x = (mt ** 3) * sx + 3 * (mt ** 2) * t * p1[0] + 3 * mt * (t ** 2) * p2[0] + (t ** 3) * ex
        y = (mt ** 3) * sy + 3 * (mt ** 2) * t * p1[1] + 3 * mt * (t ** 2) * p2[1] + (t ** 3) * ey
        raw.append((x, y))

    # Cap-pass: enforce monotonic non-increasing distance-to-end (see docstring). Deterministic,
    # no randomness introduced -- pure geometric projection toward `end` along point-to-end line.
    out = [raw[0]]
    prev_dist = _dist(raw[0], (ex, ey))
    for p in raw[1:]:
        d = _dist(p, (ex, ey))
        if d > prev_dist:
            if d == 0:
                p = (ex, ey)
            else:
                scale = prev_dist / d
                p = (ex + (p[0] - ex) * scale, ey + (p[1] - ey) * scale)
            d = prev_dist
        out.append(p)
        prev_dist = d
    out[-1] = (ex, ey)
    return out


# ---------------------------------------------------------------------------
# typo_type -- keystroke actions with rare deterministic backspace corrections (§28)
# ---------------------------------------------------------------------------

# Every Nth character (index>0, index % N == 0) -- a deterministic "typo": the QWERTY-neighbor
# key BEFORE the correct character, then Backspace. N is not given verbatim by the brief -- implementer's choice:
# 7 is rare enough to not bloat typical short test input fields into unreadability, and
# frequent enough to actually fire on strings from the brief's test fixtures.
_TYPO_EVERY_N = 7

_NEIGHBOR = {
    "a": "s", "s": "a", "e": "r", "r": "e", "i": "o", "o": "i",
    "n": "m", "m": "n", "t": "y", "y": "t", "l": "k", "k": "l",
    "d": "f", "f": "d", "u": "y", "h": "g", "g": "h", "w": "q",
}


def typo_type(text):
    """`text` -> a list of keystroke actions `[{"key": ..., "action": "type"|"backspace"}, ...]`.
    Every Nth character (`_TYPO_EVERY_N`, index>0, index%N==0) gets a deterministic "typo"
    BEFORE itself: the wrong keyboard-neighbor key (`_NEIGHBOR`, fallback `"x"`/`"z"`) is typed, then
    `Backspace` removes it, then the correct character is typed -- NOT `random` (the same `text` -> the
    same list of actions every time).

    Contract: replaying the actions (append on `"type"`, pop-last on `"backspace"`, ignoring an empty
    buffer) -> the resulting buffer == `text` EXACTLY (backspace removes exactly the typo, never touches
    an already-confirmed previous character). A non-string is coerced via `str()`; a full failure -> `[]`
    (fail-open)."""
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            return []
    actions = []
    for i, ch in enumerate(text):
        if i > 0 and i % _TYPO_EVERY_N == 0:
            wrong = _NEIGHBOR.get(ch.lower())
            if not wrong or wrong == ch:
                wrong = "x" if ch != "x" else "z"
            actions.append({"key": wrong, "action": "type"})
            actions.append({"key": "Backspace", "action": "backspace"})
        actions.append({"key": ch, "action": "type"})
    return actions


# ---------------------------------------------------------------------------
# overshoot_scroll -- overshoot past target_y + settle back (§28)
# ---------------------------------------------------------------------------

def overshoot_scroll(target_y):
    """`target_y` -> a list of Y positions modeling human scrolling: accelerate to a point PAST
    `target_y` (overshoot, `overshoot_amt` = `max(10, abs(target_y)//8)` in the direction of `target_y`, or
    `15` if `target_y==0`), then settle back TO `target_y`. Deterministic (a pure function of
    `target_y`, no `random`).

    Guarantees: at least one intermediate position STRICTLY past `target_y` in the direction of movement
    (proves the overshoot -- see `peak`), the last position == `target_y` EXACTLY (explicit
    `positions[-1] = target_y`, guards against `round()` noise on the last settle-back step).

    Non-numeric input -> coerced to `int` (failure -> `0`, fail-open)."""
    try:
        target_y = int(target_y)
    except Exception:
        target_y = 0

    direction = 1 if target_y >= 0 else -1
    overshoot_amt = max(10, abs(target_y) // 8) if target_y != 0 else 15
    peak = target_y + direction * overshoot_amt

    steps_up = 5
    steps_back = 3
    positions = []
    for i in range(1, steps_up + 1):
        positions.append(round(peak * i / steps_up))
    for i in range(1, steps_back + 1):
        frac = i / steps_back
        positions.append(round(peak + (target_y - peak) * frac))

    positions[-1] = target_y
    return positions
