# src/config.py — lettura .env e valori di config
import os
from dotenv import load_dotenv

load_dotenv()

def _get_set(name: str, default: str = ""):
    v = os.getenv(name, default)
    return set([x.strip() for x in v.split(",") if x.strip()])

RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")

# Jupiter
JUP_BASE = os.getenv("JUP_BASE", "https://quote-api.jup.ag/v6")
SOL_MINT = os.getenv("SOL_MINT", "So11111111111111111111111111111111111111112")
SLIPPAGE_BPS = int(os.getenv("SLIPPAGE_BPS", "150"))

# Copy settings
TARGET_WALLET = os.getenv("TARGET_WALLET", "").strip()
COPY_RATIO = float(os.getenv("COPY_RATIO", "0.25"))
MAX_PER_TRADE_SOL = float(os.getenv("MAX_PER_TRADE_SOL", "0.50"))
DAILY_SOL_BUDGET = float(os.getenv("DAILY_SOL_BUDGET", "2.0"))
COPY_EVENTS = _get_set("COPY_EVENTS", "BUY,SELL")
BLACKLIST_MINTS = _get_set("BLACKLIST_MINTS", "")

# PumpPortal
ENABLE_PUMPFUN = os.getenv("ENABLE_PUMPFUN", "true").lower() == "true"
PUMPFUN_BASE = os.getenv("PUMPFUN_BASE", "https://pumpportal.fun/api")
PUMPFUN_API_KEY = os.getenv("PUMPFUN_API_KEY", "").strip()
PUMPFUN_MODE = os.getenv("PUMPFUN_MODE", "local").lower()  # local | lightning
PUMP_ONLY = (os.getenv("PUMP_ONLY", "true").lower() == "true")

# Mode
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
POLL_INTERVAL_SEC = int(os.getenv("POLL_INTERVAL_SEC", "15"))

# My wallet
SECRET_KEY_BASE58 = os.getenv("SECRET_KEY_BASE58", "").strip()

# basic guards
if not TARGET_WALLET:
    raise RuntimeError("TARGET_WALLET non impostato in .env")
if not SECRET_KEY_BASE58:
    raise RuntimeError("SECRET_KEY_BASE58 non impostato in .env")
