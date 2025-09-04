# src/jupiter.py — integrazione Jupiter Quote/Swap con firma locale
import base64
import requests
from solders.transaction import VersionedTransaction
from solana.rpc.types import TxOpts
from . import config

def jup_quote(input_mint: str, output_mint: str, amount: int, slippage_bps: int):
    url = f"{config.JUP_BASE}/quote?inputMint={input_mint}&outputMint={output_mint}&amount={amount}&slippageBps={slippage_bps}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    routes = data.get("data") or []
    return routes[0] if routes else None

def jup_swap(user_pubkey: str, route: dict) -> str:
    """Ritorna la transazione base64 (swapTransaction) da firmare."""
    url = f"{config.JUP_BASE}/swap"
    payload = {
        "userPublicKey": user_pubkey,
        "wrapAndUnwrapSol": True,
        "useSharedAccounts": True,
        "asLegacyTransaction": False,
        "dynamicComputeUnitLimit": True,
        "dynamicSlippage": False,
        "quoteResponse": route,
    }
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    tx_b64 = data.get("swapTransaction")
    if not tx_b64:
        raise RuntimeError("Jupiter non ha restituito una transazione di swap.")
    return tx_b64

def sign_and_send(client, keypair, tx_b64: str) -> str:
    """Decodifica base64, firma col keypair, invia con TxOpts."""
    raw = base64.b64decode(tx_b64)
    tx = VersionedTransaction.from_bytes(raw)
    tx = VersionedTransaction(tx.message, [keypair])
    raw_signed = bytes(tx)
    resp = client.send_raw_transaction(raw_signed, opts=TxOpts(skip_preflight=False, max_retries=5))
    try:
        return str(resp.value)
    except Exception:
        try:
            return str(resp["result"])
        except Exception:
            return str(resp)
