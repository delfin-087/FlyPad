"""Discord-independent scheduling rules. All stored timestamps are UTC seconds."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

POSITIONS = ("Pilot", "HEMS", "Notarzt")


def parse_time(value: str, zone: str = "Europe/Berlin") -> int:
    try:
        naive = datetime.strptime(value.strip(), "%d.%m.%Y %H:%M")
    except ValueError:
        raise ValueError("Bitte Datum und Uhrzeit als TT.MM.JJJJ HH:MM eingeben.") from None
    tz = ZoneInfo(zone)
    candidates = set()
    for fold in (0, 1):
        aware = naive.replace(tzinfo=tz, fold=fold)
        utc = aware.astimezone(timezone.utc)
        if utc.astimezone(tz).replace(tzinfo=None) == naive:
            candidates.add(int(utc.timestamp()))
    if len(candidates) != 1:
        raise ValueError("Diese Uhrzeit ist wegen der Zeitumstellung ungültig oder doppeldeutig. Bitte eine andere Uhrzeit wählen.")
    return candidates.pop()


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS shifts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, guild INTEGER NOT NULL,
                    user INTEGER NOT NULL, name TEXT NOT NULL,
                    position TEXT NOT NULL CHECK(position IN ('Pilot','HEMS','Notarzt')),
                    start INTEGER NOT NULL, end INTEGER NOT NULL CHECK(end > start)
                );
                CREATE INDEX IF NOT EXISTS shift_lookup ON shifts(guild, end, start);
                CREATE TABLE IF NOT EXISTS panels (
                    guild INTEGER PRIMARY KEY, channel INTEGER NOT NULL,
                    message INTEGER NOT NULL
                );
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def book(self, guild, user, name, position, start, end, now):
        if position not in POSITIONS:
            raise ValueError("Unbekannte Position.")
        if end <= start:
            raise ValueError("Das Ende muss nach dem Beginn liegen; bei Nachtschichten das Folgedatum verwenden.")
        if end <= now or start < now - 60:
            raise ValueError("Die Schicht muss jetzt oder in der Zukunft beginnen.")
        if end - start > 24 * 3600:
            raise ValueError("Eine Schicht darf höchstens 24 Stunden dauern.")
        if start > now + 90 * 86400:
            raise ValueError("Du kannst höchstens 90 Tage im Voraus buchen.")
        with self.connection() as db:
            # Lock before checking: simultaneous submissions cannot double-book.
            db.execute("BEGIN IMMEDIATE")
            conflict = db.execute("""SELECT * FROM shifts WHERE guild=?
                AND start < ? AND end > ? AND (position=? OR user=?) LIMIT 1""",
                (guild, end, start, position, user)).fetchone()
            if conflict:
                if conflict["user"] == user:
                    raise ValueError("Du hast in diesem Zeitraum bereits eine Schicht. Mehrere Positionen gleichzeitig sind nicht möglich.")
                raise ValueError(f"{position} ist in diesem Zeitraum bereits belegt. Wähle eine freie Zeit oder eine direkte Folgeschicht.")
            return db.execute("INSERT INTO shifts(guild,user,name,position,start,end) VALUES(?,?,?,?,?,?)",
                              (guild, user, name[:80], position, start, end)).lastrowid

    def upcoming(self, guild, now, user=None):
        with self.connection() as db:
            query = "SELECT * FROM shifts WHERE guild=? AND end>?"
            params = [guild, now]
            if user is not None:
                query += " AND user=?"
                params.append(user)
            return [dict(r) for r in db.execute(query + " ORDER BY start,id", params)]

    def cancel(self, guild, shift_id, user, admin=False):
        with self.connection() as db:
            query = "DELETE FROM shifts WHERE guild=? AND id=?"
            params = [guild, shift_id]
            if not admin:
                query += " AND user=?"
                params.append(user)
            if not db.execute(query, params).rowcount:
                raise ValueError("Schicht nicht gefunden oder keine Berechtigung. Du kannst nur eigene Schichten stornieren.")

    def set_panel(self, guild, channel, message):
        with self.connection() as db:
            db.execute("INSERT INTO panels VALUES(?,?,?) ON CONFLICT(guild) DO UPDATE SET channel=excluded.channel,message=excluded.message",
                       (guild, channel, message))

    def panels(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT * FROM panels")]

    def delete_panel(self, guild):
        with self.connection() as db:
            db.execute("DELETE FROM panels WHERE guild=?", (guild,))

    def prune(self, now):
        with self.connection() as db:
            db.execute("DELETE FROM shifts WHERE end < ?", (now - 30 * 86400,))
