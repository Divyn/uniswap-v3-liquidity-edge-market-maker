import math
from typing import List, Dict, Tuple

# Constants for outlier filtering
MIN_REASONABLE_PRICE = 100.0
MAX_REASONABLE_PRICE = 100000.0
MAX_WETH = 1e6  # 1M WETH
MAX_USDT = 1e12  # 1T USDT
MIN_PRICE_THRESHOLD = 1e-10
MAX_PRICE_THRESHOLD = 1e10


def validate_position_prices(position: Dict, min_reasonable: float = MIN_REASONABLE_PRICE, 
                             max_reasonable: float = MAX_REASONABLE_PRICE) -> bool:
    """
    Validate that a position has reasonable price values and amounts.
    
    Args:
        position: Position dictionary
        min_reasonable: Minimum reasonable price (default: 100)
        max_reasonable: Maximum reasonable price (default: 100000)
        
    Returns:
        True if position has reasonable prices and amounts, False otherwise
    """
    price_lower = position.get("price_lower_afterdecimals")
    price_upper = position.get("price_upper_afterdecimals")
    
    if price_lower is None or price_upper is None:
        return False
    
    # Check if prices are within reasonable range
    if price_lower < min_reasonable or price_upper > max_reasonable:
        return False
    
    # Check if lower < upper
    if price_lower >= price_upper:
        return False
    
    # Check for extreme outliers (values that are too small or too large)
    if price_lower < MIN_PRICE_THRESHOLD or price_upper > MAX_PRICE_THRESHOLD:
        return False
    
    # Validate amounts using the dedicated function (without logging)
    amount_weth = position.get("amount_weth")
    amount_usdt = position.get("amount_usdt")
    if not validate_amounts(amount_weth, amount_usdt, nft_id=None):
        return False
    
    return True


def validate_amounts(amount_weth: float = None, amount_usdt: float = None, 
                    nft_id: str = None) -> bool:
    """
    Validate that amounts are reasonable (not NaN, infinity, negative, or too large).
    
    Args:
        amount_weth: WETH amount to validate
        amount_usdt: USDT amount to validate
        nft_id: Optional NFT ID for logging purposes
        
    Returns:
        True if amounts are valid, False otherwise
    """
    if amount_weth is not None:
        if (math.isnan(amount_weth) or math.isinf(amount_weth) or 
            amount_weth < 0 or amount_weth > MAX_WETH):
            if nft_id:
                print(f"Warning: Filtering out NFT {nft_id} with invalid amount_weth: {amount_weth}")
            return False
    
    if amount_usdt is not None:
        if (math.isnan(amount_usdt) or math.isinf(amount_usdt) or 
            amount_usdt < 0 or amount_usdt > MAX_USDT):
            if nft_id:
                print(f"Warning: Filtering out NFT {nft_id} with invalid amount_usdt: {amount_usdt}")
            return False
    
    return True


def filter_valid_positions(positions: List[Dict], min_reasonable: float = MIN_REASONABLE_PRICE, 
                          max_reasonable: float = MAX_REASONABLE_PRICE) -> Tuple[List[Dict], List[Dict]]:
    """
    Filter positions to only include those with reasonable price values.
    
    Args:
        positions: List of position dictionaries
        min_reasonable: Minimum reasonable price (default: 100)
        max_reasonable: Maximum reasonable price (default: 100000)
        
    Returns:
        Tuple of (valid_positions, invalid_positions)
    """
    valid_positions = []
    invalid_positions = []
    
    for position in positions:
        if validate_position_prices(position, min_reasonable, max_reasonable):
            valid_positions.append(position)
        else:
            invalid_positions.append(position)
            nft_id = position.get("nft_id", "unknown")
            price_lower = position.get("price_lower_afterdecimals")
            price_upper = position.get("price_upper_afterdecimals")
            print(f"Warning: Filtered out position {nft_id} with invalid prices: "
                  f"lower={price_lower}, upper={price_upper}")
    
    if invalid_positions:
        print(f"Filtered out {len(invalid_positions)} invalid positions, "
              f"keeping {len(valid_positions)} valid positions")
    
    return valid_positions, invalid_positions


def find_price_range(positions: List[Dict]) -> Tuple[float, float]:
    """
    Find the minimum and maximum prices across all positions.
    Uses percentile-based approach to ignore extreme outliers.
    
    Args:
        positions: List of position dictionaries
        
    Returns:
        Tuple of (min_price, max_price)
    """
    all_lowers = []
    all_uppers = []
    
    for position in positions:
        price_lower = position.get("price_lower_afterdecimals")
        price_upper = position.get("price_upper_afterdecimals")
        
        if price_lower is not None and price_lower > 0:
            all_lowers.append(price_lower)
        if price_upper is not None and price_upper > 0:
            all_uppers.append(price_upper)
    
    if not all_lowers or not all_uppers:
        raise ValueError("No valid price data found in positions")
    
    # Sort to find percentiles
    all_lowers.sort()
    all_uppers.sort()
    
    # Use 5th and 95th percentiles to ignore extreme outliers
    lower_percentile_idx = max(0, int(len(all_lowers) * 0.05))
    upper_percentile_idx = min(len(all_uppers) - 1, int(len(all_uppers) * 0.95))
    
    min_price = all_lowers[lower_percentile_idx]
    max_price = all_uppers[upper_percentile_idx]
    
    # Additional safety check: ensure reasonable range
    if min_price < MIN_PRICE_THRESHOLD or max_price > MAX_PRICE_THRESHOLD:
        # Fallback to median if percentiles are still extreme
        median_lower = all_lowers[len(all_lowers) // 2]
        median_upper = all_uppers[len(all_uppers) // 2]
        
        if median_lower >= MIN_PRICE_THRESHOLD and median_upper <= MAX_PRICE_THRESHOLD:
            min_price = median_lower
            max_price = median_upper
        else:
            # Last resort: use min/max of reasonable values only
            reasonable_lowers = [p for p in all_lowers if MIN_PRICE_THRESHOLD <= p <= MAX_PRICE_THRESHOLD]
            reasonable_uppers = [p for p in all_uppers if MIN_PRICE_THRESHOLD <= p <= MAX_PRICE_THRESHOLD]
            
            if reasonable_lowers and reasonable_uppers:
                min_price = min(reasonable_lowers)
                max_price = max(reasonable_uppers)
            else:
                raise ValueError("No reasonable price range found in positions")
    
    print(f"Min price: {min_price}, Max price: {max_price}")
    return min_price, max_price

