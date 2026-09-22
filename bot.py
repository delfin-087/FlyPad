import asyncio
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from panel import render_panel
from scheduler import POSITIONS, Store, parse_time

BASE = Path(__file__).resolve().parent
log = logging.getLogger("flypad")


def stamp(ts, style="f"):
    return f"<t:{ts}:{style}>"


async def tell(interaction, message):
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


class SafeView(discord.ui.View):
    async def on_error(self, interaction, error, item):
        log.error("Fehler im Panel", exc_info=(type(error), error, error.__traceback__))
        await tell(interaction, "Die Aktion konnte nicht abgeschlossen werden. Bitte prüfe deine Schichtübersicht, bevor du es erneut versuchst.")


class SafeModal(discord.ui.Modal):
    async def on_error(self, interaction, error):
        log.error("Fehler im Formular", exc_info=(type(error), error, error.__traceback__))
        await tell(interaction, "Die Aktion konnte nicht abgeschlossen werden. Bitte prüfe deine Schichtübersicht.")


class BookingModal(SafeModal):
    def __init__(self, bot, position):
        super().__init__(title=f"Schicht: {position}")
        self.bot, self.position = bot, position
        self.start = discord.ui.TextInput(label=f"Beginn ({bot.zone})", placeholder="TT.MM.JJJJ HH:MM oder jetzt", max_length=30)
        self.end = discord.ui.TextInput(label="Ende (Datum und Uhrzeit)", placeholder="TT.MM.JJJJ HH:MM", max_length=30)
        self.add_item(self.start)
        self.add_item(self.end)

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild_id:
            return await tell(interaction, "Bitte auf einem Server verwenden.")
        try:
            now = int(time.time())
            start = now if self.start.value.strip().lower() == "jetzt" else parse_time(self.start.value, self.bot.zone)
            end = parse_time(self.end.value, self.bot.zone)
            shift_id = await asyncio.to_thread(self.bot.store.book, interaction.guild_id,
                interaction.user.id, interaction.user.display_name, self.position, start, end, now)
        except ValueError as error:
            return await tell(interaction, str(error))
        await tell(interaction, f"Schicht **#{shift_id}** gespeichert: **{self.position}**, {stamp(start)} bis {stamp(end)}.")
        await self.bot.refresh_guild(interaction.guild_id)


class CancelModal(SafeModal, title="Eigene Schicht stornieren"):
    number = discord.ui.TextInput(label="Schicht-ID aus ‚Meine Schichten‘", placeholder="z. B. 12", max_length=18)

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild_id:
            return await tell(interaction, "Bitte auf einem Server verwenden.")
        try:
            number = int(self.number.value.strip().lstrip("#"))
        except ValueError:
            return await tell(interaction, "Bitte eine gültige Schicht-ID eingeben.")
        try:
            await asyncio.to_thread(self.bot.store.cancel, interaction.guild_id, number, interaction.user.id)
        except ValueError as error:
            return await tell(interaction, str(error))
        await tell(interaction, f"Schicht **#{number}** storniert.")
        await self.bot.refresh_guild(interaction.guild_id)


class RosterView(SafeView):
    def __init__(self, rows, owner, title):
        super().__init__(timeout=300)
        self.rows, self.owner, self.title, self.page = rows, owner, title, 0

    def embed(self):
        pages = max(1, (len(self.rows) + 7) // 8)
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page >= pages - 1
        embed = discord.Embed(title=self.title, color=0xEC2339)
        for row in self.rows[self.page * 8:(self.page + 1) * 8]:
            embed.add_field(name=f"#{row['id']} · {row['position']}",
                value=f"<@{row['user']}>\n{stamp(row['start'])} → {stamp(row['end'])}", inline=False)
        if not self.rows:
            embed.description = "Keine laufenden oder kommenden Schichten vorhanden."
        embed.set_footer(text=f"Seite {self.page + 1}/{pages} · Momentaufnahme · Zeiten in deiner Discord-Zeitzone")
        return embed

    async def interaction_check(self, interaction):
        return interaction.user.id == self.owner

    @discord.ui.button(label="Zurück", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction, button):
        self.page = max(0, self.page - 1)
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Weiter", style=discord.ButtonStyle.secondary)
    async def next(self, interaction, button):
        self.page = min(max(0, (len(self.rows) - 1) // 8), self.page + 1)
        await interaction.response.edit_message(embed=self.embed(), view=self)


class PanelView(SafeView):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.select(placeholder="Schicht eintragen – Position auswählen", custom_id="flypad:position:v1",
        options=[discord.SelectOption(label=p, value=p) for p in POSITIONS])
    async def position(self, interaction, select):
        await interaction.response.send_modal(BookingModal(self.bot, select.values[0]))

    @discord.ui.button(label="Meine Schichten", style=discord.ButtonStyle.secondary, custom_id="flypad:mine:v1")
    async def mine(self, interaction, button):
        await self.bot.show_roster(interaction, mine=True)

    @discord.ui.button(label="Schichtplan", style=discord.ButtonStyle.secondary, custom_id="flypad:plan:v1")
    async def plan(self, interaction, button):
        await self.bot.show_roster(interaction)

    @discord.ui.button(label="Stornieren", style=discord.ButtonStyle.danger, custom_id="flypad:cancel:v1")
    async def cancel(self, interaction, button):
        await interaction.response.send_modal(CancelModal(self.bot))


class FlypadBot(discord.Client):
    def __init__(self, store, zone="Europe/Berlin", guild_id=None):
        super().__init__(intents=discord.Intents.default(), allowed_mentions=discord.AllowedMentions.none())
        ZoneInfo(zone)
        self.store, self.zone, self.guild_id = store, zone, guild_id
        self.tree = app_commands.CommandTree(self)
        self.locks, self.signatures = {}, {}
        self.register_commands()

    def lock(self, guild):
        return self.locks.setdefault(guild, asyncio.Lock())

    async def setup_hook(self):
        self.add_view(PanelView(self))
        if self.guild_id:
            guild = discord.Object(id=self.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        self.update_panels.start()

    async def on_ready(self):
        log.info("Flypad-Bot verbunden als %s", self.user)
        await self.change_presence(activity=discord.Game("Flypad | Schichten planen"))

    async def close(self):
        self.update_panels.cancel()
        await super().close()

    async def show_roster(self, interaction, mine=False):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild_id:
            return await tell(interaction, "Bitte auf einem Server verwenden.")
        rows = await asyncio.to_thread(self.store.upcoming, interaction.guild_id, int(time.time()),
                                       interaction.user.id if mine else None)
        view = RosterView(rows, interaction.user.id, "Meine Schichten" if mine else "Flypad · Schichtplan")
        await interaction.followup.send(embed=view.embed(), view=view, ephemeral=True)

    async def payload(self, guild):
        now = int(time.time())
        rows = await asyncio.to_thread(self.store.upcoming, guild, now)
        active = [r for r in rows if r['start'] <= now < r['end']]
        signature = (tuple(tuple(r.values()) for r in rows), tuple(r['id'] for r in active))
        embed = discord.Embed(title="Flypad-Bot · Schichtzentrale", color=0xEC2339,
            description="Wähle unten deine Position und trage Beginn und Ende ein.\n"
                        "Pro Position ist zeitgleich eine Person möglich. Direkte Folgeschichten sind erlaubt.")
        for position in POSITIONS:
            current = next((r for r in active if r['position'] == position), None)
            upcoming = [r for r in rows if r['position'] == position and r['start'] > now]
            value = f"**Im Dienst:** <@{current['user']}>\nBis {stamp(current['end'])}" if current else "**Aktuell frei**"
            if upcoming:
                nxt = upcoming[0]
                value += f"\n**Danach:** <@{nxt['user']}>\n{stamp(nxt['start'])} → {stamp(nxt['end'])}"
                if len(upcoming) > 1:
                    value += f"\n+ {len(upcoming) - 1} weitere im Schichtplan"
            embed.add_field(name=position, value=value, inline=False)
        embed.set_image(url="attachment://flypad-panel.png")
        embed.set_footer(text=f"Eingaben & Grafik: {self.zone} · Textzeiten: deine Discord-Zeitzone · Aktualisierung ≤ 30 s")
        return rows, now, signature, embed

    async def refresh_guild(self, guild):
        async with self.lock(guild):
            panels = await asyncio.to_thread(self.store.panels)
            panel = next((p for p in panels if p['guild'] == guild), None)
            if not panel:
                return
            try:
                rows, now, signature, embed = await self.payload(guild)
                if self.signatures.get(guild) == signature:
                    return
                channel = self.get_channel(panel['channel']) or await self.fetch_channel(panel['channel'])
                message = channel.get_partial_message(panel['message'])
                graphic = await asyncio.to_thread(render_panel, rows, now, self.zone)
                await message.edit(embed=embed, attachments=[discord.File(graphic, filename="flypad-panel.png")], view=PanelView(self))
                self.signatures[guild] = signature
            except discord.NotFound:
                await asyncio.to_thread(self.store.delete_panel, guild)
                self.signatures.pop(guild, None)
                log.warning("Panel in Server %s gelöscht. /panel erneut ausführen.", guild)
            except Exception:
                log.exception("Panelaktualisierung für Server %s fehlgeschlagen; nächster Versuch folgt", guild)

    @tasks.loop(seconds=30)
    async def update_panels(self):
        try:
            await asyncio.to_thread(self.store.prune, int(time.time()))
            for panel in await asyncio.to_thread(self.store.panels):
                await self.refresh_guild(panel['guild'])
        except Exception:
            log.exception("Schichtprüfung fehlgeschlagen; nächster Versuch folgt")

    @update_panels.before_loop
    async def before_update(self):
        await self.wait_until_ready()

    def register_commands(self):
        @self.tree.command(name="panel", description="Flypad-Schichtpanel in diesem Kanal erstellen oder verschieben")
        @app_commands.guild_only()
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.checks.has_permissions(manage_guild=True)
        async def panel(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            if not isinstance(interaction.channel, discord.TextChannel):
                return await tell(interaction, "Bitte einen normalen Server-Textkanal wählen.")
            permissions = interaction.channel.permissions_for(interaction.guild.me)
            needed = ("view_channel", "send_messages", "embed_links", "attach_files", "read_message_history")
            missing = [p for p in needed if not getattr(permissions, p)]
            if missing:
                return await tell(interaction, "Dem Bot fehlen Kanalrechte: " + ", ".join(missing))
            async with self.lock(interaction.guild_id):
                existing = next((p for p in await asyncio.to_thread(self.store.panels) if p['guild'] == interaction.guild_id), None)
                if existing:
                    try:
                        channel = self.get_channel(existing['channel']) or await self.fetch_channel(existing['channel'])
                        old = channel.get_partial_message(existing['message'])
                        await old.edit(content="Dieses Panel wurde ersetzt. Bitte das neue Flypad-Panel verwenden.", embed=None, attachments=[], view=None)
                    except discord.NotFound:
                        pass
                    except discord.HTTPException:
                        return await tell(interaction, "Das alte Panel konnte nicht deaktiviert werden. Bitte seine Kanalrechte prüfen oder die alte Nachricht löschen und /panel erneut ausführen.")
                rows, now, signature, embed = await self.payload(interaction.guild_id)
                graphic = await asyncio.to_thread(render_panel, rows, now, self.zone)
                message = await interaction.channel.send(embed=embed, file=discord.File(graphic, filename="flypad-panel.png"), view=PanelView(self))
                await asyncio.to_thread(self.store.set_panel, interaction.guild_id, interaction.channel_id, message.id)
                self.signatures[interaction.guild_id] = signature
            await tell(interaction, f"Panel bereit: {message.jump_url}")

        @self.tree.command(name="schichten", description="Deine laufenden und geplanten Schichten anzeigen")
        @app_commands.guild_only()
        async def shifts(interaction: discord.Interaction):
            await self.show_roster(interaction, mine=True)

        @self.tree.command(name="schichtplan", description="Alle laufenden und geplanten Schichten anzeigen")
        @app_commands.guild_only()
        async def roster(interaction: discord.Interaction):
            await self.show_roster(interaction)

        @self.tree.command(name="stornieren", description="Eigene Schicht entfernen; Serververwaltung darf alle entfernen")
        @app_commands.guild_only()
        @app_commands.describe(schicht_id="Die Nummer aus der Schichtübersicht")
        async def cancel(interaction: discord.Interaction, schicht_id: int):
            await interaction.response.defer(ephemeral=True)
            try:
                await asyncio.to_thread(self.store.cancel, interaction.guild_id, schicht_id, interaction.user.id,
                                        interaction.permissions.manage_guild)
            except ValueError as error:
                return await tell(interaction, str(error))
            await tell(interaction, f"Schicht **#{schicht_id}** storniert.")
            await self.refresh_guild(interaction.guild_id)

        @self.tree.error
        async def on_error(interaction, error):
            if isinstance(error, app_commands.MissingPermissions):
                return await tell(interaction, "Dafür brauchst du die Berechtigung ‚Server verwalten‘.")
            log.error("Befehlsfehler", exc_info=(type(error), error, error.__traceback__))
            await tell(interaction, "Aktion fehlgeschlagen. Bitte Bot-Kanalrechte und Konsole prüfen.")


def main():
    load_dotenv(BASE / ".env")
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token or token == "HIER_DEIN_BOT_TOKEN":
        raise SystemExit("Bitte .env.example nach .env kopieren und DISCORD_TOKEN lokal eintragen. Token niemals im Chat teilen.")
    guild = os.getenv("DISCORD_GUILD_ID", "").strip()
    db_path = Path(os.getenv("DATABASE_PATH", "data/flypad.sqlite3"))
    if not db_path.is_absolute():
        db_path = BASE / db_path
    client = FlypadBot(Store(db_path), os.getenv("TIMEZONE", "Europe/Berlin"), int(guild) if guild else None)
    client.run(token, log_level=logging.INFO)


if __name__ == "__main__":
    main()
