# src/monitor.py — Helius Enhanced first, RPC fallback
from __future__ import annotations
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, parse_qs
import requests, os, time

from solders.pubkey import Pubkey
from solana.rpc.api import Client

from . import config
from .utils import lamports_to_sol


# ---------------------- Helpers comuni ----------------------

def _extract_api_key_from_rpc(rpc_url: str) -> Optional[str]:
    """
    Estrae la api-key dal parametro di query in RPC_URL (es. ...?api-key=XXXX).
    """
    try:
        qs = parse_qs(urlparse(rpc_url).query)
        key = qs.get("api-key", [None])[0]
        return key
    except Exception:
        return None


def _is_pump_mint(mint: str) -> bool:
    return (mint.endswith("pump") if config.PUMP_ONLY else True)


def _pass_basic_filters(mint: str, amt_ui: float) -> bool:
    """
    Applica filtri comuni: PUMP_ONLY, IGNORE_SOL_MINT, MIN_TOKEN_UI.
    """
    if not mint:
        return False
    if config.PUMP_ONLY and not mint.endswith("pump"):
        return False
    if config.IGNORE_SOL_MINT and mint == config.SOL_MINT:
        return False
    if amt_ui < config.MIN_TOKEN_UI:
        return False
    return True


# ---------------------- Modalità HELIUS (consigliata) ----------------------

def _helius_address_txs(api_key: str, wallet: str, before: Optional[str], limit: int) -> List[Dict[str, Any]]:
    """
    Helius Enhanced (by address):
    GET https://api.helius.xyz/v0/addresses/{wallet}/transactions?api-key=...&limit=...&before=...
    Ritorna lista (newest-first).
    """
    base = "https://api.helius.xyz/v0/addresses"
    params = {"api-key": api_key, "limit": str(limit)}
    if before:
        params["before"] = before
    url = f"{base}/{wallet}/transactions"
    r = requests.get(url, params=params, timeout=12)
    if r.status_code != 200:
        if config.DEBUG:
            print(f"[dbg] helius address http {r.status_code} {r.text[:180]}")
        return []
    arr = r.json()
    return arr if isinstance(arr, list) else []


def fetch_new_sigs_helius(client: Client, addr: str, seen: set, limit: int = 25) -> List[str]:
    """
    Usa Helius by-address: ritorna signature nuove (in ordine cronologico).
    """
    api_key = _extract_api_key_from_rpc(config.RPC_URL)
    if not api_key:
        return []  # senza key non possiamo usare il ramo HELIUS

    txs = _helius_address_txs(api_key, addr, before=None, limit=limit)
    sigs = [t.get("signature") for t in txs if isinstance(t.get("signature"), str)]
    sigs = [s for s in sigs if s and s not in seen]
    sigs.reverse()  # processa dalla più vecchia alla più nuova

    if config.DEBUG:
        print(f"[dbg] helius fetched sigs {len(sigs)} (limit={limit})")
    return sigs


def parse_events_helius(client: Client, target_addr: str, sig: str) -> List[Dict[str, Any]]:
    """
    Helius Enhanced (single lookup):
    POST https://api.helius.xyz/v0/transactions  body: {"transactions": [sig]}
    BUY: tokenTransfers con toUserAccount == target
    SELL: tokenTransfers con fromUserAccount == target
    """
    api_key = _extract_api_key_from_rpc(config.RPC_URL)
    if not api_key:
        return []

    url = "https://api.helius.xyz/v0/transactions/"
    try:
        r = requests.post(url, params={"api-key": api_key}, json={"transactions": [sig]}, timeout=12)
        if r.status_code != 200:
            if config.DEBUG:
                print(f"[dbg] helius single {sig[:10]}… http {r.status_code} {r.text[:180]}")
            return []
        arr = r.json()
        if not isinstance(arr, list) or not arr:
            return []
        tx = arr[0]
    except Exception as e:
        if config.DEBUG:
            print(f"[dbg] helius single {sig[:10]}… error {e}")
        return []

    events: List[Dict[str, Any]] = []

    # Token Transfers → deduciamo BUY/SELL
    for t in tx.get("tokenTransfers", []) or []:
        mint = str(t.get("mint", "")) if t.get("mint") else ""
        try:
            amt_ui = float(t.get("tokenAmount", 0))
        except Exception:
            amt_ui = 0.0

        if not _pass_basic_filters(mint, amt_ui):
            continue

        frm = t.get("fromUserAccount")
        to = t.get("toUserAccount")

        if to == target_addr and amt_ui > 0:
            events.append({"kind": "BUY", "mint": mint, "token_delta": amt_ui, "sol_delta": 0.0, "sig": sig})
        elif frm == target_addr and amt_ui > 0:
            events.append({"kind": "SELL", "mint": mint, "token_delta": -amt_ui, "sol_delta": 0.0, "sig": sig})

    # Native Transfers (opzionale: info su delta SOL del target)
    if events:
        lamports_delta = 0
        for nt in tx.get("nativeTransfers", []) or []:
            if nt.get("fromUserAccount") == target_addr:
                try:
                    lamports_delta -= int(nt.get("amount", 0))
                except Exception:
                    pass
            if nt.get("toUserAccount") == target_addr:
                try:
                    lamports_delta += int(nt.get("amount", 0))
                except Exception:
                    pass
        sol_delta = lamports_to_sol(lamports_delta)
        for ev in events:
            ev["sol_delta"] = sol_delta

    if config.DEBUG:
        print(f"[dbg] helius parsed {sig[:10]}… events={events}")
    return events


# ---------------------- Fallback RPC (se serve) ----------------------

def fetch_new_sigs_rpc(client: Client, addr: str, seen: set, limit: int = 25) -> List[str]:
    resp = client.get_signatures_for_address(Pubkey.from_string(addr), limit=limit)
    sigs_all = [str(x.signature) for x in resp.value]
    if not sigs_all:
        return []
    # filtra status migliori
    try:
        st = client.get_signature_statuses(sigs_all).value
        good = []
        for s, meta in zip(sigs_all, st):
            if meta is None:
                continue
            if meta.err is None and (meta.confirmation_status in ("confirmed", "finalized", None)):
                good.append(s)
        sigs = list(reversed(good))
    except Exception:
        sigs = list(reversed(sigs_all))
    return [s for s in sigs if s not in seen]


def _get_tx_json_parsed(client: Client, sig: str) -> Dict[str, Any] | None:
    payloads = [
        {"encoding": "jsonParsed", "commitment": "finalized", "maxSupportedTransactionVersion": 0},
        {"encoding": "jsonParsed", "commitment": "finalized"},
        {"encoding": "jsonParsed", "commitment": "confirmed"},
        {"encoding": "jsonParsed"},
        {"encoding": "json"},
    ]
    for p in payloads:
        try:
            raw = client._provider.make_request("getTransaction", sig, p)  # type: ignore[attr-defined]
            res = raw.get("result")
            if res:
                return res
        except Exception:
            pass
        time.sleep(0.05)
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


def parse_events_rpc(client: Client, target_addr: str, sig: str) -> List[Dict[str, Any]]:
    tx = _get_tx_json_parsed(client, sig)
    if not tx:
        if config.DEBUG:
            print(f"[dbg] rpc getTransaction {sig[:10]}… -> None")
        return []

    msg = ((tx.get("transaction") or {}).get("message")) or {}
    keys = _account_keys(msg)
    meta = tx.get("meta") or {}

    # balances path
    pre_map = {
        r.get("mint"): float((r.get("uiTokenAmount") or {}).get("uiAmount") or 0.0)
        for r in (meta.get("preTokenBalances") or [])
        if (r.get("owner") == target_addr)
        or (r.get("accountIndex") is not None and 0 <= int(r["accountIndex"]) < len(keys) and keys[int(r["accountIndex"])] == target_addr)
    }
    post_map = {
        r.get("mint"): float((r.get("uiTokenAmount") or {}).get("uiAmount") or 0.0)
        for r in (meta.get("postTokenBalances") or [])
        if (r.get("owner") == target_addr)
        or (r.get("accountIndex") is not None and 0 <= int(r["accountIndex"]) < len(keys) and keys[int(r["accountIndex"])] == target_addr)
    }

    events: List[Dict[str, Any]] = []
    for mint in (set(pre_map) | set(post_map)):
        if not mint:
            continue
        delta = post_map.get(mint, 0.0) - pre_map.get(mint, 0.0)
        if abs(delta) < 1e-12:
            continue

        amt_ui = abs(delta)
        # filtri base
        if not _pass_basic_filters(mint, amt_ui):
            continue

        kind = "BUY" if delta > 0 else "SELL"
        events.append({"kind": kind, "mint": mint, "token_delta": delta, "sol_delta": 0.0, "sig": sig})

    if events:
        return events

    # fallback su innerInstructions - solo BUY (dest == target)
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

            # amount/uiAmount
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

            # filtri base
            if not _pass_basic_filters(mint, float(amt_ui)):
                continue

            dest = info.get("destination")
            if dest == target_addr:
                events.append({"kind": "BUY", "mint": mint, "token_delta": float(amt_ui), "sol_delta": 0.0, "sig": sig})

    return events


# ---------------------- Facciata compatibile con main.py ----------------------

def fetch_new_sigs(client: Client, addr: str, seen: set, limit: int = 25) -> List[str]:
    """
    Preferisci HELIUS (se USE_HELIUS_ONLY e api-key presente), altrimenti cade su RPC.
    """
    if config.USE_HELIUS_ONLY and _extract_api_key_from_rpc(config.RPC_URL):
        return fetch_new_sigs_helius(client, addr, seen, limit)
    return fetch_new_sigs_rpc(client, addr, seen, limit)


def parse_events(client: Client, target_addr: str, sig: str) -> List[Dict[str, Any]]:
    """
    Preferisci HELIUS per la singola firma; se non ritorna nulla, prova RPC.
    """
    if config.USE_HELIUS_ONLY and _extract_api_key_from_rpc(config.RPC_URL):
        evs = parse_events_helius(client, target_addr, sig)
        if evs:
            return evs
        # se per una firma specifica Helius non dà nulla, tenta comunque RPC
    return parse_events_rpc(client, target_addr, sig)
