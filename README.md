# Solana Copytrader — Jupiter + PumpPortal (Local) • Clean Edition

Questo progetto monitora un **wallet target** su Solana (es. un trader su pump.fun) e
**replica in automatico** i suoi BUY/SELL (con rapporto e limiti) verso il **tuo wallet**.

- Prima scelta: **Jupiter** (DEX aggregatore).
- Se non c'è route: **PumpPortal Local** (`/api/trade-local`), che costruisce la tx da **firmare** col tuo wallet.
- Retry intelligente su `Blockhash not found` (ricostruisce la tx e reinvia).
- Log CSV in `copytrader_log.csv`.

> ⚠️ Rischio alto: memecoin/copy trading sono estremamente rischiosi. Usa importi minimi e consapevolezza.

## Setup

1. Python 3.10+ consigliato.
2. Installa dipendenze:
   ```bash
   pip install -r requirements.txt
