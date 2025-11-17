import json
import math
from typing import List, Dict, Tuple
from config import NUM_BINS
from outlier_service import filter_valid_positions, find_price_range, MIN_REASONABLE_PRICE, MAX_REASONABLE_PRICE


def create_bins(min_price: float, max_price: float, num_bins: int = NUM_BINS) -> List[Dict]:
    """
    Create bins (price bands) from min to max price.
    
    Args:
        min_price: Minimum price
        max_price: Maximum price
        num_bins: Number of bins to create
        
    Returns:
        List of bin dictionaries with priceLower and priceUpper
    """
    if min_price >= max_price:
        raise ValueError("min_price must be less than max_price")
    
    bin_size = (max_price - min_price) / num_bins
    bins = []
    
    for i in range(num_bins):
        price_lower = min_price + (i * bin_size)
        price_upper = min_price + ((i + 1) * bin_size)
        
        bins.append({
            "bin_index": i,
            "priceLower": price_lower,
            "priceUpper": price_upper,
            "amount_weth": 0.0,
            "amount_usdt": 0.0,
            "count_nfts": 0
        })
    
    return bins


def calculate_overlap(position_lower: float, position_upper: float, 
                     bin_lower: float, bin_upper: float) -> float:
    """
    Calculate the overlap between a position and a bin.
    
    Args:
        position_lower: Lower price of the position
        position_upper: Upper price of the position
        bin_lower: Lower price of the bin
        bin_upper: Upper price of the bin
        
    Returns:
        Overlap length (0 if no overlap)
    """
    # Find the intersection
    overlap_lower = max(position_lower, bin_lower)
    overlap_upper = min(position_upper, bin_upper)
    
    if overlap_lower >= overlap_upper:
        return 0.0
    
    return overlap_upper - overlap_lower


def distribute_position_to_bins(position: Dict, bins: List[Dict]) -> None:
    """
    Distribute a position's amounts to overlapping bins proportionally.
    If a position overlaps multiple bins, split amounts proportionally.
    
    Args:
        position: Position dictionary with price_lower_afterdecimals, price_upper_afterdecimals,
                 amount_weth, amount_usdt, nft_id
        bins: List of bin dictionaries to update
    """
    position_lower = position.get("price_lower_afterdecimals")
    position_upper = position.get("price_upper_afterdecimals")
    amount_weth = position.get("amount_weth", 0.0) or 0.0
    amount_usdt = position.get("amount_usdt", 0.0) or 0.0
    nft_id = position.get("nft_id")
    
    if position_lower is None or position_upper is None:
        return
    
    # Find all bins that overlap with this position
    overlapping_bins = []
    total_overlap = 0.0
    
    for bin in bins:
        overlap = calculate_overlap(
            position_lower, position_upper,
            bin["priceLower"], bin["priceUpper"]
        )
        
        if overlap > 0:
            overlapping_bins.append((bin, overlap))
            total_overlap += overlap
    
    # If no overlap, skip
    if total_overlap == 0 or len(overlapping_bins) == 0:
        return
    
    # Calculate position price range
    position_range = position_upper - position_lower
    if position_range == 0:
        return
    
    # Distribute amounts proportionally to each overlapping bin
    for bin, overlap in overlapping_bins:
        # Proportion of position that overlaps with this bin
        overlap_proportion = overlap / position_range
        
        # Split amounts proportionally
        bin_weth = amount_weth * overlap_proportion
        bin_usdt = amount_usdt * overlap_proportion
        
        # Add to bin totals
        bin["amount_weth"] += bin_weth
        bin["amount_usdt"] += bin_usdt
        
        # Count NFT position (count it in all overlapping bins)
        bin["count_nfts"] += 1


def create_bins_from_data(positions: List[Dict], num_bins: int = NUM_BINS, 
                         min_reasonable: float = None, max_reasonable: float = None) -> List[Dict]:
    """
    Main function to create bins from final data.
    
    Args:
        positions: List of position dictionaries with price_lower_afterdecimals, 
                  price_upper_afterdecimals, amount_weth, amount_usdt, nft_id
        num_bins: Number of bins to create (default: NUM_BINS from config)
        min_reasonable: Minimum reasonable price for filtering (default: 100)
        max_reasonable: Maximum reasonable price for filtering (default: 100000)
        
    Returns:
        List of bin dictionaries with aggregated data. Each bin contains:
        - bin_index: Index of the bin
        - priceLower: Lower price bound of the bin
        - priceUpper: Upper price bound of the bin
        - amount_weth: Total WETH amount in this bin
        - amount_usdt: Total USDT amount in this bin
        - count_nfts: Number of NFT positions in this bin
    """
    if not positions:
        raise ValueError("No positions provided")
    
    # Use defaults from outlier_service if not provided
    if min_reasonable is None:
        min_reasonable = MIN_REASONABLE_PRICE
    if max_reasonable is None:
        max_reasonable = MAX_REASONABLE_PRICE
    
    # Filter out positions with invalid/unreasonable prices
    valid_positions, invalid_positions = filter_valid_positions(positions, min_reasonable, max_reasonable)
    
    if not valid_positions:
        raise ValueError("No valid positions after filtering")
    
    # Find price range from valid positions only
    min_price, max_price = find_price_range(valid_positions)
    
    if min_price == float('inf') or max_price == float('-inf'):
        raise ValueError("Could not determine price range from positions")
    
    # Create bins
    bins = create_bins(min_price, max_price, num_bins)
    print(f"Created {len(bins)} bins")
    
    # Distribute only valid positions to bins
    for position in valid_positions:
        distribute_position_to_bins(position, bins)
    
    return bins


if __name__ == "__main__":
    # Example usage - loading from file for testing
    import sys
    
    def load_final_data_from_file(log_file_path: str) -> List[Dict]:
        """Helper function to load data from file for testing."""
        with open(log_file_path, 'r') as f:
            content = f.read()
        
        json_start = content.find('[')
        if json_start == -1:
            raise ValueError("Could not find JSON array in log file")
        
        json_content = content[json_start:]
        return json.loads(json_content)
    
    # Example: Load from file and create bins
    if len(sys.argv) > 1:
        log_file = sys.argv[1]
    else:
        log_file = "run4.log"
    
    print(f"Loading data from {log_file}...")
    positions = load_final_data_from_file(log_file)
    print(f"Loaded {len(positions)} positions")
    
    bins = create_bins_from_data(positions, NUM_BINS)
    
    # Print summary
    print("\n=== Bin Summary ===")
    print(f"Total bins: {len(bins)}")
    print(f"Bins with positions: {len([b for b in bins if b['count_nfts'] > 0])}")
    
    # Print first few bins with positions
    print("\n=== Sample Bins (first 10 with positions) ===")
    bins_with_positions = [b for b in bins if b['count_nfts'] > 0][:10]
    for bin in bins_with_positions:
        print(f"Bin {bin['bin_index']}: Price [{bin['priceLower']:.2f}, {bin['priceUpper']:.2f}] | "
              f"WETH: {bin['amount_weth']:.6f} | USDT: {bin['amount_usdt']:.2f} | "
              f"NFTs: {bin['count_nfts']}")

