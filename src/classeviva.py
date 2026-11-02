"""Client minimale per le API web di ClasseViva (Spaggiari).

API non ufficiali (reverse-engineered dal client web). Uso personale:
rispetta un ritmo moderato tra le richieste (v. REQUEST_DELAY).

Flusso:
  1. POST AuthApi4.php?a=aLoginPwd  → cookie di sessione (PHPSESSID, webidentity…)
  2. GET  /rest/w1/students/{id}/noticeboard           → elenco avvisi
  3. POST /rest/w1/students/{id}/noticeboard/read/...  → contenuto (SEGNA COME LETTO!)
  4. GET  /rest/w1/students/{id}/noticeboard/attach/...→ 302 → URL firmato su cdndoc
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

# curl_cffi invece di requests: la WAF di Spaggiari (Akamai) blocca con 403
# il fingerprint TLS di requests/curl standard. impersonate='chrome131'
# riproduce il fingerprint TLS/HTTP2 di Chrome reale.
from curl_cffi import requests as creq

log = logging.getLogger(__name__)

AUTH_URL = "https://web.spaggiari.eu/auth-p7/app/default/AuthApi4.php"
API_BASE = "https://web.spaggiari.eu/rest/w1"
IMPERSONATE = "chrome131"


class ClasseVivaError(RuntimeError):
    """Errore di autenticazione o di chiamata API."""


class ClasseVivaClient:
    def __init__(
        self,
        uid: str,
        password: str,
        cid: str = "",
        pin: str = "",
        request_delay: float = 1.0,
        timeout: float = 30.0,
    ):
        self.uid = uid
        self.password = password
        self.cid = cid
        self.pin = pin
        self.request_delay = request_delay
        self.timeout = timeout
        # Nessun User-Agent custom: lasciamo quelli coerenti dell'impersonation
        self.session = creq.Session(impersonate=IMPERSONATE)
        self.student_id: str | None = None
        self.student_name: str | None = None

    # ── Autenticazione ───────────────────────────────────────────────────
    def login(self) -> dict:
        """Effettua il login e imposta i cookie di sessione."""
        log.info("🔐 Login su ClasseViva come '%s'…", self.uid)
        payload = {
            "uid": self.uid,
            "pwd": self.password,
            "cid": self.cid,
            "pin": self.pin,
            "target": "",
        }
        log.debug("POST %s  (uid=%s, pwd=***, cid=%r, pin=%r)", AUTH_URL, self.uid, self.cid, self.pin)
        resp = self.session.post(AUTH_URL, params={"a": "aLoginPwd"}, data=payload, timeout=self.timeout)
        log.debug("← HTTP %s  body=%s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        body = resp.json()

        auth = body.get("data", {}).get("auth", {})
        if auth.get("actionRequested") == "changePasswordDialog":
            raise ClasseVivaError("La password è scaduta: va cambiata sul sito prima di procedere.")

        if auth.get("verified") and not auth.get("loggedIn"):
            # Più account corrispondono: scegliamo quello con l'uid fornito
            log.info("🔎 Più account corrispondenti, selezione con aLoginSam…")
            resp = self.session.post(
                AUTH_URL, params={"a": "aLoginSam"}, data={"uid": self.uid}, timeout=self.timeout
            )
            log.debug("← HTTP %s  body=%s", resp.status_code, resp.text[:500])
            resp.raise_for_status()
            auth = resp.json().get("data", {}).get("auth", {})

        if not auth.get("loggedIn"):
            errors = auth.get("errors") or body.get("error") or "credenziali non valide?"
            raise ClasseVivaError(f"Login fallito: {errors}")

        account = auth.get("accountInfo", {})
        self.student_id = str(account.get("id", ""))
        self.student_name = f"{account.get('nome', '')} {account.get('cognome', '')}".strip()
        log.info("✅ Login OK — studente: %s (id=%s)", self.student_name or "?", self.student_id or "?")
        log.debug("Cookie di sessione: %s", dict(self.session.cookies))
        return account

    # ── Bacheca ──────────────────────────────────────────────────────────
    def get_noticeboard(self) -> list[dict]:
        """Elenco degli avvisi in bacheca, dal più recente."""
        assert self.student_id, "Chiamare login() prima"
        url = f"{API_BASE}/students/{self.student_id}/noticeboard"
        log.debug("GET %s", url)
        body = self._get_json(url)
        items = body.get("items", [])
        log.info("📋 Bacheca: %d avvisi totali", len(items))
        for it in items:
            log.debug(
                "   • pubId=%s evtCode=%s data=%s allegati=%s | %s",
                it.get("pubId"), it.get("evtCode"), it.get("pubDT"),
                it.get("cntHasAttach"), it.get("cntTitle"),
            )
        return items

    def read_notice(self, evt_code: str, pub_id: str | int) -> dict:
        """Apre un avviso e ne restituisce il contenuto.

        ⚠️ EFFETTO COLLATERALE: l'avviso viene segnato come letto sul registro.
        """
        assert self.student_id, "Chiamare login() prima"
        url = f"{API_BASE}/students/{self.student_id}/noticeboard/read/{evt_code}/{pub_id}/101"
        log.info("📖 Lettura avviso pubId=%s evtCode=%s (segnerà come LETTO)", pub_id, evt_code)
        log.debug("POST %s", url)
        body = self._post_form(url)
        item = body.get("item", {})
        log.debug("← item=%s", str(item)[:500])
        return item

    def download_attachment(
        self, evt_code: str, pub_id: str | int, attach_num: int, dest_dir: Path
    ) -> Path:
        """Scarica un allegato PDF (segue il 302 verso cdndoc.spaggiari.eu)."""
        assert self.student_id, "Chiamare login() prima"
        url = f"{API_BASE}/students/{self.student_id}/noticeboard/attach/{evt_code}/{pub_id}/{attach_num}"
        log.info("⬇️  Download allegato n.%s di pubId=%s", attach_num, pub_id)
        log.debug("GET %s", url)
        self._throttle()
        resp = self.session.get(url, timeout=self.timeout, stream=True, allow_redirects=True)
        log.debug("← HTTP %s  final-url=%s  type=%s",
                  resp.status_code, resp.url, resp.headers.get("Content-Type"))
        resp.raise_for_status()

        filename = self._filename_from_headers(resp, fallback=f"avviso_{pub_id}_{attach_num}.pdf")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        stem, suffix, counter = dest.stem, dest.suffix, 1
        while dest.exists():
            dest = dest_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        size = 0
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                fh.write(chunk)
                size += len(chunk)
        log.info("💾 Salvato %s (%d byte)", dest, size)
        return dest

    # ── Interni ──────────────────────────────────────────────────────────
    def _get_json(self, url: str) -> dict:
        self._throttle()
        resp = self.session.get(url, timeout=self.timeout)
        log.debug("← HTTP %s  body=%s", resp.status_code, resp.text[:500])
        self._raise_with_context(resp)
        return resp.json()

    def _post_form(self, url: str) -> dict:
        self._throttle()
        resp = self.session.post(
            url, data="", headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )
        log.debug("← HTTP %s  body=%s", resp.status_code, resp.text[:500])
        self._raise_with_context(resp)
        return resp.json()

    def _raise_with_context(self, resp: creq.Response) -> None:
        if resp.status_code == 401:
            raise ClasseVivaError(
                "HTTP 401: sessione scaduta o non valida. Rilancia il comando per rifare il login."
            )
        resp.raise_for_status()

    def _throttle(self) -> None:
        if self.request_delay > 0:
            time.sleep(self.request_delay)

    @staticmethod
    def _filename_from_headers(resp: creq.Response, fallback: str) -> str:
        cd = resp.headers.get("Content-Disposition", "")
        if "filename=" in cd:
            raw = cd.split("filename=", 1)[1].strip().strip('"').strip("'")
            if raw:
                return Path(raw).name  # sanitizza percorsi
        return fallback