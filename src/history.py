# src/history.py — logging CSV
import csv, os
from datetime import datetime

CSV_PATH = "copytrader_log.csv"

def now_utc_str():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def append_row(row: dict):
    exists = os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "ts_utc","action","mint","amount_token_ui","amount_sol",
            "copy_ratio","slippage_bps","tx_signature","src_signature","note"
        ])
        if not exists:
            w.writeheader()
        w.writerow(row)
