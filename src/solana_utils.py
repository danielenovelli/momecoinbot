import base58, json
from solana.rpc.api import Client
from solders.keypair import Keypair

def get_client(rpc_url: str) -> Client:
    return Client(rpc_url, timeout=30)

def load_keypair_from_base58(secret: str) -> Keypair:
    s = (secret or "").strip()
    if not s:
        raise ValueError("SECRET_KEY_BASE58 mancante")
    if s.startswith("[") and s.endswith("]"):
        arr = json.loads(s)
        b = bytes(arr[:64])
        if len(b) == 64:
            return Keypair.from_bytes(b)
        if len(b) == 32:
            return Keypair.from_seed(b)
        raise ValueError("JSON key deve avere 32 o 64 elementi")
    raw = base58.b58decode(s)
    if len(raw) == 64:
        return Keypair.from_bytes(raw)
    if len(raw) == 32:
        return Keypair.from_seed(raw)
    raise ValueError("Secret key base58 deve essere 32 o 64 bytes")
