import os
from dotenv import load_dotenv
load_dotenv()

# === Solana RPC (con api-key già nel parametro) ===
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")

# === Wallets ===
TARGET_WALLET = os.getenv("TARGET_WALLET", "").strip()
SECRET_KEY_BASE58 = os.getenv("SECRET_KEY_BASE58", "").strip()

# === Parametri trading (se usi ancora il buyer semplificato) ===
FIXED_BUY_SOL = float(os.getenv("FIXED_BUY_SOL", "0.05"))
SLIPPAGE_BPS = int(os.getenv("SLIPPAGE_BPS", "150"))
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

# === Filtri & polling ===
PUMP_ONLY = os.getenv("PUMP_ONLY", "true").lower() == "true"
POLL_INTERVAL_SEC = int(os.getenv("POLL_INTERVAL_SEC", "8"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# === Strategy: usa direttamente Helius Enhanced (migliore) ===
USE_HELIUS_ONLY = os.getenv("USE_HELIUS_ONLY", "true").lower() == "true"

# Costanti utili
SOL_MINT = "So11111111111111111111111111111111111111112"
IGNORE_SOL_MINT = os.getenv("IGNORE_SOL_MINT", "true").lower() == "true"
MIN_TOKEN_UI = float(os.getenv("MIN_TOKEN_UI", "0.0"))
