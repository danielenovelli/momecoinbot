# src/monitor.py — legge le tx del wallet target e produce eventi BUY/SELL
from __future__ import annotations
from typing import List, Dict, Any
from solders.pubkey import Pubkey
from solana.rpc.api import Client
from .solana_utils import lamports_to_sol

def fetch_new_sigs(client: Client, addr: str, seen: set, limit: int = 25) -> List[str]:
    """Return new signatures not in 'seen', oldest-first per elaborazione cronologica."""
    resp = client.get_signatures_for_address(Pubkey.from_string(addr), limit=limit)
    sigs = [str(x.signature) for x in resp.value]
    sigs = list(reversed(sigs))
    return [s for s in sigs if s not in seen]

def _get_tx_json_parsed(client: Client, sig: str) -> Dict[str, Any] | None:
    """Ottiene JSON puro da getTransaction in jsonParsed (evita differenze di versione)."""
    try:
        raw = client._provider.make_request(  # type: ignore[attr-defined]
            "getTransaction",
            sig,
            {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
        )
        return raw.get("result")
    except Exception:
        return None

def parse_pump_action(client: Client, target_addr: str, sig: str) -> List[Dict[str, Any]]:
    """
    Ritorna eventi:
      { 'kind': 'BUY'|'SELL', 'mint': str, 'sol_delta': float, 'token_delta': float, 'sig': str }
    token_delta > 0 => BUY (target aumenta token), <0 => SELL. Filtra i mint che terminano con 'pump'.
    """
    out: List[Dict[str, Any]] = []
    tx = _get_tx_json_parsed(client, sig)
    if not tx:
        return out

    meta = tx.get("meta") or {}
    pre_bal = meta.get("preBalances") or []
    post_bal = meta.get("postBalances") or []

    msg = ((tx.get("transaction") or {}).get("message")) or {}
    ak = msg.get("accountKeys") or []
    # accountKeys in jsonParsed è una lista di dict con "pubkey" e flag
    account_keys: List[str] = [k["pubkey"] if isinstance(k, dict) else str(k) for k in ak]

    try:
        idx = account_keys.index(target_addr)
    except ValueError:
        return out

    lamports_delta = 0
    if idx < len(pre_bal) and idx < len(post_bal):
        lamports_delta = (post_bal[idx] - pre_bal[idx])

    pre_tokens = meta.get("preTokenBalances") or []
    post_tokens = meta.get("postTokenBalances") or []

    def to_map(recs):
        m: Dict[str, tuple[float, int]] = {}
        for r in recs:
            # record: {mint, owner?, uiTokenAmount:{uiAmount,decimals}, accountIndex?}
            owner = r.get("owner")
            acct_idx = r.get("accountIndex")
            owner_pk = owner
            if owner_pk is None and acct_idx is not None and 0 <= int(acct_idx) < len(account_keys):
                owner_pk = account_keys[int(acct_idx)]
            if owner_pk != target_addr:
                continue
            mint = r.get("mint")
            ui = r.get("uiTokenAmount") or {}
            try:
                amt = float(ui.get("uiAmount") or 0.0)
            except Exception:
                amt = 0.0
            dec = int(ui.get("decimals") or 6)
            if mint:
                m[mint] = (amt, dec)
        return m

    pre_map = to_map(pre_tokens)
    post_map = to_map(post_tokens)
    all_mints = set(pre_map.keys()) | set(post_map.keys())

    for mint in all_mints:
        if not mint or not mint.endswith("pump"):
            continue
        pre_amt, _ = pre_map.get(mint, (0.0, 6))
        post_amt, _ = post_map.get(mint, (0.0, 6))
        delta = post_amt - pre_amt
        if abs(delta) < 1e-12:
            continue
        kind = "BUY" if delta > 0 else "SELL"
        out.append({
            "kind": kind,
            "mint": mint,
            "token_delta": delta,
            "sol_delta": lamports_to_sol(lamports_delta) if lamports_delta else 0.0,
            "sig": sig,
        })
    return out
