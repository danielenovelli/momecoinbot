from __future__ import annotations
from typing import Optional, Dict, Any
import requests

from .solana_utils import send_and_confirm_b64_tx

class JupiterClient:
    def __init__(self, base_url: str = "https://quote-api.jup.ag/v6"):
        self.base = base_url.rstrip("/")

    def quote(
        self,
        input_mint: str,
        output_mint: str,
        amount_in_lamports: int,
        slippage_bps: int = 100,
        only_direct_routes: bool = False,
    ) -> Optional[Dict[str, Any]]:
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount_in_lamports),
            "slippageBps": str(slippage_bps),
            "onlyDirectRoutes": str(only_direct_routes).lower(),
        }
        r = requests.get(f"{self.base}/quote", params=params, timeout=20)
        if r.status_code != 200:
            return None
        data = r.json()
        # api v6: una singola route in 'data' o lista?
        if isinstance(data, dict) and "data" in data:
            routes = data["data"]
            if isinstance(routes, list) and routes:
                return routes[0]
            if isinstance(routes, dict):
                return routes
        return None

    def swap_tx_b64(self, quote: Dict[str, Any], user_pubkey: str) -> Optional[str]:
        payload = {
            "userPublicKey": user_pubkey,
            "quoteResponse": quote,
            "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": True,
            "prioritizationFeeLamports": "auto",
        }
        r = requests.post(f"{self.base}/swap", json=payload, timeout=25)
        if r.status_code != 200:
            return None
        data = r.json()
        # risposta tipica: { "swapTransaction": "<base64>" }
        return data.get("swapTransaction")

def execute_swap_via_jupiter(
    client_rpc,
    jup: JupiterClient,
    user_pubkey: str,
    input_mint: str,
    output_mint: str,
    amount_in_lamports: int,
    slippage_bps: int,
) -> Optional[str]:
    q = jup.quote(input_mint, output_mint, amount_in_lamports, slippage_bps)
    if not q:
        return None
    tx_b64 = jup.swap_tx_b64(q, user_pubkey)
    if not tx_b64:
        return None
    try:
        sig = send_and_confirm_b64_tx(client_rpc, tx_b64)
        return sig
    except Exception:
        return None
