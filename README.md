# Meteora DeFi Liquidity Pool Parser

Python script that pulls liquidity pool metrics from Meteora (Solana) via public API, calculates **24h Yield/APR** \((Fees 24h / TVL) * 100\), and prints a ranked table with direct links to pool pages on **Meteora** and token charts on **GMGN**.

## Quick start

### Requirements
- Python 3.9+

### Install

```bash
pip install requests streamlit pandas
```

### Run

```bash
streamlit run meteora_top_pools.py
```
Then open the local URL shown in your terminal (usually `http://localhost:8501`).

