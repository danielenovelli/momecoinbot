from __future__ import annotations
from typing import Optional, Dict, Any
import requests
from base64 import b64decode
from solders.transaction import VersionedTransaction

def jup_quote(input_mint: str, output_mint: str, amount: int, slippage_bps: int) -> Optional[Dict[str, Any]]:
    url = "https://quote-api.jup.ag/v6/quote"
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": str(slippage_bps),
        "onlyDirectRoutes": "false",
    }
    r = requests.get(url, params=params, timeout=20)
    if r.status_code != 200:
        return None
    data = r.json()
    if isinstance(data, dict) and "data" in data:
        routes = data["data"]
        if isinstance(routes, list) and routes:
            return routes[0]
        if isinstance(routes, dict):
            return routes
    return None

def jup_swap_tx_b64(quote: Dict[str, Any], user_pubkey: str) -> Optional[str]:
    url = "https://quote-api.jup.ag/v6/swap"
    payload = {
        "userPublicKey": user_pubkey,
        "quoteResponse": quote,
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": "auto"
    }
    r = requests.post(url, json=payload, timeout=25)
    if r.status_code != 200:
        return None
    data = r.json()
    return data.get("swapTransaction")

def send_b64_tx(client_rpc, tx_b64: str) -> str:
    raw = b64decode(tx_b64)
    tx = VersionedTransaction.from_bytes(raw)
    sig = client_rpc.send_raw_transaction(bytes(tx)).value  # type: ignore[attr-defined]
    return str(sig)
