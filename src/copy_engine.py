# src/copy_engine.py — Copia BUY/SELL pulita e manutenibile
# Scelte:
# - Jupiter come prima scelta
# - PumpPortal Local (trade-local) con retry intelligente su blockhash (ricostruisce tx)
# - Lightning opzionale (se abilitato nel chiamante)
#
# Integra: TEST_MODE, DRY_RUN, COPY_RATIO, MAX_PER_TRADE_SOL, DAILY_SOL_BUDGET,
#          BLACKLIST_MINTS, COPY_EVENTS, logging CSV.

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import random, string

from . import config, notifier
from .history import append_row, now_utc_str
from .solana_utils import get_token_accounts_by_owner, get_token_balance_ui, sol_to_lamports
from .jupiter import jup_quote, jup_swap, sign_and_send
from .pumpfun import pf_build_buy_tx_local, pf_build_sell_tx_local
from .tx_retry import send_pump_local_with_retry

# ========= Utility =========
def _fake_sig(prefix="TEST"):
    return f"{prefix}-" + "".join(random.choice(string.ascii_letters + string.digits) for _ in range(24))

def _allow(event: str) -> bool:
    return event.upper() in config.COPY_EVENTS

def _log_exec_buy(sig: str, token_mint: str, amount_sol: float, note: str):
    notifier.notify(f"🟢 BUY eseguito: {amount_sol:.6f} SOL → {token_mint} ({note})\n🔗 https://solscan.io/tx/{sig}")
    append_row({
        "ts_utc": now_utc_str(), "action": "EXEC_BUY", "mint": token_mint,
        "amount_token_ui": "", "amount_sol": f"{amount_sol:.9f}",
        "copy_ratio": f"{config.COPY_RATIO}", "slippage_bps": f"{config.SLIPPAGE_BPS}",
        "tx_signature": sig, "src_signature": "", "note": note,
    })

def _log_exec_sell(sig: str, token_mint: str, amount_ui: float, note: str):
    notifier.notify(f"🔴 SELL eseguito: {amount_ui:.6f} {token_mint} → SOL ({note})\n🔗 https://solscan.io/tx/{sig}")
    append_row({
        "ts_utc": now_utc_str(), "action": "EXEC_SELL", "mint": token_mint,
        "amount_token_ui": f"{amount_ui:.9f}", "amount_sol": "",
        "copy_ratio": f"{config.COPY_RATIO}", "slippage_bps": f"{config.SLIPPAGE_BPS}",
        "tx_signature": sig, "src_signature": "", "note": note,
    })

def _log_skip_no_route(kind: str, token_mint: str, amount_sol: float = 0.0, amount_ui: float | None = None):
    msg = f"⚠️ Nessuna rotta (Jupiter/PumpPortal) per {kind} "
    msg += f"{amount_sol:.6f} SOL → {token_mint}" if kind == "BUY" else f"{amount_ui:.6f} {token_mint} → SOL"
    notifier.notify(msg + ".")
    append_row({
        "ts_utc": now_utc_str(), "action": "SKIP_NO_ROUTE", "mint": token_mint,
        "amount_token_ui": "" if amount_ui is None else f"{amount_ui:.9f}",
        "amount_sol": "" if kind == "SELL" else f"{amount_sol:.9f}",
        "copy_ratio": f"{config.COPY_RATIO}", "slippage_bps": f"{config.SLIPPAGE_BPS}",
        "tx_signature": "", "src_signature": "", "note": "no route",
    })

def _log_error_send(kind: str, token_mint: str, err: Exception, amount_sol: float = 0.0, amount_ui: float | None = None):
    notifier.notify(f"❌ Invio {kind} fallito: {err}")
    append_row({
        "ts_utc": now_utc_str(), "action": "ERROR_SEND", "mint": token_mint,
        "amount_token_ui": "" if amount_ui is None else f"{amount_ui:.9f}",
        "amount_sol": "" if kind == "SELL" else f"{amount_sol:.9f}",
        "copy_ratio": f"{config.COPY_RATIO}", "slippage_bps": f"{config.SLIPPAGE_BPS}",
        "tx_signature": "", "src_signature": "", "note": f"{type(err).__name__}",
    })

# ========= Stato/Budget =========
@dataclass
class BudgetState:
    spent_date: str = ""
    spent_today_sol: float = 0.0

    def ensure_today(self):
        today = str(date.today())
        if self.spent_date != today:
            self.spent_date = today
            self.spent_today_sol = 0.0

    def can_spend(self, qty: float) -> bool:
        self.ensure_today()
        return (self.spent_today_sol + qty) <= config.DAILY_SOL_BUDGET

    def add_spent(self, qty: float):
        self.ensure_today()
        self.spent_today_sol += qty

# ========= Engine =========
class CopyEngine:
    def __init__(self, client, keypair, public_key: str, state: dict):
        self.client = client
        self.keypair = keypair
        self.public_key = public_key
        # normalizza state in BudgetState
        self.budget = BudgetState(
            spent_date=state.get("spent_date", ""),
            spent_today_sol=state.get("spent_today_sol", 0.0),
        )
        self._external_state = state  # per persistenza retrocompatibile

    # ----- BUY flow -----
    def replicate_buy(self, token_mint: str, trader_sol_spent: float):
        if not _allow("BUY"):
            notifier.notify("ℹ️ COPY_EVENTS non include BUY: salto.")
            return
        if token_mint in config.BLACKLIST_MINTS:
            notifier.notify(f"⛔ Skip BUY (blacklist): {token_mint}")
            return

        to_spend = self._calc_buy_size(trader_sol_spent)
        if to_spend <= 0:
            notifier.notify("ℹ️ BUY troppo piccolo, salto.")
            return
        if not self.budget.can_spend(to_spend):
            notifier.notify(f"⏸️ Budget giornaliero esaurito: {self.budget.spent_today_sol:.3f}/{config.DAILY_SOL_BUDGET} SOL")
            return
        lamports = sol_to_lamports(to_spend)

        # Test mode
        if config.TEST_MODE:
            sig = _fake_sig("TESTBUY")
            notifier.notify(f"🧪 TEST_MODE: simulato BUY {to_spend:.6f} SOL → {token_mint} | sig {sig}")
            append_row({
                "ts_utc": now_utc_str(), "action": "EXEC_BUY", "mint": token_mint,
                "amount_token_ui": "", "amount_sol": f"{to_spend:.9f}",
                "copy_ratio": f"{config.COPY_RATIO}", "slippage_bps": f"{config.SLIPPAGE_BPS}",
                "tx_signature": sig, "src_signature": "", "note": "test-mode",
            })
            self._on_spent(to_spend)
            return

        # 1) Jupiter
        if self._try_jupiter_buy(token_mint, lamports, to_spend):
            return
        # 2) PumpPortal Local (fallback)
        if self._try_pump_local_buy(token_mint, lamports, to_spend):
            return

        _log_skip_no_route("BUY", token_mint, amount_sol=to_spend)

    def _calc_buy_size(self, trader_sol_spent: float) -> float:
        return min(config.MAX_PER_TRADE_SOL, max(0.0, trader_sol_spent * config.COPY_RATIO))

    def _try_jupiter_buy(self, token_mint: str, lamports: int, to_spend: float) -> bool:
        route = jup_quote(config.SOL_MINT, token_mint, lamports, config.SLIPPAGE_BPS)
        if not route:
            return False
        if config.DRY_RUN:
            notifier.notify(f"DRY-RUN ✅ BUY {to_spend:.6f} SOL → {token_mint} (JUPITER)")
            append_row({
                "ts_utc": now_utc_str(), "action": "DRY_RUN_BUY", "mint": token_mint,
                "amount_token_ui": "", "amount_sol": f"{to_spend:.9f}",
                "copy_ratio": f"{config.COPY_RATIO}", "slippage_bps": f"{config.SLIPPAGE_BPS}",
                "tx_signature": "", "src_signature": "", "note": "JUPITER",
            })
            self._on_spent(to_spend)
            return True
        try:
            tx_b64 = jup_swap(self.public_key, route)
            sig = sign_and_send(self.client, self.keypair, tx_b64)
            _log_exec_buy(sig, token_mint, to_spend, "JUPITER")
            self._on_spent(to_spend)
            return True
        except Exception as e:
            _log_error_send("BUY", token_mint, e, amount_sol=to_spend)
            return False

    def _try_pump_local_buy(self, token_mint: str, lamports: int, to_spend: float) -> bool:
        if not config.ENABLE_PUMPFUN:
            return False
        if config.DRY_RUN:
            notifier.notify(f"DRY-RUN ✅ BUY {to_spend:.6f} SOL → {token_mint} (PUMPFUN_LOCAL)")
            append_row({
                "ts_utc": now_utc_str(), "action": "DRY_RUN_BUY", "mint": token_mint,
                "amount_token_ui": "", "amount_sol": f"{to_spend:.9f}",
                "copy_ratio": f"{config.COPY_RATIO}", "slippage_bps": f"{config.SLIPPAGE_BPS}",
                "tx_signature": "", "src_signature": "", "note": "PUMPFUN_LOCAL",
            })
            self._on_spent(to_spend)
            return True
        try:
            def _build_bytes():
                return pf_build_buy_tx_local(
                    user_pubkey=self.public_key,
                    mint=token_mint,
                    amount_lamports=lamports,
                    slippage_bps=config.SLIPPAGE_BPS,
                )
            sig = send_pump_local_with_retry(self.client, self.keypair, _build_bytes, retries=3, backoff_s=0.2)
            _log_exec_buy(sig, token_mint, to_spend, "PUMPFUN_LOCAL")
            self._on_spent(to_spend)
            return True
        except Exception as e:
            _log_error_send("BUY", token_mint, e, amount_sol=to_spend)
            return False

    # ----- SELL flow -----
    def replicate_sell(self, token_mint: str, trader_token_sold_ui: float):
        if not _allow("SELL"):
            notifier.notify("ℹ️ COPY_EVENTS non include SELL: salto.")
            return
        if token_mint in config.BLACKLIST_MINTS:
            notifier.notify(f"⛔ Skip SELL (blacklist): {token_mint}")
            return

        # Quanto possiedo
        bal_ui = get_token_balance_ui(self.public_key, token_mint)
        qty_ui = min(bal_ui, max(0.0, trader_token_sold_ui * config.COPY_RATIO))
        if qty_ui <= 0:
            notifier.notify(f"ℹ️ SELL: bilancio insufficiente ({bal_ui:.6f}) per {token_mint}, salto.")
            append_row({
                "ts_utc": now_utc_str(), "action": "SKIP_BALANCE", "mint": token_mint,
                "amount_token_ui": f"{trader_token_sold_ui:.9f}", "amount_sol": "",
                "copy_ratio": f"{config.COPY_RATIO}", "slippage_bps": f"{config.SLIPPAGE_BPS}",
                "tx_signature": "", "src_signature": "", "note": "no balance",
            })
            return

        # test mode
        if config.TEST_MODE:
            sig = _fake_sig("TESTSELL")
            notifier.notify(f"🧪 TEST_MODE: simulato SELL {qty_ui:.6f} {token_mint} → SOL | sig {sig}")
            append_row({
                "ts_utc": now_utc_str(), "action": "EXEC_SELL", "mint": token_mint,
                "amount_token_ui": f"{qty_ui:.9f}", "amount_sol": "",
                "copy_ratio": f"{config.COPY_RATIO}", "slippage_bps": f"{config.SLIPPAGE_BPS}",
                "tx_signature": sig, "src_signature": "", "note": "test-mode",
            })
            return

        raw_amount = self._ui_to_raw(token_mint, qty_ui)

        # 1) Jupiter
        if self._try_jupiter_sell(token_mint, raw_amount, qty_ui):
            return
        # 2) PumpPortal Local
        if self._try_pump_local_sell(token_mint, raw_amount, qty_ui):
            return

        _log_skip_no_route("SELL", token_mint, amount_ui=qty_ui)

    def _ui_to_raw(self, token_mint: str, qty_ui: float) -> int:
        decimals = 6
        try:
            res = get_token_accounts_by_owner(self.public_key, token_mint)
            v = res
            if v:
                amt = v[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]
                decimals = int(amt.get("decimals") or 6)
        except Exception:
            pass
        return int(qty_ui * (10 ** decimals))

    def _try_jupiter_sell(self, token_mint: str, raw_amount: int, qty_ui: float) -> bool:
        route = jup_quote(token_mint, config.SOL_MINT, raw_amount, config.SLIPPAGE_BPS)
        if not route:
            return False
        if config.DRY_RUN:
            notifier.notify(f"DRY-RUN ✅ SELL {qty_ui:.6f} {token_mint} → SOL (JUPITER)")
            append_row({
                "ts_utc": now_utc_str(), "action": "DRY_RUN_SELL", "mint": token_mint,
                "amount_token_ui": f"{qty_ui:.9f}", "amount_sol": "",
                "copy_ratio": f"{config.COPY_RATIO}", "slippage_bps": f"{config.SLIPPAGE_BPS}",
                "tx_signature": "", "src_signature": "", "note": "JUPITER",
            })
            return True
        try:
            tx_b64 = jup_swap(self.public_key, route)
            sig = sign_and_send(self.client, self.keypair, tx_b64)
            _log_exec_sell(sig, token_mint, qty_ui, "JUPITER")
            return True
        except Exception as e:
            _log_error_send("SELL", token_mint, e, amount_ui=qty_ui)
            return False

    def _try_pump_local_sell(self, token_mint: str, raw_amount: int, qty_ui: float) -> bool:
        if not config.ENABLE_PUMPFUN:
            return False
        if config.DRY_RUN:
            notifier.notify(f"DRY-RUN ✅ SELL {qty_ui:.6f} {token_mint} → SOL (PUMPFUN_LOCAL)")
            append_row({
                "ts_utc": now_utc_str(), "action": "DRY_RUN_SELL", "mint": token_mint,
                "amount_token_ui": f"{qty_ui:.9f}", "amount_sol": "",
                "copy_ratio": f"{config.COPY_RATIO}", "slippage_bps": f"{config.SLIPPAGE_BPS}",
                "tx_signature": "", "src_signature": "", "note": "PUMPFUN_LOCAL",
            })
            return True
        try:
            def _build_bytes():
                return pf_build_sell_tx_local(
                    user_pubkey=self.public_key,
                    mint=token_mint,
                    raw_amount=raw_amount,
                    slippage_bps=config.SLIPPAGE_BPS,
                )
            sig = send_pump_local_with_retry(self.client, self.keypair, _build_bytes, retries=3, backoff_s=0.2)
            _log_exec_sell(sig, token_mint, qty_ui, "PUMPFUN_LOCAL")
            return True
        except Exception as e:
            _log_error_send("SELL", token_mint, e, amount_ui=qty_ui)
            return False
