"""Drawing helpers for the Streamlit app: network diagram and coloured message log.

Both return a complete HTML page (string) to show with components.html.
"""
import html
import math

# One consistent colour theme used everywhere
STATUS_COLORS = {"Idle": "#9AA5B1", "Waiting": "#F5B921",
                 "Withdrawing": "#2EAD6B", "Crashed": "#D64545"}
STATUS_TEXT = {"Idle": "#1B2430", "Waiting": "#1B2430",
               "Withdrawing": "#FFFFFF", "Crashed": "#FFFFFF"}
MSG_COLORS = {"REQUEST": "#2F6FDE", "REPLY": "#1E9E5A", "DEFERRED": "#E8820C",
              "WITHDRAW": "#7B4FD0", "TOKEN": "#0E9AA7", "CRASHED": "#D64545", "RECOVERY": "#C026D3"}
# Brighter versions for text on a dark background
DARK_MSG_COLORS = {"REQUEST": "#6FA0FF", "REPLY": "#4FD08A", "DEFERRED": "#FFA94D",
                   "WITHDRAW": "#B497F5", "TOKEN": "#4CD3DE", "CRASHED": "#FF7B7B", "RECOVERY": "#E879F9"}
TOKEN_GOLD = "#F2C230"
TOKEN_PATH_COLOR = "#0E9AA7"     # bold token path in the crash diagram

# ATM 1 on top, ATM 2 bottom-left, ATM 3 bottom-right
# Colours that differ between light and dark mode (key = dark?)
THEMES = {
    False: {"bg": "#FFFFFF", "text": "#1B2430", "outline": "#1B2430",
            "halo": "#FFFFFF", "muted": "#5B6675", "border": "#D5DCE6"},
    True: {"bg": "#0E1420", "text": "#E8EDF5", "outline": "#E8EDF5",
           "halo": "#0E1420", "muted": "#9AA7BA", "border": "#2C3A52"},
}

POSITIONS = [(280, 95), (110, 265), (450, 265)]
RADIUS = 54
FONT = "Segoe UI, Arial, sans-serif"


# ------------------------------------------------------------ network diagram
def _curve(frm, to, bend, label_push=0):
    """Quadratic curve between two circles. Returns path and label position.

    The bend is on the same side relative to travel direction, so an arrow
    A->B and an arrow B->A never sit on top of each other.
    """
    ax, ay = POSITIONS[frm]
    bx, by = POSITIONS[to]
    dist = math.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / dist, (by - ay) / dist
    px, py = -uy, ux                                   # perpendicular
    sx, sy = ax + ux * RADIUS, ay + uy * RADIUS        # start on edge of first circle
    ex, ey = bx - ux * (RADIUS + 4), by - uy * (RADIUS + 4)
    cx = (sx + ex) / 2 + px * bend * 2
    cy = (sy + ey) / 2 + py * bend * 2
    lx = 0.25 * sx + 0.5 * cx + 0.25 * ex + px * label_push
    ly = 0.25 * sy + 0.5 * cy + 0.25 * ey + py * label_push
    return f"M{sx:.0f},{sy:.0f} Q{cx:.0f},{cy:.0f} {ex:.0f},{ey:.0f}", lx, ly


def _marker(color):
    mid = "m" + color.strip("#")
    return (f'<marker id="{mid}" markerWidth="16" markerHeight="16" refX="12" refY="7" '
            f'orient="auto" markerUnits="userSpaceOnUse">'
            f'<path d="M0,0 L14,7 L0,14 z" fill="{color}"/></marker>')


def _label(x, y, text, color, size=17, halo="white"):
    # white outline keeps the text readable on top of lines
    return (f'<text x="{x:.0f}" y="{y:.0f}" text-anchor="middle" font-size="{size}" '
            f'font-weight="700" fill="{color}" stroke="{halo}" stroke-width="5" '
            f'paint-order="stroke" font-family="{FONT}">{html.escape(text)}</text>')


def network_svg(names, statuses, notes, arrows=(), ring_edges=False, token=None,
                height=400, dark=False, ring_path=None, skip=None):
    """Draw 3 ATMs as circles.

    statuses: "Idle" / "Waiting" / "Withdrawing" / "Crashed" per ATM
    notes:    short text under each name (e.g. the Lamport clock)
    arrows:   dicts with frm, to, label, color, dashed
    ring_edges: draw the faint ring ATM1 -> ATM2 -> ATM3 -> ATM1 (Token Ring)
    ring_path: ring edges the token really travelled (edge i = ATM i -> next ATM).
              Those are drawn bold, the rest faint and dashed. None = all plain.
    skip:     id of a crashed ATM the repaired ring skips (draws the ring among the others)
    token:    None, {"kind": "at", "node": i}, {"kind": "moving", "frm": i, "to": j}
              or {"kind": "lost", "node": i}
    """
    theme = THEMES[dark]
    colors = {"#B8C1CC", TOKEN_PATH_COLOR} | {a["color"] for a in arrows}
    body = ['<defs>' + "".join(_marker(c) for c in colors) + '</defs>']

    if ring_edges and skip is not None:
        alive = [i for i in range(3) if i != skip]
        for k, i in enumerate(alive):                      # new ring: bold, skipping the dead ATM
            path, _, _ = _curve(i, alive[(k + 1) % len(alive)], 18)
            body.append(f'<path d="{path}" fill="none" stroke="{TOKEN_PATH_COLOR}" '
                        f'stroke-width="8" marker-end="url(#m{TOKEN_PATH_COLOR.strip("#")})"/>')
        for i, j in (((skip - 1) % 3, skip), (skip, (skip + 1) % 3)):    # old edges: faint
            path, _, _ = _curve(i, j, 0)
            body.append(f'<path d="{path}" fill="none" stroke="#B8C1CC" stroke-width="3" '
                        f'stroke-dasharray="8 8" opacity="0.55" marker-end="url(#mB8C1CC)"/>')
    elif ring_edges:
        for i in range(3):
            path, _, _ = _curve(i, (i + 1) % 3, 0)
            if ring_path is None:                          # plain ring
                style = f'stroke="#B8C1CC" stroke-width="4" marker-end="url(#mB8C1CC)"'
            elif i in ring_path:                           # the token really went here
                style = (f'stroke="{TOKEN_PATH_COLOR}" stroke-width="8" '
                         f'marker-end="url(#m{TOKEN_PATH_COLOR.strip("#")})"')
            else:                                          # never used: faint and dashed
                style = (f'stroke="#B8C1CC" stroke-width="3" stroke-dasharray="8 8" '
                         f'opacity="0.55" marker-end="url(#mB8C1CC)"')
            body.append(f'<path d="{path}" fill="none" {style}/>')

    for a in arrows:
        path, lx, ly = _curve(a["frm"], a["to"], 30, label_push=26)
        dash = ' stroke-dasharray="9 7"' if a.get("dashed") else ""
        body.append(f'<path d="{path}" fill="none" stroke="{a["color"]}" stroke-width="4"{dash} '
                    f'marker-end="url(#m{a["color"].strip("#")})"/>')
        body.append(_label(lx, ly, a["label"], a["color"], halo=theme["halo"]))

    for i in range(3):
        x, y = POSITIONS[i]
        status = statuses[i]
        if token and token["kind"] in ("at", "lost") and token["node"] == i:
            ring_color = "#D64545" if token["kind"] == "lost" else TOKEN_GOLD
            body.append(f'<circle cx="{x}" cy="{y}" r="{RADIUS + 9}" fill="none" '
                        f'stroke="{ring_color}" stroke-width="8"/>')
        body.append(f'<circle cx="{x}" cy="{y}" r="{RADIUS}" fill="{STATUS_COLORS[status]}" '
                    f'stroke="{theme["outline"]}" stroke-width="3"/>')
        txt = STATUS_TEXT[status]
        body.append(f'<text x="{x}" y="{y - 6}" text-anchor="middle" font-size="22" '
                    f'font-weight="800" fill="{txt}" font-family="{FONT}">{html.escape(names[i])}</text>')
        body.append(f'<text x="{x}" y="{y + 16}" text-anchor="middle" font-size="15" '
                    f'font-weight="600" fill="{txt}" font-family="{FONT}">{html.escape(status)}</text>')
        if notes[i]:
            note_y = y - RADIUS - 20 if i == 0 else y + RADIUS + 24
            body.append(_label(x, note_y, notes[i], theme["text"], 16, halo=theme["halo"]))

    def badge_spot(i, text):
        """Badge position next to (never on) the circle and its highlight ring."""
        x, y = POSITIONS[i]
        half = (20 + len(text) * 11) / 2
        clear = RADIUS + 9 + 10                      # circle + ring + a small gap
        if i == 0:                                   # top ATM: to its right
            return x + clear + half, y - 10
        return x, y - clear - 15                     # bottom ATMs: above

    if token:
        if token["kind"] == "moving":
            _, lx, ly = _curve(token["frm"], token["to"], 0)
            body.append(_token_badge(lx, ly, "TOKEN"))
        elif token["kind"] == "at":
            bx, by = badge_spot(token["node"], "TOKEN")
            body.append(_token_badge(bx, by, "TOKEN"))
        else:
            bx, by = badge_spot(token["node"], "TOKEN LOST")
            body.append(_token_badge(bx, by, "TOKEN LOST", lost=True))

    # legend
    legend_x = 20
    for status in ("Idle", "Waiting", "Withdrawing", "Crashed"):
        body.append(f'<circle cx="{legend_x}" cy="{height - 22}" r="9" '
                    f'fill="{STATUS_COLORS[status]}" stroke="{theme["outline"]}" stroke-width="2"/>')
        body.append(f'<text x="{legend_x + 15}" y="{height - 16}" font-size="16" '
                    f'fill="{theme["text"]}" font-family="{FONT}">{status}</text>')
        legend_x += 28 + len(status) * 10 + 20

    svg = (f'<svg viewBox="0 0 560 {height}" xmlns="http://www.w3.org/2000/svg" '
           f'style="width:100%;height:auto;max-height:{height + 20}px">' + "".join(body) + '</svg>')
    return (f'<html><body style="margin:0;background:{theme["bg"]}">{svg}</body></html>')


def _token_badge(x, y, text, lost=False):
    width = 20 + len(text) * 11
    stroke = "#D64545" if lost else "#1B2430"
    return (f'<rect x="{x - width / 2:.0f}" y="{y - 15:.0f}" width="{width}" height="30" rx="15" '
            f'fill="{TOKEN_GOLD}" stroke="{stroke}" stroke-width="3"/>'
            f'<text x="{x:.0f}" y="{y + 6:.0f}" text-anchor="middle" font-size="16" '
            f'font-weight="800" fill="{stroke}" font-family="{FONT}">{text}</text>')


def message_arrows(messages, names):
    """Turn Network messages into arrow dicts for network_svg."""
    arrows = []
    for m in messages:
        label = m["type"]
        if m["type"] == "REQUEST":
            label = f"REQUEST (ticket {m['time']})"
        arrows.append({"frm": m["from"], "to": m["to"], "label": label,
                       "color": MSG_COLORS[m["type"]]})
    return arrows


# ------------------------------------------------------------ message log
def classify(line):
    """Pick the colour category of a log line."""
    if "CRASHED" in line or "FAILURE" in line:
        return "CRASHED"
    if "REGENERATED" in line:
        return "RECOVERY"
    if "DEFERRED" in line or "got ACK" in line:
        return "DEFERRED"
    if "WITHDRAW" in line:
        return "WITHDRAW"
    if "REQUEST" in line:
        return "REQUEST"
    if "REPLY" in line:
        return "REPLY"
    if "TOKEN" in line:
        return "TOKEN"
    return None


def log_html(lines, show_token=False, height=360, follow=True, dark=False, recovery=False):
    """Colour-coded log, oldest first (newest at the bottom, auto-scrolled)."""
    theme = THEMES[dark]
    kinds = ["REQUEST", "REPLY", "DEFERRED", "WITHDRAW"] + (["TOKEN"] if show_token else [])
    if recovery:
        kinds += ["CRASHED", "RECOVERY"]
    labels = {"CRASHED": "FAILURE"}                     # chip text when it differs
    chips = "".join(
        f'<span style="background:{MSG_COLORS[k]};color:white;padding:3px 12px;'
        f'border-radius:12px;font-weight:700">{labels.get(k, k)}</span>'
        for k in kinds)

    rows = []
    for line in lines:                                  # oldest -> newest
        kind = classify(line)
        color = (DARK_MSG_COLORS if dark else MSG_COLORS).get(kind, theme["muted"])
        rows.append(f'<div style="border-left:6px solid {color};background:{color}18;color:{color};'
                    f'padding:3px 10px;margin:2px 0;font-weight:600">{html.escape(line)}</div>')
    if not rows:
        rows = [f'<div style="color:{theme["muted"]};padding:6px">(no messages yet)</div>']
    # column-reverse keeps the view pinned to the newest line (bottom), so we emit newest first
    if follow:
        rows.reverse()
    direction = "column-reverse" if follow else "column"

    return (f'<html><body style="margin:0;font-family:{FONT};font-size:16px;background:{theme["bg"]}">'
            f'<div style="margin-bottom:8px;display:flex;flex-wrap:wrap;gap:6px">{chips}</div>'
            f'<div style="display:flex;flex-direction:{direction};overflow-y:auto;'
            f'height:{height - 50}px;font-family:Consolas,monospace;font-size:16px;'
            f'border:1px solid {theme["border"]};border-radius:8px;padding:6px">'
            + "".join(rows) + '</div></body></html>')
