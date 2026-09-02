"""Quanto trova davvero la ricerca semantica, e con quale modello.

Prima di scegliere quali pesi spedire (#104) servono due numeri che non si
possono dedurre dalla scheda del modello:

- **quanto trova**: su domande poste come le pone chi cerca — con altre parole
  rispetto a quelle dette in call — quante volte il passaggio giusto esce
  primo, e quante volte esce nei primi tre. Il secondo numero conta più del
  primo: chi cerca guarda tre righe, non una.
- **quanto separa**: la distanza fra il punteggio del passaggio giusto e quello
  del primo passaggio sbagliato. È questo numero, non il punteggio assoluto,
  a dire se una soglia è possibile.

Il confronto è contro una base lessicale — parole in comune, che è in piccolo
quello che fa l'indice FTS5 già presente — perché «la ricerca semantica
funziona» senza un termine di paragone non vuol dire niente: se trovasse quanto
la ricerca per parole, non varrebbe i megabyte che costa.

Uso:
    python spikes/bench_semantica.py <cartella-con-model_f32.onnx-e-tokenizer.json> [altre...]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

from scriba_core.semantica.modello import EmbedderE5  # noqa: E402

# Un archivio finto ma verosimile: quattro call di lavoro, il parlato spezzato
# come lo spezzerebbe `semantica/spezza.py`. Le domande più sotto sono scritte
# apposta con parole diverse da quelle dei passaggi: se coincidessero, si
# starebbe misurando la ricerca per parole con passaggi in più.
ARCHIVIO = [
    "Allora sul preventivo: la cifra che abbiamo messo giù non ci sta dentro. Se dobbiamo "
    "aggiungere anche la parte di formazione bisogna rivedere la tariffa oraria, altrimenti "
    "ci rimettiamo su tutto il progetto.",
    "La consegna era prevista per il quindici di aprile ma il fornitore ci ha spostato tutto "
    "di tre settimane. Realisticamente prima di inizio maggio non riusciamo a portarvi niente "
    "in produzione.",
    "Per la parte tecnica useremmo Postgres come già fate voi, con lo schema separato così non "
    "tocchiamo niente di quello che avete adesso. La migrazione dei dati storici la facciamo "
    "in una finestra notturna.",
    "Sì scusate un attimo che mi si è bloccato il video. Mi sentite adesso? Ecco, perfetto, "
    "allora riprendo da dove ero rimasto.",
    "Il contratto lo giriamo all'ufficio legale lunedì. Loro di solito ci mettono una "
    "settimana, quindi contate che la firma arriva verso fine mese, non prima.",
    "Abbiamo preso due persone nuove nel gruppo di supporto, quindi i tempi di risposta "
    "dovrebbero scendere parecchio rispetto a quello che avete visto a gennaio.",
    "Quello che mi preoccupa è il budget del prossimo anno: se ci tagliano come dicono, "
    "questo progetto è il primo che salta.",
    "Vi mando dopo la call il verbale con tutti i punti che ci siamo detti, così avete anche "
    "i riferimenti alle slide che vi ho mostrato oggi.",
    "L'anno scorso abbiamo perso tre giorni per un disco pieno sul server di produzione. "
    "Da allora c'è un controllo automatico che avvisa quando si supera l'ottanta per cento.",
    "Se dobbiamo integrare anche il gestionale vecchio serve qualcuno che ci dia le "
    "credenziali di accesso, perché quello lo tiene ancora il fornitore di prima.",
    "Sulla privacy: i dati dei dipendenti non escono dall'Italia, restano sui nostri server. "
    "È scritto nel contratto quadro che avete già firmato voi l'anno scorso.",
    "Il capo dice che senza un risparmio dimostrabile del venti per cento non ci autorizzano "
    "a rinnovare. Dobbiamo portargli dei numeri, non delle impressioni.",
    "Facciamo una prova con dieci utenti per un mese e poi decidiamo. Se funziona lo apriamo "
    "a tutto l'ufficio commerciale, altrimenti ci siamo fermati in tempo.",
    "La formazione la facciamo in due mezze giornate invece che in una intera: la gente non "
    "regge otto ore di corso e si dimentica metà delle cose.",
    "Il vostro sistema attuale ci mette venti minuti a tirare fuori il report mensile. "
    "Il nostro lo fa in meno di un minuto, e questo è il numero che vi interessa.",
    "Mi raccomando: la fattura intestatela alla sede di Milano, non a quella di Torino, "
    "altrimenti l'amministrazione ce la rimanda indietro come l'altra volta.",
    "Marco segue la parte tecnica, io seguo la parte commerciale. Per qualunque cosa sui "
    "tempi di sviluppo scrivete direttamente a lui che è più veloce di me.",
    "Ad agosto non c'è nessuno, quindi se partiamo a luglio poi ci fermiamo comunque. "
    "Tanto vale far partire tutto a settembre con la squadra al completo.",
    "La cosa che ci ha convinti della vostra proposta è che non dobbiamo buttare via quello "
    "che abbiamo già: le altre due ci chiedevano di ricominciare da zero.",
    "Se il collaudo va male voi ci rimborsate quanto abbiamo versato all'inizio, senza "
    "penali per nessuno dei due. Questo mettetelo nero su bianco.",
]

# (domanda, indice del passaggio che risponde). Le parole della domanda non
# compaiono nel passaggio: è il punto della prova.
DOMANDE: list[tuple[str, int]] = [
    ("hanno detto che costiamo troppo", 0),
    ("quando ci arriva la roba", 1),
    ("che database usiamo", 2),
    ("quando ci mettono la firma", 4),
    ("hanno assunto gente nuova", 5),
    ("rischiamo di perdere il progetto per i soldi", 6),
    ("cos'era successo al server", 8),
    ("chi ha le password del vecchio programma", 9),
    ("dove finiscono i dati personali", 10),
    ("cosa vogliono per rinnovare", 11),
    ("partiamo in piccolo prima di allargare?", 12),
    ("come è organizzato il corso", 13),
    ("quanto è più veloce del loro", 14),
    ("a chi va intestata la fattura", 15),
    ("a chi scrivo per lo sviluppo", 16),
    ("perché non iniziamo prima dell'estate", 17),
    ("perché hanno scelto noi", 18),
    ("cosa succede se il collaudo non passa", 19),
]


def lessicale(domanda: str, archivio: list[str]) -> np.ndarray:
    """Base di confronto: quante parole della domanda compaiono nel passaggio.

    È l'ossatura di quello che fa FTS5 — token in comune — senza la sua
    pesatura. Basta a rispondere alla domanda che conta: c'è qualcosa che le
    parole in comune non trovano?
    """
    parole = {p.strip(".,:;?!«»").lower() for p in domanda.split() if len(p) > 3}
    return np.array(
        [len(parole & {q.strip(".,:;?!«»").lower() for q in testo.split()}) for testo in archivio],
        dtype=np.float32,
    )


def valuta(punteggi: np.ndarray, attesi: list[int]) -> dict[str, float]:
    primo = secondo = terzo = 0
    reciproci: list[float] = []
    margini: list[float] = []
    for riga, atteso in zip(punteggi, attesi, strict=True):
        ordine = np.argsort(-riga)
        posizione = int(np.where(ordine == atteso)[0][0])
        primo += posizione == 0
        secondo += posizione < 2
        terzo += posizione < 3
        reciproci.append(1.0 / (posizione + 1))
        # Quanto il giusto stacca il migliore fra gli sbagliati. Negativo
        # quando il giusto non è primo.
        migliore_sbagliato = max(float(riga[i]) for i in range(len(riga)) if i != atteso)
        margini.append(float(riga[atteso]) - migliore_sbagliato)
    n = len(attesi)
    return {
        "primo": primo / n,
        "primi_tre": terzo / n,
        "mrr": float(np.mean(reciproci)),
        "margine": float(np.mean(margini)),
        "margine_min": float(np.min(margini)),
    }


def tagli(punteggi: np.ndarray, attesi: list[int], quanti: list[float]) -> str:
    """Dove si può tagliare senza perdere la risposta giusta.

    I punteggi di E5 stanno tutti fra 0,80 e 0,90 anche fra frasi che non
    c'entrano niente: una soglia assoluta («mostra sopra 0,75») mostrerebbe
    tutto o niente. L'unica soglia che significhi qualcosa è **relativa al
    migliore** di quella ricerca, e quanto valga va misurato, non scelto.
    """
    fuori = []
    for margine in quanti:
        tenuti, trovati = [], 0
        for r, atteso in zip(punteggi, attesi, strict=True):
            soglia = float(r.max()) - margine
            sopra = [i for i in range(len(r)) if float(r[i]) >= soglia]
            tenuti.append(len(sopra))
            trovati += atteso in sopra
        fuori.append(
            f"    -{margine:.3f}: tiene {np.mean(tenuti):4.1f} passaggi su {punteggi.shape[1]}, "
            f"la risposta giusta ci sta {trovati}/{len(attesi)} volte"
        )
    return "\n".join(fuori)


def riga(nome: str, m: dict[str, float], extra: str = "") -> str:
    return (
        f"{nome:<22} primo {m['primo']:5.0%}  primi tre {m['primi_tre']:5.0%}  "
        f"MRR {m['mrr']:.3f}  margine medio {m['margine']:+.4f}  peggiore {m['margine_min']:+.4f}"
        f"{extra}"
    )


def main() -> int:
    cartelle = [Path(a) for a in sys.argv[1:]]
    if not cartelle:
        print(__doc__)
        return 2

    domande = [d for d, _ in DOMANDE]
    attesi = [i for _, i in DOMANDE]

    base = np.vstack([lessicale(d, ARCHIVIO) for d in domande])
    print(f"{len(ARCHIVIO)} passaggi, {len(domande)} domande\n")
    print(riga("parole in comune", valuta(base, attesi)))

    for cartella in cartelle:
        modello = cartella / "model_f32.onnx"
        if not modello.exists():
            print(f"{cartella.name:<22} manca {modello.name}")
            continue
        t0 = time.perf_counter()
        embedder = EmbedderE5(modello, cartella / "tokenizer.json")
        caricato = time.perf_counter() - t0

        t0 = time.perf_counter()
        passaggi = embedder.vettori(ARCHIVIO, come="passaggio")
        per_passaggio = (time.perf_counter() - t0) / len(ARCHIVIO) * 1000

        t0 = time.perf_counter()
        query = embedder.vettori(domande, come="domanda")
        per_domanda = (time.perf_counter() - t0) / len(domande) * 1000

        somiglianze = query @ passaggi.T
        extra = (
            f"\n{'':22} carica {caricato:.1f}s · {per_passaggio:.0f}ms a passaggio · "
            f"{per_domanda:.0f}ms a domanda · {modello.stat().st_size / 1e6:.0f} MB"
        )
        print(riga(cartella.name, valuta(somiglianze, attesi), extra))
        print(tagli(somiglianze, attesi, [0.01, 0.02, 0.03, 0.05, 0.08]))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
