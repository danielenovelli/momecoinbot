from __future__ import annotations
from typing import List, Dict, Any
from solders.pubkey import Pubkey
from solana.rpc.api import Client
from .utils import lamports_to_sol
from . import config

def fetch_new_sigs(client: Client, addr: str, seen: set, limit: int = 25) -> List[str]:
    resp = client.get_signatures_for_address(Pubkey.from_string(addr), limit=limit)
    sigs = [str(x.signature) for x in resp.value]
    sigs = list(reversed(sigs))
    return [s for s in sigs if s not in seen]

def _get_tx_parsed(client: Client, sig: str) -> Dict[str, Any] | None:
    try:
        raw = client._provider.make_request("getTransaction", sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0})
        return raw.get("result")
    except Exception:
        return None

def _account_keys(msg: Dict[str, Any]) -> List[str]:
    keys: List[str] = []
    for k in (msg.get("accountKeys") or []):
        keys.append(k["pubkey"] if isinstance(k, dict) and "pubkey" in k else str(k))
    la = msg.get("loadedAddresses") or {}
    for bucket in ("writable", "readonly"):
        for v in (la.get(bucket) or []):
            keys.append(str(v))
    return keys

def parse_events(client: Client, target_addr: str, sig: str) -> List[Dict[str, Any]]:
    """Rileva BUY (token in aumento) usando pre/postTokenBalances; fallback su transferChecked in innerInstructions."""
    tx = _get_tx_parsed(client, sig)
    if not tx:
        return []
    msg = ((tx.get("transaction") or {}).get("message")) or {}
    keys = _account_keys(msg)
    meta = tx.get("meta") or {}

    # lamports delta (non usato per decisione BUY/SELL ma lo logghiamo)
    lamports_delta = 0
    try:
        idx = keys.index(target_addr)
        pre_bal = meta.get("preBalances") or []
        post_bal = meta.get("postBalances") or []
        if idx < len(pre_bal) and idx < len(post_bal):
            lamports_delta = (post_bal[idx] - pre_bal[idx])
    except ValueError:
        pass

    # 1) balances path
    pre_map = {r.get("mint"): float((r.get("uiTokenAmount") or {}).get("uiAmount") or 0.0)
               for r in (meta.get("preTokenBalances") or [])
               if (r.get("owner") == target_addr) or (r.get("accountIndex") is not None and 0 <= int(r["accountIndex"]) < len(keys) and keys[int(r["accountIndex"])] == target_addr)}
    post_map = {r.get("mint"): float((r.get("uiTokenAmount") or {}).get("uiAmount") or 0.0)
               for r in (meta.get("postTokenBalances") or [])
               if (r.get("owner") == target_addr) or (r.get("accountIndex") is not None and 0 <= int(r["accountIndex"]) < len(keys) and keys[int(r["accountIndex"])] == target_addr)}

    events: List[Dict[str, Any]] = []
    all_mints = set(pre_map) | set(post_map)
    for mint in all_mints:
        if not mint:
            continue
        if config.PUMP_ONLY and not mint.endswith("pump"):
            continue
        delta = (post_map.get(mint, 0.0) - pre_map.get(mint, 0.0))
        if delta > 1e-12:  # BUY
            events.append({"kind": "BUY", "mint": mint, "token_delta": delta, "sol_delta": lamports_to_sol(lamports_delta), "sig": sig})

    if events:
        return events

    # 2) fallback: innerInstructions -> transfer/transferChecked
    ii = meta.get("innerInstructions") or []
    for inner in ii:
        for ins in inner.get("instructions") or []:
            parsed = ins.get("parsed")
            program = ins.get("program") or ins.get("programId")
            if not parsed or str(program).lower() not in ("token", "spl-token"):
                continue
            if parsed.get("type") not in ("transfer", "transferChecked"):
                continue
            info = parsed.get("info") or {}
            mint = info.get("mint")
            if not mint:
                continue
            if config.PUMP_ONLY and not mint.endswith("pump"):
                continue
            dest = info.get("destination")
            if dest == target_addr:
                amt_ui = None
                if "tokenAmount" in info:
                    try:
                        amt_ui = float(info["tokenAmount"].get("uiAmount") or 0.0)
                    except Exception:
                        amt_ui = None
                if amt_ui is None:
                    try:
                        amt_ui = float(info.get("amount"))
                    except Exception:
                        continue
                events.append({"kind": "BUY", "mint": mint, "token_delta": amt_ui, "sol_delta": lamports_to_sol(lamports_delta), "sig": sig})
    return events
