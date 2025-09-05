from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Optional

from .solana_utils import sol_to_lamports
from .history import append_row, now_utc_str
from . import config
from .jupiter import JupiterClient, execute_swap_via_jupiter
from .pumpfun import trade_local_b64
from . import notifier

@dataclass
class BudgetState:
    spent_date: str
    spent_today_sol: float

class CopyEngine:
    def __init__(self, client_rpc, keypair, my_pubkey: str, state: dict):
        self.client = client_rpc
        self.kp = keypair
        self.my_pub = my_pubkey
        self.jup = JupiterClient(getattr(config, "JUP_BASE", "https://quote-api.jup.ag/v6"))

        self.state = state
        self.state.setdefault("spent_date", "")
        self.state.setdefault("spent_today_sol", 0.0)

    # ---------- utils stato/budget ----------
    def _rollover_budget_if_needed(self):
        today = str(date.today())
        if self.state["spent_date"] != today:
            self.state["spent_date"] = today
            self.state["spent_today_sol"] = 0.0

    def _can_spend(self, amount_sol: float) -> bool:
        self._rollover_budget_if_needed()
        return (self.state["spent_today_sol"] + amount_sol) <= float(config.DAILY_SOL_BUDGET)

    def _add_spent(self, amount_sol: float):
        self._rollover_budget_if_needed()
        self.state["spent_today_sol"] += amount_sol

    # ---------- BUY ----------
    def replicate_buy(self, mint: str, src_sol_spent: float):
        if "BUY" not in str(config.COPY_EVENTS).upper():
            return
        if mint in (getattr(config, "BLACKLIST_MINTS", "") or "").split(","):
            return

        # calcolo importo copia
        ratio = float(config.COPY_RATIO)
        max_per = float(config.MAX_PER_TRADE_SOL)
        amount_copy_sol = max(0.0, min(src_sol_spent * ratio if src_sol_spent > 0 else max_per * ratio, max_per))
        if amount_copy_sol <= 0.0:
            notifier.notify("ℹ️ BUY troppo piccolo, salto.")
            return
        if not self._can_spend(amount_copy_sol):
            notifier.notify("⚠️ Budget giornaliero esaurito, salto BUY.")
            return

        slippage = int(config.SLIPPAGE_BPS)
        amount_lamports = sol_to_lamports(amount_copy_sol)

        # DRY RUN
        if bool(str(config.DRY_RUN).lower() == "true"):
            append_row({
                "ts_utc": now_utc_str(), "action": "DRY_RUN_BUY",
                "mint": mint, "amount_token_ui": "", "amount_sol": f"{amount_copy_sol:.9f}",
                "copy_ratio": f"{ratio}", "slippage_bps": f"{slippage}",
                "tx_signature": "", "src_signature": "", "note": "DRY_RUN"
            })
            notifier.notify(f"🧪 DRY_RUN BUY {amount_copy_sol:.6f} SOL → {mint}")
            return

        # 1) Jupiter
        sig = execute_swap_via_jupiter(
            self.client, self.jup, self.my_pub,
            getattr(config, "SOL_MINT", "So11111111111111111111111111111111111111112"),
            mint, amount_lamports, slippage
        )
        if sig:
            self._add_spent(amount_copy_sol)
            append_row({
                "ts_utc": now_utc_str(), "action": "EXEC_BUY",
                "mint": mint, "amount_token_ui": "", "amount_sol": f"{amount_copy_sol:.9f}",
                "copy_ratio": f"{ratio}", "slippage_bps": f"{slippage}",
                "tx_signature": sig, "src_signature": "", "note": "JUPITER"
            })
            notifier.notify(f"🟢 BUY eseguito {amount_copy_sol:.6f} SOL → {mint} | sig {sig[:12]}… (Jupiter)")
            return

        # 2) PumpPortal local (opzionale)
        if getattr(config, "ENABLE_PUMPFUN", True):
            tx_b64 = trade_local_b64(
                getattr(config, "PUMPFUN_BASE", "https://pumpportal.fun/api"),
                self.my_pub, mint, "buy", amount_lamports, 0.0, slippage
            )
            if tx_b64:
                try:
                    sig2 = self._send_b64(tx_b64)
                    self._add_spent(amount_copy_sol)
                    append_row({
                        "ts_utc": now_utc_str(), "action": "EXEC_BUY",
                        "mint": mint, "amount_token_ui": "", "amount_sol": f"{amount_copy_sol:.9f}",
                        "copy_ratio": f"{ratio}", "slippage_bps": f"{slippage}",
                        "tx_signature": sig2, "src_signature": "", "note": "PUMPFUN_LOCAL"
                    })
                    notifier.notify(f"🟢 BUY eseguito {amount_copy_sol:.6f} SOL → {mint} | sig {sig2[:12]}… (PumpPortal)")
                    return
                except Exception as e:
                    notifier.notify(f"⚠️ PumpPortal Local BUY errore: {e}")

        notifier.notify(f"⚠️ Nessuna rotta (Jupiter/PumpPortal) per BUY {amount_copy_sol:.6f} SOL → {mint}.")

    # ---------- SELL ----------
    def replicate_sell(self, mint: str, qty_token_ui: float):
        if "SELL" not in str(config.COPY_EVENTS).upper():
            return
        if mint in (getattr(config, "BLACKLIST_MINTS", "") or "").split(","):
            return
        slippage = int(config.SLIPPAGE_BPS)

        if bool(str(config.DRY_RUN).lower() == "true"):
            append_row({
                "ts_utc": now_utc_str(), "action": "DRY_RUN_SELL",
                "mint": mint, "amount_token_ui": f"{qty_token_ui:.9f}", "amount_sol": "",
                "copy_ratio": f"{config.COPY_RATIO}", "slippage_bps": f"{slippage}",
                "tx_signature": "", "src_signature": "", "note": "DRY_RUN"
            })
            notifier.notify(f"🧪 DRY_RUN SELL {qty_token_ui:.6f} {mint} → SOL")
            return

        # Jupiter: mint -> SOL
        # amount_in va espresso in "base units" del token. Senza decimals precisi useremo via quote
        # Esecuzione semplificata: proviamo 'exactOut' no; usiamo la quantità UI come 'amount' moltiplicata per 10^dec?
        # Poiché non abbiamo i decimals qui, lasciamo al servizio /swap di Jupiter interpretare dal quote.
        # La strada più robusta sarebbe leggere 'decimals' via getMint, ma teniamo il flusso semplice:
        # -> tentiamo via PumpPortal local; in alternativa potremmo espandere Jupiter per SELL con mintDecimals.
        from .jupiter import JupiterClient
        # TODO: per SELL seriamente, integra getMint decimals. Per ora usiamo PumpPortal local se disponibile.
        if getattr(config, "ENABLE_PUMPFUN", True):
            tx_b64 = trade_local_b64(
                getattr(config, "PUMPFUN_BASE", "https://pumpportal.fun/api"),
                self.my_pub, mint, "sell", 0, float(qty_token_ui), slippage
            )
            if tx_b64:
                try:
                    sig = self._send_b64(tx_b64)
                    append_row({
                        "ts_utc": now_utc_str(), "action": "EXEC_SELL",
                        "mint": mint, "amount_token_ui": f"{qty_token_ui:.9f}", "amount_sol": "",
                        "copy_ratio": f"{config.COPY_RATIO}", "slippage_bps": f"{slippage}",
                        "tx_signature": sig, "src_signature": "", "note": "PUMPFUN_LOCAL"
                    })
                    notifier.notify(f"🟢 SELL eseguito {qty_token_ui:.6f} {mint} → SOL | sig {sig[:12]}… (PumpPortal)")
                    return
                except Exception as e:
                    notifier.notify(f"⚠️ PumpPortal Local SELL errore: {e}")

        notifier.notify(f"⚠️ Nessuna rotta disponibile per SELL {qty_token_ui:.6f} {mint} → SOL.")

    # ---------- low-level ----------
    def _send_b64(self, tx_b64: str) -> str:
        from .solana_utils import send_and_confirm_b64_tx
        return send_and_confirm_b64_tx(self.client, tx_b64)
