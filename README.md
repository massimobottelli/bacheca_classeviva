# bacheca_classeviva 📚 → 🤖 → 💬

Agente che accede a **ClasseViva** (registro elettronico Spaggiari), consulta la
**bacheca** (circolari e comunicazioni), **scarica gli allegati PDF**, ne estrae il
testo, lo **sintetizza** con un LLM e invia il tutto su **Telegram**.

> ⚠️ **Disclaimer**: le API usate sono non ufficiali (reverse-engineered dal client
> web di ClasseViva). Questo progetto è pensato per **uso personale** e didattico:
> usalo con moderazione (es. una esecuzione al giorno), a tuo rischio e nel rispetto
> dei termini di servizio della scuola.

## Come funziona

```
login → elenco bacheca → filtro avvisi nuovi → [lettura corpo*] → download PDF
      → estrazione testo → sintesi LLM → invio Telegram (messaggio + PDF)
```

\* La lettura del corpo dell'avviso avviene **solo** se `MARK_AS_READ=true`
(default: `false`). Vedi la sezione dedicata più sotto.

Lo stato locale (SQLite in `data/state.db`) ricorda quali avvisi sono già stati
inviati: ogni esecuzione processa **solo le novità**, e gli avvisi falliti
vengono ritentati alla successiva. L'elaborazione segue l'ordine cronologico:
dai messaggi più vecchi ai più recenti.

## Requisiti

- Python 3.9+
- Un account ClasseViva (studente o genitore)
- Un bot Telegram (creabile gratis con [@BotFather](https://t.me/BotFather))
- *(Opzionale)* Una API key per un LLM (OpenAI, Claude, Gemini, o locale con Ollama)

## Installazione

### macOS

```bash
./scripts/setup_mac.sh
```

### Linux (Debian/Ubuntu)

```bash
./scripts/setup_linux.sh
```

Entrambi gli script creano l'ambiente virtuale `.venv`, installano le dipendenze
(`requests`, `pypdf`, `curl_cffi`) e, se manca, lanciano la **configurazione guidata di `.env`**.

## Configurazione iniziale (.env)

Se vuoi crearlo/aggiornarlo manualmente con le domande guidate:

```bash
source .venv/bin/activate
python3 scripts/setup_env.py
```

In alternativa copia il template e compilalo a mano:

```bash
cp .env.example .env
```

| Variabile | Obbligatoria | Descrizione |
|---|---|---|
| `CV_UID` | ✅ | Nome utente ClasseViva |
| `CV_PASSWORD` | ✅ | Password |
| `CV_CID` | – | Codice scuola (spesso non richiesto) |
| `CV_PIN` | – | PIN (solo se impostato) |
| `MARK_AS_READ` | – | `true`/`false`, default **`false`** |
| `TG_BOT_TOKEN` | ✅ | Token del bot Telegram |
| `TG_CHAT_ID` | ✅ | Chat ID di destinazione |
| `SEND_ATTACHMENTS` | – | Invia i PDF come documenti su Telegram, default **`true`** |
| `LLM_API_URL` | – | Endpoint OpenAI-compatibile per la sintesi |
| `LLM_API_KEY` | – | API key del servizio LLM |
| `LLM_MODEL` | – | Nome del modello (es. `gpt-4o-mini`) |
| `BACKFILL_DAYS` | – | Giorni di storico alla prima esecuzione (default 7) |
| `REQUEST_DELAY` | – | Pausa in secondi tra richieste HTTP (default 1) |

### ⚠️ `MARK_AS_READ=false` (impostazione predefinita)

L'unico modo per leggere il **testo completo** di un avviso è l'endpoint
`noticeboard/read/...`, che però **segna l'avviso come letto** sul registro.
Per non alterare lo stato della tua bacheca:

- Con `MARK_AS_READ=false` (default) l'agente **non legge il corpo** degli avvisi:
  la sintesi si basa su titolo, data, categoria e **testo degli allegati PDF**.
- Con `MARK_AS_READ=true` l'agente recupera anche il corpo del messaggio
  (e segna l'avviso come letto).

### 📎 Allegati PDF

Gli allegati vengono scaricati, usati per estrarre il testo della sintesi e
(con `SEND_ATTACHMENTS=true`, default) inviati su Telegram come documenti.
Vengono poi **sempre rimossi dal disco**: `data/attachments` non si riempie
nel tempo. Con `SEND_ATTACHMENTS=false` si invia solo il messaggio di testo.

### Bot Telegram

1. Su Telegram apri [@BotFather](https://t.me/BotFather) → `/newbot` → scegli nome e username.
2. Copia il **token** fornito in `TG_BOT_TOKEN`.
3. Apri una chat con il tuo nuovo bot e premi **/start**.
4. Scopri la tua chat ID aprendo `https://api.telegram.org/bot<TOKEN>/getUpdates`
   e cercando `"chat":{"id": 123456789, ...}` → mettilo in `TG_CHAT_ID`.

### LLM per la sintesi (opzionale)

Se `LLM_API_URL`/`LLM_API_KEY`/`LLM_MODEL` sono vuoti, la sintesi diventa un
semplice estratto del testo (funziona comunque tutto). Configurazioni tipiche:

```dotenv
# OpenAI
LLM_API_URL=https://api.openai.com/v1/chat/completions
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini

# Claude (endpoint compatibile OpenAI)
LLM_API_URL=https://api.anthropic.com/v1/chat/completions
LLM_API_KEY=sk-ant-...
LLM_MODEL=claude-sonnet-4-5

# Gemini (endpoint compatibile OpenAI)
LLM_API_URL=https://generativelanguage.googleapis.com/v1beta/openai/chat/completions
LLM_API_KEY=...
LLM_MODEL=gemini-2.0-flash

# OpenRouter (molti modelli con un'unica API key)
LLM_API_URL=https://openrouter.ai/api/v1/chat/completions
LLM_API_KEY=sk-or-...
LLM_MODEL=deepseek/deepseek-v4.1-flash

# Ollama locale
LLM_API_URL=http://localhost:11434/v1/chat/completions
LLM_API_KEY=ollama
LLM_MODEL=llama3.1
```

> Nota: se `LLM_API_URL` indica solo la base API (es. `https://openrouter.ai/api/v1`)
> il path `/chat/completions` viene aggiunto automaticamente.

## Utilizzo

```bash
source .venv/bin/activate

# Prova sicura: login, scarica e mostra la sintesi SENZA inviare a Telegram
python3 -m src.main --dry-run

# Esecuzione completa
python3 -m src.main

# Opzioni
python3 -m src.main --backfill-days 30   # processa anche avvisi più vecchi
python3 -m src.main --verbose            # output verboso (livello DEBUG)
```

Di default l'output su console è compatto (livello INFO). Con `--verbose` diventa
**verboso** (livello DEBUG) per il debug: mostra ogni chiamata HTTP con il relativo
body, la configurazione caricata e ogni passo della pipeline.

Codici di uscita: `0` tutto ok, `1` qualche avviso fallito (verrà ritentato),
`2` configurazione mancante.

## Esecuzione automatica (cron)

Una volta verificato il funzionamento manuale, puoi automatizzarlo con lo
script `scripts/run_bacheca.sh`, pensato per cron: lock contro esecuzioni
sovrapposte, log con rotazione in `logs/bacheca.log`, nessuna mail spuria.

```bash
crontab -e
```

```cron
# Ogni giorno alle 08:00
0 8 * * * /Users/massimo/VSCode/bacheca_classeviva/scripts/run_bacheca.sh

# Con opzioni (es. storico più ampio)
0 8 * * * /Users/massimo/VSCode/bacheca_classeviva/scripts/run_bacheca.sh --backfill-days 30
```

Lo script accetta gli stessi argomenti di `python3 -m src.main` e usa
l'interprete di `.venv` se presente. Il log delle esecuzioni è in
`logs/bacheca.log` (oltre 5 MB ruota in `bacheca.log.1`); l'ultimo run si
controlla con `tail -f logs/bacheca.log`.

> **macOS**: concedi a `/usr/sbin/cron` l'accesso completo ai file
> (Impostazioni di Sistema → Privacy e Sicurezza → Accesso completo al disco),
> altrimenti cron non potrà leggere il progetto. In alternativa usa `launchd`
> (plist in `~/Library/LaunchAgents/`).

## Struttura del progetto

```
bacheca_classeviva/
├── .env.example          # template della configurazione
├── requirements.txt      # dipendenze Python (requests, pypdf)
├── scripts/
│   ├── setup_mac.sh      # setup completo su macOS
│   ├── setup_linux.sh    # setup completo su Linux
│   ├── setup_env.py      # configurazione guidata di .env
│   └── run_bacheca.sh    # avvio per cron (log + lock, da crontab)
├── src/
│   ├── config.py         # lettura/validazione di .env
│   ├── classeviva.py     # client API ClasseViva (login, bacheca, allegati)
│   ├── pdf_text.py       # estrazione testo dai PDF
│   ├── summarizer.py     # sintesi via LLM (con fallback senza API key)
│   ├── telegram.py       # invio messaggi/documenti su Telegram
│   ├── state.py          # stato locale SQLite (avvisi già processati)
│   └── main.py           # orchestrazione della pipeline + CLI
├── data/                 # generato: stato + allegati temporanei (rimossi dopo l'uso)
└── logs/                 # generato: log di esecuzione (non committato)
```

## Risoluzione problemi

| Problema | Soluzione |
|---|---|
| `Login fallito` | Verifica credenziali; se hai più account collegati, il login usa `aLoginSam` automaticamente |
| `403 Access Denied` | La WAF di Spaggiari (Akamai) blocca il fingerprint TLS dei client standard: il progetto usa `curl_cffi` con impersonation Chrome, che aggira il blocco. Verifica che sia installato (`pip install curl_cffi`) e che la versione sia aggiornata |
| `HTTP 401` | Sessione scaduta: rilancia semplicemente il comando |
| `La password è scaduta` | Cambiala sul sito, poi aggiorna `.env` |
| Telegram `chat not found` | Hai avviato la chat col bot con `/start`? Controlla `TG_CHAT_ID` |
| PDF senza testo estratto | Probabile scansione immagine: servirebbe OCR (fuori scope attuale) |
| Nessun avviso processato | Alza `BACKFILL_DAYS` o verifica che ci siano novità: lo stato salta il già processato |