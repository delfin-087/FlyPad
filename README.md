# Flypad-Bot

Ein deutscher Discord-Schichtbot für **Pilot, HEMS und Notarzt**. Mit einem echten rot-weiß-schwarzen Grafikpanel, einem Positionsmenü und Formularen direkt in Discord.

## Enthalten

- Jede Position ist pro Server zu jedem Zeitpunkt höchstens einmal belegt.
- Überlappungen werden auch bei gleichzeitigen Buchungen verhindert.
- Direkte Folgeschichten sind möglich, etwa 12–14 Uhr und 14–16 Uhr.
- Eine Person kann nicht gleichzeitig mehrere Positionen belegen.
- Aktuelle Besetzung und nächste Schicht je Position im Panel; vollständiger Schichtplan mit Seitenwechsel.
- Eigene Schichten anzeigen und stornieren; Serververwaltung kann alle Schichten stornieren.
- Automatischer Besetzungswechsel innerhalb von 30 Sekunden, solange der Bot läuft.
- SQLite speichert Schichten und Panel-Nachricht dauerhaft. Buttons funktionieren nach Neustarts weiter.
- Ein Panel je Server; `/panel` kann es in einen anderen Textkanal verschieben.
- Buchung maximal 90 Tage im Voraus, Schichtdauer höchstens 24 Stunden. Abgelaufene Schichten werden nach 30 Tagen gelöscht.

## Start auf Windows

1. Python **3.12 oder neuer** installieren, inklusive Python Launcher (`py`).
2. Im [Discord Developer Portal](https://discord.com/developers/applications) eine Anwendung mit dem Namen **Flypad-Bot** erstellen. Unter **Bot** den Bot-Namen ebenfalls auf **Flypad-Bot** setzen und ein Bot-Token erzeugen/kopieren.
3. Unter **OAuth2 → URL Generator** die Scopes `bot` und `applications.commands` wählen. Bot-Rechte: **View Channels, Send Messages, Embed Links, Attach Files, Read Message History**. Über die erzeugte URL dem Server hinzufügen. Administratorrechte und privilegierte Gateway-Intents sind nicht erforderlich.
4. ZIP vollständig entpacken und `Start-Flypad.bat` doppelklicken. Es installiert die Abhängigkeiten und öffnet beim ersten Start die neue `.env` im Editor.
5. In `.env` bei `DISCORD_TOKEN` den Token eintragen. Optional bei `DISCORD_GUILD_ID` deine Server-ID eintragen (Discord-Entwicklermodus aktivieren, Rechtsklick auf Server → ID kopieren). Speichern und schließen. **Den Token nur lokal speichern, niemals im Chat oder auf GitHub teilen.**
6. `Start-Flypad.bat` erneut starten und geöffnet lassen. Als Mitglied mit **Server verwalten** im gewünschten Textkanal `/panel` ausführen.

Mit `DISCORD_GUILD_ID` werden die Befehle direkt für diesen Server registriert. Ohne diese Einstellung werden sie global registriert; bis sie in Discord erscheinen, kann es etwas dauern. Die Einstellung nach der Einrichtung möglichst unverändert lassen, damit keine alten globalen bzw. Server-Befehle parallel angezeigt werden.

## Benutzung

1. Im Panel Position auswählen: **Pilot**, **HEMS** oder **Notarzt**.
2. Beginn und Ende einfach als Uhrzeit im Format `HH:MM` eintragen; beim Beginn funktioniert auch `jetzt`. Ein Datum ist nicht nötig.
3. Alle Eingaben gelten in **Europe/Berlin**, inklusive Sommer-/Winterzeit. Beispiel: `18:00` bis `22:00`. Liegt die Beginn-Uhrzeit heute schon in der Vergangenheit, wird automatisch morgen angenommen; liegt das Ende vor oder auf dem Beginn, wird automatisch eine Nachtschicht bis zum nächsten Tag angenommen.
4. Die Bestätigung ist nur für dich sichtbar. Im Panel erscheinst du während deiner Schicht; davor als nächste Schicht oder im vollständigen Schichtplan.

Uhrzeiten, die beim Wechsel der Sommer-/Winterzeit nicht existieren oder doppelt vorkommen, werden mit einer Erklärung zurückgewiesen. Discord-Zeitstempel im Nachrichtentext folgen der persönlichen Discord-Zeitzone; die Grafik nutzt immer die konfigurierte Zeitzone.

| Befehl / Schaltfläche | Funktion |
| --- | --- |
| `/panel` | Panel erstellen/verschieben, benötigt „Server verwalten“ |
| `/schichten` / Meine Schichten | Eigene aktive und geplante Schichten samt ID |
| `/schichtplan` / Schichtplan | Alle aktiven und geplanten Schichten |
| `/stornieren schicht_id:12` | Eigene Schicht #12 löschen; Serververwaltung darf auch fremde löschen |
| Stornieren | Formular zum Löschen einer eigenen Schicht anhand der ID |

Die drei Positionen sind Buchungspositionen und benötigen keine gleichnamigen Discord-Rollen. Alle Mitglieder mit Zugang zum Panel können buchen. Auch laufende Schichten können storniert werden; die Position wird dann frei.

## Betrieb und Grenzen

Der Bot läuft nur, solange sein Python-Prozess und die Internetverbindung laufen. Für 24/7-Betrieb ist ein dauerhaft laufender Rechner oder ein Bot-Host nötig. Die Uhr des Hosts muss korrekt sein. Je Datenbank genau eine Bot-Instanz starten. SQLite-Dateien müssen auf einem persistenten lokalen Datenträger liegen, besonders bei Container-Hosting. Für ein Backup den Bot beenden und den Ordner `data` kopieren.

Ohne Bot-Token wurde kein Live-Test auf einem Discord-Server durchgeführt. Automatisierte Prüfungen decken Buchungsregeln, gleichzeitige Buchungen, Zeitumstellung, Speicherung, Panelgrafik, Slash-Befehle und persistente Buttons ab. Nach Einrichtung zwei überlappende Testbuchungen und einen direkten Schichtwechsel auf dem Server ausprobieren.

Die Panelgrafik verwendet Rot, Weiß und Schwarz. Die Discord-Oberfläche und normalen Nachrichtentexte folgen dem Theme der jeweiligen Nutzer. Namen in der Grafik werden beim Buchen gespeichert; spätere Namensänderungen erscheinen dort erst bei einer neuen Buchung. In den Textfeldern werden Discord-Erwähnungen angezeigt, ohne Benachrichtigung auszulösen.

## Manueller Start / Linux

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
# .env.example nach .env kopieren und lokal ausfüllen
python bot.py
```

Unter Linux je nach System `python3` verwenden. Optional `DejaVu Sans` installieren, damit die Grafik mit der Standardschrift gerendert wird; ansonsten wird die mitgelieferte Pillow-Schrift verwendet.

Tests im Projektordner:

```sh
python -m unittest discover -s tests -v
```

## Weitere Ideen

Diese Erweiterungen sind noch nicht implementiert:

- Erinnerung per Direktnachricht 15 Minuten vor Schichtbeginn.
- Freigabe von Positionen anhand von Discord-Rollen, etwa „Pilotenausbildung“.
- Schichttausch mit Bestätigung beider Personen.
- Wiederkehrende Schichten und persönliche Stundenstatistik.
- Separate Panels für mehrere Helikopter oder Standorte.

Grundlagen: [discord.py Interactions](https://discordpy.readthedocs.io/en/stable/interactions/api.html) und [offizielle Discord-Einrichtung](https://docs.discord.com/developers/quick-start/getting-started).
