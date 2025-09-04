# src/solana_utils.py — utilità Solana
from __future__ import annotations
from typing import Any, Dict
from solana.rpc.api import Client
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from base58 import b58decode
import json

LAMPORTS_PER_SOL = 1_000_000_000

def get_client(rpc_url: str) -> Client:
    return Client(rpc_url)

def load_keypair_from_base58(b58: str) -> Keypair:
    # accetta sia stringa JSON "[..]" che base58 concatenato
    s = b58.strip()
    if s.startswith("["):
        arr = json.loads(s)
        secret_bytes = bytes(arr)
    else:
        secret_bytes = b58decode(s)
    if len(secret_bytes) == 64:
        return Keypair.from_bytes(secret_bytes)
    elif len(secret_bytes) == 32:
        # alcune esportazioni danno solo la seed (32) -> usa from_seed
        return Keypair.from_seed(secret_bytes)
    else:
        raise ValueError(f"SECRET_KEY_BASE58 lunghezza inattesa: {len(secret_bytes)} bytes")

def sol_to_lamports(sol: float) -> int:
    return int(sol * LAMPORTS_PER_SOL)

def lamports_to_sol(lamports: int) -> float:
    return lamports / LAMPORTS_PER_SOL

def get_token_accounts_by_owner(owner_pubkey: str, mint: str, client: Client | None = None) -> Dict[str, Any]:
    from solana.rpc.types import TokenAccountOpts
    c = client or get_client("https://api.mainnet-beta.solana.com")
    return c.get_token_accounts_by_owner_json_parsed(Pubkey.from_string(owner_pubkey), TokenAccountOpts(mint=mint)).value

def get_token_balance_ui(owner_pubkey: str, mint: str, client: Client | None = None) -> float:
    try:
        res = get_token_accounts_by_owner(owner_pubkey, mint, client=None)
        v = res
        if not v:
            return 0.0
        amt = v[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]
        return float(amt["uiAmount"] or 0.0)
    except Exception:
        return 0.0
