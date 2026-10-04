# 🌊 Umi – Dein persönlicher KI-Assistent mit Sprachsteuerung

**Umi** ist ein vollständiger Sprach- und Chat-Assistent – entwickelt für **Python 3.13**
unter Windows, der **komplett in einer einzigen Python-Datei** (`umi_assistent.py`) steckt.

```
┌──────────────────────────────────────────────────────────────┐
│  (U) Umi · Dein persönlicher KI-Assistent      ● Bereit   ⚙ │
│                                                              │
│     (U) Umi · 14:32                                          │
│         ╭──────────────────────────────────────╮             │
│         │ Hallo! Was kann ich für dich tun?     │            │
│         ╰──────────────────────────────────────╯             │
│                                                              │
│                                          14:33 · Du (Du)     │
│             ╭──────────────────────────────────────╮         │
│             │ Hey Umi, wie spät ist es?             │        │
│             ╰──────────────────────────────────────╯         │
│                                                              │
│ ┌──────────────────────────────────────────────┐  ➤  🎙      │
│ │ Nachricht an Umi … (Eingabetaste = senden)    │            │
│ └──────────────────────────────────────────────┘             │
│  Mikrofon ▁▃▅▂  🔔 Aktivierungswort: AN     Umi v1.0        │
└──────────────────────────────────────────────────────────────┘
```

---

## ✨ Funktionen

| Funktion | Beschreibung |
|---|---|
| 🎙 **Sprachsteuerung** | Aktivierungswort **„Hey Umi“**, danach einfach den Wunsch sagen |
| 🗣 **Spracherkennung** | Sprache → Text über die kostenlose Google Web Speech API (`de-DE` u. v. m.) |
| 🔊 **Text-to-Speech** | Natürliche Stimmen über **Edge TTS** (online) mit automatischem Fallback auf **Windows-SAPI-Stimmen** (offline) |
| ⌨️ **Texteingabe** | Chat-Fenster mit Eingabefeld – Antworten werden auch vorgelesen |
| 💬 **Chat-Verlauf** | Moderne, dunkle Chat-Oberfläche mit Sprechblasen |
| 🚦 **Statusanzeige** | „Bereit“, „Hört zu …“, „Denkt nach …“, „Spricht …“ (mit Puls-Animation) |
| ⚙️ **Einstellungen** | Mikrofon & Lautsprecher wählbar, Empfindlichkeit, Stimme, Tempo, Lautstärke, Erkennungssprache, Aktivierungswort, Online-KI |
| 🧠 **Fähigkeiten offline** | Uhrzeit, Datum, Taschenrechner, Witze, Würfeln/Münzwurf, Wetter (Open-Meteo, ohne API-Key), Timer/Erinnerungen, Hilfe |
| 🌐 **Online-KI (optional)** | Freie Fragen an jede **OpenAI-kompatible** Chat-API (OpenAI, **Ollama lokal**, LM Studio, …) |
| 🧩 **Erweiterbar** | Eigene Fähigkeiten in wenigen Zeilen ergänzen (Klasse `Skill`) |
| 🛡 **Fehlerbehandlung** | Verständliche Meldungen bei fehlendem Mikrofon, ohne Internet, falschen Einstellungen usw. |

---

## 📦 Installation (Windows, Python 3.13)

1. **Python 3.13** installieren: <https://www.python.org/downloads/>
   → im Installer unbedingt **„Add python.exe to PATH“** anhaken!
2. Eingabeaufforderung (cmd) im Projektordner öffnen und installieren:

   ```bat
   pip install -r requirements.txt
   ```

   bzw. einzeln:

   ```bat
   pip install numpy sounddevice soundfile SpeechRecognition edge-tts pyttsx3
   ```

3. **Mikrofon erlauben**: Windows → Einstellungen → Datenschutz & Sicherheit →
   Mikrofon → „Zugriff auf Mikrofon“ erlauben.

> **Hinweis:** `pyaudio` wird **nicht** benötigt – Umi nutzt `sounddevice`,
> das für Python 3.13 fertige Windows-Pakete mitbringt.

### Benötigte Bibliotheken

| Paket | Zweck |
|---|---|
| `numpy` | Audio-Verarbeitung (Pegel, PCM, Signaltöne) |
| `sounddevice` | Mikrofon-Aufnahme & Lautsprecher-Wiedergabe |
| `soundfile` | Dekodiert die MP3-Stimmausgabe von Edge TTS |
| `SpeechRecognition` | Sprache → Text (Google Web Speech API) |
| `edge-tts` | Text → Sprache (natürliche Microsoft-Stimmen, online) |
| `pyttsx3` | Offline-Fallback: Windows-SAPI-Stimmen (optional) |

Alles Weitere (tkinter, JSON, HTTP, …) liefert Pythons Standardbibliothek.

---

## ▶️ Starten

```bat
python umi_assistent.py
```

Das war's – Umi öffnet das Fenster, lauscht auf **„Hey Umi“** und nimmt zusätzlich
Nachrichten über die **🎙-Taste** oder die **Tastatur** entgegen.

**Nützliche Startoptionen:**

```bat
python umi_assistent.py --selftest     :: Funktionstest ohne GUI (Fehlersuche)
python umi_assistent.py --geraete      :: Audio-Geräte auflisten
python umi_assistent.py --ohne-wake    :: Aktivierungswort für diese Sitzung aus
python umi_assistent.py --ohne-tts     :: Sprachausgabe für diese Sitzung aus
```

---

## 🗣 So funktioniert die Sprachsteuerung

1. Umi lauscht im Hintergrund auf das Aktivierungswort **„Hey Umi“**
   (auch „Hey Uni“, „A Umi“ o. Ä. werden dank unscharfer Erkennung verstanden).
2. Es ertönt ein kurzer Signalton, die Statusanzeige wechselt auf „Hört zu …“.
3. Sprich den Wunsch in **einem Atemzug** mit dem Aktivierungswort
   („Hey Umi, wie spät ist es?“) oder warte nach dem Piep und sprich dann.
4. Nach einer kurzen Sprechpause (~1,1 s, einstellbar) wird der Satz erkannt,
   Umi zeigt „Denkt nach …“ und antwortet per Text **und** Sprache.
5. Mit **„gute Nacht“/„Tschüss“** pausiert Umi die Sprachsteuerung –
   die 🎙-Taste weckt ihn wieder. Über den Knopf unten
   (🔔/🔕) schaltest du das Aktivierungswort jederzeit ein/aus.

---

## ⚙️ Einstellungen

Über den **⚙-Knopf** (Reiter 🎙 Audio / 🔊 Sprache / 🧠 KI / ℹ️ Info):

- **Mikrofon & Lautsprecher** einzeln wählen (inkl. Mikrofon-Test),
- **Empfindlichkeit** und **Sprechpause** anpassen,
- **Stimme** wählen (alle Edge-Stimmen, z. B. `de-DE-KatjaNeural`, oder Windows-Offline-Stimmen), **Tempo** & **Lautstärke**,
- **Aktivierungswort** und **Erkennungssprache** (de-DE, de-AT, en-US, …),
- **Online-KI**: Basis-URL, API-Schlüssel, Modell, Temperatur.

Alle Einstellungen liegen lokal in **`umi_einstellungen.json`** neben der Programmdatei
(API-Schlüssel bleiben auf deinem PC).

### Online-KI verbinden (für freie Fragen)

| Anbieter | Basis-URL | Modell-Beispiel | Key |
|---|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` | erforderlich |
| **Ollama (lokal)** | `http://localhost:11434/v1` | `llama3.2` | beliebig, z. B. `ollama` |
| LM Studio (lokal) | `http://localhost:1234/v1` | geladenes Modell | beliebig |

---

## 🧩 Eigene Fähigkeiten ergänzen

Umi ist bewusst **modular** aufgebaut: `Skill` (Basis-Klasse), `UmiGehirn` (Antwort-Logik),
`Sprecher` (TTS), `SprachErkenner` (STT), `SprachEngine` (Mikrofon), `UmiApp` (GUI).

Eigene Fähigkeit in `umi_assistent.py` hinzufügen:

```python
class KaffeeSkill(Skill):
    name = "Kaffee-Berater"

    def match(self, text):                      # Wann bin ich zuständig?
        return "kaffee" in text

    def handle(self, text, umi):                # Was antworte ich?
        return "60 Gramm Kaffee auf einen Liter Wasser – perfekt!"

# in UmiGehirn.__init__ in die Liste eintragen:
self.skills: list[Skill] = [ ..., KaffeeSkill() ]
```

Auch STT/TTS lassen sich austauschen (z. B. lokale Whisper-Erkennung): einfach
`SprachErkenner.transkribieren()` bzw. `Sprecher.sagen()` ersetzen.

---

## 🛠 Fehlerbehebung

| Problem | Lösung |
|---|---|
| „Auf das Mikrofon konnte nicht zugegriffen werden“ | Mikrofon anschließen, als Standard setzen, Windows-Datenschutz-Einstellung prüfen; dann in Umi ⚙ → 🎙 das Gerät wählen |
| Umi reagiert nicht auf „Hey Umi“ | Empfindlichkeit in ⚙ erhöhen, deutlich sprechen, Internet prüfen (Erkennung läuft über Google) |
| Keine Sprachausgabe | ⚙ → 🔊 → „Testansage“; ohne Internet automatisch Windows-Offline-Stimme (`pyttsx3`) |
| `pip install pyaudio` schlägt fehl | Nicht nötig – Umi nutzt `sounddevice` |
| Funktionstest | `python umi_assistent.py --selftest` zeigt alle Bausteine mit Status |

**Datenschutz-Hinweis:** Für Spracherkennung (Google) und Edge-TTS werden Audio-Daten
an die jeweiligen Dienste übertragen. Wer das vermeiden möchte: TTS auf „windows“
stellen und das Aktivierungswort deaktivieren (🎙-Taste nutzen) – allerdings bleibt
die Erkennung selbst ein Online-Dienst.

---

## 📁 Dateien

| Datei | Zweck |
|---|---|
| `umi_assistent.py` | **Das komplette Programm** (eine Datei, gut kommentiert) |
| `requirements.txt` | Benötigte Python-Bibliotheken |
| `README_Umi.md` | Diese Anleitung |
| `umi_einstellungen.json` | Wird beim ersten Start automatisch angelegt |
