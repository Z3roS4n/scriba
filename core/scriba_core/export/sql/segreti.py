"""Cifra l'indirizzo del database con la chiave dell'utente di Windows.

Il token di Notion sta in chiaro in un file accanto al database, e per una
chiave API di un servizio è una scelta difendibile. Qui no: l'URL di
connessione contiene la password di un PostgreSQL che può essere di produzione,
e chi legge quel file ci entra dentro.

Windows ha già quello che serve — DPAPI — e non richiede né una dipendenza né
una passphrase da chiedere all'utente: cifra con una chiave derivata dal suo
account. Un altro utente dello stesso computer non lo legge, e nemmeno chi si
porta via il file.

**Cosa questo NON protegge.** Un programma che gira come te può richiamare
DPAPI esattamente come lo facciamo noi. Non è una cassaforte contro chi ha già
il tuo account: è la differenza fra una password che si legge aprendo un file
e una che no.

Se DPAPI non risponde — non è Windows, o la chiamata fallisce — si salva in
chiaro con l'etichetta che dice che è in chiaro. Un connettore che si rifiuta
di funzionare sarebbe peggio, ma nascondere in quale delle due forme è finito
il segreto sarebbe peggio ancora.
"""

from __future__ import annotations

import base64
import ctypes
import logging
import sys
from ctypes import wintypes

log = logging.getLogger(__name__)

#: I due prefissi con cui un valore salvato dice come è stato salvato.
CIFRATO = "dpapi:"
CHIARO = "chiaro:"

#: Legato al segreto: DPAPI lo richiede identico per decifrare, e se cambia il
#: valore diventa illeggibile. Non è un ingrediente segreto, è un'etichetta.
_ENTROPIA = b"scriba/database-remoto/v1"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def bytes(self) -> bytes:
        return ctypes.string_at(self.pbData, self.cbData)


def _blob(dati: bytes) -> _Blob:
    buf = ctypes.create_string_buffer(dati, len(dati))
    return _Blob(len(dati), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def disponibile() -> bool:
    return sys.platform == "win32"


def cifra(valore: str) -> str:
    """Restituisce il valore pronto da salvare, con il prefisso che dice come."""
    if not valore:
        return ""
    if not disponibile():
        return CHIARO + valore

    try:
        dentro = _blob(valore.encode("utf-8"))
        entropia = _blob(_ENTROPIA)
        fuori = _Blob()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(dentro), None, ctypes.byref(entropia), None, None, 0, ctypes.byref(fuori)
        )
        if not ok:
            raise OSError(ctypes.GetLastError())
        try:
            return CIFRATO + base64.b64encode(fuori.bytes()).decode("ascii")
        finally:
            ctypes.windll.kernel32.LocalFree(fuori.pbData)
    except Exception as exc:
        log.warning("Segreto salvato in chiaro: DPAPI non ha risposto (%s)", exc)
        return CHIARO + valore


def decifra(salvato: str) -> str:
    """Il valore originale. Stringa vuota se non si riesce a leggerlo.

    Non solleva: un segreto illeggibile — perché è stato copiato da un altro
    account, o da un altro computer — deve presentarsi come «non collegato», che
    è la verità, e non come un guasto dell'applicazione.
    """
    if not salvato:
        return ""
    if salvato.startswith(CHIARO):
        return salvato[len(CHIARO) :]
    if not salvato.startswith(CIFRATO):
        # Salvato da una versione precedente a questo file: era in chiaro senza
        # etichetta.
        return salvato
    if not disponibile():
        log.warning("Segreto cifrato con DPAPI, ma questo sistema non lo sa leggere.")
        return ""

    try:
        grezzo = base64.b64decode(salvato[len(CIFRATO) :])
        dentro = _blob(grezzo)
        entropia = _blob(_ENTROPIA)
        fuori = _Blob()
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(dentro), None, ctypes.byref(entropia), None, None, 0, ctypes.byref(fuori)
        )
        if not ok:
            raise OSError(ctypes.GetLastError())
        try:
            return fuori.bytes().decode("utf-8")
        finally:
            ctypes.windll.kernel32.LocalFree(fuori.pbData)
    except Exception as exc:
        log.warning("Segreto non decifrabile su questo account (%s)", exc)
        return ""


def in_chiaro(salvato: str) -> bool:
    """Il segreto è finito in chiaro? Si dice all'utente, non si nasconde."""
    return bool(salvato) and not salvato.startswith(CIFRATO)
