from typing import List, Dict, Callable, Optional
from datetime import datetime, timedelta, timezone


def calculate_total_liquidity(bin: Dict) -> float:
    """
    Calculate total liquidity value for a bin.
    Uses mid-price to convert WETH to USDT equivalent.
    
    Args:
        bin: Bin dictionary with amount_weth, amount_usdt, priceLower, priceUpper
        
    Returns:
        Total liquidity value in USDT equivalent
    """
    amount_weth = bin.get("amount_weth", 0.0) or 0.0
    amount_usdt = bin.get("amount_usdt", 0.0) or 0.0
    price_lower = bin.get("priceLower", 0.0)
    price_upper = bin.get("priceUpper", 0.0)
    
    # Calculate mid-price for the bin
    mid_price = (price_lower + price_upper) / 2.0 if price_lower > 0 and price_upper > 0 else 0.0
    
    # Total liquidity = USDT amount + (WETH amount * mid-price)
    total_liquidity = amount_usdt + (amount_weth * mid_price)
    
    return total_liquidity


def get_top_liquidity_bands(bins: List[Dict], top_n: int = 5) -> List[Dict]:
    """
    Get top N price bands with most liquidity.
    
    Args:
        bins: List of bin dictionaries
        top_n: Number of top bands to return (default: 5)
        
    Returns:
        List of top N bins sorted by liquidity (descending)
    """
    # Calculate liquidity for each bin
    bins_with_liquidity = []
    for bin in bins:
        total_liquidity = calculate_total_liquidity(bin)
        bin_copy = bin.copy()
        bin_copy["total_liquidity"] = total_liquidity
        bins_with_liquidity.append(bin_copy)
    
    # Sort by total liquidity (descending)
    sorted_bins = sorted(bins_with_liquidity, key=lambda x: x["total_liquidity"], reverse=True)
    
    # Return top N
    return sorted_bins[:top_n]


def recommend_top_bands(bins: List[Dict], top_n: int = 5, 
                        fetch_volume_func: Optional[Callable] = None) -> Dict:
    """
    Main recommender function that returns top bands by liquidity.
    
    Args:
        bins: List of bin dictionaries with priceLower, priceUpper, amount_weth, 
              amount_usdt, count_nfts
        top_n: Number of top bands to return (default: 5)
        fetch_volume_func: Optional function to fetch trading volume. Should accept
                          (price_low, price_high, start_date, end_date) and return
                          response data that can be parsed for volume.
        
    Returns:
        Dictionary with one category:
        - top_liquidity_bands: Top N bands by liquidity (with trading_volume_24h if fetched)
    """
    top_liquidity = get_top_liquidity_bands(bins, top_n)
    
    # Fetch trading volumes if function is provided
    if fetch_volume_func:
        # Calculate last 24 hours
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(hours=24)
        
        # Fetch volumes for top liquidity bands
        for band in top_liquidity:
            price_low = band.get("priceLower", 0.0)
            price_high = band.get("priceUpper", 0.0)
            if price_low > 0 and price_high > 0:
                volume_response = fetch_volume_func(price_low, price_high, start_date, end_date)
                if volume_response:
                    from parser import parse_trading_volume
                    volume = parse_trading_volume(volume_response)
                    band["trading_volume_24h"] = volume
                else:
                    band["trading_volume_24h"] = 0.0
            else:
                band["trading_volume_24h"] = 0.0
    
    return {
        "top_liquidity_bands": top_liquidity
    }


def format_band_info(band: Dict) -> str:
    """
    Format a band dictionary into a readable string.
    
    Args:
        band: Band dictionary
        
    Returns:
        Formatted string representation
    """
    bin_index = band.get("bin_index", "N/A")
    price_lower = band.get("priceLower", 0.0)
    price_upper = band.get("priceUpper", 0.0)
    amount_weth = band.get("amount_weth", 0.0)
    amount_usdt = band.get("amount_usdt", 0.0)
    count_nfts = band.get("count_nfts", 0)
    total_liquidity = band.get("total_liquidity", 0.0)
    trading_volume_24h = band.get("trading_volume_24h")
    
    info = f"Bin {bin_index}: Price Range [{price_lower:.2f}, {price_upper:.2f}]"
    if total_liquidity > 0:
        info += f" | Total Liquidity: ${total_liquidity:,.2f}"
    info += f" | WETH: {amount_weth:.6f} | USDT: {amount_usdt:,.2f} | Positions: {count_nfts}"
    
    if trading_volume_24h is not None:
        info += f" | 24h Trading Volume: ${trading_volume_24h:,.2f}"
    
    return info


def print_recommendations(recommendations: Dict) -> None:
    """
    Print recommendations in a formatted way.
    
    Args:
        recommendations: Dictionary returned by recommend_top_bands
    """
    print("\n" + "="*80)
    print("TOP 5 PRICE BANDS BY LIQUIDITY")
    print("="*80)
    
    for i, band in enumerate(recommendations["top_liquidity_bands"], 1):
        print(f"\n{i}. {format_band_info(band)}")
    
    print("\n" + "="*80)



