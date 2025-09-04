# src/tx_retry.py — helpers per invio PumpPortal Local con retry su blockhash
from __future__ import annotations
import time
from typing import Callable
from solana.rpc.types import TxOpts
from solders.transaction import VersionedTransaction

_BLOCKHASH_ERR_TOKENS = (
    "Blockhash not found",
    "BlockhashNotFound",
    "blockhash not found",
)

def is_blockhash_err(exc: Exception) -> bool:
    msg = f"{exc}"
    return any(tok in msg for tok in _BLOCKHASH_ERR_TOKENS)

def send_raw(client, raw_signed: bytes) -> str:
    resp = client.send_raw_transaction(raw_signed, opts=TxOpts(skip_preflight=False, max_retries=5))
    try:
        return str(resp.value)
    except Exception:
        try:
            return str(resp["result"])
        except Exception:
            return str(resp)

def send_pump_local_with_retry(client, keypair, build_bytes_fn: Callable[[], bytes], retries: int = 3, backoff_s: float = 0.2) -> str:
    """
    build_bytes_fn: funzione senza argomenti -> BYTES della tx (nuova trade-local ogni volta).
    Firma e invia. Se vede "Blockhash not found", ricostruisce e riprova fino a 'retries'.
    """
    attempt = 0
    while True:
        attempt += 1
        # 1) costruisci bytes freschi
        tx_bytes = build_bytes_fn()
        # 2) firma
        tx = VersionedTransaction.from_bytes(tx_bytes)
        tx = VersionedTransaction(tx.message, [keypair])
        raw_signed = bytes(tx)
        # 3) invia
        try:
            return send_raw(client, raw_signed)
        except Exception as e:
            if is_blockhash_err(e) and attempt <= retries:
                time.sleep(backoff_s)
                continue
            raise
