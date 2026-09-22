"""A genuine red, white and black panel image, independent of Discord themes."""
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont
from scheduler import POSITIONS


def font(size):
    for name in ("arial.ttf", "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def render_panel(shifts, now, zone):
    image = Image.new("RGB", (1200, 650), "#090909")
    draw = ImageDraw.Draw(image)
    red, white = "#ec2339", "#ffffff"
    def fit(text, size, width=312):
        text = " ".join(text.split())
        while draw.textlength(text, font=font(size)) > width:
            text = text[:-2] + "…"
        return text
    draw.rectangle((0, 0, 1200, 10), fill=red)
    draw.text((42, 40), "FLYPAD", font=font(52), fill=white)
    draw.text((284, 57), "/ SCHICHTPANEL", font=font(25), fill=red)
    draw.text((44, 112), "Drei Positionen. Ein Team.", font=font(22), fill=white)
    local = lambda ts: datetime.fromtimestamp(ts, ZoneInfo(zone)).strftime("%d.%m. %H:%M")
    for i, position in enumerate(POSITIONS):
        x = 40 + 380 * i
        draw.rounded_rectangle((x, 173, x + 360, 545), radius=12, outline=white, width=2)
        draw.rectangle((x + 1, 195, x + 5, 245), fill=red)
        draw.text((x + 22, 197), position.upper(), font=font(29), fill=white)
        active = next((s for s in shifts if s["position"] == position and s["start"] <= now < s["end"]), None)
        draw.text((x + 22, 262), "IM DIENST" if active else "POSITION FREI", font=font(17), fill=red)
        name = fit(active["name"] if active else "Noch unbesetzt", 25)
        draw.text((x + 22, 297), name, font=font(25), fill=white)
        draw.text((x + 22, 337), f"bis {local(active['end'])}" if active else "Jetzt Schicht eintragen", font=font(18), fill=white)
        draw.line((x + 22, 383, x + 338, 383), fill=red, width=2)
        draw.text((x + 22, 407), "ALS NÄCHSTES", font=font(15), fill=red)
        nxt = next((s for s in shifts if s["position"] == position and s["start"] > now), None)
        draw.text((x + 22, 444), fit(nxt["name"] if nxt else "Keine Folgeschicht", 20), font=font(20), fill=white)
        if nxt:
            draw.text((x + 22, 478), local(nxt["start"]), font=font(18), fill=white)
    draw.text((42, 583), "FLYPAD-BOT  /  EINSATZBEREIT ALS TEAM", font=font(18), fill=white)
    draw.text((42, 613), f"Zeiten: {zone}  •  Stand: {local(now)}", font=font(15), fill=white)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer
