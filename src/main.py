"""bacheca_classeviva — agente che legge la bacheca di ClasseViva e invia
sintesi + allegati PDF su Telegram.

Usage:
    python3 -m src.main              # esecuzione completa
    python3 -m src.main --dry-run    # scarica e prepara, ma NON invia a Telegram
                                     # e NON marca nulla come processato
    python3 -m src.main --backfill-days 30
    python3 -m src.main --verbose     # output verboso (DEBUG) su console
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone

from .classeviva import ClasseVivaClient, ClasseVivaError
from .config import ATTACHMENTS_DIR, ConfigError, ensure_dirs, load_config
from .pdf_text import extract_pdf_text
from .state import StateStore
from .summarizer import summarize_notice
from .telegram import TelegramError, send_document, send_message

log = logging.getLogger("bacheca")


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def _md_escape(text: str) -> str:
    """Escape minimale dei caratteri speciali di Telegram Markdown."""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text


def format_message(title: str, date_str: str, category: str, summary: str) -> str:
    """Compone il messaggio Telegram: data, poi titolo, poi categoria (una riga ciascuna)."""
    lines = []
    if date_str:
        lines.append(f"📅 {date_str}")
    lines.append(f"*{_md_escape(title)}*")
    if category:
        lines.append(f"Categoria: {_md_escape(category)}")
    return "\n".join(lines) + f"\n\n{summary}\n"


def is_recent(item: dict, days: int) -> bool:
    raw = item.get("pubDT") or ""
    try:
        pub_dt = datetime.fromisoformat(raw)
    except ValueError:
        log.debug("Data pubDT non interpretabile (%r): considero recente", raw)
        return True
    if pub_dt.tzinfo is None:
        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
    return pub_dt >= datetime.now(timezone.utc) - timedelta(days=days)


def sort_notices(items: list[dict]) -> list[dict]:
    """Ordina gli avvisi dal più vecchio al più recente (pubDT)."""
    return sorted(items, key=lambda it: it.get("pubDT") or "")


def process_notice(
    client: ClasseVivaClient,
    item: dict,
    cfg,
    state: StateStore,
    dry_run: bool,
) -> None:
    pub_id = item.get("pubId")
    evt_code = item.get("evtCode", "CF")
    title = (item.get("cntTitle") or "Avviso senza titolo").strip()
    date_str = (item.get("pubDT") or "")[:10]
    log.info("━━━ ELABORAZIONE pubId=%s | 📅 %s | %s", pub_id, date_str or "n/d", title)

    # 1) Contenuto testuale dell'avviso (solo se MARK_AS_READ=true)
    notice_text = ""
    if cfg.mark_as_read:
        content = client.read_notice(evt_code, pub_id)
        notice_text = (content.get("text") or "").strip()
        title = (content.get("title") or title).strip()
    else:
        log.info("🚫 MARK_AS_READ=false: salto la lettura del corpo (non segno come letto)")

    # 2) Allegati: download + estrazione testo (rimossi dal disco a fine elaborazione)
    attachment_texts: list[tuple[str, str]] = []
    downloaded: list = []
    try:
        for att in item.get("attachments") or []:
            attach_num = att.get("attachNum")
            if attach_num is None:
                continue
            try:
                path = client.download_attachment(evt_code, pub_id, attach_num, ATTACHMENTS_DIR)
                downloaded.append(path)
                attachment_texts.append((path.name, extract_pdf_text(path)))
            except Exception as exc:
                log.error("❌ Allegato n.%s di pubId=%s non scaricato: %s", attach_num, pub_id, exc)

        # 3) Sintesi
        summary = summarize_notice(
            title, notice_text, attachment_texts, cfg,
            notice_date=date_str, category=item.get("cntCategory") or "",
        )

        message = format_message(title, date_str, item.get("cntCategory") or "", summary)

        # 4) Invio Telegram (saltato in dry-run)
        if dry_run:
            log.info("🏃 DRY-RUN: salto invio Telegram. Messaggio che sarebbe stato inviato:\n%s", message)
            return

        send_message(cfg.tg_bot_token, cfg.tg_chat_id, message)
        if cfg.send_attachments:
            for path in downloaded:
                send_document(cfg.tg_bot_token, cfg.tg_chat_id, path, caption=_md_escape(title)[:200])
        else:
            log.info("📎 SEND_ATTACHMENTS=false: allegati non inviati su Telegram")
    finally:
        # Cache sempre pulita: gli allegati servono solo per l'elaborazione
        for path in downloaded:
            try:
                path.unlink(missing_ok=True)
                log.info("🗑️  Rimosso allegato temporaneo %s", path.name)
            except OSError as exc:
                log.warning("⚠️  Non riesco a rimuovere %s: %s", path, exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bacheca ClasseViva → sintesi PDF su Telegram")
    parser.add_argument("--dry-run", action="store_true",
                        help="non invia a Telegram e non marca gli avvisi come processati")
    parser.add_argument("--backfill-days", type=int, default=None,
                        help="giorni di storico da considerare (default: BACKFILL_DAYS da .env)")
    parser.add_argument("--verbose", action="store_true",
                        help="output verboso su console (livello DEBUG)")
    args = parser.parse_args()

    setup_logging(args.verbose)
    log.info("🚀 Avvio bacheca_classeviva  (dry_run=%s)", args.dry_run)

    try:
        cfg = load_config()
    except ConfigError as exc:
        log.error("❌ %s", exc)
        return 2
    ensure_dirs()

    backfill_days = args.backfill_days if args.backfill_days is not None else cfg.backfill_days
    log.info("⚙️  Config: MARK_AS_READ=%s  BACKFILL_DAYS=%d  REQUEST_DELAY=%.1fs  dry_run=%s",
             cfg.mark_as_read, backfill_days, cfg.request_delay, args.dry_run)
    log.debug("⚙️  Dettagli: uid=%s cid=%r pin=%r telegram_chat=%s llm_model=%r",
              cfg.cv_uid, cfg.cv_cid, cfg.cv_pin, cfg.tg_chat_id, cfg.llm_model)

    client = ClasseVivaClient(
        uid=cfg.cv_uid,
        password=cfg.cv_password,
        cid=cfg.cv_cid,
        pin=cfg.cv_pin,
        request_delay=cfg.request_delay,
    )

    try:
        client.login()
        # Elaborazione in ordine cronologico: dai messaggi più vecchi ai più recenti
        items = sort_notices(client.get_noticeboard())
    except ClasseVivaError as exc:
        log.error("❌ Errore ClasseViva: %s", exc)
        return 1
    except Exception as exc:
        log.error("❌ Errore di rete o API: %s", exc)
        return 1

    with StateStore() as state:
        log.info("🗃  Stato locale: %d avvisi già processati", state.count())
        processed = failed = skipped = 0

        for item in items:
            pub_id = str(item.get("pubId"))
            if state.is_processed(pub_id):
                log.debug("⏭  pubId=%s già processato, salto", pub_id)
                skipped += 1
                continue
            if not is_recent(item, backfill_days):
                log.debug("⏭  pubId=%s più vecchio di %d giorni, salto", pub_id, backfill_days)
                skipped += 1
                continue

            try:
                process_notice(client, item, cfg, state, args.dry_run)
                if not args.dry_run:
                    state.mark_processed(
                        pub_id=pub_id,
                        evt_code=item.get("evtCode", "CF"),
                        cnt_id=str(item.get("cntId", "")),
                        title=item.get("cntTitle", ""),
                    )
                processed += 1
                log.info("✅ pubId=%s completato", pub_id)
            except TelegramError as exc:
                failed += 1
                log.error("❌ pubId=%s: errore Telegram (NON marcato, verrà ritentato): %s", pub_id, exc)
            except Exception as exc:
                failed += 1
                log.exception("❌ pubId=%s: errore imprevisto (NON marcato, verrà ritentato): %s", pub_id, exc)

    # Pulizia finale: rimuove eventuali allegati orfani (es. run interrotte)
    for path in ATTACHMENTS_DIR.glob("*"):
        if path.is_file():
            path.unlink(missing_ok=True)
            log.info("🗑️  Rimosso allegato orfano %s", path.name)

    log.info("🏁 FINE — processati=%d  saltati=%d  falliti=%d", processed, skipped, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())