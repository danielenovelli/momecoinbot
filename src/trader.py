from __future__ import annotations
from typing import Optional
from . import config
from .utils import sol_to_lamports
from .jupiter import jup_quote, jup_swap_tx_b64, send_b64_tx

def copy_buy(client_rpc, my_pubkey: str, mint: str) -> Optional[str]:
    if config.DRY_RUN:
        print(f"🧪 DRY_RUN BUY {config.FIXED_BUY_SOL:.4f} SOL → {mint}")
        return None
    lamports = sol_to_lamports(config.FIXED_BUY_SOL)
    q = jup_quote(config.SOL_MINT, mint, lamports, config.SLIPPAGE_BPS)
    if not q:
        print(f"⚠️ Jupiter: nessuna route per {config.FIXED_BUY_SOL:.4f} SOL → {mint}")
        return None
    tx_b64 = jup_swap_tx_b64(q, my_pubkey)
    if not tx_b64:
        print("⚠️ Jupiter: swapTransaction mancante")
        return None
    try:
        sig = send_b64_tx(client_rpc, tx_b64)
        return sig
    except Exception as e:
        print("❌ Invio fallito:", e)
        return None
