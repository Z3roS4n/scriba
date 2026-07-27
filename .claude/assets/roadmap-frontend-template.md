# Roadmap frontend — {{NAME}}

> File permanente. Traccia l'applicazione di un redesign/nuovo design alla webapp. In futuro
> arriveranno altre pagine/modalità: **non eliminare questo file**, si estende.

## Design system, decisioni e convenzioni → cartella [`design/`](design/README.md)
**Non duplicare qui.** Scope, fedeltà, processo, harness di anteprima, regole trasversali e log
delle decisioni vivono in [`design/design-system.md`](design/design-system.md) e
[`design/decisions.md`](design/decisions.md). I gap funzionali (design → nessun backend) sono in
[`design/da-implementare.md`](design/da-implementare.md). Questo file traccia **solo l'avanzamento**
per fase/sezione.

## Fasi

### Fase A — Design system + shell (fondamenta)  ✅ = fatto · 🔄 = in corso · ⬜ = da fare
| # | Blocco | Stato | Note |
|---|---|---|---|
| A1 | Token colore/tema in uso dal design system del progetto | ⬜ | |
| A2 | Font | ⬜ | |
| A3 | Tema dark/light (se previsto) + toggle | ⬜ | |
| A4 | Shell desktop (navigazione principale, ricerca/comando globale) | ⬜ | |
| A5 | Shell mobile (se previsto) | ⬜ | |
| A6 | Primitive UI mancanti (installare/creare al bisogno) | ⬜ | |
| A7 | Controlli nativi → primitive stilizzate (select/checkbox/radio) in tutti i form | ⬜ | vedi `design/design-system.md` |

### Fase B — Schermate
| # | Schermata | Route | Componente esistente | Stato |
|---|---|---|---|---|
| B1 | <...> | <...> | <...> | ⬜ |

### Fase C — Mobile (se il design lo prevede come piattaforma separata)
| Gruppo | Schermate | Stato |
|---|---|---|
| <...> | <...> | ⬜ |

## Log avanzamento
- {{TODAY}} — Avvio. Creati `design/` (README, design-system, decisions, da-implementare) e questa roadmap.
