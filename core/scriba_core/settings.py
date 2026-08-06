"""Impostazioni dell'applicazione.

Un file JSON accanto al database. Le chiavi API stanno qui e non nel database
perché è più facile spiegare a qualcuno "cancella questo file" che "apri il
database e svuota questa tabella".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PREDEFINITE: dict[str, Any] = {
    "llm": {
        # Il locale è il predefinito: una call di lavoro contiene nomi, cifre e
        # questioni che non c'è motivo di mandare fuori se la macchina può fare
        # il lavoro da sola.
        "provider": "local",
        "base_url": "http://127.0.0.1:8080",
        "model": "gemma-4-12b-it",
        "api_key": "",
    },
    "stt": {
        "provider": "local",
        "lingua": "it",
        # None = predefinito di sistema. Valorizzati solo se l'utente sceglie
        # un dispositivo specifico dalle impostazioni.
        "microfono_id": None,
        "loopback_id": None,
        "filtro_eco": "medio",
        # Nomi che il modello non conosce e sbaglia a ogni occorrenza: clienti,
        # partecipanti, prodotti. Vengono rimessi a posto dopo la trascrizione
        # (vedi stt/glossario.py) perché Parakeet non ha un modo di riceverli
        # prima.
        "glossario": [],
        # Quanto può essere storpiata una parola perché venga comunque
        # riconosciuta: 'prudente' | 'medio' | 'aggressivo'. Prudente di
        # default — allargare la rete significa anche correggere nomi che
        # erano già giusti, e quello non lo si nota rileggendo.
        "glossario_livello": "prudente",
        # I nomi dei clienti entrano nel glossario da soli: sono già scritti
        # nell'anagrafica, e riscriverli a mano è il modo di tenerli disallineati.
        "glossario_clienti": True,
        # Ripassare la trascrizione a call finita con Canary, che è più preciso
        # e a cui la lingua si può imporre davvero (vedi stt/rifinitura.py).
        # Spenta: costa un modello da 1 GB da scaricare e minuti di CPU dopo
        # ogni call. Il comando resta disponibile a mano sulla singola call.
        "rifinitura_automatica": False,
    },
    "analisi_automatica": True,
    # Aggiorna una nota di lavoro mentre la call è ancora in corso, invece di
    # aspettare la fine. Spento di default: costa una chiamata al modello ogni
    # finestra, e non tutti la vogliono accesa per ogni call.
    "note_incrementali": False,
    "interfaccia": {
        # 'scuro' | 'chiaro' | 'sistema'.
        #
        # Scuro come predefinito, non "come il sistema": Scriba è sempre stato
        # scuro, e far cambiare aspetto da sola a un'applicazione già
        # installata, perché qualcun altro ha deciso il default, è una
        # sorpresa che nessuno ha chiesto. Chi vuole seguire il sistema lo
        # sceglie, ed è una scelta sola.
        "tema": "scuro",
        # Scorciatoie globali: funzionano anche quando Scriba non ha il fuoco,
        # che è il punto — durante una call il fuoco ce l'ha la riunione.
        "scorciatoia_overlay": "Alt+R",
        "scorciatoia_screenshot": "CommandOrControl+Shift+S",
        # Quante righe tiene l'overlay. Poche di proposito: sta sopra la
        # finestra della call e più cresce più copre quello che serve vedere.
        "righe_overlay": 6,
        "opacita_overlay": 0.92,
        "overlay_ridotto": False,
    },
    "rilevamento": {
        # Sorveglia il microfono per accorgersi quando si entra in una call.
        # Attivo di default: è la funzione per cui l'applicazione esiste, e
        # limitarsi a proporre non è invasivo.
        "attivo": True,
        # Proporre e basta. Avviare da soli una registrazione che coinvolge
        # altre persone non è una decisione che spetta a un programma.
        "avvio_automatico": False,
        "conferma_s": 5.0,
    },
    "export": {
        # None = accanto al database, come già fa /export/markdown quando non
        # gli si passa una destinazione.
        "cartella": None,
        "formato": "markdown",
    },
}


class Settings:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._dati = self._leggi()

    def _leggi(self) -> dict[str, Any]:
        if not self.path.exists():
            return json.loads(json.dumps(PREDEFINITE))
        try:
            salvate = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Un file rovinato non deve impedire l'avvio: si riparte dai valori
            # predefiniti invece di lasciare l'utente senza applicazione.
            return json.loads(json.dumps(PREDEFINITE))

        unite = json.loads(json.dumps(PREDEFINITE))
        for chiave, valore in salvate.items():
            if isinstance(valore, dict) and isinstance(unite.get(chiave), dict):
                unite[chiave].update(valore)
            else:
                unite[chiave] = valore
        return unite

    def tutto(self, *, con_segreti: bool = False) -> dict[str, Any]:
        dati = json.loads(json.dumps(self._dati))
        if not con_segreti:
            # Verso l'interfaccia si dice se una chiave c'è, non qual è.
            llm = dati.get("llm", {})
            llm["api_key_presente"] = bool(llm.pop("api_key", ""))
        return dati

    def llm(self) -> dict[str, Any]:
        return dict(self._dati.get("llm", {}))

    def aggiorna(self, modifiche: dict[str, Any]) -> dict[str, Any]:
        for chiave, valore in modifiche.items():
            if isinstance(valore, dict) and isinstance(self._dati.get(chiave), dict):
                # Una chiave API vuota significa "non la sto cambiando", non
                # "cancellala": altrimenti salvare una qualsiasi impostazione
                # dall'interfaccia la spazzerebbe via.
                valore = {k: v for k, v in valore.items() if not (k == "api_key" and v == "")}
                self._dati[chiave].update(valore)
            else:
                self._dati[chiave] = valore
        self.salva()
        return self.tutto()

    def salva(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._dati, ensure_ascii=False, indent=2), encoding="utf-8"
        )
