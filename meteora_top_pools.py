"""
Meteora (Solana) — DeFi trader screener (DLMM).

Install dependencies before running:
    pip install requests tabulate

Run:
    python meteora_top_pools.py
    python meteora_top_pools.py --top 15
    python meteora_top_pools.py --min-tvl 50000


"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import requests
from tabulate import tabulate


DLMM_POOLS_API = "https://dlmm.datapi.meteora.ag/pools"

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
WSOL_MINT = "So11111111111111111111111111111111111111112"
EXCLUDED_GMGN_MINTS = {USDC_MINT, WSOL_MINT}


@dataclass(frozen=True)
class PoolRow:
    name: str
    tvl_usd: float
    yield24_pct: float
    fees24_usd: float
    address: str
    meteora_link: str
    dex_link: str


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _format_usd(value: Any) -> str:
    x = _to_float(value)
    # Keep output compact/readable: no decimals for >= $1, otherwise 2 decimals.
    if abs(x) >= 1:
        return f"${x:,.0f}"
    return f"${x:,.2f}"


def _format_pct(value: Any) -> str:
    x = _to_float(value)
    return f"{x:,.1f}%"


def _safe_get(d: Dict[str, Any], path: Iterable[str]) -> Any:
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _request_json(
    url: str, *, params: Optional[Dict[str, Any]] = None, timeout_s: int = 30
) -> Any:
    r = requests.get(
        url,
        params=params,
        timeout=timeout_s,
        headers={"accept": "application/json"},
    )
    r.raise_for_status()
    return r.json()


def _pick_gmgn_mint(token_x_mint: Optional[str], token_y_mint: Optional[str]) -> str:
    tx = (token_x_mint or "").strip()
    ty = (token_y_mint or "").strip()
    if tx and tx not in EXCLUDED_GMGN_MINTS:
        return tx
    if ty and ty not in EXCLUDED_GMGN_MINTS:
        return ty
    return tx or ty


def fetch_most_profitable_pools(*, top_n: int, min_tvl_usd: float) -> List[PoolRow]:
    """
    Returns top-N pools by 24h yield:
        24h Yield (%) = (Fees 24h / TVL) * 100

    Strategy:
    - Ask the API for pools sorted by `fee_tvl_ratio_24h:desc` (server-side).
    - Apply strict TVL filter locally (TVL > min_tvl_usd).
    - Stop as soon as we collected top_n pools (safe because source ordering is by yield desc).
    """

    collected: List[PoolRow] = []
    seen: set[str] = set()

    page = 1
    page_size = 200
    max_pages = 200  # safety guard

    while len(collected) < top_n and page <= max_pages:
        payload = _request_json(
            DLMM_POOLS_API,
            params={
                "page": page,
                "page_size": page_size,
                "sort_by": "fee_tvl_ratio_24h:desc",
            },
            timeout_s=30,
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list) or not data:
            break

        for p in data:
            if not isinstance(p, dict):
                continue

            address = str(p.get("address") or "")
            if not address or address in seen:
                continue
            seen.add(address)

            tvl = _to_float(p.get("tvl"))
            if not (tvl > float(min_tvl_usd)):  # strict filter
                continue

            token_x_sym = _safe_get(p, ["token_x", "symbol"])
            token_y_sym = _safe_get(p, ["token_y", "symbol"])
            pool_name = (
                f"{token_x_sym}-{token_y_sym}"
                if isinstance(token_x_sym, str) and isinstance(token_y_sym, str)
                else str(p.get("name") or address)
            )

            fees24 = _to_float(_safe_get(p, ["fees", "24h"]))
            yield24 = (fees24 / tvl) * 100.0 if tvl > 0 else 0.0

            token_x_mint = _safe_get(p, ["token_x", "address"])
            token_y_mint = _safe_get(p, ["token_y", "address"])
            gmgn_mint = _pick_gmgn_mint(
                token_x_mint if isinstance(token_x_mint, str) else None,
                token_y_mint if isinstance(token_y_mint, str) else None,
            )

            meteora_link = f"https://app.meteora.ag/dlmm/{address}"
            dex_link = f"https://gmgn.ai/sol/token/{gmgn_mint}" if gmgn_mint else ""

            collected.append(
                PoolRow(
                    name=pool_name,
                    tvl_usd=tvl,
                    yield24_pct=yield24,
                    fees24_usd=fees24,
                    address=address,
                    meteora_link=meteora_link,
                    dex_link=dex_link,
                )
            )

            if len(collected) >= top_n:
                break

        page += 1

    collected.sort(key=lambda r: r.yield24_pct, reverse=True)
    return collected[:top_n]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Print Meteora most profitable pools (24h yield) with TVL filter."
    )
    ap.add_argument(
        "--top", type=int, default=15, help="How many pools to show (default: 15)."
    )
    ap.add_argument(
        "--min-tvl",
        type=float,
        default=50_000,
        help="Strict TVL floor in USD (default: 50000).",
    )
    args = ap.parse_args()

    rows = fetch_most_profitable_pools(
        top_n=max(1, int(args.top)), min_tvl_usd=float(args.min_tvl)
    )
    table = [
        {
            "Pool Name": r.name,
            "TVL": _format_usd(r.tvl_usd),
            "24h Yield (%)": _format_pct(r.yield24_pct),
            "Fees 24h": _format_usd(r.fees24_usd),
            "Link (Meteora)": r.meteora_link,
            "dex (gmgn.ai)": r.dex_link,
        }
        for r in rows
    ]

    print(
        tabulate(
            table,
            headers="keys",
            tablefmt="github",
            showindex=False,
            colalign=("left", "right", "right", "right", "left", "left"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
