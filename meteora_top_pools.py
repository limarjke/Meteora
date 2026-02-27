"""
Meteora (Solana) — DeFi trader screener (DLMM).

Install dependencies before running:
    pip install requests streamlit pandas

Run:
    streamlit run meteora_top_pools.py

"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import requests
import streamlit as st


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


def _rows_to_dataframe(rows: List[PoolRow]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Pool Name": r.name,
                "TVL": r.tvl_usd,
                "24h Yield (%)": r.yield24_pct,
                "Fees 24h": r.fees24_usd,
                "Link (Meteora)": r.meteora_link,
                "dex (gmgn.ai)": r.dex_link,
            }
            for r in rows
        ]
    )


@st.cache_data(show_spinner=False)
def _load_data(top_n: int, min_tvl_usd: float) -> pd.DataFrame:
    rows = fetch_most_profitable_pools(top_n=top_n, min_tvl_usd=min_tvl_usd)
    df = _rows_to_dataframe(rows)
    df = df.sort_values(by="24h Yield (%)", ascending=False, kind="mergesort")
    return df


def _render_table(df: pd.DataFrame) -> None:
    # Prefer Streamlit's native link columns; fall back to HTML if unavailable.
    try:
        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "TVL": st.column_config.NumberColumn("TVL", format="$%,.0f"),
                "Fees 24h": st.column_config.NumberColumn("Fees 24h", format="$%,.0f"),
                "24h Yield (%)": st.column_config.NumberColumn("24h Yield (%)", format="%.1f%%"),
                "Link (Meteora)": st.column_config.LinkColumn("Link (Meteora)"),
                "dex (gmgn.ai)": st.column_config.LinkColumn("dex (gmgn.ai)"),
            },
        )
    except Exception:
        df2 = df.copy()
        df2["TVL"] = df2["TVL"].map(_format_usd)
        df2["Fees 24h"] = df2["Fees 24h"].map(_format_usd)
        df2["24h Yield (%)"] = df2["24h Yield (%)"].map(_format_pct)
        st.write(df2.to_html(escape=False, render_links=True, index=False), unsafe_allow_html=True)


def app() -> None:
    st.set_page_config(page_title="Meteora DeFi Yield Tracker", layout="wide")
    st.title("🚀 Meteora DeFi Yield Tracker")

    top_n = 20
    min_tvl_usd = 50_000.0

    if "last_updated" not in st.session_state:
        st.session_state.last_updated = None

    col_a, col_b = st.columns([1, 5])
    with col_a:
        refresh = st.button("Refresh Data", type="primary")

    if refresh:
        _load_data.clear()

    with st.spinner("Loading pools from Meteora..."):
        df = _load_data(top_n=top_n, min_tvl_usd=min_tvl_usd)

    st.session_state.last_updated = datetime.now().astimezone()
    st.caption(f"Last updated: {st.session_state.last_updated.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    _render_table(df)


if __name__ == "__main__":
    app()
