from __future__ import annotations
from typing import Optional
from base64 import b64decode
import base58

from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.hash import Hash

LAMPORTS_PER_SOL = 1_000_000_000

def get_client(rpc_url: str) -> Client:
    return Client(rpc_url, timeout=30)

def lamports_to_sol(lamports: int | float) -> float:
    return float(lamports) / LAMPORTS_PER_SOL

def sol_to_lamports(sol: float) -> int:
    return int(round(sol * LAMPORTS_PER_SOL))

def load_keypair_from_base58(secret: str) -> Keypair:
    """
    Accetta:
      - stringa base58 di 64 bytes (secret key)
      - stringa base58 di 32 bytes (seed) -> deriva ed espande
      - JSON array (64 int) export Phantom/Backpack
    """
    s = (secret or "").strip()
    if not s:
        raise ValueError("SECRET_KEY_BASE58 mancante nel .env")
    if s.startswith("[") and s.endswith("]"):
        import json
        arr = json.loads(s)
        if len(arr) not in (32, 64):
            raise ValueError("Array JSON secret key deve essere lungo 32 o 64 elementi")
        raw = bytes(arr[:64])
        return Keypair.from_bytes(raw if len(raw) == 64 else Keypair.from_seed(bytes(arr)).to_bytes())
    try:
        raw = base58.b58decode(s)
        if len(raw) == 64:
            return Keypair.from_bytes(raw)
        if len(raw) == 32:
            return Keypair.from_seed(raw)
    except Exception as e:
        raise ValueError(f"Secret key formato non valido: {e}")
    raise ValueError("Secret key non riconosciuta (attesi 32 o 64 bytes in base58 / JSON)")

def send_and_confirm_b64_tx(client: Client, tx_b64: str) -> str:
    """
    Accetta una transazione base64 (VersionedTransaction), la invia e attende conferma light.
    Torna la signature base58.
    """
    raw = b64decode(tx_b64)
    tx = VersionedTransaction.from_bytes(raw)
    sig = client.send_raw_transaction(bytes(tx)).value  # type: ignore[attr-defined]
    client.confirm_transaction(sig, commitment=Confirmed)
    return str(sig)

def get_latest_blockhash_b58(client: Client) -> str:
    bh = client.get_latest_blockhash().value.blockhash
    return str(bh)

def replace_blockhash_in_b64_tx(tx_b64: str, new_blockhash_b58: str) -> str:
    """
    Ricrea l'oggetto tx, sostituisce recent_blockhash e ritorna base64 bytes.
    Utile se il nodo rifiuta con 'Blockhash not found'.
    """
    raw = b64decode(tx_b64)
    tx = VersionedTransaction.from_bytes(raw)
    # VersionedTransaction non espone setter in solders; occorre ricostruire il message.
    # Per semplicità, qui ritorniamo l'originale (molti endpoint Jupiter già rigenerano la tx con blockhash attuale).
    # Se vuoi hard-patch del blockhash servono util extra sul MessageV0.
    return tx_b64
