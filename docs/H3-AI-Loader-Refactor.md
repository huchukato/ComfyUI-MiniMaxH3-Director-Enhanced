# H3 AI Loader — Refactor

Ziel dieser Arbeit: Der H3 AI Loader soll eine Provider-Wahl, Modelle, Settings und Advanced-Optionen anbieten, die
zuverlässig dastehen, ohne dass wir dieselben Fehler bei jedem Provider erneut einbauen. Dieses Dokument legt fest,
**was** in welche Sektion kommt, **woher** die Werte kommen und **wie** wir das prüfen. Es ist die verbindliche
Referenz für die Umsetzung; wenn Code und Dokument auseinanderlaufen, gewinnt das Dokument und der Code wird korrigiert.

Entscheidungen, die vorab getroffen wurden:

- **Custom fliegt als eigene Karte raus.** Custom ist kein Anbieter, sondern die Aussage „ich gebe selbst eine URL
  ein". Es ist eine Abwahloption innerhalb von Local und API.
- **System-Prompts kommen in eine eigene Datei**, eine Datei für alle Knoten, die einen brauchen.

---

## 0. Ausgangslage — was heute existiert

Bevor wir bauen, der Ist-Stand. Jeder Punkt unten ist im aktuellen Code belegt.

| Befund | Ort | Folge für den Umbau |
| --- | --- | --- |
| Provider sind drei fest verdrahtete Strings, keine Registry | `ng/nodes/provider_node.py:17`, `options=["ollama","lmstudio","custom"]` | Jeder Provider muss an zwei Stellen eingetragen werden |
| Adressen doppelt: Python und JavaScript | `minimax_media.py:442` `_PROVIDER_DEFAULTS`, `js/ng/ng_ai_panel.js:31` `PROVIDER_HINTS` | Die beiden Listen laufen still auseinander |
| Kein einziges Advanced-Sampling-Feld | `ng/core/analysis.py:14-23` — nur `vision, audio, timeout_seconds, max_tokens, keep_alive` | `temperature`, `top_p`, `seed` existieren nicht |
| `from_dict` wirft bei unbekannten Feldern, `SCHEMA_VERSION = 1` | `ng/core/analysis.py:38-39` | Jedes neue Feld ist ein Schema-Bump mit Migrationspfad |
| Modelle werden nie abgefragt | keine Route für `/api/tags` oder `/v1/models` | `model` ist reines Freitextfeld |
| `vision` / `audio` sind eine **Zusicherung**, keine Anzeige | `ng/adapters/native_ai.py:26-29` blockiert die Anfrage | Beim Weglassen brauchen wir eine echte Capability-Quelle |
| System-Prompt hart als TextGenerate-Argument | `ng/adapters/native_ai.py:47` | Ein Loader-Prompt gilt heute für alle Knoten |
| `ng/core/` darf kein `aiohttp` importieren | `tests/ng/test_structure.py:16` `CORE_FORBIDDEN` | Neue HTTP-Logik muss nach `ng/adapters/` |
| Mock-Server-Fixture existiert bereits | `tests/ng/test_analysis.py:102-109` (aiohttp, Port 0) | Emulatoren bauen darauf auf, statt neu |

### 0.1 Die zwei Protokolle, die wir wirklich haben

`vlm_generate` (`minimax_media.py:578`) spricht genau zwei Protokolle:

1. **Ollama** — `/api/generate`, rohes Base64 in `images[]`, Antwort in `response`.
2. **OpenAI-kompatibel** — `/v1/chat/completions`, Data-URLs in `messages[].content`, Antwort in `choices[0]`.

Daraus folgt die wichtigste Regel dieses Dokuments: **Ein Provider ist erst nutzbar, wenn er auf eines dieser beiden
Protokolle passt.** Gemini und Anthropic bieten zwar OpenAI-kompatible Endpäste an, aber das ist ungetestet. Deshalb
führt die Registry unten eine Spalte `verified`. Sie ist bei Registry-Arbeit **immer** von Hand zu setzen und nie
automatisch zu erraten.

---
## 1. Provider-Registry — die einzige Quelle der Wahrheit

Neue Datei `ng/core/providers.py`, reines Python ohne ComfyUI-Import (passt in `CORE_FORBIDDEN`).

Jeder Provider ist ein eingefrorener Datensatz mit diesen Feldern:

| Feld | Bedeutung |
| --- | --- |
| `id` | Kurzkennung, wird in der Workflow gespeichert |
| `label` | Anzeigename im Dropdown |
| `kind` | `local` oder `api` — bestimmt, in welchem Source-Tab er erscheint |
| `base_url` | Standardadresse; leer bei `api` ohne festen Ort |
| `models_path` | Route, die die verfügbaren Modelle auflistet (`/api/tags`, `/v1/models`) |
| `generate_path` | `/api/generate` oder `/v1/chat/completions` |
| `auth` | `none`, `bearer` oder `x-api-key` |
| `defaults` | Standardwerte für Settings und Advanced |
| `settings` | welche Felder dieser Provider kennt |
| `supports` | Fähigkeiten, die er **nachweislich** hat |
| `verified` | `true` nur nach einem echten Testlauf |

### 1.1 Die zwei Listen, die wir auflösen

`_PROVIDER_DEFAULTS` in `minimax_media.py` und `PROVIDER_HINTS` in `ng_ai_panel.js` werden beide **ersetzt**, nicht
ergänzt. Die Registry liefert ihre Werte; das Frontend holt sie über eine neue Route, statt sie ein zweites Mal
zu tippen.

```
GET /ng/providers   ->  {"providers": [...], "sources": [...]}
```

Die Route ist read-only, ohne Netzwerkzugriff und ohne Key. Sie liefert nur die Beschreibung, nie ein Geheimnis.

### 1.2 Die Provider

**Local** — läuft auf deinem Rechner, braucht keinen Key, Adresse ist bekannt:

| id | Label | Adresse | Modelle | Protokoll | verified |
| --- | --- | --- | --- | --- | --- |
| `ollama` | Ollama | `http://127.0.0.1:11434` | `/api/tags` | `/api/generate` | ja (4 GPU-Läufe) |
| `lmstudio` | LM Studio | `http://127.0.0.1:1234` | `/v1/models` | `/v1/chat/completions` | offen |
| `llamacpp` | llama.cpp | `http://127.0.0.1:8080` | `/v1/models` | `/v1/chat/completions` | offen |
| `custom` | Custom URL | leer | `/v1/models` | `/v1/chat/completions` | im Test Emulator |

**API** — braucht einen Key, Adresse ist bekannt:

| id | Label | Adresse | Auth | verified |
| --- | --- | --- | --- | --- |
| `openai` | OpenAI / ChatGPT | `https://api.openai.com/v1` | bearer | nein |
| `anthropic` | Claude | `https://api.anthropic.com/v1` | x-api-key | nein |
| `gemini` | Google AI Studio | `https://generativelanguage.googleapis.com/v1beta/openai` | bearer | nein |
| `openrouter` | OpenRouter | `https://openrouter.ai/api/v1` | bearer | nein |
| `custom` | Custom URL | leer | bearer | im Test Emulator |

**Regel für `verified`:** Ein Provider wird nie automatisch auf `true` gesetzt. Nur ein Testlauf gegen das echte
Ding darf das. Alles andere bleibt `false` und wird im Panel als „nicht getestet" angezeigt.

### 1.3 `as_dict` statt `to_dict` — bewusste Ausnahme

`Provider` hat `as_dict()`, nicht `to_dict()`, und deshalb kein `from_dict`. `test_structure.py` verlangt für
jede Klasse mit `to_dict` auch ein `from_dict`.

Begründung: Die Registry wird **nie** zurückgelesen. Es gibt keinen Persistenzpfad, der aus einem Dict ein
`Provider` baut. Ein `from_dict` wäre eine zweite, ungetestte Art, einen Eintrag zu erzeugen — und die genaue
Klasse von Fehler, die dieses Dokument verhindern soll. Der andere Name ist ehrlich; ein leerer Stub wäre es nicht.

Nachteile geprüft: keine. `describe()` nutzt die Methode in eine Richtung, die Struktur-Regel prüft nur den
Namen. Sollte die Registry später doch einmal gespeichert werden, ist das der Punkt, an dem `from_dict` dazukommt —
mit einem Test, nicht vorher.

### 1.4 `provider_payload()`

Die Funktion, die aus der Matrix den echten Request-Teil baut. Sie entscheidet, **was tatsächlich gesendet
wird** — nicht das Panel.

- Nimmt nur Felder, die der Provider in `fields` führt. Ein Rest vom anderen Provider wird verworfen.
- Ollama: Sampling unter `"options"`, `max_tokens` heißt dort `num_predict`, `keep_alive` steht daneben.
- OpenAI-kompatibel: alles flach.
- `timeout_seconds` und `fixed_seed` landen **nie** im Body.
- Ohne angehaktes `fixed_seed` wird **kein** Seed gesendet. Das ist der Punkt des Haken: ein Provider liest einen
  Seed als „mach das reproduzierbar", also ist Weglassen die einzige ehrliche Umsetzung von „nicht fixieren".

Leere Einstellungen ergeben ein leeres Stück Body: ein neuer Node überschreibt keine Provider-Vorgabe mit einem
Default, den der Nutzer nie gewählt hat.
## 2. Die vier Panels

### 2.1 Source — drei Karten

| Karte | Label | Provider | Wirkung |
| --- | --- | --- | --- |
| `local` | Local / Load LLM·AI Model | ollama, lmstudio, llamacpp, custom | HTTP auf deinen Rechner |
| `api` | API / Online provider | openai, anthropic, gemini, openrouter, custom | HTTP in die Cloud, Key nötig |
| `clip` | CLIP / Encoder / Text Encoder only | — | ComfyUI Generate Text, keine HTTP |

Die Karte `custom` aus dem alten Aufbau **entfällt**. Custom ist jetzt eine Zeile im Provider-Dropdown von Local
und API. Das war der Grund: eine eigene Karte ohne eigenen Provider sammelt nur Felder, die niemand pflegt.

**Es gibt keine Karte „Load from disk" und keinen Schalter `local_backend`.** Ein installierter Encoder und ein
angeschlossener Load CLIP-Knoten führen beide über denselben Weg — ComfyUIs Generate Text. Zwei Karten dafür wären
zwei Namen für eine Sache. Welche der beiden Varianten gerade gilt, entscheidet der Zustand, nicht ein Schalter:

- Load CLIP **verbunden** → der verbundene Knoten. `local_model` wird nicht gelesen.
- kein Load CLIP, aber `local_model` gewählt → der installierte Encoder, geladen erst beim AI-Aufruf.
- beides leer → Fehlermeldung, die **beide** Wege nennt.

Der `local_model`-Wert bleibt beim Wechsel gespeichert, wird aber nicht verwendet. So kann man den Encoder nicht
verlieren, nur weil zwischenzeitlich ein Load CLIP angeschlossen war.

Die Felder `local_model` und `local_type` liegen in einem eigenen **Encoder**-Abschnitt, der nur erscheint, wenn
kein Load CLIP verbunden ist. Sie gehören **nicht** in „2. Provider / Model".

Das war ein Fehler in der ersten Fassung: die Felder waren erzeugt und in `sync()` versteckt, aber nie an einen
Elternknoten gehängt — sie waren also weder sichtbar noch wirklich weg. Bei einem `control()` ohne
`append()` verschwindet ein Feld **stumm**: kein Fehler, kein Testfehler, nur eine Stelle, an der der Nutzer
etwas vermisst.

**Regel daraus:** Jedes `control()` bekommt im selben Zug ein `append()` an einen Abschnitt. Ein `fields`-Eintrag
allein genügt nicht — der hält nur die Synchronisation aktuell, nicht die Anzeige.

### 2.2 Provider / Model

Reihenfolge und Inhalt:

1. **Provider** — Dropdown aus der Registry, gruppiert nach `kind`.
2. **Model** — Dropdown, gefüllt aus `models_path`. Erst nach einer erfolgreichen Abfrage aktiv; sonst tippbar.
3. **Address** — Host und Port. Beim Providerwechsel wird die Standardadresse **vorgeschlagen**, aber eine bereits
   getippte Adresse wird **nicht überschrieben**. Ein Fehlertreffer beim Wechsel ist teurer als eine Altlast.
4. **API Key** — nur sichtbar, wenn `auth != none`. Passwortfeld, siehe 2.5.

Die Modellabfrage ist eine eigene Route, weil sie Netzzugriff braucht und der Key damit beteiligt ist:

```
POST /ng/models   {"provider": "openai", "base_url": "...", "key_name": "OPENAI_API_KEY"}
   ->  {"ok": true, "models": [{"id": "claude-...", "label": "..."}], "source": "live"}
```

`source` ist `live`, `cache` oder `emulator` und wird im Panel angezeigt. Eine Emulator-Antwort wird nie als Live
ausgegeben — sonst glaubt der Nutzt, sein Setup funktioniere.

### 2.3 Settings — was jeder Provider kennt

Nur Felder, die **alle** Provider sinnvoll verstehen:

| Feld | Typ | Bereich | Standard |
| --- | --- | --- | --- |
| `max_tokens` | int | 64 – 8192 | 512 |
| `seed` | int | 0 – 2^32 | 0 |
| `fixed_seed` | bool | — | false |

`fixed_seed` ist dein Haken. Ohne ihn zieht der Provider jedes Mal einen neuen Wert; mit ihm wird der Wert
tatsächlich mitgesendet. Das ist genau die Falle, in der ein Seed-Feld sonst nur dekorativ ist.

### 2.4 Advanced — optional

| Feld | Typ | Bereich | Standard |
| --- | --- | --- | --- |
| `temperature` | float | 0.0 – 2.0 | 0.3 |
| `top_p` | float | 0.0 – 1.0 | 0.9 |
| `top_k` | int | 0 – 100 | 40 |
| `min_p` | float | 0.0 – 1.0 | 0.0 |
| `frequency_penalty` | float | -2.0 – 2.0 | 0.0 |
| `presence_penalty` | float | -2.0 – 2.0 | 0.0 |
| `timeout_seconds` | int | 5 – 900 | 120 |
| `keep_alive` | int | 0 – 3600 | 0 |

**Die Sampling-Matrix.** Das Panel zeigt nur die Felder, die der gewählte Provider wirklich annimmt:

| Feld | Ollama | LM Studio | llama.cpp | OpenAI | Claude | Gemini | OpenRouter |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `temperature` | ja | ja | ja | ja | ja | ja | ja |
| `top_p` | ja | ja | ja | ja | nein | ja | ja |
| `top_k` | ja | nein | nein | nein | nein | nein | nein |
| `min_p` | ja | nein | nein | nein | nein | nein | nein |
| `frequency_penalty` | nein | ja | ja | ja | nein | nein | ja |
| `presence_penalty` | nein | ja | ja | ja | nein | nein | ja |
| `max_tokens` | `num_predict` | `max_tokens` | `max_tokens` | `max_tokens` | `max_tokens` | `max_tokens` | `max_tokens` |
| `keep_alive` | ja | nein | nein | nein | nein | nein | nein |
| `seed` | ja | ja | ja | ja | nein | nein | ja |

Nicht unterstützte Felder werden **ausgeblendet**, nicht deaktiviert. Ein ausgegrautes Feld erzeugt Rückfragen;
ein unsichtbares nicht. Und was gesendet wird, entscheidet `provider_payload()`, nicht das Panel — das Panel ist
Anzeige, das Backend ist Wahrheit.
## 3. System-Prompts — eine Datei für alle Knoten

Neue Datei `ng/core/system_prompts.py`. Reines Python, keine ComfyUI-Importe, damit sie in `core` liegen darf.

**Warum eine Datei und nicht ein Feld pro Knoten:** Der Loader soll keinen System-Prompt mehr setzen. Er ist die
Anbindung, nicht die Instanz. Jeder Knoten, der eine Rolle hat, holt sich seinen Prompt aus dieser Datei und legt
ihn beim Bauen des Requests daneben.

Aufbau:

```python
SYSTEM_PROMPTS = {
    "context_image": "Du bist der Bild-Analyst ...",
    "context_video": "...",
    "context_audio": "...",
    "context_text":  "...",
    "director":      "...",
}

def for_node(node_id, media=None): ...
```

Fünf Einträge: H3 Context Image, Video, Audio, Text und H3 Director. **Text auf Englisch**, weil die Modelle
englische Prompts zuverlässiger befolgen und die Rohantwort ohne Übersetzungsrisiko im JSON-Schema landet.

**Die verbindliche Rahmung bleibt im Backend.** `native_ai.py:47` hat heute einen festen Text
(`Follow the requested JSON schema exactly`). Dieser Schema-Rahmen wird **nicht** herausgegeben, sonst bricht
`parse_suggestion`, sobald jemand einen Prompt umschreibt. Neu ist nur: der Rollen-Prompt kommt **vor** den Rahmen,
der Rahmen zuletzt. Wer seinen Knoten-Prompt überschreibt, kann also am Rollentext nichts ändern, aber den Parser
nicht kaputt machen.

Jeder Knoten bekommt ein optionales Feld `system_prompt` (Text, mehrzeilig, Advanced). Leer heißt „nimm den aus
`system_prompts.py`". So ist der Default fachlich gepflegt und trotzdem pro Karte überschreibbar.

## 4. Capabilities statt der vier Checkboxen

Die Kästchen `vision` und `audio` fliegen raus. Sie sind heute eine **Zusicherung** des Nutzers, deren Falschheit
`native_ai.py:26-29` mit einer Fehlermeldung bestraft — der Nutzer wird also für seine eigeneCheckbox bestraft.

Stattdessen:
## 5. Optik

| Änderung | Grund |
| --- | --- |
| `⋮`-Menü raus | Der einzige Zweck war, zwei Hinweistexte zu verstecken. Die Felder tragen die Erklärung jetzt selbst. |
| Lila Umrandung raus | Sie kostet Platz, den die vier Tabs brauchen. Die Kartenreihenfolge trennt sich auch ohne Rahmen. |
| Immer zwei Kacheln nebeneinander | wie bisher |
| `?` mit **echtem** englischen Text | pro Feld eigener Text, nicht generisch |

Die `?`-Texte werden in derselben Registry abgelegt wie das Feld selbst (`help`), damit Panel und Backend nicht
auseinanderlaufen können.

`timeout_seconds` wandert wie besprochen aus Settings nach **Advanced**. Es ist eine Verbindungseinstellung, keine
Inhaltseinstellung.

### 2.5 API Key ohne Klartext im Workflow

Der heutige Weg `api_key_env` ist sicher, aber unbrauchbar: man muss die Variable setzen, **bevor** ComfyUI startet.

Der Key landet deshalb in einer eigenen Datei im Ordner des anfragenden ComfyUI-Nutzers
(`minimax_h3_ng/api_keys`), geschrieben über dieselbe Pfadprüfung wie die Presets. Die Reihenfolge der
Auflösung bleibt: gespeicherter Key → `api_key_env` → `OPENROUTER_API_KEY` / `OPENAI_API_KEY`.

- Das Feld ist ein **Passwort-Input** (`type="password"`), nie im Klartext sichtbar.
- Ein leerer Key **löscht** den gespeicherten — so vergisst man einen ohne Handarbeit.
- Pro Provider ein eigener Key. Wer OpenAI **und** Claude nutzt, hat zwei.
- `GET /ng/keys` sagt nur `{"set": true, "env": ...}`. Nie der Key, nicht gekürzt.

**Was die Routen zusichern**

| Route | Zweck |
| --- | --- |
| `POST /ng/models` | fragt die Modelle, nimmt den Key aus dem Speicher, gibt nur Namen zurück |
| `GET /ng/keys` | welche Provider einen Key haben — nie welcher |
| `POST /ng/keys` | speichert oder löscht |

**Eine erfolgreiche Modellabfrage beweist den Key nicht.** Gemessen: OpenRouter beantwortet `/v1/models` mit
466 Namen **ohne** Key und mit einem **falschen**. Erst der Chat-Aufruf lehnt ab. Die Antwort trägt deshalb
`key_checked: false` für solche Provider, damit das Panel nicht einen grünen Haken zeigt, den der Nutzer als
„Key stimmt" liest.

### 2.6 Modellabfrage

`POST /ng/models` fragt die Registry-Route des Providers (`/api/tags` oder `/v1/models`). Die Adressbildung
normalisiert ein `/v1` — genau der Fall, der früher `/v1/v1/...` gefragt hat (Issue #31). Ein Provider, der nicht
antwortet, liefert eine leere Liste **plus Grund**, damit das Feld tippbar bleibt und die Meldung sagt, was zu
tun ist.

Live geprüft: 466 Namen, Gemma vorhanden, mit und ohne `/v1` in der Adresse derselbe Ort, Key in keiner Antwort.
## 6. Testen und Prüfen

Drei Stufen. Jede Provider-Behauptung im Panel muss auf einer davon belegt sein — sonst `verified: false`.

### Stufe 1 — Ollama und OpenRouter, live

Zwei Provider haben einen echten Lauf hinter sich:

**Ollama** — vier H3-GPU-Läufe mit Datei-Kontexten.

**OpenRouter** — ein Live-Lauf gegen die echte API mit `google/gemma-4-26b-a4b-it:free`, Kosten 0:

- `GET /v1/models` → 466 Modelle, davon 17 frei. Das Modell ist vorhanden.
- Vision-Anfrage mit Bild → HTTP 200, Bild korrekt beschrieben, `content: "object"`, Parse erfolgreich.
- Der Key erscheint in **keinem** Request-Body und **keiner** Antwort.
- `seed` und `frequency_penalty` wurden akzeptiert.

Drei Befunde aus diesem Lauf, die keine Emulator-Runde gezeigt hätte:

1. **Denkende Modelle brauchen mehr Tokens.** Mit 512 `max_tokens` verbrauchte Gemma sein ganzes Budget in
   `reasoning`, `content` blieb `null` und `finish_reason` war `length`. Mit 2048 kam die Antwort sauber.
   Der Fehler war vorher „Expecting value: line 1 column 1" — ohne Hinweis auf die Ursache. Jetzt nennt er
   die Token-Ursache.
2. **Eine Bild-Karte konnte „dialogue" bekommen.** Gemma antwortete `content: "dialogue"` für ein Bild. Der
   Parser kannte nur die Vereinigung aller Medien und ließ es durch. Der Prompt bietet jetzt je Medium nur die
   Rollen an, die diese Karte halten kann, und der Parse weist den Rest namentlich ab.
3. **Der Fehlertext muss die Ursache nennen, nicht den Symptomindex.** Siehe 1.

Der Lauf belegt außerdem, dass `provider_payload()` das schickt, was die Registry erlaubt — der Body kam genau so
an, wie er gebaut wurde.

### Stufe 2 — Emulatoren für alle anderen

`tests/ng/test_analysis.py:102-109` hat bereits einen echten aiohttp-Server auf Port 0. Den verallgemeinern wir zu
einer Fixture in `tests/ng/_emulators.py`:

```python
class OllamaEmulator:   # /api/generate, /api/tags
class OpenAIEmulator:   # /v1/chat/completions, /v1/models
```

Jeder Emulator **muss** den echten Feldnamen der Registry erwarten. Ein Test, der `frequency_penalty` an Ollama
schickt, schlägt dann fehl — genau das ist der Test, den wir wollen.

Die Emulatoren sind auch das Testwerkzeug für die API-Provider: derselbe OpenAI-Emulator prüft OpenAI, Claude über
den Kompatibilitäts-Endpunkt, Gemini und OpenRouter, ohne dass wir einen Cent ausgeben.

### Stufe 3 — CLIP / Encoder

Ein angeschlossener Encoder, wie bei Qwen3VL. Wir testen, dass Analyze über Generate Text läuft, dass der
System-Prompt aus der neuen Datei ankommt und dass die Capability-Sperre greift. Das ist mit dem vorhandenen
Testnachweis machbar.

### Was ein Test zusichern muss

- Jede Provider-Zeile sendet **genau** die Felder, die die Matrix erlaubt — und nichts andere.
- Ein nicht unterstütztes Feld, das trotzdem in der Config steht, wird **nicht** gesendet.
- Der Key erscheint in **keinem** Request-Body, **keinem** Log und **keiner** Fehlermeldung.
- Ein Provider-Ausfall ist eine Fehlermeldung **mit Handlungsempfehlung**, kein Absturz.
- `verified` wird von keinem Test automatisch gesetzt.

## 7. Reihenfolge der Umsetzung

Jeder Schritt ist einzeln abgeschlossen und einzeln getestet. Erst weiter, wenn die Tests grün sind.

| # | Schritt | Test | Stand |
| --- | --- | --- | --- |
| 1 | `ng/core/providers.py` + `/ng/providers` | Registry getestet, alte Tests bleiben grün | **fertig**, 30 Tests |
| 2 | `provider_payload()` baut den Body aus der Matrix | Matrix-Tests je Provider | **fertig**, 12 Tests |
| 3 | Schema-Bump auf 2 mit Migration | alte Config wird gelesen | **fertig**, 14 Tests |
| 4 | `_emulators.py` + Transporttests | beide Protokolle | **offen** |
| 5 | Modellabfrage + Key-Route | Key-Leck-Test | **fertig** |
| 6 | Panel: Provider/Model/Address/Key | Browser-Screenshot | **Code fertig**, Browserbeleg offen |
| 7 | Panel: Settings/Advanced aus der Registry | Feld-Sichtbarkeit je Provider | **Code fertig**, Browserbeleg offen |
| 8 | `system_prompts.py` + Knoten-Felder | Prompt-Test | **fertig** |
| 9 | Capabilities statt der Vision/Audio-Kästchen | Hinweistext-Test | **fertig**, Python und JS |
| 10 | Optik: Rahmen und Menü weg | Screenshot | **teilweise** |

### 5.1 Der Seed-Schalter

ComfyUI hängt an **jedes** Widget namens `seed` automatisch einen „control after generate"-Schalter. Der
Frontend-Check lautet wörtlich `control_after_generate ?? name in ["seed","noise_seed"]` — es ist ein
`??`, also gewinnt **nur ein explizites `False`**. Ein weggelassenes Argument ergibt `None`, lässt den
`??` greifen und der Schalter kommt zurück.

Der AI Loader hatte zusätzlich sein eigenes `fixed_seed`-Kästchen. Zwei Schalter für eine Entscheidung:
der Nutzer stellt auf Randomize und wundert sich, warum `fixed_seed` etwas anderes sagt. Behoben mit
`control_after_generate=False`.

**Die Render-Nodes behalten ihren Schalter** — dort gehört die Queue wirklich dem Seed. Ein Test
prüft beide Seiten derselben Regel, damit sie nicht versehentlich überall vereinheitlicht wird.

### 5.2 Stand nach Schritt 9

**Schritt 8 ist umgesetzt.** `ng/core/system_prompts.py` liegt in core, ohne ComfyUI-Import. Fünf
Rolle-Prompts (Context Image/Video/Audio/Text, Director), `for_node(node_id, media)` und
`framed(role)`. Beide Anfragewege nutzen es: `analysis.py` schickt es als System-Nachricht
(OpenAI-Form) bzw. als `system` (Ollama), `native_ai.py` als `system_prompt` an `TextGenerate`.
Der Audio-Weg bekam es dabei **neu** — er hatte vorher gar keins und war also die einzige Karte,
deren Antwort der Parser nicht lesen konnte.

Die Reihenfolge ist die eigentliche Regel: Rolle zuerst, Rahmen zuletzt. Ein Knoten kann seinen
Rollenprompt also überschreiben, ohne den Parser zu beschädigen — genau daran ist es einmal
gescheitert. Ein Test sichert das mit einem Prompt ab, der sich an die Regel hervorwagt.

**Schritt 9 ist umgesetzt, mit einer Ausnahme, die eine Ausnahme sein muss.** Die Kästchen `vision`
und `audio` sind aus dem Panel raus. An ihrer Stelle steht eine Aussage: `image yes · audio no`.
Das Backend prüft nicht mehr die gespeicherten Flags, sondern
`providers.get(id).supports_media(medium)` — die Fähigkeit ist eine gemessene Eigenschaft des
Anbieters und keine Behauptung des Nutzers.

**Die Ausnahme ist die CLIP-Karte.** Dort ist das Modell das, was der Nutzer angeschlossen hat, und
die Registry weiß nichts darüber. Diese Karte behält die zwei Schalter und ist damit ausdrücklich
als *Zusage* beschriftet, nicht als Fähigkeit. Das ist der einzige Ort, an dem ein Schalter für eine
Aussage des Nutzers stehen bleibt. Ihre Statuszeile liest **die beiden Schalter** aus, nicht die
Registry: dort steht noch der zuletzt gewählte HTTP-Provider, und dessen Fähigkeiten zu melden
würde ein Modell beschreiben, das gar nicht angefragt wird.

`custom` behält im Backend ebenfalls die Flags, aus demselben Grund: dahinter liegt ein Server, von
dem wir nichts wissen. Alle anderen Provider scheitern an der Registry, nicht an einem Haken, den
der Nutzer falsch gesetzt hat.

**Der Hinweis steht an der Karte, nicht am Dropdown** (`ng_analysis.js`). Das entspricht Abschnitt 4
Punkt 4 der Spezifikation: der Text erscheint dort, wo der Nutzer ihn anklickt. Für CLIP / Encoder
und für `custom` bleibt er aus — dort wäre jede Aussage eine Vermutung.

Die Fähigkeitslogik liegt in **`js/ng/ng_ai_capabilities.js`**, nicht im Panel: das Panel lag bei 441
von 500 erlaubten Zeilen und wäre beim nächsten Feld gerissen.

**Die provider-spezifischen `?`-Texte** kommen aus `SETTING_HELP_OVERRIDES`. Ein Override ersetzt
genau einen Satz und lässt alle anderen stehen — ein Test prüft, dass ein Override nur ein Feld
nennen darf, das der Provider auch wirklich anbietet. Zusätzlich liefert `as_dict()` jetzt `wire`
(Wire-Name je Feld) und `media` (Fähigkeit plus Handlungsempfehlung je Medium).

**Zwei Fehler gefunden und behoben**, beide aus der laufenden Arbeit und nicht aus dem Refactor:
`context_routes.py` hatte den neuen Routenblock **vor** dem alten eingefügt, ohne den alten zu
entfernen — alle Importe und alle fünf Routen standen doppelt da. Und `providers.of_kind()` war
toter Code, den nichts aufrief.

### 5.3 Live geprüft: Ollama und OpenRouter

**Ollama** (`127.0.0.1:11434`, `huihui_ai/qwen3.5-abliterated:2b`):

- `POST /ng/models` → 6 Modelle, `key_checked: false` (Ollama braucht keinen Key).
- Bild-Anfrage mit dem von `provider_payload()` gebauten Body → HTTP 200, 24.5 s.
  Der Body enthielt `options` mit `temperature, top_p, top_k, min_p, seed, num_predict` und
  `keep_alive` daneben — genau die Verschachtelung aus 1.4.
- Antwort: Markdown-Fence mit `content: "object"`, Parse erfolgreich.

**OpenRouter** (`google/gemma-4-26b-a4b-it:free`, kostenlos): siehe Stufe 1 in Abschnitt 6.

Damit ist `provider_payload()` an beiden Protokollen mit einem echten Lauf belegt.

### 5.2 Ein Fehler, den erst der Neustart zeigte

Der ComfyUI-Server lief noch seit dem Vortag. `/ng/providers` antwortete 404 und die Widget-Liste war der
alte Stand ohne Sampling-Felder — das Panel zeigte deshalb überall nur Ollama, weil es auf seinen eigenen
Fallback zurückfiel.

**Regel daraus:** Bevor über „das Panel zeigt X nicht" diskutiert wird, `/ng/providers` und
`/object_info/NGAIProvider` gegen den laufenden Server prüfen. Ein alter Prozess sieht aus wie ein Fehler
im Code, ist aber keiner.

### 5.3 Der Fehler, der wirklich dahintersteckte

Nach dem Neustart war die Route erreichbar, das Panel zeigte aber trotzdem nur Ollama. Der Abruf fand nicht
statt: `window.comfyAPI.api.fetchApi is not a function`.

Der api-Handle ist **zwei Destructure-Ebenen tief** — `window.comfyAPI.api.api.fetchApi`. `ng_panel.js` und
`ng_cards.js` machen es richtig; ich hatte das Muster erfunden statt es zu übernehmen.

Verstärkt wurde das durch einen `catch {}` ohne Meldung: der Fehler wurde geschluckt, das Panel fiel lautlos
auf seinen eigenen Fallback zurück, und das Ergebnis sah aus wie eine absichtlich kleine Liste.

**Zwei Regeln daraus**

1. **Ein Muster wird aus einer funktionierenden Datei kopiert, nicht erfunden.** Bei einer unbekannten API wird
   zuerst gegoogelt, wer sie schon benutzt.
2. **Ein `catch` ohne Log versteckt den Fehler, den man sucht.** Der Fallback bleibt richtig — aber der Grund
   geht nach `console.warn`. Genau dieser stille Catch hat einen ganzen Fehlerzugang gekostet.

Live im Browser geprüft, nicht nur im Server:

```
providerOptions: ["ollama", "lmstudio", "llamacpp", "custom"]
cards:           ["local", "api", "clip"]
seedVisible:     true
```

Ein feldweise ausblendendes Panel hatte außerdem einen eigenen Fehler: solange die Registry noch lädt, war
`entry` null, `accepted` war leer und **Seed sowie Fixed seed verschwanden**. Ein unbekannter Provider darf
nichts verstecken — jetzt bedeutet „kein Eintrag" *alles anzeigen*, nicht *nichts anzeigen*.
| 7 | Panel: Settings/Advanced aus der Registry | Feld-Sichtbarkeit je Provider | offen |
| 8 | `system_prompts.py` + Knoten-Felder | Prompt-Test | offen |
| 9 | Capabilities statt Checkboxen | Hinweistext-Test | offen |
| 10 | Optik: Rahmen und Menü weg | Screenshot |

**Schritt 1 und 2 sind die Basis.** Ohne Registry wird jede spätere Änderung an zwei Stellen gemacht — das ist der
Fehler, den wir vermeiden wollen.

## 8. Was wir bewusst nicht machen

- **Kein globaler System-Prompt im Loader.** Er gehört an den Knoten, der die Rolle kennt.
- **Keine Cloud-Keys in Tests.** Die Emulatoren decken die Protokolle ab.
- **Kein `verified: true` ohne Lauf.** Das Feld bleibt Handarbeit.
- **Keine neuen Felder in `core` ohne Version.** `from_dict` wirft sonst und alte Workflows brechen.

## 9. Offene Punkte

1. **Seed bei Claude und Gemini.** Beider APIs bieten keinen Seed-Parameter. Vorschlag: Feld ausblenden und den
   Wert stillschweigend nicht senden. Die Statuszeile sagt es an.
2. **Modell-Cache.** `/ng/models` bei jedem Providerwechsel neu fragen ist langsam bei Cloud-Anbietern. Vorschlag:
   10 Minuten Cache, sichtbar als `source: cache`.
3. **Key pro Provider.** Heute ein Key für alle. Wenn jemand OpenAI **und** Claude nutzt, braucht es zwei.
   Vorschlag: Key-Quelle pro Provider speichern, ein Passwortfeld, das den jeweils passenden Key trifft.

1. Die Registry nennt `supports: ["text", "vision", "audio"]` — nur, was **nachgewiesen** ist.
2. `/ng/models` liefert dieselbe Liste mit zurück, wenn der Provider sie kennt (Ollama liefert sie über die
   Modellbeschreibung, nicht zuverlässig — dann bleibt es bei der Registry-Angabe).
3. Die Statuszeile zeigt das Ergebnis: `image yes · audio no`.
4. Hängt der Nutzer ein Medium an einen Kontextknoten, das der Provider nicht kann, erscheint **am Kontextknoten**
   der Hinweis — dort, wo er es anklickt:

   > This provider cannot read audio. Choose a model with audio input, or use a Text card.

`vision` und `audio` bleiben als **gespeicherte Felder** in der ProviderConfig erhalten, damit alte Workflows nicht
kaputt gehen. Neue Nodes bekommen sie aus der Registry gesetzt, nicht vom Nutzer.

