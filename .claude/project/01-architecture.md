# Scriba — Architettura

> Ultimo aggiornamento: 2026-07-27. Documento vivo: aggiornare a ogni decisione architetturale.

## Visione
<una-due frasi: cosa fa il prodotto e per chi>

## Diagramma logico
```
<schema ASCII dei componenti: client, server, DB, servizi esterni>
```

## Componenti chiave
### 1. <Componente>
- <responsabilità, tecnologie, confini>

## Flussi principali
1. <flusso end-to-end critico>

## Struttura repo
```
src/
  app/        # entrypoint / route
  server/     # logica server-only (services, db, integrazioni)
  components/ # UI
  lib/        # utility pure e schema
```
