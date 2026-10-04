#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════════
  UMI – Dein persönlicher KI-Assistent mit Sprachsteuerung
═══════════════════════════════════════════════════════════════════════════════

  Umi ist ein vollständiger Sprach- und Chat-Assistent in EINER einzigen
  Python-Datei:

    • Moderne, dunkle Chat-Oberfläche (tkinter, keine weiteren GUI-Pakete)
    • Sprachsteuerung über das Mikrofon (Aktivierungswort: „Hey Umi“)
    • Spracherkennung (Sprache → Text) über die Google Web Speech API
    • Natürlich klingende Sprachausgabe (Text → Sprache) über Edge TTS,
      mit automatischem Offline-Fallback auf Windows-SAPI-Stimmen
    • Chat-Verlauf, Texteingabe, Statusanzeige (Bereit / Hört zu / Denkt nach / Spricht)
    • Einstellungsdialog: Mikrofon, Lautsprecher, Stimme, Tempo, Lautstärke,
      Empfindlichkeit, Aktivierungswort, Erkennungssprache, Online-KI (LLM)
    • Erweiterbare Architektur: eigene Fähigkeiten ("Skills") lassen sich in
      wenigen Zeilen ergänzen – siehe Klasse „Skill“ weiter unten.

  ─────────────────────────────────────────────────────────────────────────────
  INSTALLATION (Windows, Python 3.13)
  ─────────────────────────────────────────────────────────────────────────────

    1. Python 3.13 installieren:  https://www.python.org/downloads/
       (beim Installer unbedingt „Add python.exe to PATH“ anhaken!)
    2. Eingabeaufforderung öffnen und im Projektordner ausführen:

         pip install numpy sounddevice soundfile SpeechRecognition edge-tts pyttsx3

       oder mit der beiliegenden Datei:

         pip install -r requirements.txt

    3. Programm starten:

         python umi_assistent.py

  ─────────────────────────────────────────────────────────────────────────────
  HINWEISE
  ─────────────────────────────────────────────────────────────────────────────
    • Spracherkennung und Edge-TTS benötigen eine Internetverbindung.
      Die Offline-Stimmen von Windows (SAPI) funktionieren ohne Internet.
    • Windows fragt beim ersten Start nach der Mikrofon-Freigabe – bitte
      erlauben (Einstellungen → Datenschutz → Mikrofon).
    • Eigene Einstellungen landen in „umi_einstellungen.json“ neben dieser Datei.
    • Nützliche Startoptionen:
        python umi_assistent.py --selftest    (Funktionstest ohne GUI)
        python umi_assistent.py --geraete     (Audio-Geräte auflisten)
        python umi_assistent.py --ohne-wake   (nur Mikrofon-Taste, kein Wake-Wort)
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
#  IMPORTS – Standardbibliothek
# ─────────────────────────────────────────────────────────────────────────────
import argparse
import asyncio
import collections
import datetime as dt
import difflib
import io
import json
import math
import os
import queue
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

# Tkinter gehört zur Standardbibliothek; falls es fehlt (z. B. einige
# Linux-Distributionen ohne python3-tk), läuft wenigstens der Selbsttest.
try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import ttk
    TKINTER_OK = True
except Exception:                                    # pragma: no cover
    TKINTER_OK = False

# ─────────────────────────────────────────────────────────────────────────────
#  IMPORTS – externe Bibliotheken (bewusst "weich": fehlt ein Paket, startet
#  Umi trotzdem und zeigt eine verständliche Fehlermeldung statt abzustürzen)
# ─────────────────────────────────────────────────────────────────────────────
# Grund fehlgeschlagener Imports merken, damit Selbsttest und GUI eine
# verständliche Fehlermeldung zeigen können ("PortAudio fehlt" statt "fehlt").
IMPORT_FEHLER: dict = {}


def _lade_modul(pipname, import_befehl, alias):
    """Führt `import_befehl` aus; im Fehlerfall None + Grund in IMPORT_FEHLER."""
    namespace: dict = {"__name__": "umi_import"}
    try:
        exec(import_befehl, namespace)               # noqa: S102 – kontrolliert
    except Exception as fehler:
        IMPORT_FEHLER[pipname] = str(fehler)
        return None
    return namespace.get(alias)                      # das importierte Modul


np       = _lade_modul("numpy",              "import numpy as np",              "np")
sd       = _lade_modul("sounddevice",        "import sounddevice as sd",        "sd")
sf       = _lade_modul("soundfile",          "import soundfile as sf",          "sf")
sr       = _lade_modul("SpeechRecognition",  "import speech_recognition as sr", "sr")
edge_tts = _lade_modul("edge-tts",           "import edge_tts",                 "edge_tts")
pyttsx3  = _lade_modul("pyttsx3",            "import pyttsx3",                  "pyttsx3")

# ─────────────────────────────────────────────────════════════════════════════
#  1) KONSTANTEN & KLEINE HILFSFUNKTIONEN
# ─────────────────────────────────────────────────────────────────────────────

APP_NAME    = "Umi"
APP_VERSION = "1.0.0"
WAKE_TOKEN  = "umi"                                  # Aktivierungswort-Kern

# Pfad der Einstellungsdatei = Ordner, in dem diese Skriptdatei liegt
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "umi_einstellungen.json")

# Zerlegung des Mikrofon-Signals in 100-ms-Blöcke
CHUNK_SEK  = 0.10
CHUNK_MS   = int(CHUNK_SEK * 1000)
PRE_ROLL_CHUNKS = 8                                  # 0,8 s Vorlauf puffern

# Zustände der Statusanzeige (Schlüssel → (Farbe, Beschriftung))
STATUS_STILE = {
    "ready":     ("#22c55e", "Bereit"),
    "listening": ("#f59e0b", "Hört zu …"),
    "thinking":  ("#3b82f6", "Denkt nach …"),
    "speaking":  ("#a855f7", "Spricht …"),
    "error":     ("#ef4444", "Fehler"),
}

# Fallback-Stimmen, falls die Edge-Stimmliste nicht geladen werden kann
EDGE_STIMMEN_FALLBACK = [
    "de-DE-KatjaNeural", "de-DE-ConradNeural", "de-DE-AmalaNeural",
    "de-DE-KillianNeural", "de-DE-FlorianMultilingual", "de-AT-JonasNeural",
    "de-AT-NeleNeural", "de-CH-LeniNeural",
]

# Standard-Persona für die Online-KI (kann in den Einstellungen geändert werden)
STANDARD_SYSTEM_PROMPT = (
    "Du bist Umi, ein freundlicher, hilfsbereiter, deutschsprachiger "
    "KI-Assistent. Deine Antworten werden auch laut vorgelesen: antworte "
    "deshalb natürlich, kurz (höchstens etwa 4 Sätze) und ohne Markdown, "
    "Listen oder Sonderzeichen. Nimm dir ein Beispiel am Gesprächston eines "
    "helfenden Assistenten wie „Siri“ oder „Alexa“."
)


def normalisiere(text: str) -> str:
    """
    Kleinbuchstaben + Satzzeichen entfernen (Umlaute bleiben erhalten).
    Dezimalzeichen zwischen Ziffern bleiben erhalten ("12,5" -> "12.5"),
    damit Rechenfragen durch die Normalisierung nicht zerstört werden.
    """
    text = re.sub(r"(\d)[,.](\d)", r"\1.\2", text.lower())
    bereinigt = "".join(
        ch if ch.isalnum() or ch.isspace() or ch in ".," else " "
        for ch in text)
    return " ".join(bereinigt.split())


def enthaelt_wake_wort(text: str) -> tuple[bool, str]:
    """
    Prüft, ob das Aktivierungswort („Umi“/„Hey Umi“) im Text steckt.

    Google erkennt „Hey Umi“ manchmal als „Hey Umi“, „Hey Uni“, „A Umi“ …
    Deshalb kombinieren wir exakte Treffer mit einer unscharfen (fuzzy)
    Ähnlichkeitsprüfung. Rückgabe: (gefunden, restlicher Befehl danach).
    """
    tokens = normalisiere(text).split()
    begruessungen = {"hey", "hej", "hay", "hallo", "hi", "ok", "okay", "a"}
    for i, token in enumerate(tokens):
        if token == WAKE_TOKEN:
            return True, " ".join(tokens[i + 1:])
        # Unscharfer Treffer – aber nur, wenn davor eine Begrüßung stand,
        # damit Wörter wie „Union“ nicht fälschlich auslösen.
        aehnlichkeit = difflib.SequenceMatcher(None, token, WAKE_TOKEN).ratio()
        if aehnlichkeit >= 0.72 and i > 0 and tokens[i - 1] in begruessungen:
            return True, " ".join(tokens[i + 1:])
    return False, ""


def pegel(block: "np.ndarray") -> float:
    """Lautstärke (RMS) eines int16-AudioBlocks, normalisiert auf 0…1."""
    if np is None or block is None or len(block) == 0:
        return 0.0
    f = block.astype("float64") / 32768.0
    return float(math.sqrt(float(np.mean(f * f))))


def empfindlichkeit_zu_schwellwert(empfindlichkeit: int) -> float:
    """
    Wandelt die Empfindlichkeit (0–100 %) in einen RMS-Schwellwert um.
    Hohe Empfindlichkeit = kleiner Schwellwert = Umi reagiert leiser.
    """
    e = min(100, max(0, int(empfindlichkeit)))
    return 0.05 * math.exp(-0.045 * e)


def zahl_de(x: float) -> str:
    """Zahl im deutschen Format ausgeben (Komma als Dezimaltrennzeichen)."""
    s = f"{x:,.4f}".rstrip("0").rstrip(".")
    s = s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return s


def uhrzeit_text() -> str:
    jetzt = dt.datetime.now()
    return f"Es ist jetzt {jetzt.strftime('%H:%M')} Uhr."


def datum_text() -> str:
    wochentage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                  "Freitag", "Samstag", "Sonntag"]
    monate = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
              "August", "September", "Oktober", "November", "Dezember"]
    heute = dt.date.today()
    return (f"Heute ist {wochentage[heute.weekday()]}, der "
            f"{heute.day}. {monate[heute.month - 1]} {heute.year}.")


def tageszeit_gruss() -> str:
    stunde = dt.datetime.now().hour
    if 5 <= stunde < 11:
        return "Guten Morgen"
    if 11 <= stunde < 18:
        return "Hallo"
    if 18 <= stunde < 23:
        return "Guten Abend"
    return "Hallo"


def http_json(url: str, daten: dict | None = None,
              header: dict | None = None, timeout: int = 10) -> dict:
    """
    Minimaler JSON-HTTP-Client auf Basis der Standardbibliothek
    (POST bei `daten`, sonst GET). Wirft klare Ausnahmen bei Problemen.
    """
    body = None
    kopf = {"User-Agent": f"{APP_NAME}/{APP_VERSION}"}
    if header:
        kopf.update(header)
    if daten is not None:
        body = json.dumps(daten).encode("utf-8")
        kopf.setdefault("Content-Type", "application/json")
    anfrage = urllib.request.Request(url, data=body, headers=kopf)
    with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
        return json.loads(antwort.read().decode("utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
#  2) KONFIGURATION – Laden, Zusammenführen, Speichern (JSON)
# ─────────────────────────────────────────────────────────────────────────────

STANDARD_KONFIG = {
    "_info": "Einstellungen von Umi – Datei kann bei Bedarf gelöscht werden.",
    "general": {
        "sprache_stt": "de-DE",      # Erkennungssprache
        "wake_aktiv":  True,         # Aktivierungswort „Hey Umi“ überwachen
        "tts_aktiv":   True,         # Antworten laut vorlesen
        "piepser":     True,         # Signalton bei erkanntem Aktivierungswort
    },
    "audio": {
        "eingang":          "",      # Mikrofon-Name ("" = Systemstandard)
        "ausgang":          "",      # Lautsprecher-Name ("" = Systemstandard)
        "sample_rate":      16000,
        "empfindlichkeit":  35,      # 0–100 (höher = reagiert leiser)
        "sprechpause_ms":   1100,    # Stille, die einen Satz beendet
        "max_laenge_s":     12.0,    # Längste Aufnahme pro Äußerung
    },
    "sprache_tts": {
        "anbieter":    "auto",       # auto | edge | windows
        "stimme":      "edge:de-DE-KatjaNeural",
        "tempo":       0,            # −50 … +50 (Prozent)
        "lautstaerke": 85,           # 0–100
    },
    "ki": {
        "aktiv":         False,      # Online-KI (LLM) für freie Gespräche
        "basis_url":     "https://api.openai.com/v1",
        "api_key":       "",
        "modell":        "gpt-4o-mini",
        "temperatur":    0.7,
        "system_prompt": STANDARD_SYSTEM_PROMPT,
    },
    "wetter": {
        "standard_stadt": "Berlin",
    },
}


class Konfiguration:
    """
    Verwaltet die Einstellungen in einer JSON-Datei.

    Fehlende Schlüssel werden automatisch aus STANDARD_KONFIG ergänzt
    ("deep merge") – so bleiben alte Einstellungsdateien bei Updates kompatibel.
    """

    def __init__(self, pfad: str = CONFIG_PATH):
        self.pfad = pfad
        # RLock (statt Lock), da laden() intern speichern() aufruft
        self._sperre = threading.RLock()
        self.daten = json.loads(json.dumps(STANDARD_KONFIG))  # tiefe Kopie
        self.laden()

    # ── Laden / Speichern ────────────────────────────────────────────────
    def laden(self) -> None:
        with self._sperre:
            if os.path.exists(self.pfad):
                try:
                    with open(self.pfad, "r", encoding="utf-8") as d:
                        benutzer = json.load(d)
                    self.daten = self._verschmelze(
                        json.loads(json.dumps(STANDARD_KONFIG)), benutzer)
                except Exception as fehler:
                    print(f"[Umi] Einstellungen konnten nicht gelesen werden "
                          f"({fehler}) – verwende Standardeinstellungen.")
            else:
                self.speichern()          # Datei mit Standardwerten anlegen

    def speichern(self) -> None:
        with self._sperre:
            try:
                with open(self.pfad, "w", encoding="utf-8") as d:
                    json.dump(self.daten, d, ensure_ascii=False, indent=2)
            except Exception as fehler:
                print(f"[Umi] Einstellungen konnten nicht gespeichert "
                      f"werden: {fehler}")

    def neu_laden(self) -> None:
        self.laden()

    # ── Zugriff ──────────────────────────────────────────────────────────
    def get(self, abschnitt: str, schluessel: str):
        return self.daten.get(abschnitt, {}).get(schluessel)

    def setze(self, abschnitt: str, schluessel: str, wert) -> None:
        self.daten.setdefault(abschnitt, {})[schluessel] = wert

    # ── intern ───────────────────────────────────────────────────────────
    @staticmethod
    def _verschmelze(basis: dict, extra: dict) -> dict:
        """Rekursiv: `extra` übernimmt nur Schlüssel, die auch in `basis` sind."""
        ergebnis = dict(basis)
        for schluessel, wert in extra.items():
            if (schluessel in ergebnis
                    and isinstance(ergebnis[schluessel], dict)
                    and isinstance(wert, dict)):
                ergebnis[schluessel] = Konfiguration._verschmelze(
                    ergebnis[schluessel], wert)
            else:
                ergebnis[schluessel] = wert
        return ergebnis


# ─────────────────────────────────────────────────────────────────────────────
#  3) EREIGNIS-BUS – sichere Brücke zwischen Hintergrund-Threads und GUI
# ─────────────────────────────────────────────────────────────────────────────

class EreignisBus:
    """
    Threads (Sprach-Engine, Gesprächs-Worker, …) legen hier Ereignisse ab;
    die GUI holt sie im Haupt-Thread ab. So wird tkinter niemals aus einem
    Nebenthread heraus berührt (tkinter ist nicht thread-sicher).
    """

    def __init__(self):
        self._warteschlange: "queue.Queue[tuple]" = queue.Queue()

    def sende(self, art: str, **inhalt) -> None:
        self._warteschlange.put((art, inhalt))

    def hole(self) -> list[tuple]:
        """Alle wartenden Ereignisse auf einmal abholen."""
        ereignisse = []
        while True:
            try:
                ereignisse.append(self._warteschlange.get_nowait())
            except queue.Empty:
                break
        return ereignisse


# ─────────────────────────────────────────────────────────────────────────────
#  4) FÄHIGKEITEN ("SKILLS") – offline verfügbare Befehle von Umi
# ─────────────────────────────────────────────────────────────────────────────

class Skill:
    """
    Basisklasse für alle Fähigkeiten von Umi.

    Eigene Fähigkeit ergänzen – so geht's:

        class KaffeeSkill(Skill):
            name = "Kaffee-Berater"
            def match(self, text):  return "kaffee" in text
            def handle(self, text, umi):
                return "Ein guter Kaffee braucht 60 g Kaffee pro Liter Wasser!"

        # und in UmiBrain.__init__:  self.skills.append(KaffeeSkill())

    `match` entscheidet, ob die Fähigkeit zuständig ist; `handle` liefert die
    Antwort (wird angezeigt und vorgelesen). Über `umi` hat die Fähigkeit
    Zugriff auf Konfiguration (umi.konfig) und Hinweise (umi.hinweis(...)).
    """

    name = "Basis-Fähigkeit"
    beschreibung = ""

    def match(self, text: str) -> bool:      # noqa: D401
        return False

    def handle(self, text: str, umi: "UmiGehirn") -> str:
        return ""


class BegruessungsSkill(Skill):
    """Begrüßung, Smalltalk, Dank, Vorstellung."""

    name = "Smalltalk"
    beschreibung = "Begrüßung, Befinden, Dank, Vorstellung"

    def match(self, text):
        return re.search(r"\b(hallo|hi|hey|hej|moin|servus|guten (morgen|tag|abend)|"
                         r"wie geht|wie geht's|geht es dir|danke|dankeschön|"
                         r"wer bist du|wie heißt du|wer hat dich|"
                         r"wer (hat )?(dich )?(entwickelt|programmiert|erstellt))\b",
                         text) is not None

    def handle(self, text, umi):
        if re.search(r"wer bist du|wie heißt du", text):
            return ("Ich bin Umi, dein persönlicher Sprach- und Chat-Assistent. "
                    "Sage „Hey Umi“ gefolgt von deinem Wunsch, oder tippe mir "
                    "einfach eine Nachricht!")
        if re.search(r"wer hat dich|entwickelt|programmiert|erstellt", text):
            return ("Ich wurde in Python programmiert – mit einer erweiterbaren "
                    "Architektur, damit jederzeit neue Fähigkeiten dazukommen "
                    "können.")
        if re.search(r"wie geht|geht es dir", text):
            return random.choice([
                "Mir geht es bestens, danke der Nachfrage! Und dir?",
                "Ich fühle mich großartig – immerhin laufe ohne Kaffee rund um die Uhr!",
            ])
        if re.search(r"danke", text):
            return random.choice([
                "Gern geschehen!", "Immer wieder gerne!",
                "Keine Ursache – dafür bin ich ja da.",
            ])
        return random.choice([
            f"{tageszeit_gruss()}! Was kann ich für dich tun?",
            f"{tageszeit_gruss()}! Ich bin bereit – sage oder tippe einfach, "
            f"was du brauchst.",
        ])


class ZeitSkill(Skill):
    """Aktuelle Uhrzeit."""

    name = "Uhrzeit"

    def match(self, text):
        return re.search(r"\b(wie spät|uhrzeit|wie viel uhr)\b", text) is not None

    def handle(self, text, umi):
        return uhrzeit_text()


class DatumSkill(Skill):
    """Heutiges Datum / Wochentag."""

    name = "Datum"

    def match(self, text):
        return re.search(r"\b(datum|welcher tag|welches datum|welcher wochentag|"
                         r"was ist heute)\b", text) is not None

    def handle(self, text, umi):
        return datum_text()


class RechenSkill(Skill):
    """Rechnet einfache Rechen Aufgaben in gesprochener oder getippter Form."""

    name = "Taschenrechner"
    beschreibung = "„Rechne 12,5 mal 4“, „was ist 2 hoch 10“, „Wurzel aus 144“"

    # Erkennung: Zahl + Rechenoperator in irgendeiner Form
    _erkennung = re.compile(
        r"\d\s*(?:[+\-*/]|plus|minus|mal|geteilt|durch|hoch)|"
        r"wurzel|\bprozent\b")

    def match(self, text):
        return self._erkennung.search(text) is not None

    def handle(self, text, umi):
        formel = self._zu_formel(text)
        if formel is None:
            return ("Das konnte ich leider nicht als Rechnung erkennen. "
                    "Zum Beispiel: „rechne 12,5 mal 4“.")
        try:
            # absichtlich abgeschottet: nur Zahlen, Operatoren, math-Funktionen
            ergebnis = eval(formel, {"__builtins__": {}, "math": math}, {})
        except ZeroDivisionError:
            return "Durch null kann ich leider nicht teilen."
        except Exception:
            return "Diese Rechnung war zu knifflig für mich. Versuch es anders formuliert."
        # Boolsche/andere Typen abfangen
        if isinstance(ergebnis, bool) or not isinstance(ergebnis, (int, float)):
            return "Diese Rechnung war zu knifflig für mich."
        ergebnis = round(ergebnis, 6)
        return f"Das Ergebnis ist {zahl_de(ergebnis)}."

    @staticmethod
    def _zu_formel(text: str):
        """Wandelt gesprochene Mathematik in eine sichere Formel um."""
        t = text.replace(",", ".")

        # Sonderfall: "20 Prozent von 50"
        t = re.sub(r"(\d+(?:\.\d+)?)\s*prozent\s*von\s*(\d+(?:\.\d+)?)",
                   r"(\1/100)*\2", t)
        # Sonderfall: "Wurzel aus 144"
        w = re.search(r"wurzel\s*(?:aus)?\s*(\d+(?:\.\d+)?)", t)
        if w:
            return f"math.sqrt({w.group(1)})"

        # Wörter in Operatoren übersetzen
        ersetzt = [
            (r"\bplus\b", "+"), (r"\bminus\b", "-"),
            (r"\bmal\b", "*"), (r"\bgeteilt durch\b", "/"), (r"\bgeteilt\b", "/"),
            (r"\bdurch\b", "/"), (r"\bhoch\b", "**"),
        ]
        for muster, op in ersetzt:
            t = re.sub(muster, f" {op} ", t)
        # Füllwörter entfernen
        t = re.sub(r"\b(rechne|berechne|was ist|wie viel ist|wieviel ist|ist|"
                   r"das ergebnis|ergebnis|bitte|gleich|mal genommen)\b", " ", t)
        # Nur noch Zahlen, Operatoren, Klammern erlauben
        erlaubt = set("0123456789+-*/(). ")
        t = "".join(ch for ch in t if ch in erlaubt).strip()
        if not t or not re.search(r"\d", t) or not re.search(r"[+\-*/]", t):
            return None
        if "__" in t or any(c.isalpha() for c in t):
            return None
        return t


class WitzSkill(Skill):
    """Erzählt einen zufälligen Witz."""

    name = "Witze"
    _witze = [
        "Warum können Geister so schlecht lügen? Weil man durch sie hindurchsieht!",
        "Treffen sich zwei Magneten. Sagt der eine: „Ich weiß nicht, was ich an dir habe – aber ich werde ständig angezogen.“",
        "Was macht ein Clown im Büro? Faxen!",
        "Warum haben Bienen so klebrige Haare? Weil sie Honigkämme benutzen!",
        "Kommt ein Pferd in eine Bar. Fragt der Barkeeper: „Warum so ein langes Gesicht?“",
        "Was sagt ein Krokodil, das um die Ecke kommt? „Bis später, Alligator!“",
        "Warum ging der Pilz auf die Party? Weil er ein Champignon war!",
        "Mein Computer hat mir heute einen Kaffee gemacht. Jetzt startet er langsam und will erst mal in Ruhe surfen.",
    ]

    def match(self, text):
        return re.search(r"\b(witz|joke|lustig|bring mich zum lachen)\b",
                         text) is not None

    def handle(self, text, umi):
        return random.choice(self._witze)


class ZufallsSkill(Skill):
    """Münzwurf, Würfeln, Zufallszahl."""

    name = "Zufall"

    def match(self, text):
        return re.search(r"\b(münze|coin|werfe|würfel|würfle|würfeln|"
                         r"zufallszahl|zahl zwischen)\b", text) is not None

    def handle(self, text, umi):
        if re.search(r"münze|coin", text):
            return f"Ich habe eine Münze geworfen: {random.choice(['Kopf', 'Zahl'])}!"
        z = re.search(r"zahl zwischen (\d+) und (\d+)", text)
        if z:
            a, b = int(z.group(1)), int(z.group(2))
            if a > b:
                a, b = b, a
            return f"Meine Zufallszahl lautet: {random.randint(a, b)}."
        return f"Der Würfel zeigt: {random.randint(1, 6)}."


class WiederholSkill(Skill):
    """Wiederholt die letzte Antwort: „Wiederhole das“, „Wie bitte?“."""

    name = "Wiederholen"

    def match(self, text):
        return re.search(r"\b(wiederhol\w*|wie bitte|was hast du gesagt|"
                         r"sag (das|es) noch(einmal| mal)?)\b", text) is not None

    def handle(self, text, umi):
        if umi.letzte_antwort:
            return umi.letzte_antwort
        return "Ich habe noch nichts gesagt – frag mich einfach etwas!"


class LautstaerkeSkill(Skill):
    """
    Sprachausgabe lauter/leiser stellen: „Mach lauter“, „Mach leiser“,
    „Lautstärke 50“, „Stumm schalten“.
    """

    name = "Lautstärke"

    def match(self, text):
        return re.search(r"\b(lauter|leiser|lautstärke|stumm)\b",
                         text) is not None

    def handle(self, text, umi):
        aktuell = int(umi.konfig.get("sprache_tts", "lautstaerke") or 80)
        if "stumm" in text:
            neu = 0
        elif "lauter" in text:
            neu = min(100, aktuell + 15)
        elif "leiser" in text:
            neu = max(0, aktuell - 15)
        else:
            z = re.search(r"\b(\d{1,3})\b", text)
            if z:
                neu = min(100, max(0, int(z.group(1))))
            else:
                return ("Sage zum Beispiel „mach lauter“, „mach leiser“, "
                        "„stumm“ oder „Lautstärke 50“.")
        umi.konfig.setze("sprache_tts", "lautstaerke", neu)
        umi.konfig.speichern()
        if neu == 0:
            return ("Okay, ich schweige. Sage „Lautstärke 50“, um mich wieder "
                    "zu hören.")
        return f"Die Lautstärke ist jetzt bei {neu} Prozent."


class WebsiteSkill(Skill):
    """
    Öffnet Websites im Standardbrowser: „Öffne YouTube“, „Öffne spiegel.de“.
    Unbekannte Begriffe werden als Google-Suche geöffnet.
    """

    name = "Websites öffnen"
    _seiten = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "wikipedia": "https://de.wikipedia.org",
        "github": "https://github.com",
        "gmx": "https://www.gmx.net",
        "web.de": "https://web.de",
        "amazon": "https://www.amazon.de",
        "spiegel": "https://www.spiegel.de",
        "tagesschau": "https://www.tagesschau.de",
        "kicker": "https://www.kicker.de",
        "wetter": "https://www.wetter.de",
    }
    _schluessel = re.compile(r".*?(?:öffne|oeffne|mach auf|aufmachen)\s*"
                             r"(?:bitte\s*)?(?:die |den |das |mal )?")

    def match(self, text):
        return re.search(r"\b(öffne|oeffne|mach auf|aufmachen)\b",
                         text) is not None

    def handle(self, text, umi):
        ziel = self._schluessel.sub("", text, count=1).strip()
        if not ziel:
            return ("Welche Website soll ich öffnen? Sag zum Beispiel "
                    "„öffne YouTube“.")
        for name, url in self._seiten.items():
            if name in ziel:
                webbrowser.open(url)
                return f"Ich öffne {name.title()} im Browser."
        d = re.search(r"([a-z0-9\-]+)\.(de|com|net|org|io|eu|at|ch)(?!\w)", ziel)
        if d:
            webbrowser.open(f"https://www.{d.group(1)}.{d.group(2)}")
            return f"Ich öffne {d.group(1)}.{d.group(2)} im Browser."
        suche = urllib.parse.quote_plus(ziel)
        webbrowser.open(f"https://www.google.com/search?q={suche}")
        return f"Ich suche nach „{ziel}“ im Browser."


class WetterSkill(Skill):
    """
    Aktuelles Wetter über die kostenlose Open-Meteo-API (kein API-Schlüssel
    nötig). Beispiel: „Wie wird das Wetter in Hamburg?“
    """

    name = "Wetter"
    _codes = {
        0: "klarem Himmel", 1: "überwiegend klarem Himmel",
        2: "ein paar Wolken", 3: "bedecktem Himmel", 45: "Nebel", 48: "Reifnebel",
        51: "leichtem Nieselregen", 53: "Nieselregen", 55: "starkem Nieselregen",
        61: "leichtem Regen", 63: "Regen", 65: "starkem Regen",
        66: "gefrierendem Regen", 67: "starkem gefrierendem Regen",
        71: "leichtem Schneefall", 73: "Schneefall", 75: "starkem Schneefall",
        77: "Schneegriesel", 80: "leichten Regenschauern", 81: "Regenschauern",
        82: "heftigen Regenschauern", 85: "Schneeschauern", 86: "starken Schneeschauern",
        95: "Gewitter", 96: "Gewitter mit leichtem Hagel",
        99: "Gewitter mit Hagel",
    }

    def match(self, text):
        return re.search(r"\bwetter\b|\bregnet\b|\bwie warm\b|\btemperatur\b",
                         text) is not None

    def handle(self, text, umi):
        stadt = self._stadt_aus_text(text) or \
            (umi.konfig.get("wetter", "standard_stadt") or "Berlin")
        try:
            geo = http_json(
                "https://geocoding-api.open-meteo.com/v1/search?"
                + urllib.parse.urlencode({"name": stadt, "count": 1,
                                          "language": "de", "format": "json"}),
                timeout=8)
            if not geo.get("results"):
                return f"Ich konnte die Stadt „{stadt.title()}“ leider nicht finden."
            ort = geo["results"][0]
            wetter = http_json(
                "https://api.open-meteo.com/v1/forecast?"
                + urllib.parse.urlencode({
                    "latitude": ort["latitude"], "longitude": ort["longitude"],
                    "current": "temperature_2m,apparent_temperature,"
                               "weather_code,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min,"
                             "precipitation_probability_max",
                    "timezone": "auto"}), timeout=8)
        except (urllib.error.URLError, TimeoutError, OSError):
            return ("Ich konnte die Wetterdaten leider nicht abrufen. "
                    "Bitte prüfe deine Internetverbindung.")
        except Exception as fehler:
            return f"Wetterabruf fehlgeschlagen: {fehler}"

        aktuell = wetter.get("current", {})
        tage = wetter.get("daily", {})
        beschreibung = self._codes.get(aktuell.get("weather_code"), "wechselhaftem Wetter")
        quelle = ort.get("name", stadt.title())
        antwort = (f"In {quelle} sind es aktuell {round(aktuell.get('temperature_2m', 0))} Grad "
                   f"bei {beschreibung}, gefühlt "
                   f"{round(aktuell.get('apparent_temperature', 0))} Grad und Wind mit bis zu "
                   f"{round(aktuell.get('wind_speed_10m', 0))} Kilometern pro Stunde.")
        if tage.get("temperature_2m_max"):
            antwort += (f" Heute werden es {round(tage['temperature_2m_max'][0])} bis "
                        f"{round(tage['temperature_2m_min'][0])} Grad mit "
                        f"{round(tage.get('precipitation_probability_max', [0])[0])} Prozent "
                        f"Regenwahrscheinlichkeit.")
        return antwort

    @staticmethod
    def _stadt_aus_text(text: str) -> str:
        m = re.search(r"(?:wetter|regnet|warm)\s*(?:es |wird |ist |heute |morgen |gerade |"
                      r"jetzt |aktuell )*?(?:in|für|bei|von)\s+([a-zäöüß \-]{2,})", text)
        if not m:
            return ""
        stadt = m.group(1).strip()
        # Füllwörter am Ende entfernen ("wetter in berlin heute bitte")
        for fuell in ("heute", "morgen", "bitte", "denn", "eigentlich", "gerade",
                      "jetzt", "aktuell", "draußen"):
            stadt = re.sub(rf"\b{fuell}\b", "", stadt).strip()
        return stadt


class TimerSkill(Skill):
    """Stellt einen Timer: „Stelle einen Timer auf 5 Minuten“ oder
    „Erinnere mich in 10 Minuten an die Wäsche“."""

    name = "Timer & Erinnerungen"
    _muster = re.compile(
        r"(?:erinnere mich (?:in|mich)?\s*|stelle(?:n)?\s*(?:einen\s*)?timer\s*(?:auf)?\s*|"
        r"timer\s*(?:auf|auf\s*etwa)?\s*)"
        r"(\d+)\s*(sekunden?|sek|minuten?|min|stunden?|std|std\.|h)\s*"
        r"(?:an|auf|für|zu|fuer)?\s*(.*)")

    def match(self, text):
        return ("timer" in text) or ("erinnere mich" in text)

    def handle(self, text, umi):
        m = self._muster.search(text)
        if not m:
            return ("Gerne – sage zum Beispiel: „Stelle einen Timer auf "
                    "5 Minuten“ oder „Erinnere mich in 10 Minuten an die Wäsche“.")
        menge, einheit, zweck = int(m.group(1)), m.group(2), (m.group(3) or "").strip()
        sekunden = menge * {"s": 1, "sek": 1, "sekunde": 1, "sekunden": 1,
                            "min": 60, "minute": 60, "minuten": 60,
                            "h": 3600, "std": 3600, "std.": 3600,
                            "stunde": 3600, "stunden": 3600}[einheit]
        zweck = re.sub(r"\b(bitte|einmal)\b", "", zweck).strip(" ,.")
        zweck = zweck or "deine Erinnerung"
        umi.timer_starten(sekunden, zweck)
        schoene_einheit = {"sek": "Sekunden", "sekunde": "Sekunden",
                           "sekunden": "Sekunden", "min": "Minuten",
                           "minute": "Minuten", "minuten": "Minuten",
                           "h": "Stunden", "std": "Stunden", "std.": "Stunden",
                           "stunde": "Stunden", "stunden": "Stunden"}[einheit]
        if menge == 1:                        # „1 Minute“ statt „1 Minuten“
            schoene_einheit = {"Sekunden": "Sekunde", "Minuten": "Minute",
                               "Stunden": "Stunde"}[schoene_einheit]
        return (f"Alles klar! Ich erinnere dich in {menge} "
                f"{schoene_einheit} an „{zweck}“.")


class HilfeSkill(Skill):
    """Übersicht, was Umi kann."""

    name = "Hilfe"

    def match(self, text):
        return re.search(r"\b(hilfe|help|was kannst du|befehle|funktionen|"
                         r"fähigkeiten|anleitung)\b", text) is not None

    def handle(self, text, umi):
        zeilen = ["Das kann ich alles – sag oder tippe einfach:",
                  "• „Wie spät ist es?“ / „Welches Datum haben wir?“",
                  "• „Rechne 12,5 mal 4“ / „Wurzel aus 144“",
                  "• „Erzähl mir einen Witz“ / „Wirf eine Münze“ / „Würfle“",
                  "• „Mach lauter“ / „Lautstärke 50“ / „Öffne YouTube“",
                  "• „Wie wird das Wetter in Hamburg?“",
                  "• „Stelle einen Timer auf 5 Minuten“",
                  "• Freie Fragen – wenn du unter Einstellungen → KI eine "
                  "Online-Verbindung aktivierst, beantworte ich fast alles.",
                  "Sprachsteuerung: sage „Hey Umi“ und dann deinen Wunsch – "
                  "oder nutze die Mikrofon-Taste unten."]
        return "\n".join(zeilen)


class AbschiedSkill(Skill):
    """Verabschiedet sich und pausiert das Aktivierungswort."""

    name = "Abschied"

    def match(self, text):
        return re.search(r"\b(gute nacht|schlaf gut|auf wiederhören|"
                         r"auf wiedersehen|tschüss|tschuess|beende dich|"
                         r"abschalten|geh schlafen|bye)\b", text) is not None

    def handle(self, text, umi):
        umi.sprachsteuerung_pausieren()
        return random.choice([
            "Alles klar, ich schlafe. Du kannst mich jederzeit über die "
            "Mikrofon-Taste wieder wecken!",
            "Auf Wiederhören! Die Sprachsteuerung ist pausiert – die "
            "Mikrofon-Taste unten weckt mich wieder.",
        ])


# ─────────────────────────────────────────────────────────────────────────────
#  5) GEBIRN – koordiniert Skills + optionale Online-KI (LLM)
# ─────────────────────────────────────────────────────────────────────────────

class UmiGehirn:
    """
    Das "Gehirn" von Umi:

      1. Offene Fähigkeiten (Skills) prüfen, ob sie die Eingabe beantworten.
      2. Falls nicht und eine Online-KI konfiguriert ist: Frage an das
         OpenAI-kompatible Chat-Modell (OpenAI, Ollama, LM Studio, …).
      3. Falls weder Skill noch Online-KI: freundlicher Hinweis.

    Zusätzlich verwaltet das Gehirn den Gesprächsverlauf für die Online-KI
    und die Timer-Funktion.
    """

    def __init__(self, konfig: Konfiguration, ereignisse: EreignisBus):
        self.konfig = konfig
        self.ereignisse = ereignisse
        self.verlauf: list[dict] = []            # für die Online-KI
        self._timer: set[threading.Timer] = set()
        self._erinnerungs_kanal = None           # wird von main() gesetzt
        self.wake_callback = None                # wird von main() gesetzt
        self.letzte_antwort = ""                 # für „Wiederhole das“
        # Liste der Fähigkeiten – hier kannst du eigene Skills ergänzen!
        self.skills: list[Skill] = [
            AbschiedSkill(), HilfeSkill(), WiederholSkill(), ZeitSkill(),
            DatumSkill(), RechenSkill(), WitzSkill(), ZufallsSkill(),
            LautstaerkeSkill(), WebsiteSkill(), WetterSkill(),
            TimerSkill(), BegruessungsSkill(),
        ]

    # ── Zentrale Antwort-Funktion ────────────────────────────────────────
    def antworten(self, text: str, quelle: str = "text") -> str:
        """
        Ermittelt die Antwort und merkt sie sich als letzte Antwort,
        damit „Wiederhole das“ funktioniert.
        """
        antwort = self._antwort_ermitteln(text, quelle)
        if antwort and "wiederhol" not in normalisiere(text or ""):
            self.letzte_antwort = antwort
        return antwort

    def _antwort_ermitteln(self, text: str, quelle: str = "text") -> str:
        text = (text or "").strip()
        if not text:
            return "Ich habe leider nichts gehört. Wie kann ich helfen?"
        norm = normalisiere(text)
        for skill in self.skills:
            try:
                if skill.match(norm):
                    return skill.handle(norm, self)
            except Exception as fehler:
                return (f"Tut mir leid, in der Fähigkeit „{skill.name}“ "
                        f"ist ein Fehler aufgetreten: {fehler}")
        if self._ki_aktiv():
            return self._ki_frage(text)
        return random.choice([
            "Das übersteigt meine Offline-Fähigkeiten. Aktiviere in den "
            "Einstellungen den Bereich „KI“ mit einem Chat-Modell – dann "
            "beantworte ich dir fast jede Frage!",
            "Darauf habe ich (noch) keine Antwort. Tippe „Hilfe“ für eine "
            "Übersicht meiner Fähigkeiten – oder hinterlege in den "
            "Einstellungen eine Online-KI.",
        ])

    # ── Online-KI (OpenAI-kompatible Schnittstelle) ──────────────────────
    def _ki_aktiv(self) -> bool:
        ki = self.konfig.daten.get("ki", {})
        return bool(ki.get("aktiv")) and bool(ki.get("basis_url"))

    def _ki_frage(self, text: str) -> str:
        ki = self.konfig.daten.get("ki", {})
        nachrichten = ([{"role": "system",
                         "content": ki.get("system_prompt") or STANDARD_SYSTEM_PROMPT}]
                       + self.verlauf[-12:] + [{"role": "user", "content": text}])
        nutzdaten = {
            "model": ki.get("modell") or "gpt-4o-mini",
            "messages": nachrichten,
            "temperature": float(ki.get("temperatur", 0.7)),
        }
        kopf = {"Content-Type": "application/json"}
        if ki.get("api_key"):
            kopf["Authorization"] = f"Bearer {ki['api_key']}"
        url = (ki.get("basis_url") or "").rstrip("/") + "/chat/completions"
        try:
            antwort = http_json(url, daten=nutzdaten, header=kopf, timeout=60)
            inhalt = antwort["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as fehler:
            detail = ""
            try:
                detail = json.loads(fehler.read().decode("utf-8")) \
                    .get("error", {}).get("message", "")
            except Exception:
                pass
            return f"Die Online-KI meldet einen Fehler: {detail or fehler.code}"
        except (urllib.error.URLError, TimeoutError, OSError):
            return ("Ich konnte die Online-KI nicht erreichen. Bitte prüfe "
                    "deine Internetverbindung und die KI-Einstellungen.")
        except Exception as fehler:
            return f"Die Online-KI hat unerwartet geantwortet: {fehler}"
        # Verlauf für den Kontext kürzen und pflegen
        self.verlauf.append({"role": "user", "content": text})
        self.verlauf.append({"role": "assistant", "content": inhalt})
        del self.verlauf[:-24]
        return inhalt

    def gespraech_zuruecksetzen(self) -> None:
        self.verlauf.clear()

    # ── Timer / Erinnerungen ─────────────────────────────────────────────
    def timer_starten(self, sekunden: int, zweck: str) -> None:
        timer = threading.Timer(max(1, int(sekunden)), self._timer_abgelaufen,
                                args=(zweck,))
        timer.daemon = True
        timer.start()
        self._timer.add(timer)

    def _timer_abgelaufen(self, zweck: str) -> None:
        text = f"⏰ Zeit ist um! Erinnerung: {zweck}."
        if self._erinnerungs_kanal:
            try:
                self._erinnerungs_kanal(text)
            except Exception:
                pass

    def timer_abbrechen(self) -> None:
        for timer in list(self._timer):
            timer.cancel()
        self._timer.clear()

    # ── Schnittstellen für Skills ────────────────────────────────────────
    def setze_erinnerungs_kanal(self, funktion) -> None:
        """Wird von main() gesetzt: Funktion, die eine Erinnerung an Umi
        (anzeigen + vorlesen) weiterreicht."""
        self._erinnerungs_kanal = funktion

    def hinweis(self, text: str) -> None:
        """Fähigkeiten können System-Hinweise in den Chat schreiben."""
        self.ereignisse.sende("chat_system", text=text)

    def sprachsteuerung_pausieren(self) -> None:
        """Sprachsteuerung pausieren (z. B. auf „gute Nacht“)."""
        self.konfig.setze("general", "wake_aktiv", False)
        self.konfig.speichern()
        if self.wake_callback:
            # wake_setzen sendet das „wake_aenderung“-Ereignis selbst
            try:
                self.wake_callback(False, speichern=False)
            except Exception:
                self.ereignisse.sende("wake_aenderung", aktiv=False)
        else:
            self.ereignisse.sende("wake_aenderung", aktiv=False)


# ─────────────────────────────────────────────────────────────────────────────
#  6) SPRACHAUSGABE (Text-to-Speech): Edge TTS + Windows-Offline-Fallback
# ─────────────────────────────────────────────────────────────────────────────

class Sprecher:
    """
    Erzeugt und spielt Sprachausgabe.

    • „edge“    – Microsoft Edge TTS über das Internet (natürliche Stimmen)
    • „windows“ – offline über pyttsx3/SAPI5 (funktioniert immer unter Windows)

    Bei „auto“ wird zuerst Edge versucht; scheitert das (z. B. ohne Internet),
    greift automatisch die Windows-Stimme.
    """

    def __init__(self, konfig: Konfiguration, ereignisse: EreignisBus):
        self.konfig = konfig
        self.ereignisse = ereignisse
        self._sperre = threading.Lock()          # nur eine Ausgabe gleichzeitig
        self._stop = threading.Event()           # laufende Ausgabe abbrechen
        self._stimmen_cache: list[str] = []

    # ── Öffentliche API ──────────────────────────────────────────────────
    def sagen(self, text: str) -> None:
        """Text anzeigen-unabhängig vorlesen (blockiert bis zum Ende)."""
        text = (text or "").strip()
        if not text:
            return
        with self._sperre:
            self._stop.clear()
            letzter_fehler = None
            for engine in self._engine_reihenfolge():
                try:
                    if engine == "edge":
                        self._sage_edge(text)
                    else:
                        self._sage_windows(text)
                    return
                except Exception as fehler:
                    letzter_fehler = fehler
            self.ereignisse.sende(
                "chat_system",
                text=f"⚠️ Sprachausgabe fehlgeschlagen: {letzter_fehler}")

    def stoppen(self) -> None:
        """Aktuelle Sprachausgabe sofort abbrechen."""
        self._stop.set()
        if sd is not None:
            try:
                sd.stop()
            except Exception:
                pass

    def beep(self, art: str = "zuhoeren") -> None:
        """Kurzer Signalton (z. B. wenn das Aktivierungswort erkannt wurde)."""
        if not self.konfig.get("general", "piepser") or np is None or sd is None:
            return
        try:
            rate = 24000
            def ton(frequenz, dauer):
                t = np.linspace(0.0, dauer, int(rate * dauer), endpoint=False)
                huelle = np.sin(np.pi * np.linspace(0.0, 1.0, len(t)))
                return 0.28 * huelle * np.sin(2 * np.pi * frequenz * t)
            if art == "zuhoeren":
                klang = np.concatenate([ton(740, 0.09), np.zeros(int(rate * 0.03)),
                                        ton(1100, 0.12)])
            else:
                klang = ton(520, 0.14)
            self._spiele(klang.astype("float32"), rate)
        except Exception:
            pass                                   # Ton ist nur Deko – nie kritisch

    def stimmen_async_laden(self) -> None:
        """Edge-Stimmliste im Hintergrund laden und per Ereignis melden."""
        def arbeit():
            try:
                stimmen = asyncio.run(edge_tts.list_voices())
                kurznamen = [v["ShortName"] for v in stimmen
                             if v.get("ShortName")]
                # Deutsche zuerst, danach alphabetisch
                kurznamen.sort(key=lambda n: (not n.lower().startswith("de"), n))
                self._stimmen_cache = kurznamen
                self.ereignisse.sende("stimmen", liste=kurznamen)
            except Exception:
                self.ereignisse.sende("stimmen", liste=list(EDGE_STIMMEN_FALLBACK))
        threading.Thread(target=arbeit, daemon=True, name="UmiStimmen").start()

    def stimmen_liste(self) -> list[str]:
        return self._stimmen_cache or list(EDGE_STIMMEN_FALLBACK)

    # ── Interna ──────────────────────────────────────────────────────────
    def _engine_reihenfolge(self) -> list[str]:
        anbieter = (self.konfig.get("sprache_tts", "anbieter") or "auto")
        stimme = self.konfig.get("sprache_tts", "stimme") or ""
        if anbieter == "edge":
            return ["edge"]
        if anbieter == "windows":
            return ["windows"]
        # auto: gewählte Stimme hat Vorrang, danach der jeweils andere
        if stimme.startswith("sapi:"):
            return ["windows", "edge"]
        return ["edge", "windows"]

    def _sage_edge(self, text: str) -> None:
        if edge_tts is None:
            raise RuntimeError("Das Paket „edge-tts“ ist nicht installiert.")
        stimme = (self.konfig.get("sprache_tts", "stimme") or "edge:de-DE-KatjaNeural")
        stimme = stimme.split("edge:", 1)[-1]
        tempo = int(self.konfig.get("sprache_tts", "tempo") or 0)
        mp3 = asyncio.run(self._edge_synthetisieren(text, stimme, tempo))
        if sf is None or np is None:
            raise RuntimeError("„soundfile“/„numpy“ fehlen für die Wiedergabe.")
        pcm, rate = sf.read(io.BytesIO(mp3), dtype="float32", always_2d=True)
        pcm = pcm.flatten()
        laut = min(100, max(0, int(self.konfig.get("sprache_tts", "lautstaerke") or 80)))
        gain = (laut / 100.0) ** 1.5               # Kurve: leise bleibt leiser
        pcm = np.clip(pcm * gain, -1.0, 1.0)
        self._spiele(pcm, rate)

    @staticmethod
    async def _edge_synthetisieren(text: str, stimme: str, tempo: int) -> bytes:
        async def erzeugen():
            buf = bytearray()
            kommunikation = edge_tts.Communicate(text, stimme,
                                                 rate=f"{tempo:+d}%",
                                                 volume="+0%")
            async for stueck in kommunikation.stream():
                if stueck["type"] == "audio":
                    buf.extend(stueck["data"])
            return bytes(buf)

        async def mit_timeout():
            if hasattr(asyncio, "timeout"):        # 3.11+, sonst ohne Timeout  # novm
                async with asyncio.timeout(30):
                    return await erzeugen()
            return await erzeugen()

        return await mit_timeout()

    def _sage_windows(self, text: str) -> None:
        if pyttsx3 is None:
            raise RuntimeError("Das Paket „pyttsx3“ ist nicht installiert.")
        tempo = int(self.konfig.get("sprache_tts", "tempo") or 0)
        laut = min(100, max(0, int(self.konfig.get("sprache_tts", "lautstaerke") or 80)))
        stimme = self.konfig.get("sprache_tts", "stimme") or ""
        engine = pyttsx3.init()
        try:
            if stimme.startswith("sapi:"):
                ziel = stimme.split("sapi:", 1)[-1].lower()
                for v in engine.getProperty("voices"):
                    if ziel in (v.name or "").lower() or ziel in (v.id or "").lower():
                        engine.setProperty("voice", v.id)
                        break
            engine.setProperty("rate", int(180 + tempo * 0.9))
            engine.setProperty("volume", laut / 100.0)
            engine.say(text)
            engine.runAndWait()
        finally:
            try:
                engine.stop()
            except Exception:
                pass

    def _spiele(self, pcm: "np.ndarray", rate: int) -> None:
        """Spielt float32-PCM ab (abrufbar stoppbar über self._stop)."""
        if sd is None:
            raise RuntimeError("„sounddevice“ ist nicht installiert – "
                               "keine Audio-Wiedergabe möglich.")
        geraet = geraet_finden(self.konfig.get("audio", "ausgang") or "",
                               eingang=False)
        sd.play(pcm, rate, device=geraet)
        while sd.playing() and not self._stop.is_set():
            time.sleep(0.04)
        sd.stop()


def geraet_finden(name: str, eingang: bool):
    """Sucht den Geräte-Index anhand des Namens (None = Systemstandard)."""
    if sd is None or not name:
        return None
    try:
        alle = sd.query_devices()
    except Exception:
        return None
    kanal = "max_input_channels" if eingang else "max_output_channels"
    for index, geraet in enumerate(alle):
        if geraet.get("name") == name and geraet.get(kanal, 0) > 0:
            return index
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  7) SPRACHERKENNUNG (Speech-to-Text) – Google Web Speech API
# ─────────────────────────────────────────────────────────────────────────────

class SprachErkenner:
    """
    Wandelt rohe PCM-Aufnahmen (int16, mono) in Text um.

    Wir nutzen die Google Web Speech API über das Paket SpeechRecognition
    (kostenlos, ohne eigenen API-Schlüssel, benötigt aber Internet). Die Klasse
    ist bewusst austauschbar: Für eine lokale Erkennung (z. B. faster-whisper)
    genügt es, `transkribieren` zu ersetzen.
    """

    def __init__(self, konfig: Konfiguration):
        self.konfig = konfig

    @property
    def sprache(self) -> str:
        return self.konfig.get("general", "sprache_stt") or "de-DE"

    def transkribieren(self, pcm: "np.ndarray", rate: int) -> tuple[str, str]:
        """
        Rückgabe: (text, fehler). `fehler` ist None bei Erfolg,
        "netz" bei Verbindungsproblemen, sonst eine Klartext-Beschreibung.
        """
        if sr is None:
            return "", ("Das Paket „SpeechRecognition“ ist nicht installiert "
                        "(pip install SpeechRecognition).")
        audio = sr.AudioData(pcm.tobytes(), rate, 2)
        erkenner = sr.Recognizer()
        try:
            text = erkenner.recognize_google(audio, language=self.sprache)
            return (text or "").strip(), None
        except sr.UnknownValueError:
            return "", None                        # unverständlich = kein Text
        except sr.RequestError as fehler:
            return "", "netz"
        except Exception as fehler:
            return "", f"Spracherkennung fehlgeschlagen: {fehler}"


# ─────────────────────────────────────────────────────────────────────────────
#  8) GESPRÄCHS-WORKER – denkt nach und spricht (eigener Thread)
# ─────────────────────────────────────────────────────────────────────────────

class GespraechsWorker(threading.Thread):
    """
    Nimmt Fragen (aus Texteingabe oder Sprache) entgegen und arbeitet sie
    nacheinander ab: Antwort ermitteln → anzeigen → vorlesen.

    `busy` teilt der Sprach-Engine mit, dass Umi gerade beschäftigt ist
    (das Mikrofon soll nicht mithören, während Umi selbst spricht).
    """

    def __init__(self, konfig: Konfiguration, ereignisse: EreignisBus,
                 gehirn: UmiGehirn, sprecher: Sprecher):
        super().__init__(daemon=True, name="UmiGespraech")
        self.konfig = konfig
        self.ereignisse = ereignisse
        self.gehirn = gehirn
        self.sprecher = sprecher
        self.busy = threading.Event()
        self._auftraege: "queue.Queue[dict]" = queue.Queue()
        self._stop = threading.Event()

    # ── Öffentliche API ──────────────────────────────────────────────────
    def frage(self, text: str, quelle: str = "text") -> None:
        self._auftraege.put({"art": "frage", "text": text, "quelle": quelle})

    def mitteilung(self, text: str) -> None:
        """Direkt anzeigen + vorlesen (z. B. Timer-Erinnerung)."""
        self._auftraege.put({"art": "mitteilung", "text": text})

    def beenden(self) -> None:
        self._stop.set()
        self._auftraege.put({"art": "mitteilung", "text": ""})  # aufwecken

    # ── Thread-Arbeit ────────────────────────────────────────────────────
    def run(self) -> None:
        while not self._stop.is_set():
            try:
                auftrag = self._auftraege.get(timeout=0.25)
            except queue.Empty:
                continue
            text = (auftrag.get("text") or "").strip()
            if not text:
                continue
            self.busy.set()
            try:
                if auftrag["art"] == "frage":
                    self.ereignisse.sende("status", zustand="thinking")
                    start = time.time()
                    antwort = self.gehirn.antworten(text, auftrag.get("quelle", "text"))
                    # Kurze Mindest-Denkzeit, damit der Status ruhig wirkt
                    rest = 0.45 - (time.time() - start)
                    if rest > 0:
                        time.sleep(rest)
                else:
                    antwort = text
                self.ereignisse.sende("chat_umi", text=antwort)
                if self.konfig.get("general", "tts_aktiv"):
                    self.ereignisse.sende("status", zustand="speaking")
                    self.sprecher.sagen(antwort)
            except Exception as fehler:
                self.ereignisse.sende(
                    "chat_system",
                    text=f"⚠️ Interner Fehler im Gesprächs-Worker: {fehler}")
            finally:
                self.busy.clear()
                self.ereignisse.sende("status", zustand="ready")


# ─────────────────────────────────────────────────────────────────────────────
#  9) SPRACH-ENGINE – Mikrofon, Wake-Wort, Aufnahme (eigener Thread)
# ─────────────────────────────────────────────────────────────────────────────

class SprachEngine(threading.Thread):
    """
    Die Stimme von Umi – ein Hintergrund-Thread, der dauerhaft lauscht:

      • Modus „wake“   : lauscht passiv auf das Aktivierungswort („Hey Umi“)
      • Modus „warten“ : hat das Wake-Wort gehört und erwartet den Befehl
      • Modus „command“: Aufnahme per Mikrofon-Taste (Push-to-Talk)
      • Modus „idle“   : Sprachsteuerung aus – nur Taste nutzbar

    Sprachaktivität wird über die Lautstärke (RMS) erkannt; Aufnahmen enden
    nach einer konfigurierbaren Sprechpause. Erkannte Befehle gehen an den
    GespraechsWorker weiter.
    """

    def __init__(self, konfig: Konfiguration, ereignisse: EreignisBus,
                 erkenner: SprachErkenner, sprecher: Sprecher,
                 worker: GespraechsWorker):
        super().__init__(daemon=True, name="UmiSprache")
        self.konfig = konfig
        self.ereignisse = ereignisse
        self.erkenner = erkenner
        self.sprecher = sprecher
        self.worker = worker

        self._stop = threading.Event()
        self._neu_oeffnen = threading.Event()    # Gerät geändert → Stream neu
        self._aufnahme_wunsch = threading.Event()   # Mikrofon-Taste gedrückt
        self._aufnahme_abbrechen = threading.Event()  # Taste nochmal gedrückt
        self._wake = bool(konfig.get("general", "wake_aktiv"))

    # ── Öffentliche Steuerung (aus der GUI heraus) ───────────────────────
    def beenden(self) -> None:
        self._stop.set()

    def aufnahme_anfordern(self) -> None:
        """Mikrofon-Taste: sofort einen Befehl aufnehmen."""
        self._aufnahme_wunsch.set()

    def aufnahme_stoppen(self) -> None:
        """Mikrofon-Taste erneut: laufende Aufnahme jetzt auswerten."""
        self._aufnahme_abbrechen.set()

    def neu_starten(self) -> None:
        """Einstellungen (Gerät/Samplerate) haben sich geändert."""
        self._neu_oeffnen.set()

    def wake_setzen(self, aktiv: bool, speichern: bool = True) -> None:
        """Aktivierungswort ein-/ausschalten."""
        self._wake = aktiv
        if speichern:
            self.konfig.setze("general", "wake_aktiv", aktiv)
            self.konfig.speichern()
        self.ereignisse.sende("wake_aenderung", aktiv=aktiv)

    # ── Thread-Hauptlauf ─────────────────────────────────────────────────
    def run(self) -> None:
        self.ereignisse.sende("status", zustand="ready")
        if sd is None or np is None:
            self.ereignisse.sende("status", zustand="error", text="Kein Audio")
            grund = IMPORT_FEHLER.get("sounddevice") or IMPORT_FEHLER.get("numpy") or ""
            self.ereignisse.sende(
                "chat_system",
                text="❌ Mikrofon-Module fehlen. Bitte im Terminal ausführen:\n"
                     "pip install numpy sounddevice soundfile SpeechRecognition\n"
                     + (f"Technischer Grund: {grund}" if grund else ""))
            return
        try:
            stream = self._stream_oeffnen()
        except Exception as fehler:
            self.ereignisse.sende("status", zustand="error", text="Mikrofon")
            self.ereignisse.sende(
                "chat_system",
                text="❌ Auf das Mikrofon konnte nicht zugegriffen werden.\n"
                     "Bitte prüfe:\n"
                     "• Ist ein Mikrofon angeschlossen und als Standard gesetzt?\n"
                     "• Windows: Einstellungen → Datenschutz → Mikrofon → "
                     "Zugriff für Apps erlauben.\n"
                     f"Technischer Hinweis: {fehler}")
            return

        modus = "wake" if self._wake else "idle"
        ring: collections.deque = collections.deque(maxlen=PRE_ROLL_CHUNKS)
        puffer: list = []
        stimme_ms = 0
        stille_ms = 0
        abkling_bis = 0.0        # Kurze Pause nach jedem Befehl
        warte_bis = 0.0          # Timeout im Modus „warten“
        block_nr = 0

        while not self._stop.is_set():
            # ── Stream ggf. neu öffnen (Gerät wurde geändert) ────────────
            if self._neu_oeffnen.is_set():
                self._neu_oeffnen.clear()
                try:
                    stream.close()
                except Exception:
                    pass
                try:
                    stream = self._stream_oeffnen()
                    self.ereignisse.sende("chat_system",
                                          text="🔄 Audio-Einstellungen übernommen.")
                except Exception as fehler:
                    self.ereignisse.sende("status", zustand="error", text="Mikrofon")
                    self.ereignisse.sende(
                        "chat_system",
                        text=f"❌ Mikrofon konnte nicht geöffnet werden: {fehler}")
                    return

            # ── Audio-Block lesen ─────────────────────────────────────────
            try:
                roh, ueberlauf = stream.read(self._blockgroesse)
            except (Exception, OSError) as fehler:
                self.ereignisse.sende("status", zustand="error", text="Mikrofon weg")
                self.ereignisse.sende(
                    "chat_system",
                    text="❌ Das Mikrofon wurde getrennt oder gesperrt. "
                         "Bitte in den Einstellungen ein Gerät wählen.")
                return
            block = roh.flatten() if hasattr(roh, "flatten") else roh
            aktuell = pegel(block)
            block_nr += 1
            if block_nr % 3 == 0:
                self.ereignisse.sende("level", wert=min(1.0, aktuell * 14))

            # ── Während Umi denkt/spricht: nicht mithören ────────────────
            if self.worker.busy.is_set():
                ring.clear()
                puffer, stimme_ms, stille_ms = [], 0, 0
                continue

            # ── Wake-Wort umschaltet? Modus sofort anpassen ───────────────
            basis_modus = self._basis_modus()
            if modus in ("idle", "wake") and modus != basis_modus:
                modus = basis_modus
                puffer, stimme_ms, stille_ms = [], 0, 0
                self.ereignisse.sende("status", zustand="ready")
                continue

            pause_ms = int(self.konfig.get("audio", "sprechpause_ms") or 1100)
            max_ms = int(float(self.konfig.get("audio", "max_laenge_s") or 12) * 1000)
            empfindlichkeit = self.konfig.get("audio", "empfindlichkeit")
            schwelle = empfindlichkeit_zu_schwellwert(
                35 if empfindlichkeit is None else int(empfindlichkeit))

            # ── Push-to-Talk-Anfrage aus der GUI? ────────────────────────
            if (self._aufnahme_wunsch.is_set() and modus != "command"
                    and time.time() > abkling_bis):
                self._aufnahme_wunsch.clear()
                self._aufnahme_abbrechen.clear()
                modus = "command"
                puffer = list(ring) + [block]
                ring.clear()
                stimme_ms = CHUNK_MS if aktuell >= schwelle else 0
                stille_ms = 0
                self.ereignisse.sende("aufnahme_start")
                self.ereignisse.sende("status", zustand="listening")
                continue

            # ── Timeout im „warten“-Modus (kein Befehl gefolgt) ──────────
            if modus == "warten" and time.time() > warte_bis:
                self.ereignisse.sende(
                    "chat_system", text="Ich habe leider nichts gehört.")
                self.ereignisse.sende("status", zustand="ready")
                modus = self._basis_modus()
                puffer, stimme_ms, stille_ms = [], 0, 0
                continue

            # ── Modus „idle“: nur Puffern, nichts tun ────────────────────
            if modus == "idle":
                ring.append(block)
                continue

            # ── Sprachaktivität erkennen (wake/warten/command) ───────────
            if not puffer:
                ring.append(block)
                if time.time() > abkling_bis and aktuell >= schwelle:
                    puffer = list(ring)
                    ring.clear()
                    stimme_ms, stille_ms = CHUNK_MS, 0
                    self.ereignisse.sende("status", zustand="listening")
                continue

            # Aufnahme läuft: Blöcke sammeln, Stille messen
            puffer.append(block)
            if aktuell >= schwelle:
                stimme_ms += CHUNK_MS
                stille_ms = 0
            else:
                stille_ms += CHUNK_MS

            fertig = ((stimme_ms >= 250 and stille_ms >= pause_ms)
                      or len(puffer) * CHUNK_MS >= max_ms
                      or (modus == "command" and self._aufnahme_abbrechen.is_set()
                          and stimme_ms >= 250))
            if fertig:
                self._aufnahme_abbrechen.clear()
                pcm = np.concatenate(puffer)
                puffer, stimme_ms, stille_ms = [], 0, 0
                if modus == "command":
                    self.ereignisse.sende("aufnahme_ende")
                abkling_bis = time.time() + 1.2
                modus, warte_bis = self._utterance_verarbeiten(pcm, modus)

        try:
            stream.close()
        except Exception:
            pass

    # ── Interna ──────────────────────────────────────────────────────────
    def _basis_modus(self) -> str:
        return "wake" if self._wake else "idle"

    def _stream_oeffnen(self):
        rate = int(self.konfig.get("audio", "sample_rate") or 16000)
        geraet = geraet_finden(self.konfig.get("audio", "eingang") or "",
                               eingang=True)
        self._blockgroesse = int(rate * CHUNK_SEK)
        stream = sd.InputStream(samplerate=rate, channels=1, dtype="int16",
                                blocksize=self._blockgroesse, device=geraet)
        stream.start()
        return stream

    def _utterance_verarbeiten(self, pcm: "np.ndarray", modus: str):
        """
        Wertet eine aufgenommene Äußerung aus.
        Rückgabe: (neuer Modus, Zeitlimit für „warten“).
        """
        basis = self._basis_modus()
        dauer_s = len(pcm) / float(self.konfig.get("audio", "sample_rate") or 16000)
        if dauer_s < 0.35:                        # nur Rascheln – ignorieren
            self.ereignisse.sende("status", zustand="ready")
            return basis, 0.0

        rate = int(self.konfig.get("audio", "sample_rate") or 16000)
        text, fehler = self.erkenner.transkribieren(pcm, rate)

        if fehler == "netz":
            self.ereignisse.sende(
                "chat_system",
                text="❌ Die Spracherkennung ist gerade nicht erreichbar. "
                     "Bitte prüfe deine Internetverbindung.")
            self.ereignisse.sende("status", zustand="ready")
            return basis, 0.0
        if fehler:
            self.ereignisse.sende("chat_system", text=f"⚠️ {fehler}")
            self.ereignisse.sende("status", zustand="ready")
            return basis, 0.0

        if modus == "wake":
            gefunden, rest = enthaelt_wake_wort(text)
            if not gefunden:
                # Kein Aktivierungswort → still weiterlauschen
                self.ereignisse.sende("status", zustand="ready")
                return basis, 0.0
            self.ereignisse.sende("wake_erkannt", text=text)
            self.sprecher.beep("zuhoeren")
            rest = rest.strip()
            if rest:                              # Befehl direkt im Satz
                self._frage_stellen(rest)
                return basis, 0.0
            return "warten", time.time() + 8      # erst Wake-Wort gehört

        if not text:
            self.ereignisse.sende(
                "chat_system",
                text="🤔 Ich habe dich nicht verstanden. Versuch es bitte noch einmal.")
            self.ereignisse.sende("status", zustand="ready")
            return basis, 0.0

        self._frage_stellen(text)
        return basis, 0.0

    def _frage_stellen(self, text: str) -> None:
        self.ereignisse.sende("chat_user", text=f"🎤 {text}")
        self.worker.frage(text, quelle="sprache")


# ─────────────────────────────────────────────────────────────────────────────
# 10) GRAFISCHE BENUTZEROBERFLÄCHE (tkinter) – dunkles, modernes Chat-Design
# ─────────────────────────────────────────────────────────────────────────────

# Farbwelt (dunkles Theme)
F_BG      = "#0e1320"     # Fenster-Hintergrund
F_PANEL   = "#141c2e"     # Kopf-/Fußleiste, Eingabefeld
F_FLAECH  = "#1b2334"     # Eingabefeld
F_UMI     = "#1e2740"     # Chat-Bubble von Umi
F_UMI_R   = "#2b3854"     # … Rand
F_USER    = "#2f6bff"     # Chat-Bubble des Benutzers
F_AKZENT  = "#4f8cff"     # Akzentfarbe (Buttons, Logo)
F_TEXT    = "#e8ecf5"     # Normaler Text
F_GRAU    = "#93a0b8"     # Sekundärer Text
F_GRAU2   = "#5b6880"     # Tertiärer Text


# ─────────────────────────────────────────────────────────────────────────────
# 10) GRAFISCHE BENUTZEROBERFLÄCHE (tkinter) – dunkles, modernes Chat-Design
# ─────────────────────────────────────────────────────────────────────────────
if TKINTER_OK:
    class StatusAnzeige(tk.Canvas):
        """Abgerundete Status-Pill im Kopf der Oberfläche (Canvas-gemalt)."""

        BREITE, HOEHE = 196, 34

        def __init__(self, master):
            super().__init__(master, width=self.BREITE, height=self.HOEHE,
                             bg=F_PANEL, highlightthickness=0)
            self.zustand = "ready"
            self.phase = 0.0

        def setzen(self, zustand: str) -> None:
            self.zustand = zustand if zustand in STATUS_STILE else "ready"
            self.zeichnen(puls=0.0)

        def tick(self) -> None:
            """Wird periodisch aufgerufen – lässt „Hört zu“ sanft pulsieren."""
            if self.zustand == "listening":
                self.phase += 0.12
                self.zeichnen(puls=(math.sin(self.phase) + 1) / 2)
            else:
                self.zeichnen(puls=0.0)

        def zeichnen(self, puls: float = 0.0) -> None:
            farbe, text = STATUS_STILE[self.zustand]
            self.delete("all")
            w, h = self.BREITE, self.HOEHE
            r = h / 2
            # Abgerundete Pill (Polygon mit geglätteten Ecken)
            punkte = [r, 0, w - r, 0, w, 0, w, r, w, h - r, w, h,
                      w - r, h, r, h, 0, h, 0, h - r, 0, r, 0, 0]
            self.create_polygon(punkte, smooth=True, fill="#10192b", outline="")
            # Farbiger Status-Punkt (pulsiert, während Umi zuhört)
            faktor = 1.0 + 0.35 * puls
            pr = 5.0 * faktor
            cx = 20
            self.create_oval(cx - pr, h / 2 - pr, cx + pr, h / 2 + pr, fill=farbe,
                             outline="")
            self.create_text(36, h / 2, anchor="w", text=text, fill=farbe,
                             font=(SCHRIFTART, 11, "bold"))


    class ChatFlaeche(tk.Canvas):
        """
        Scrollbare Chat-Ansicht mit abgerundeten Sprechblasen:
          • „user“   rechts, blaue Bubble, Sprecher „Du“
          • „umi“    links, dunkle Bubble, Sprecher „Umi“
          • „system“ zentriert, kursiv (Hinweise/Fehler)
        """

        ABSTAND = 46             # Platz links/rechts für den Avatar

        def __init__(self, master):
            super().__init__(master, bg=F_BG, highlightthickness=0, bd=0)
            self.nachrichten: list[dict] = []
            self._scrollbar = ttk.Scrollbar(master, orient="vertical",
                                            command=self.yview)
            self.configure(yscrollcommand=self._scrollbar.set)
            self.bind("<Configure>", lambda e: self.zeichnen())   # Größenänderung
            self.bind_all("<MouseWheel>", self._mausrad)          # Windows/macOS
            self.bind("<Button-4>", lambda e: self.yview_scroll(-3, "units"))
            self.bind("<Button-5>", lambda e: self.yview_scroll(3, "units"))
            self.font_text = tkfont.Font(family=SCHRIFTART, size=11)
            self.font_meta = tkfont.Font(family=SCHRIFTART, size=9)

        # ── Nachrichten ──────────────────────────────────────────────────────
        def hinzufuegen(self, rolle: str, text: str) -> None:
            zeit = dt.datetime.now().strftime("%H:%M")
            self.nachrichten.append({"rolle": rolle, "text": text, "zeit": zeit})
            self.zeichnen()
            self.yview_moveto(1.0)

        def leeren(self) -> None:
            self.nachrichten.clear()
            self.zeichnen()

        # ── Zeichnen ─────────────────────────────────────────────────────────
        def zeichnen(self) -> None:
            self.delete("all")
            breite = max(self.winfo_width(), 200)
            y = 18
            for nachricht in self.nachrichten:
                y = self._zeichne_nachricht(nachricht, breite, y)
            self.configure(scrollregion=(0, 0, breite, y + 20))

        def _zeichne_nachricht(self, n: dict, breite: int, y: int) -> int:
            rolle, text = n["rolle"], n["text"]
            if rolle == "system":
                tid = self.create_text(breite / 2, y, text=text, width=breite - 80,
                                       justify="center", fill=F_GRAU,
                                       font=(SCHRIFTART, 10, "italic"))
                box = self.bbox(tid)
                return (box[3] if box else y) + 18

            ist_user = rolle == "user"
            autor = "Du" if ist_user else "Umi"
            fuellung = F_USER if ist_user else F_UMI
            rand = F_USER if ist_user else F_UMI_R
            textfarbe = "#ffffff" if ist_user else F_TEXT

            max_text = max(240, breite - 2 * self.ABSTAND - 40)
            # Meta-Zeile (Autor · Uhrzeit)
            if ist_user:
                self.create_text(breite - self.ABSTAND, y, anchor="ne",
                                 text=f"{autor} · {n['zeit']}", fill=F_GRAU,
                                 font=self.font_meta)
            else:
                self.create_text(self.ABSTAND, y, anchor="nw",
                                 text=f"{autor} · {n['zeit']}", fill=F_GRAU,
                                 font=self.font_meta)
            y += 18

            # Text zuerst erzeugen, um die Größe zu messen
            if ist_user:
                tid = self.create_text(breite - self.ABSTAND, y, anchor="ne",
                                       text=text, width=max_text, justify="left",
                                       fill=textfarbe, font=self.font_text)
            else:
                tid = self.create_text(self.ABSTAND, y, anchor="nw", text=text,
                                       width=max_text, justify="left",
                                       fill=textfarbe, font=self.font_text)
            x1, y1, x2, y2 = self.bbox(tid)
            polster = 11
            bx1, by1 = x1 - polster, y1 - polster + 2
            bx2, by2 = x2 + polster, y2 + polster - 2
            self._abgerundetes_rechteck(bx1, by1, bx2, by2, 14,
                                        fill=fuellung, outline=rand)
            self.tag_raise(tid)                      # Bubble liegt hinter dem Text
            y = by2 + 16

            # Avatar-Kreis mit Anfangsbuchstaben
            r = 14
            cy = (by1 + by2) / 2
            ax = (breite - r - 8) if ist_user else (r + 8)
            self.create_oval(ax - r, cy - r, ax + r, cy + r,
                             fill="#3a4661" if ist_user else F_AKZENT, outline="")
            self.create_text(ax, cy, text="Du" if ist_user else "U",
                             fill="#ffffff", font=(SCHRIFTART, 9, "bold"))
            return y

        def _abgerundetes_rechteck(self, x1, y1, x2, y2, r, **kw):
            punkte = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
                      x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
                      x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
            return self.create_polygon(punkte, smooth=True, **kw)

        def _mausrad(self, ereignis):
            try:
                self.yview_scroll(-int(ereignis.delta / 40), "units")
            except tk.TclError:
                pass


    class EinstellungsDialog(tk.Toplevel):
        """
        Einstellungen-Fenster mit Reitern für Audio, Sprache (TTS), KI und Info.
        Änderungen werden erst bei „Speichern“ übernommen.
        """

        def __init__(self, app: "UmiApp"):
            super().__init__(app.root)
            self.app = app
            self.konfig = app.konfig
            self.title("Umi – Einstellungen")
            self.configure(bg=F_BG)
            self.transient(app.root)
            self.geometry("640x560")
            self.minsize(560, 500)
            self.grab_set()                          # modaler Dialog
            self.protocol("WM_DELETE_WINDOW", self._abbrechen)
            app._einstellungen = self                # Referenz für Live-Updates

            # ── Variablen aus der Konfiguration vorbelegen ───────────────────
            self.var_mikrofon = tk.StringVar(
                value=self.konfig.get("audio", "eingang") or "Systemstandard")
            self.var_lautsprecher = tk.StringVar(
                value=self.konfig.get("audio", "ausgang") or "Systemstandard")
            self.var_empfindlichkeit = tk.IntVar(
                value=self._gwert("audio", "empfindlichkeit", 35, int))
            self.var_pause = tk.IntVar(
                value=self._gwert("audio", "sprechpause_ms", 1100, int))
            self.var_wake = tk.BooleanVar(
                value=bool(self.konfig.get("general", "wake_aktiv")))
            self.var_stt = tk.StringVar(
                value=self.konfig.get("general", "sprache_stt") or "de-DE")
            self.var_tts_an = tk.BooleanVar(
                value=bool(self.konfig.get("general", "tts_aktiv")))
            self.var_piepser = tk.BooleanVar(
                value=bool(self.konfig.get("general", "piepser")))
            self.var_anbieter = tk.StringVar(
                value=self.konfig.get("sprache_tts", "anbieter") or "auto")
            self.var_stimme = tk.StringVar(
                value=self.konfig.get("sprache_tts", "stimme")
                or "edge:de-DE-KatjaNeural")
            self.var_tempo = tk.IntVar(
                value=self._gwert("sprache_tts", "tempo", 0, int))
            self.var_laut = tk.IntVar(
                value=self._gwert("sprache_tts", "lautstaerke", 85, int))
            self.var_ki_aktiv = tk.BooleanVar(value=bool(self.konfig.get("ki", "aktiv")))
            self.var_ki_url = tk.StringVar(value=self.konfig.get("ki", "basis_url") or "")
            self.var_ki_key = tk.StringVar(value=self.konfig.get("ki", "api_key") or "")
            self.var_ki_modell = tk.StringVar(value=self.konfig.get("ki", "modell") or "")
            self.var_ki_temp = tk.DoubleVar(
                value=self._gwert("ki", "temperatur", 0.7, float))
            self.var_stadt = tk.StringVar(
                value=self.konfig.get("wetter", "standard_stadt") or "Berlin")

            # ── Reiter anlegen ───────────────────────────────────────────────
            stil = ttk.Style(self)
            stil.configure("Umi.TNotebook", background=F_BG, borderwidth=0)
            stil.configure("Umi.TNotebook.Tab", background=F_PANEL, foreground=F_TEXT,
                           padding=(14, 8))
            stil.map("Umi.TNotebook.Tab",
                     background=[("selected", F_AKZENT)],
                     foreground=[("selected", "#ffffff")])
            notiz = ttk.Notebook(self, style="Umi.TNotebook")
            notiz.pack(fill="both", expand=True, padx=12, pady=(12, 0))

            self._tab_audio(notiz)
            self._tab_sprache(notiz)
            self._tab_ki(notiz)
            self._tab_info(notiz)

            # ── Schaltflächen unten ──────────────────────────────────────────
            leiste = tk.Frame(self, bg=F_BG)
            leiste.pack(fill="x", padx=12, pady=10)
            tk.Button(leiste, text="💾 Speichern", command=self._speichern,
                      bg=F_AKZENT, fg="#ffffff", activebackground="#3f78e0",
                      activeforeground="#ffffff", relief="flat", bd=0,
                      padx=18, pady=7, cursor="hand2",
                      font=(SCHRIFTART, 10, "bold")).pack(side="right")
            tk.Button(leiste, text="Abbrechen", command=self._abbrechen,
                      bg=F_PANEL, fg=F_TEXT, activebackground="#20293f",
                      activeforeground=F_TEXT, relief="flat", bd=0,
                      padx=14, pady=7, cursor="hand2",
                      font=(SCHRIFTART, 10)).pack(side="right", padx=8)

        # ── Hilfs-Widgets ────────────────────────────────────────────────────
        def _seite(self, notebook, titel: str) -> tk.Frame:
            seite = tk.Frame(notebook, bg=F_BG)
            notebook.add(seite, text=f"  {titel}  ")
            return seite

        def _zeile(self, eltern, beschriftung) -> tk.Frame:
            zeile = tk.Frame(eltern, bg=F_BG)
            zeile.pack(fill="x", pady=(10, 2))
            tk.Label(zeile, text=beschriftung, bg=F_BG, fg=F_GRAU,
                     font=(SCHRIFTART, 10)).pack(anchor="w")
            return zeile

        def _entry(self, eltern, variable, zeigen="") -> tk.Entry:
            e = tk.Entry(eltern, textvariable=variable, bg=F_FLAECH, fg=F_TEXT,
                         insertbackground=F_TEXT, relief="flat", bd=0,
                         font=(SCHRIFTART, 11), show=zeigen)
            e.pack(fill="x", ipady=6)
            return e

        def _kombi(self, eltern, variable, werte) -> ttk.Combobox:
            k = ttk.Combobox(eltern, textvariable=variable, values=werte,
                             state="readonly", font=(SCHRIFTART, 10))
            k.pack(fill="x", ipady=3)
            return k

        def _schalter(self, eltern, text, variable) -> tk.Checkbutton:
            return tk.Checkbutton(eltern, text=text, variable=variable,
                                  bg=F_BG, fg=F_TEXT, selectcolor=F_FLAECH,
                                  activebackground=F_BG, activeforeground=F_TEXT,
                                  highlightthickness=0, bd=0, anchor="w",
                                  font=(SCHRIFTART, 11))

        def _schieber(self, eltern, von, bis, variable, aufloesung=1) -> tk.Scale:
            return tk.Scale(eltern, from_=von, to=bis, orient="horizontal",
                            variable=variable, resolution=aufloesung, bg=F_BG,
                            fg=F_GRAU, highlightthickness=0, troughcolor=F_FLAECH,
                            activebackground=F_AKZENT, bd=0, length=260,
                            font=(SCHRIFTART, 8), showvalue=True)

        def _gwert(self, abschnitt, schluessel, standard, typ):
            """Konfigurationswert lesen, der 0 als gültigen Wert erlaubt."""
            wert = self.konfig.get(abschnitt, schluessel)
            return typ(standard if wert is None else wert)

        # ── Reiter: Audio ────────────────────────────────────────────────────
        def _tab_audio(self, notiz):
            seite = self._seite(notiz, "🎙 Audio")

            zeile = self._zeile(seite, "Mikrofon")
            self.kombi_mikrofon = self._kombi(zeile, self.var_mikrofon, [])
            self._mikrofone_laden()

            zeile = self._zeile(seite, "Lautsprecher")
            self.kombi_lautsprecher = self._kombi(zeile, self.var_lautsprecher, [])
            self._lautsprecher_laden()

            zeile = self._zeile(seite,
                                "Mikrofon-Empfindlichkeit (höher = Umi reagiert leiser)")
            self._schieber(zeile, 0, 100, self.var_empfindlichkeit).pack(anchor="w")

            zeile = self._zeile(seite, "Sprechpause, die einen Satz beendet (ms)")
            self._schieber(zeile, 500, 2500, self.var_pause, 50).pack(anchor="w")

            self._schalter(seite, "🔔 Auf Aktivierungswort „Hey Umi“ lauschen",
                           self.var_wake).pack(anchor="w", pady=(12, 0))

            zeile = self._zeile(seite, "Erkennungssprache")
            self._kombi(zeile, self.var_stt,
                        ["de-DE", "de-AT", "de-CH", "en-US", "en-GB", "fr-FR",
                         "es-ES", "it-IT", "nl-NL", "pl-PL", "tr-TR", "ru-RU"])

            zeile = self._zeile(seite, "Mikrofon-Test (3 Sekunden)")
            tk.Button(zeile, text="🎙 Mikrofon testen", command=self._test_mikrofon,
                      bg=F_PANEL, fg=F_TEXT, activebackground="#20293f",
                      relief="flat", bd=0, padx=12, pady=6, cursor="hand2",
                      font=(SCHRIFTART, 10)).pack(anchor="w")
            self.lbl_mikrofon_test = tk.Label(zeile, text="", bg=F_BG, fg=F_GRAU,
                                              font=(SCHRIFTART, 10))
            self.lbl_mikrofon_test.pack(anchor="w", pady=(4, 0))

        # ── Reiter: Sprache (TTS) ────────────────────────────────────────────
        def _tab_sprache(self, notiz):
            seite = self._seite(notiz, "🔊 Sprache")

            self._schalter(seite, "🗣 Antworten laut vorlesen (Text-to-Speech)",
                           self.var_tts_an).pack(anchor="w")
            self._schalter(seite, "🔔 Signalton bei erkanntem Aktivierungswort",
                           self.var_piepser).pack(anchor="w")

            zeile = self._zeile(seite, "Sprachausgabe-Engine")
            self._kombi(zeile, self.var_anbieter, ["auto", "edge", "windows"])

            zeile = self._zeile(seite,
                                "Stimme  („edge:“ = natürlich & online, "
                                "„sapi:“ = Windows-Offline-Stimme)")
            self.kombi_stimme = self._kombi(zeile, self.var_stimme, [])
            self._stimmen_laden()
            tk.Button(zeile, text="Stimmliste neu laden", command=self._stimmen_laden,
                      bg=F_PANEL, fg=F_TEXT, activebackground="#20293f",
                      relief="flat", bd=0, padx=10, pady=5, cursor="hand2",
                      font=(SCHRIFTART, 9)).pack(anchor="w", pady=(6, 0))

            zeile = self._zeile(seite, "Sprechtempo (−50 langsam … +50 schnell)")
            self._schieber(zeile, -50, 50, self.var_tempo, 5).pack(anchor="w")

            zeile = self._zeile(seite, "Lautstärke")
            self._schieber(zeile, 0, 100, self.var_laut, 5).pack(anchor="w")

            zeile = self._zeile(seite, "Stimme testen")
            tk.Button(zeile, text="🔊 Testansage", command=self._test_stimme,
                      bg=F_PANEL, fg=F_TEXT, activebackground="#20293f",
                      relief="flat", bd=0, padx=12, pady=6, cursor="hand2",
                      font=(SCHRIFTART, 10)).pack(anchor="w")

        # ── Reiter: KI ───────────────────────────────────────────────────────
        def _tab_ki(self, notiz):
            seite = self._seite(notiz, "🧠 KI")
            hinweis = tk.Label(
                seite, justify="left", bg=F_BG, fg=F_GRAU,
                font=(SCHRIFTART, 10), wraplength=560, text=(
                    "Freie Gesprächsantworten kommen von einer OpenAI-kompatiblen "
                    "Chat-API. Beispiele:\n"
                    "• OpenAI:  https://api.openai.com/v1   (Modell z. B. "
                    "gpt-4o-mini, API-Key erforderlich)\n"
                    "• Ollama (lokal):  http://localhost:11434/v1   (Modell z. B. "
                    "llama3.2, Key frei wählbar)\n"
                    "• LM Studio (lokal):  http://localhost:1234/v1"))
            hinweis.pack(anchor="w", pady=(4, 8))

            self._schalter(seite, "🧠 Online-KI für freie Fragen aktivieren",
                           self.var_ki_aktiv).pack(anchor="w", pady=(6, 0))

            zeile = self._zeile(seite, "Basis-URL")
            self._entry(zeile, self.var_ki_url)
            zeile = self._zeile(seite,
                                "API-Schlüssel (bleibt nur lokal auf diesem PC)")
            self._entry(zeile, self.var_ki_key, zeigen="*")
            zeile = self._zeile(seite, "Modell")
            self._entry(zeile, self.var_ki_modell)
            zeile = self._zeile(seite, "Kreativität (Temperatur 0–1)")
            self._schieber(zeile, 0.0, 1.0, self.var_ki_temp, 0.1).pack(anchor="w")
            zeile = self._zeile(seite, "Standard-Stadt für Wetterfragen")
            self._entry(zeile, self.var_stadt)

        # ── Reiter: Info ─────────────────────────────────────────────────────
        def _tab_info(self, notiz):
            seite = self._seite(notiz, "ℹ️ Info")
            info = (
                f"{APP_NAME} v{APP_VERSION} – persönlicher KI-Assistent\n\n"
                "Spracherkennung: Google Web Speech API (kostenlos, benötigt "
                "Internet).\n"
                "Sprachausgabe: Edge TTS (online, natürliche Stimmen) mit Fallback "
                "auf\nWindows-SAPI-Stimmen (offline).\n\n"
                "Deine API-Schlüssel und Einstellungen werden ausschließlich lokal "
                "in\n„umi_einstellungen.json“ gespeichert.\n\n"
                "Tipp: Eigene Fähigkeiten lassen sich in der Datei "
                "umi_assistent.py\nin wenigen Zeilen ergänzen – siehe Klasse "
                "„Skill“.")
            tk.Label(seite, text=info, justify="left", bg=F_BG, fg=F_GRAU,
                     font=(SCHRIFTART, 10)).pack(anchor="w", pady=8)

        # ── Aktionsknöpfe ────────────────────────────────────────────────────
        def _mikrofone_laden(self):
            werte = ["Systemstandard"]
            if sd is not None:
                try:
                    for g in sd.query_devices():
                        if g.get("max_input_channels", 0) > 0:
                            name = g.get("name", "?")
                            if name not in werte:
                                werte.append(name)
                except Exception:
                    pass
            self.kombi_mikrofon["values"] = werte
            if self.var_mikrofon.get() not in werte:
                self.var_mikrofon.set(werte[0])

        def _lautsprecher_laden(self):
            werte = ["Systemstandard"]
            if sd is not None:
                try:
                    for g in sd.query_devices():
                        if g.get("max_output_channels", 0) > 0:
                            name = g.get("name", "?")
                            if name not in werte:
                                werte.append(name)
                except Exception:
                    pass
            self.kombi_lautsprecher["values"] = werte
            if self.var_lautsprecher.get() not in werte:
                self.var_lautsprecher.set(werte[0])

        def _stimmen_laden(self):
            """Edge-Stimmen (im Hintergrund) + Windows-Stimmen auflisten."""
            self.app.sprecher.stimmen_async_laden()
            liste = [f"edge:{name}" for name in self.app.sprecher.stimmen_liste()]
            try:
                if pyttsx3 is not None:
                    engine = pyttsx3.init()
                    for v in engine.getProperty("voices"):
                        liste.append(f"sapi:{v.name}")
                    try:
                        engine.stop()
                    except Exception:
                        pass
            except Exception:
                pass
            self.kombi_stimme["values"] = liste
            if self.var_stimme.get() not in liste:
                self.var_stimme.set(liste[0])

        def stimmen_aktualisieren(self, edge_liste):
            """Wird aufgerufen, sobald die Edge-Stimmliste geladen ist."""
            werte = [f"edge:{name}" for name in edge_liste]
            for alt in (self.kombi_stimme["values"] or ()):
                if str(alt).startswith("sapi:") and alt not in werte:
                    werte.append(str(alt))          # Windows-Stimmen anhängen
            self.kombi_stimme["values"] = werte
            if self.var_stimme.get() not in werte:
                self.var_stimme.set(werte[0])

        def _sammeln(self) -> None:
            """Werte der Steuerelemente in die Konfiguration übernehmen."""
            k = self.konfig
            k.setze("audio", "eingang",
                    "" if self.var_mikrofon.get() == "Systemstandard"
                    else self.var_mikrofon.get())
            k.setze("audio", "ausgang",
                    "" if self.var_lautsprecher.get() == "Systemstandard"
                    else self.var_lautsprecher.get())
            k.setze("audio", "empfindlichkeit", int(self.var_empfindlichkeit.get()))
            k.setze("audio", "sprechpause_ms", int(self.var_pause.get()))
            k.setze("general", "wake_aktiv", bool(self.var_wake.get()))
            k.setze("general", "sprache_stt", self.var_stt.get())
            k.setze("general", "tts_aktiv", bool(self.var_tts_an.get()))
            k.setze("general", "piepser", bool(self.var_piepser.get()))
            k.setze("sprache_tts", "anbieter", self.var_anbieter.get())
            k.setze("sprache_tts", "stimme", self.var_stimme.get())
            k.setze("sprache_tts", "tempo", int(self.var_tempo.get()))
            k.setze("sprache_tts", "lautstaerke", int(self.var_laut.get()))
            k.setze("ki", "aktiv", bool(self.var_ki_aktiv.get()))
            k.setze("ki", "basis_url", self.var_ki_url.get().strip())
            k.setze("ki", "api_key", self.var_ki_key.get().strip())
            k.setze("ki", "modell", self.var_ki_modell.get().strip())
            k.setze("ki", "temperatur", float(self.var_ki_temp.get()))
            k.setze("wetter", "standard_stadt", self.var_stadt.get().strip() or "Berlin")

        def _speichern(self) -> None:
            self._sammeln()
            self.konfig.speichern()
            self.app._einstellungen = None
            self.app.einstellungen_uebernehmen()
            self.destroy()

        def _abbrechen(self) -> None:
            self.konfig.neu_laden()                 # evtl. Test-Änderungen verwerfen
            self.app._einstellungen = None
            self.destroy()

        def _test_mikrofon(self) -> None:
            """Nimmt 3 Sekunden auf und meldet, ob ein Signal ankommt."""
            self._sammeln()

            def arbeit():
                try:
                    geraet = geraet_finden(
                        self.konfig.get("audio", "eingang") or "", eingang=True)
                    with sd.InputStream(samplerate=16000, channels=1,
                                        dtype="int16", blocksize=1600,
                                        device=geraet) as st:
                        spitze = 0.0
                        for _ in range(30):
                            daten, _ueber = st.read(1600)
                            block = (daten.flatten()
                                     if hasattr(daten, "flatten") else daten)
                            spitze = max(spitze, pegel(block))
                            time.sleep(0.1)
                    meldung = ("✅ Mikrofon funktioniert – Signal erkannt."
                               if spitze > 0.002 else
                               "⚠️ Mikrofon antwortet, aber es kommt kaum Signal an "
                               "(zu leise oder falsches Gerät?).")
                except Exception as fehler:
                    meldung = f"❌ Mikrofon-Fehler: {fehler}"
                self.after(0, lambda: self.lbl_mikrofon_test.config(text=meldung))

            threading.Thread(target=arbeit, daemon=True).start()
            self.lbl_mikrofon_test.config(text=" … höre 3 Sekunden zu …")

        def _test_stimme(self) -> None:
            self._sammeln()
            threading.Thread(
                target=lambda: self.app.sprecher.sagen(
                    "Hallo! Ich bin Umi, dein Sprachassistent. So klingt die "
                    "aktuell gewählte Stimme."),
                daemon=True).start()


    class UmiApp:
        """Das Hauptfenster – verbindet GUI, Sprach-Engine und Gesprächs-Worker."""

        def __init__(self, konfig: Konfiguration, ereignisse: EreignisBus,
                     gehirn: UmiGehirn, sprecher: Sprecher, erkenner: SprachErkenner,
                     engine: SprachEngine, worker: GespraechsWorker):
            self.konfig = konfig
            self.ereignisse = ereignisse
            self.gehirn = gehirn
            self.sprecher = sprecher
            self.erkenner = erkenner
            self.engine = engine
            self.worker = worker
            self._einstellungen = None               # geöffnetes Dialogfenster

            self.root = tk.Tk()
            self.root.title(f"{APP_NAME} – Dein persönlicher KI-Assistent")
            self.root.geometry("1020x680")
            self.root.minsize(780, 560)
            self.root.configure(bg=F_BG)
            self._stil_setzen()
            self._oberflaeche_bauen()
            self.willkommen()
            self.root.after(50, self._ereignisse_verarbeiten)

        # ── Aufbau ───────────────────────────────────────────────────────────
        def _stil_setzen(self):
            stil = ttk.Style(self.root)
            try:
                stil.theme_use("clam")
            except tk.TclError:
                pass
            stil.configure("Messbar.TProgressbar", troughcolor=F_FLAECH,
                           background=F_AKZENT, borderwidth=0, thickness=6)
            stil.configure("TCombobox", fieldbackground=F_FLAECH, background=F_PANEL,
                           foreground=F_TEXT, arrowcolor=F_TEXT, borderwidth=0)
            self.root.option_add("*TCombobox*Listbox.background", F_PANEL)
            self.root.option_add("*TCombobox*Listbox.foreground", F_TEXT)
            self.root.option_add("*TCombobox*Listbox.selectBackground", F_AKZENT)

        def _oberflaeche_bauen(self):
            # ── Kopfleiste ───────────────────────────────────────────────────
            self.kopf = tk.Frame(self.root, bg=F_PANEL, height=64)
            self.kopf.pack(fill="x")
            self.kopf.pack_propagate(False)

            logo = tk.Canvas(self.kopf, width=40, height=40, bg=F_PANEL,
                             highlightthickness=0)
            logo.create_oval(2, 2, 38, 38, fill=F_AKZENT, outline="")
            logo.create_text(20, 20, text="U", fill="#ffffff",
                             font=(SCHRIFTART, 16, "bold"))
            logo.pack(side="left", padx=(14, 8), pady=12)

            titel = tk.Frame(self.kopf, bg=F_PANEL)
            titel.pack(side="left")
            tk.Label(titel, text="Umi", bg=F_PANEL, fg=F_TEXT,
                     font=(SCHRIFTART, 17, "bold")).pack(anchor="w")
            tk.Label(titel, text="Dein persönlicher KI-Assistent", bg=F_PANEL,
                     fg=F_GRAU, font=(SCHRIFTART, 9)).pack(anchor="w")

            self.status = StatusAnzeige(self.kopf)
            self.status.pack(side="right", padx=6, pady=15)

            knopf_leiste = tk.Frame(self.kopf, bg=F_PANEL)
            knopf_leiste.pack(side="right", padx=8)
            tk.Button(knopf_leiste, text="🗑", command=self._verlauf_leeren,
                      bg=F_PANEL, fg=F_TEXT, activebackground="#20293f",
                      relief="flat", bd=0, padx=10, pady=6, cursor="hand2",
                      font=(SCHRIFTART, 12)).pack(side="left", padx=3)
            tk.Button(knopf_leiste, text="⚙", command=self._einstellungen_oeffnen,
                      bg=F_PANEL, fg=F_TEXT, activebackground="#20293f",
                      relief="flat", bd=0, padx=10, pady=6, cursor="hand2",
                      font=(SCHRIFTART, 12)).pack(side="left", padx=3)

            # ── Chat ─────────────────────────────────────────────────────────
            chat_bereich = tk.Frame(self.root, bg=F_BG)
            chat_bereich.pack(fill="both", expand=True)
            self.chat = ChatFlaeche(chat_bereich)
            self.chat._scrollbar.pack(side="right", fill="y")      # erst Scrollbalken …
            self.chat.pack(side="left", fill="both", expand=True)  # … dann Canvas

            # ── Eingabezeile ─────────────────────────────────────────────────
            eingabe_leiste = tk.Frame(self.root, bg=F_PANEL)
            eingabe_leiste.pack(fill="x", padx=10, pady=(0, 4))

            self.eingabe = tk.Entry(eingabe_leiste, bg=F_FLAECH, fg=F_GRAU2,
                                    insertbackground=F_TEXT, relief="flat", bd=0,
                                    font=(SCHRIFTART, 12))
            self.eingabe.pack(side="left", fill="x", expand=True, ipady=10,
                              padx=(8, 4), pady=8)
            self.eingabe.insert(0, "Nachricht an Umi … (Eingabetaste = senden)")
            self.eingabe.bind("<Return>", lambda e: self.senden())
            self.eingabe.bind("<FocusIn>", self._eingabe_fokus_an)
            self.eingabe.bind("<FocusOut>", self._eingabe_fokus_aus)

            tk.Button(eingabe_leiste, text="➤", command=self.senden,
                      bg=F_AKZENT, fg="#ffffff", activebackground="#3f78e0",
                      relief="flat", bd=0, padx=16, pady=9, cursor="hand2",
                      font=(SCHRIFTART, 12, "bold")).pack(side="right",
                                                          padx=(4, 8), pady=8)
            self.btn_mikrofon = tk.Button(
                eingabe_leiste, text="🎙", command=self._mikrofon_taste,
                bg=F_PANEL, fg=F_TEXT, activebackground="#20293f",
                relief="flat", bd=0, padx=13, pady=9, cursor="hand2",
                font=(SCHRIFTART, 13))
            self.btn_mikrofon.pack(side="right", padx=2, pady=8)

            # ── Fußleiste ────────────────────────────────────────────────────
            fuss = tk.Frame(self.root, bg=F_PANEL)
            fuss.pack(fill="x", side="bottom")
            tk.Label(fuss, text="Mikrofon", bg=F_PANEL, fg=F_GRAU,
                     font=(SCHRIFTART, 9)).pack(side="left", padx=(14, 6))
            self.pegel_balken = ttk.Progressbar(fuss, style="Messbar.TProgressbar",
                                                length=140, maximum=1.0,
                                                orient="horizontal",
                                                mode="determinate")
            self.pegel_balken.pack(side="left", pady=12)
            self.btn_wake = tk.Button(fuss, text="", command=self._wake_umschalten,
                                      bg=F_PANEL, fg=F_GRAU,
                                      activebackground="#20293f", relief="flat",
                                      bd=0, padx=10, cursor="hand2",
                                      font=(SCHRIFTART, 9))
            self.btn_wake.pack(side="left", padx=14)
            self._wake_knopf_text()
            tk.Label(fuss, text=f"Umi v{APP_VERSION} · Python "
                                f"{sys.version.split()[0]}",
                     bg=F_PANEL, fg=F_GRAU2, font=(SCHRIFTART, 9)).pack(
                         side="right", padx=14)

            self.root.protocol("WM_DELETE_WINDOW", self._schliessen)

        def willkommen(self):
            self.chat.hinzufuegen(
                "system",
                "Willkommen bei Umi! 👋 Tippe unten eine Nachricht, klicke auf 🎙 "
                "oder sage „Hey Umi“ – gefolgt von deinem Wunsch. „Hilfe“ zeigt "
                "alle Möglichkeiten.")

        # ── Aktionen (Haupt-Thread) ──────────────────────────────────────────
        def senden(self):
            text = self.eingabe.get().strip()
            if not text or text.startswith("Nachricht an Umi"):
                return
            self.chat.hinzufuegen("user", text)
            self._eingabe_leeren()
            self.worker.frage(text, quelle="text")

        def _mikrofon_taste(self):
            if sd is None or np is None:
                grund = IMPORT_FEHLER.get("sounddevice") or IMPORT_FEHLER.get("numpy") or ""
                self.chat.hinzufuegen(
                    "system",
                    "❌ Audio-Module fehlen – bitte im Terminal ausführen:\n"
                    "pip install numpy sounddevice soundfile SpeechRecognition\n"
                    + (f"Technischer Grund: {grund}" if grund else ""))
                return
            if self.engine.aufnahme_aktiv():
                # Zweite Betätigung: laufende Aufnahme beenden
                self.engine.aufnahme_stoppen()
            else:
                self.sprecher.stoppen()
                self.engine.aufnahme_anfordern()

        def _mikrofon_taste_normal(self):
            self.btn_mikrofon.config(bg=F_PANEL, fg=F_TEXT,
                                     activebackground="#20293f")

        def _mikrofon_taste_aktiv(self):
            self.btn_mikrofon.config(bg="#b45309", fg="#ffffff",
                                     activebackground="#d97706")

        def _wake_umschalten(self):
            neu = not bool(self.konfig.get("general", "wake_aktiv"))
            self.engine.wake_setzen(neu)        # sendet „wake_aenderung“-Event

        def _wake_knopf_text(self):
            aktiv = bool(self.konfig.get("general", "wake_aktiv"))
            self.btn_wake.config(
                text=("🔔 Aktivierungswort: AN  („Hey Umi“)" if aktiv
                      else "🔕 Aktivierungswort: AUS  (nur Mikrofon-Taste)"),
                fg=F_AKZENT if aktiv else F_GRAU)

        def _verlauf_leeren(self):
            self.chat.leeren()
            self.gehirn.gespraech_zuruecksetzen()
            self.willkommen()

        def _einstellungen_oeffnen(self):
            if self._einstellungen is not None and self._einstellungen.winfo_exists():
                self._einstellungen.lift()
                return
            EinstellungsDialog(self)            # trägt sich selbst in _einstellungen ein

        def einstellungen_uebernehmen(self):
            """Nach „Speichern“ im Einstellungsdialog: alles live aktualisieren."""
            self.engine.neu_starten()
            self.engine.wake_setzen(bool(self.konfig.get("general", "wake_aktiv")),
                                    speichern=False)
            self._wake_knopf_text()
            self.chat.hinzufuegen("system", "✅ Einstellungen gespeichert.")

        def _eingabe_fokus_an(self, _e=None):
            if self.eingabe.get().startswith("Nachricht an Umi"):
                self._eingabe_leeren()

        def _eingabe_fokus_aus(self, _e=None):
            if not self.eingabe.get().strip():
                self.eingabe.insert(0, "Nachricht an Umi … (Eingabetaste = senden)")
                self.eingabe.config(fg=F_GRAU2)

        def _eingabe_leeren(self):
            self.eingabe.delete(0, "end")
            self.eingabe.config(fg=F_TEXT)

        def _schliessen(self):
            try:
                self.sprecher.stoppen()
                self.engine.beenden()
                self.worker.beenden()
                self.gehirn.timer_abbrechen()
            finally:
                self.root.after(200, self.root.destroy)

        def starten(self):
            self.root.mainloop()

        # ── Ereignisse aus den Nebenthreads ──────────────────────────────────
        def _ereignisse_verarbeiten(self):
            for art, daten in self.ereignisse.hole():
                try:
                    if art == "status":
                        self.status.setzen(daten.get("zustand", "ready"))
                    elif art == "chat_user":
                        self.chat.hinzufuegen("user", daten["text"])
                    elif art == "chat_umi":
                        self.chat.hinzufuegen("umi", daten["text"])
                    elif art == "chat_system":
                        self.chat.hinzufuegen("system", daten["text"])
                    elif art == "level":
                        self.pegel_balken["value"] = float(daten.get("wert", 0))
                    elif art == "aufnahme_start":
                        self._mikrofon_taste_aktiv()
                    elif art == "aufnahme_ende":
                        self._mikrofon_taste_normal()
                    elif art == "wake_erkannt":
                        self.chat.hinzufuegen("system",
                                              "🔔 Aktivierungswort gehört …")
                    elif art == "wake_aenderung":
                        self.konfig.setze("general", "wake_aktiv",
                                          bool(daten.get("aktiv")))
                        self._wake_knopf_text()
                        aktiv = bool(daten.get("aktiv"))
                        self.chat.hinzufuegen(
                            "system",
                            ("🔔 Sprachsteuerung aktiv – sage „Hey Umi“." if aktiv
                             else "🔕 Sprachsteuerung pausiert – nutze die "
                                  "Mikrofon-Taste 🎙, um zu sprechen."))
                    elif art == "stimmen":
                        dialog = self._einstellungen
                        if dialog is not None and dialog.winfo_exists():
                            dialog.stimmen_aktualisieren(daten.get("liste", []))
                except Exception:
                    pass                                   # GUI-Fehler nie fatal
            self.status.tick()
            self.root.after(50, self._ereignisse_verarbeiten)


def geraete_auflisten() -> None:
    """Alle Audio-Geräte lesbar ausgeben (python umi_assistent.py --geraete)."""
    if sd is None:
        print("❌ sounddevice ist nicht installiert "
              "(pip install sounddevice).")
        return
    print(f"Standard-Eingang : {sd.default.device[0]}")
    print(f"Standard-Ausgang : {sd.default.device[1]}")
    print("-" * 70)
    try:
        for index, geraet in enumerate(sd.query_devices()):
            art = ("EINGANG " if geraet["max_input_channels"] > 0 else "")
            art += ("AUSGANG" if geraet["max_output_channels"] > 0 else "")
            print(f"[{index:2d}] {geraet['name'][:48]:<48} "
                  f"{art:>14} ({geraet['hostapi']})")
    except Exception as fehler:
        print(f"❌ Audio-Geräte konnten nicht abgefragt werden: {fehler}")


def selbsttest() -> int:
    """
    Umfangreicher Funktionstest ohne GUI – prüft Installation, Konfiguration,
    Fähigkeiten, Aktivierungswort-Erkennung, Rechner, Sprachausgabe und
    Spracherkennung. Ideal zur Fehlersuche direkt nach der Installation.
    """
    print("═" * 70)
    print(f"  {APP_NAME} v{APP_VERSION} – Selbsttest")
    print("═" * 70)
    fehler = 0
    hinweise = 0

    def ok(text):      print(f"  [OK]      {text}")
    def fehler_punkt(text):
        nonlocal fehler
        fehler += 1
        print(f"  [FEHLER]  {text}")
    def hinweis(text):
        nonlocal hinweise
        hinweise += 1
        print(f"  [HINWEIS] {text}")

    # 1) Python-Version
    print(f"\n▶ Python {sys.version.split()[0]} "
          f"(empfohlen: 3.10+, entwickelt für 3.13)")
    if sys.version_info >= (3, 10):
        ok("Python-Version geeignet")
    else:
        fehler_punkt("Python 3.10 oder neuer wird benötigt")

    # 2) Bibliotheken
    print("\n▶ Bibliotheken")
    for name, modul, noetig in [
            ("numpy", np, True), ("sounddevice", sd, True),
            ("soundfile", sf, True), ("SpeechRecognition", sr, True),
            ("edge-tts", edge_tts, True), ("pyttsx3 (optional)", pyttsx3, False)]:
        if modul is not None:
            version = getattr(modul, "__version__", "?")
            ok(f"{name} {version}")
        elif noetig and name in IMPORT_FEHLER and "No module named" in IMPORT_FEHLER[name]:
            fehler_punkt(f"{name} fehlt – bitte mit pip installieren")
        elif noetig:
            fehler_punkt(f"{name} konnte nicht geladen werden: "
                         f"{IMPORT_FEHLER.get(name, 'unbekannter Grund')}")
        else:
            hinweis(f"{name} fehlt (optional – Offline-Stimmen stehen dann "
                    f"nicht zur Verfügung)")

    # 3) GUI
    print("\n▶ Grafische Oberfläche")
    if TKINTER_OK:
        ok("tkinter verfügbar")
    else:
        fehler_punkt("tkinter fehlt (Windows: Python neu installieren mit tcl/tk)")

    # 4) Audio-Geräte
    print("\n▶ Audio-Geräte")
    if sd is None:
        hinweis("sounddevice nicht ladbar – Details siehe oben "
                f"({IMPORT_FEHLER.get('sounddevice', '?')})")
    else:
        try:
            geraete = sd.query_devices()
            eingaenge = [g for g in geraete if g["max_input_channels"] > 0]
            ausgaenge = [g for g in geraete if g["max_output_channels"] > 0]
            ok(f"{len(eingaenge)} Eingangs- und {len(ausgaenge)} Ausgangsgeräte")
            if not eingaenge:
                hinweis("Kein Mikrofon gefunden – Sprachsteuerung nicht möglich")
        except Exception as ex:
            hinweis(f"Audio-Geräte nicht abfragbar ({ex}) – gilt nur in "
                    f"Umgebungen ohne Soundkarte")

    # 5) Konfiguration
    print("\n▶ Konfiguration")
    try:
        konfig = Konfiguration()
        konfig.setze("general", "piepser", konfig.get("general", "piepser"))
        konfig.speichern()
        ok(f"Einstellungen gelesen/geschrieben: {konfig.pfad}")
    except Exception as ex:
        fehler_punkt(f"Konfiguration: {ex}")

    # 6) Fähigkeiten ("Gehirn")
    print("\n▶ Fähigkeiten – Beispielfragen und Antworten")
    bus = EreignisBus()
    gehirn = UmiGehirn(konfig, bus)
    gehirn.setze_erinnerungs_kanal(lambda text: print(f"      [Erinnerung] {text}"))
    fragen = ["hallo umi", "wie spät ist es?", "welches datum haben wir?",
              "rechne 12,5 mal 4", "was ist 2 hoch 10", "wurzel aus 144",
              "erzähl mir einen witz", "würfle", "hilfe", "wiederhole das"]
    for frage in fragen:
        antwort = gehirn.antworten(frage).replace("\n", " ")
        print(f"      Du : {frage}\n      Umi: {antwort[:90]}")
    ok("Fähigkeiten antworten")

    # 7) Aktivierungswort
    print("\n▶ Aktivierungswort-Erkennung")
    test = [
        ("hey umi wie spät ist es", True, "wie spät ist es"),
        ("hallo umi", True, ""),
        ("UMI! erzähl einen witz", True, "erzähl einen witz"),
        ("wie wird das wetter in uni bremen", False, ""),
    ]
    for text, erwartet, rest in test:
        gefunden, ergebnis = enthaelt_wake_wort(text)
        if gefunden == erwartet and (not erwartet or ergebnis == rest):
            ok(f"„{text}“ → erkannt={gefunden}"
               + (f", Befehl=„{ergebnis}“" if ergebnis else ""))
        else:
            fehler_punkt(f"„{text}“ → unerwartet ({gefunden}, „{ergebnis}“)")

    # 8) Rechenmaschine
    print("\n▶ Rechenmaschine")
    for aufgabe, erwartet in [("12,5 mal 4", 50.0), ("2 hoch 10", 1024.0),
                              ("10 geteilt durch 4", 2.5)]:
        formel = RechenSkill._zu_formel(normalisiere(aufgabe))
        wert = eval(formel, {"__builtins__": {}}, {}) if formel else None
        if wert == erwartet:
            ok(f"{aufgabe} = {wert}")
        else:
            fehler_punkt(f"{aufgabe} → {wert} (erwartet {erwartet})")

    # 9) Sprachausgabe (Synthese – Wiedergabe nur mit Soundkarte)
    print("\n▶ Sprachausgabe (Edge TTS, benötigt Internet)")
    if edge_tts is not None:
        try:
            mp3 = asyncio.run(Sprecher._edge_synthetisieren(
                "Selbsttest", "de-DE-KatjaNeural", 0))
            if len(mp3) > 500:
                ok(f"Edge-TTS-Synthese erfolgreich ({len(mp3)} Bytes Audio)")
            else:
                hinweis("Edge-TTS antwortete mit unerwartet wenig Audio")
        except Exception as ex:
            hinweis(f"Edge-TTS nicht erreichbar ({type(ex).__name__}) – im "
                    f"Browser/Netz ohne Sperren funktioniert es automatisch; "
                    f"Fallback: Windows-Offline-Stimmen")
    if pyttsx3 is not None:
        ok("pyttsx3 verfügbar (Offline-Fallback)") if sys.platform == "win32" \
            else hinweis("pyttsx3 vorhanden, benötigt unter Linux zusätzlich "
                         "„espeak“, unter macOS „say“")
    else:
        hinweis("pyttsx3 nicht installiert – Offline-Fallback deaktiviert")

    # 10) Spracherkennung (Erreichbarkeit)
    print("\n▶ Spracherkennung (Google, benötigt Internet)")
    if sr is not None and np is not None:
        test_audio = (np.zeros(16000 * 1, dtype="int16"))
        erkenner = SprachErkenner(Konfiguration())
        _text, stt_fehler = erkenner.transkribieren(test_audio, 16000)
        if stt_fehler is None:
            ok("Google-Spracherkennung erreichbar")
        elif stt_fehler == "netz":
            hinweis("Google-Spracherkennung hier nicht erreichbar (Netzwerk "
                    "gesperrt) – auf einem normalen PC funktioniert dies")
        else:
            hinweis(f"Spracherkennung: {stt_fehler}")

    # 11) Timer
    print("\n▶ Timer-Fähigkeit")
    gehirn.timer_starten(1, "Selbsttest-Timer")
    gehirn.timer_abbrechen()
    ok("Timer anlegen/abbrechen")

    # ── Zusammenfassung ──────────────────────────────────────────────────
    print("\n" + "═" * 70)
    if fehler == 0:
        print(f"  ✅ Selbsttest bestanden"
              + (f" ({hinweise} Hinweis/Hinweise)" if hinweise else ""))
    else:
        print(f"  ❌ {fehler} Fehler gefunden"
              + (f", {hinweise} Hinweise" if hinweise else ""))
    print("═" * 70)
    return 0 if fehler == 0 else 1


# ─────────────────────────────────────────────────────────────────────────────
# 12) PROGRAMMSTART
# ─────────────────────────────────────────────────────────────────────────────

def _dpi_aktivieren():
    """Unter Windows für scharfe Schrift sorgen (High-DPI-Displays)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


SCHRIFTART = "Segoe UI"


def _schriftart_waehlen():
    """Segoe UI auf Windows verwenden, sonst eine passende Fallback-Schrift."""
    global SCHRIFTART
    if not TKINTER_OK:
        return
    try:
        probe = tk.Tk()
        probe.withdraw()
        verfuegbar = set(tkfont.families(probe))
        for kandidat in ("Segoe UI", "SF Pro Text", "Ubuntu", "DejaVu Sans",
                         "Helvetica"):
            if kandidat in verfuegbar:
                SCHRIFTART = kandidat
                break
        probe.destroy()
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="umi_assistent.py",
        description=f"{APP_NAME} – persönlicher KI-Assistent mit Sprachsteuerung")
    parser.add_argument("--selftest", action="store_true",
                        help="Funktionstest ohne grafische Oberfläche")
    parser.add_argument("--geraete", action="store_true",
                        help="Audio-Geräte auflisten und beenden")
    parser.add_argument("--ohne-wake", action="store_true",
                        help="Aktivierungswort für diese Sitzung deaktivieren")
    parser.add_argument("--ohne-tts", action="store_true",
                        help="Sprachausgabe für diese Sitzung deaktivieren")
    parser.add_argument("--config", metavar="PFAD", default=CONFIG_PATH,
                        help="Pfad der Einstellungsdatei (Standard: neben "
                             "dieser Datei)")
    argumente = parser.parse_args()

    if argumente.geraete:
        geraete_auflisten()
        return 0
    if argumente.selftest:
        return selbsttest()

    _dpi_aktivieren()
    if not TKINTER_OK:
        print("❌ tkinter fehlt. Unter Windows Python unbedingt über den "
              "offiziellen Installer von python.org installieren.")
        return 1
    _schriftart_waehlen()

    # ── Bausteine von Umi zusammenbauen ──────────────────────────────────
    konfig = Konfiguration(argumente.config)
    if argumente.ohne_wake:
        konfig.setze("general", "wake_aktiv", False)
    if argumente.ohne_tts:
        konfig.setze("general", "tts_aktiv", False)

    ereignisse = EreignisBus()
    gehirn = UmiGehirn(konfig, ereignisse)
    sprecher = Sprecher(konfig, ereignisse)
    erkenner = SprachErkenner(konfig)
    worker = GespraechsWorker(konfig, ereignisse, gehirn, sprecher)
    engine = SprachEngine(konfig, ereignisse, erkenner, sprecher, worker)
    gehirn.setze_erinnerungs_kanal(worker.mitteilung)
    gehirn.wake_callback = engine.wake_setzen

    app = UmiApp(konfig, ereignisse, gehirn, sprecher, erkenner, engine, worker)

    # ── Threads starten und Hauptschleife laufen lassen ───────────────────
    worker.start()
    engine.start()
    sprecher.stimmen_async_laden()
    try:
        app.starten()
    except KeyboardInterrupt:
        pass
    finally:
        sprecher.stoppen()
        engine.beenden()
        worker.beenden()
        gehirn.timer_abbrechen()
    return 0


if __name__ == "__main__":
    sys.exit(main())
