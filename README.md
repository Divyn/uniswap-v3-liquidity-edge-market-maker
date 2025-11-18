# Uniswap Liquidity Finder For Market Makers to Add/Remove Liquidity

Analyze Uniswap v3 WETH/USDT liquidity, bucket positions into price bands, and highlight the most capitalized ranges. The project ships both a command-line workflow (`main.py`) and a cached Flask API/UI (`app.py`).

- Fetches mint positions plus increase/decrease liquidity calls via Bitquery GraphQL
- Cleans and normalizes ticks, prices, and token amounts (`parser.py`, `outlier_service.py`)
- Aggregates liquidity into configurable price bins (`bin_service.py`)
- Ranks bands by combined WETH+USDT value and annotates 24 h trading volume (`recommender_service.py`)

### Final Output

![](/runlog.png)

### Project Structure
- `bitquery_service.py` – GraphQL queries for mint positions, liquidity events, and 24 h trading volume
- `parser.py` – normalizes tick/price math, token decimals, and merges mint + liquidity deltas
- `outlier_service.py` – clamps unreasonable prices/amounts before binning
- `bin_service.py` – creates price buckets and distributes liquidity proportionally
- `recommender_service.py` – ranks bins by total liquidity and formats results
- `app.py` / `templates/recommendations.html` – Flask API + basic UI
- `run*.log` – sample logs that capture raw Bitquery responses for offline experiments


### Setup
1. Clone the repo and install dependencies:
   ```bash
   git clone https://github.com/Divyn/uniswap-v3-liquidity-edge-market-maker
   pip install -r requirements.txt
   ```
2. Create a `.env` file (or export env vars) with your Bitquery token:
   ```bash
   echo 'BITQUERY_API_KEY=your_token_here' > .env
   ```


### CLI Workflow
Run the end‑to‑end analysis (default lookback = last 240 h):
```bash
python main.py
```
You will see:
1. Count of mint positions pulled
2. Liquidity adjustments detected per NFT
3. Final summary JSON
4. Bin breakdown and top price-band recommendations (with optional 24 h volume calls per band)

Adjust the time window by editing the `timedelta` in `main.py`, and change the number of bands via `NUM_BINS` in `config.py`.


### Flask API & UI
Launch the web server:
```bash
python app.py
```
Endpoints:
- `GET /` – renders `templates/recommendations.html`, which loads data asynchronously
- `GET /api/recommendations` – returns JSON containing top bands plus metadata

Useful query params for `/api/recommendations`:
- `price_lower`, `price_upper` (floats) to focus on a price window
- `refresh=true` to bypass the 10‑minute in‑memory cache

Example:
```bash
curl 'http://localhost:5000/api/recommendations?price_lower=1500&price_upper=2500'
```

Both routes log to stdout and `app.log`. Cached bins let price-filtered requests return instantly without re-querying Bitquery unless the cache expires.



