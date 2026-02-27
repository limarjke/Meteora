# Meteora DeFi Liquidity Pool Parser

Python script that pulls liquidity pool metrics from Meteora (Solana) via public API, calculates **24h Yield/APR** \((Fees 24h / TVL) * 100\), and prints a ranked table with direct links to pool pages on **Meteora** and token charts on **GMGN**.

## Quick start

### Requirements
- Python 3.9+

### Install

```bash
pip install requests tabulate
```

### Run

```bash
python meteora_top_pools.py
```

Optional flags:

```bash
python meteora_top_pools.py --top 15 --min-tvl 50000
```

- `--top`: number of pools to display (default: 15)
- `--min-tvl`: strict TVL filter in USD (default: 50000; only pools with TVL **>** this value are shown)

