import numpy as np
from tools.backtest import run
from bot.metrics import stability_pick


def compute_grid(df, lengths, mults, adx_period, adx_thresh,
                 risk_pct, leverage_cap, taker_fee, funding_per_bar):
    """Return (grid of total_return per (length, mult), (stable_i, stable_j))."""
    grid = np.zeros((len(lengths), len(mults)))
    for i, L in enumerate(lengths):
        for j, M in enumerate(mults):
            r = run(df, L, M, adx_period, adx_thresh,
                    risk_pct, leverage_cap, 1000.0, taker_fee, funding_per_bar)
            grid[i, j] = r["total_return"]
    si, sj, _ = stability_pick(grid, k=1.5)
    return grid, (si, sj)


def run_grid(df, args):
    lengths = [5, 7, 9, 11, 13, 15, 17, 19, 21, 23]
    mults = [1.0, 1.3, 1.6, 1.9, 2.2, 2.5, 2.8, 3.1, 3.4, 3.7]
    # Honest validation: fit the grid on the TRAIN half only, then evaluate the chosen
    # params on the held-out TEST half. Fitting on full data and reporting "OOS" on a
    # subset of that same data is in-sample by construction.
    half = len(df) // 2
    train = df.iloc[:half].reset_index(drop=True)
    test = df.iloc[half:].reset_index(drop=True)
    grid, (si, sj) = compute_grid(
        train, lengths, mults, args.adx_period, args.adx_thresh,
        args.risk_pct, args.leverage_cap, args.taker_fee, args.funding_per_bar,
    )
    print("\n=== Stability Grid (total return %) ===")
    print("len\\mult " + " ".join(f"{m:6.1f}" for m in mults))
    best = np.unravel_index(np.argmax(grid), grid.shape)
    for i, L in enumerate(lengths):
        cells = []
        for j in range(len(mults)):
            tag = "*" if (i, j) == best else ("#" if (i, j) == (si, sj) else " ")
            cells.append(f"{grid[i,j]*100:5.0f}{tag}")
        print(f"{L:7d} " + " ".join(cells))
    print(f"\n* = peak (overfit risk)   # = stable pick (recommended)")
    print(f"Stable params: st_len={lengths[si]}, st_mult={mults[sj]}, "
          f"train return={grid[si,sj]*100:.1f}%")
    # The number that actually matters: stable params on data never seen during fitting.
    test_r = run(test, lengths[si], mults[sj], args.adx_period, args.adx_thresh,
                 args.risk_pct, args.leverage_cap, 1000.0, args.taker_fee, args.funding_per_bar)
    print(f"Held-out TEST return for stable params: {test_r['total_return']*100:.1f}%  "
          f"(this is the honest number)")
