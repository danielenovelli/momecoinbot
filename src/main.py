from __future__ import annotations
import os, time
from . import config
from .solana_utils import get_client, load_keypair_from_base58
from .monitor import fetch_new_sigs, parse_events
from .trader import copy_buy
from .utils import now_utc_str

STATE_FILE = os.path.join(os.path.dirname(__file__), "state_simple.json")

def load_seen() -> set:
    try:
        import json
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f).get("seen", []))
    except Exception:
        return set()

def save_seen(seen: set):
    import json
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"seen": list(seen)[-5000:]}, f, indent=2)

def main():
    client = get_client(config.RPC_URL)
    kp = load_keypair_from_base58(config.SECRET_KEY_BASE58)
    my_pub = str(kp.pubkey())
    target = config.TARGET_WALLET

    seen = load_seen()
    print(f"🚀 Semplice copy-buyer avviato. Mio wallet: {my_pub[:6]}…{my_pub[-4:]}; DRY_RUN={config.DRY_RUN}")

    while True:
        try:
            sigs = fetch_new_sigs(client, target, seen, limit=25)
            for sig in sigs:
                evs = parse_events(client, target, sig)
                if not evs:
                    # silenzio → meno rumore, ma puoi riattivare un log se vuoi
                    seen.add(sig); continue
                for ev in evs:
                    if ev["kind"] != "BUY":
                        continue
                    mint = ev["mint"]
                    print(f"📈 BUY rilevato {mint} @ {now_utc_str()} | sig {ev['sig'][:12]}…")
                    sig_out = copy_buy(client, my_pub, mint)
                    if sig_out:
                        print(f"🟢 BUY eseguito: {sig_out}")
                    seen.add(sig)
            save_seen(seen)
        except KeyboardInterrupt:
            print("👋 Stop")
            break
        except Exception as e:
            print("[errore]", e)
        time.sleep(config.POLL_INTERVAL_SEC)

if __name__ == "__main__":
    main()
