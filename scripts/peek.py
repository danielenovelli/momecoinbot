# scripts/peek.py
import os, sys, json
from solana.rpc.api import Client
from dotenv import load_dotenv
load_dotenv()

RPC = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
SIG = sys.argv[1] if len(sys.argv) > 1 else ""
if not SIG:
    print("Usage: python scripts/peek.py <signature>")
    sys.exit(1)

c = Client(RPC)
raw = c._provider.make_request("getTransaction", SIG, {"encoding":"jsonParsed","maxSupportedTransactionVersion":0})
print(json.dumps(raw.get("result") or {"error":"no result"}, indent=2))
