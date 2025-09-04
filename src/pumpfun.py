from __future__ import annotations
from typing import Optional, Dict, Any
import requests

def trade_local_b64(
    base_url: str,
    user_pubkey: str,
    mint: str,
    side: str,                 # "buy" | "sell"
    amount_lamports: int = 0,  # per BUY (SOL in)
    amount_tokens_ui: float = 0.0,  # per SELL (token qty)
    slippage_bps: int = 150,
) -> Optional[str]:
    """
    Endpoint 'local' di PumpPortal dovrebbe restituire una transazione base64 pronta da firmare.
    Poiché esistono varianti diverse, qui usiamo un payload generico. Se l'endpoint non esiste,
    torniamo None e il chiamante resterà su Jupiter.
    """
    url = f"{base_url.rstrip('/')}/trade-local"
    try:
        payload: Dict[str, Any] = {
            "userPublicKey": user_pubkey,
            "mint": mint,
            "slippageBps": slippage_bps,
            "side": side.lower(),
        }
        if side.lower() == "buy":
            payload["amountSolLamports"] = str(amount_lamports)
        else:
            payload["amountTokensUi"] = float(amount_tokens_ui)

        r = requests.post(url, json=payload, timeout=20)
        if r.status_code != 200:
            return None
        data = r.json()
        # esempi possibili:
        # { "transaction": "<base64>" }  oppure { "swapTransaction":"<base64>" }
        return data.get("transaction") or data.get("swapTransaction")
    except Exception:
        return None
