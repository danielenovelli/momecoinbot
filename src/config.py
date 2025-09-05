import os
from dotenv import load_dotenv
load_dotenv()

RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
TARGET_WALLET = os.getenv("TARGET_WALLET", "").strip()
SECRET_KEY_BASE58 = os.getenv("SECRET_KEY_BASE58", "").strip()

FIXED_BUY_SOL = float(os.getenv("FIXED_BUY_SOL", "0.05"))
SLIPPAGE_BPS = int(os.getenv("SLIPPAGE_BPS", "150"))
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
PUMP_ONLY = os.getenv("PUMP_ONLY", "true").lower() == "true"

POLL_INTERVAL_SEC = int(os.getenv("POLL_INTERVAL_SEC", "8"))

SOL_MINT = "So11111111111111111111111111111111111111112"
