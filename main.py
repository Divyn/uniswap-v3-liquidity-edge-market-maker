import json
from datetime import datetime, timedelta, timezone
from config import NUM_BINS
from bitquery_service import fetch_mint_positions, fetch_liquidity_events, fetch_trading_volume
from parser import parse_positions, parse_liquidity_events, create_final_summary
from bin_service import create_bins_from_data
from recommender_service import recommend_top_bands, print_recommendations


def main():
    """Main function to orchestrate the liquidity analysis flow."""
    # Default to last 240 hours (10 days)
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(hours=240)
    
    # Fetch mint positions
    print("Fetching mint positions from Bitquery...")
    response_data, status_code = fetch_mint_positions(start_date, end_date)
    
    if status_code != 200:
        print(f"Error: {status_code}")
        if response_data is None:
            print("Failed to fetch mint positions")
        return
    
    # Parse the mint positions response
    mint_positions = parse_positions(response_data)
    print(f"\nFound {len(mint_positions)} mint positions with WETH and USDT")
    
    # Extract NFT IDs
    nft_ids = [str(pos["nft_id"]) for pos in mint_positions]
    
    if not nft_ids:
        print("No NFT IDs found to query")
        return
    
    print(f"Querying increaseLiquidity calls for {len(nft_ids)} NFT IDs...")
    
    # Query increaseLiquidity calls
    liquidity_data, liquidity_status_code = fetch_liquidity_events(nft_ids, start_date, end_date)
    liquidity_event_counts = {}
    
    if liquidity_status_code == 200:
        liquidity_event_counts = parse_liquidity_events(liquidity_data)
        print(f"Found increaseLiquidity calls for {len(liquidity_event_counts)} NFT IDs")
    else:
        print(f"Error querying liquidity events: {liquidity_status_code}")
        if liquidity_data is None:
            print("Failed to fetch liquidity events")
    
    # Create final summary
    final_summary = create_final_summary(mint_positions, liquidity_event_counts)
    
    print(f"\n=== Final Summary ===")
    print(json.dumps(final_summary, indent=2))
    
    # Create bins from final summary
    print(f"\n=== Creating Bins ===")
    bins = create_bins_from_data(final_summary, num_bins=NUM_BINS)
    
    print(f"Created {len(bins)} bins")
    print(f"Bins with positions: {len([b for b in bins if b['count_nfts'] > 0])}")
    
    print(f"\n=== Bin Summary ===")
    print(json.dumps(bins, indent=2))
    
    # Get and print recommendations
    print(f"\n=== Recommendations ===")
    print("Fetching 24h trading volumes for recommended bands...")
    recommendations = recommend_top_bands(bins, top_n=5, fetch_volume_func=fetch_trading_volume)
    print_recommendations(recommendations)


if __name__ == "__main__":
    main()

