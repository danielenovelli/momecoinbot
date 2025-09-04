# src/main.py — entrypoint (usa CopyEngine)
from __future__ import annotations
import json, time, os
from . import config, notifier
from .solana_utils import get_client, load_keypair_from_base58
from .history import now_utc_str
from .monitor import fetch_new_sigs, parse_pump_action
from .copy_engine import CopyEngine  # usa la classe

STATE_PATH = os.path.join(os.path.dirname(__file__), "state.json")

def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"seen": [], "spent_date": "", "spent_today_sol": 0.0}

def save_state(st: dict):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)

def main():
    client = get_client(config.RPC_URL)
    kp = load_keypair_from_base58(config.SECRET_KEY_BASE58)
    my_pub = str(kp.pubkey())
    target = config.TARGET_WALLET

    st = load_state()
    seen = set(st.get("seen", []))
    engine = CopyEngine(client, kp, my_pub, st)

    notifier.notify(f"🚀 Copy-trader avviato ({'mainnet' if 'mainnet' in config.RPC_URL else 'custom'}). Mio wallet: {my_pub[:6]}…{my_pub[-4:]}; DRY_RUN={config.DRY_RUN}")

    while True:
        try:
            new_sigs = fetch_new_sigs(client, target, seen, limit=25)
            for sig in new_sigs:
                events = parse_pump_action(client, target, sig)
                if not events:
                    notifier.notify(f"ℹ️ Tx non copiata (unknown) Sig {sig[:10]}… Mint n/a")
                    seen.add(sig)
                    continue
                for ev in events:
                    mint = ev["mint"]
                    kind = ev["kind"]
                    sig_src = ev["sig"]
                    if kind == "BUY":
                        # Se non riusciamo a stimare il delta SOL, usa un fallback nominale piccolo
                        sol_spent = abs(min(ev["sol_delta"], 0.0)) or 0.04
                        notifier.notify(f"📈 Detected BUY {sol_spent:.6f} SOL → {mint} @ {now_utc_str()} | Sig {sig_src[:12]}…")
                        engine.replicate_buy(mint, sol_spent)
                    else:
                        qty_ui = abs(ev["token_delta"])
                        notifier.notify(f"📉 Detected SELL {qty_ui:.6f} {mint} → SOL @ {now_utc_str()} | Sig {sig_src[:12]}…")
                        engine.replicate_sell(mint, qty_ui)
                    seen.add(sig)
                st["seen"] = list(seen)[-5000:]
                save_state(st)

        except KeyboardInterrupt:
            notifier.notify("👋 Stop richiesto.")
            break
        except Exception as e:
            notifier.notify(f"[errore] {e}")

        time.sleep(config.POLL_INTERVAL_SEC)

if __name__ == "__main__":
    main()
