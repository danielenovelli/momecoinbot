# Solana CopyTrader (Pump.fun & DEX) — Python

Monitora un wallet **target** su Solana e **replica** automaticamente BUY/SELL dal tuo wallet
con importi ridotti. Usa **Jupiter** per gli swap e, se abilitato, un **fallback Pump.fun**
per operare su token appena creati (bonding curve) quando Jupiter non ha ancora rotta.

> ⚠️ Rischi elevati: memecoin/pump.fun sono volatili e possono essere rug/honeypot.
> Usa SEMPRE un wallet dedicato e prova prima con `TEST_MODE=true` e/o `DRY_RUN=true`.

## Funzionalità
- Polling RPC del wallet target con classificazione **BUY/SELL**
- Esecuzione copia via **Jupiter** (quote + swap) quando disponibile
- **Fallback Pump.fun** (facoltativo) per bonding curve (richiede endpoint di terze parti)
- Sicurezze: `COPY_RATIO`, `MAX_PER_TRADE_SOL`, `DAILY_SOL_BUDGET`, `SLIPPAGE_BPS`, `BLACKLIST`
- **TEST_MODE** (esecuzioni simulate) e **DRY_RUN** (solo logging)
- Storico in **CSV** (`logs/trades.csv`)
- Notifiche **Telegram** opzionali

## Struttura
```
solana-copytrader-full/
├─ README.md
├─ requirements.txt
├─ .env.example
├─ scripts/
│  └─ run.sh
└─ src/
   ├─ main.py
   ├─ config.py
   ├─ notifier.py
   ├─ solana_utils.py
   ├─ classifier.py
   ├─ jupiter.py
   ├─ pumpfun.py
   ├─ copy_engine.py
   ├─ history.py
   └─ state.json          # generato a runtime
```

## Installazione
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Apri .env e compila i campi richiesti
```

## Esecuzione
```bash
bash scripts/run.sh
# oppure
python -m src.main
```

## Note su Pump.fun fallback
Per operare su token appena creati, serve un endpoint che esponga quote/swap per la **bonding curve**.
Imposta `ENABLE_PUMPFUN=true` e `PUMPFUN_BASE=<endpoint>` nel `.env`.
Questo repository include un client **placeholder** (vedi `src/pumpfun.py`): adegua gli URL ai provider (es. QuickNode Metis, PumpPortal).

## CSV storico
Ogni azione rilevante viene scritta in `logs/trades.csv` con: timestamp, azione, mint, quantità, SOL, ratio, slippage, signature della tua tx (se eseguita), signature sorgente, note.

## Licenza
MIT
