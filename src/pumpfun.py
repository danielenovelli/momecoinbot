# src/pumpfun.py — Client PumpPortal (Local bytes / Lightning JSON)
import requests
from . import config

def _endpoint(path: str) -> str:
    base = (config.PUMPFUN_BASE or "").rstrip("/")
    if not base:
        raise RuntimeError("PUMPFUN_BASE non configurato")
    return f"{base}/{path.lstrip('/')}"

def _slippage_percent_from_bps(bps: int) -> int:
    # PumpPortal usa percentuali intere (1,2,5...). 150 bps -> 1.5% -> 2
    return max(1, int(round(bps / 100)))

# -------- Local (bytes) --------
def pf_build_buy_tx_local(user_pubkey: str, mint: str, amount_lamports: int, slippage_bps: int, priority_fee_sol: float | None = None) -> bytes:
    url = _endpoint("trade-local")
    body = {
        "publicKey": user_pubkey,
        "action": "buy",
        "mint": mint,
        "amount": str(amount_lamports),
        "denominatedInSol": True,
        "slippage": _slippage_percent_from_bps(slippage_bps),
        "pool": "pump",
    }
    if priority_fee_sol is not None:
        body["priorityFee"] = priority_fee_sol
    r = requests.post(url, json=body, timeout=20)
    r.raise_for_status()
    return r.content  # BYTES!

def pf_build_sell_tx_local(user_pubkey: str, mint: str, raw_amount: int, slippage_bps: int, priority_fee_sol: float | None = None) -> bytes:
    url = _endpoint("trade-local")
    body = {
        "publicKey": user_pubkey,
        "action": "sell",
        "mint": mint,
        "amount": str(raw_amount),
        "denominatedInSol": False,
        "slippage": _slippage_percent_from_bps(slippage_bps),
        "pool": "pump",
    }
    if priority_fee_sol is not None:
        body["priorityFee"] = priority_fee_sol
    r = requests.post(url, json=body, timeout=20)
    r.raise_for_status()
    return r.content  # BYTES!

# -------- Lightning (JSON) --------
def pf_trade_lightning(user_pubkey: str, mint: str, side: str, amount: int, is_sol: bool, slippage_bps: int, priority_fee_sol: float | None = None) -> dict:
    url = _endpoint("trade")
    params = {}
    if getattr(config, "PUMPFUN_API_KEY", "").strip():
        params["api-key"] = config.PUMPFUN_API_KEY.strip()
    body = {
        "publicKey": user_pubkey,
        "action": side.lower(),   # "buy" | "sell"
        "mint": mint,
        "amount": str(amount),
        "denominatedInSol": bool(is_sol),
        "slippage": _slippage_percent_from_bps(slippage_bps),
        "pool": "pump",
    }
    if priority_fee_sol is not None:
        body["priorityFee"] = priority_fee_sol
    r = requests.post(url, params=params, json=body, timeout=20)
    r.raise_for_status()
    return r.json()
