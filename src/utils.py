LAMPORTS_PER_SOL = 1_000_000_000

def lamports_to_sol(lamports: int | float) -> float:
    return float(lamports) / LAMPORTS_PER_SOL

def sol_to_lamports(sol: float) -> int:
    return int(round(sol * LAMPORTS_PER_SOL))

def now_utc_str() -> str:
    import datetime as dt
    return dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
