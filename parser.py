import json
import math
from typing import List, Dict, Optional
from outlier_service import validate_amounts, validate_position_prices

# Token addresses (case-insensitive comparison)
WETH_ADDRESS = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
USDT_ADDRESS = "0xdac17f958d2ee523a2206206994597c13d831ec7"

# Token decimals
WETH_DECIMALS = 18
USDT_DECIMALS = 6


def normalize_address(address: str) -> str:
    """Normalize address to lowercase for comparison."""
    return address.lower() if address else ""


def calculate_price_from_tick(tick: int) -> float:
    """
    Calculate price using the formula: 1.0001^tick
    
    Args:
        tick: The tick value
        
    Returns:
        Price as a float
    """
    return 1.0001 ** tick


def calculate_price_with_decimals(tick: int, decimal0: int, decimal1: int) -> float:
    """
    Calculate price using the formula: (1.0001^tick) / (10^(Decimal1 - Decimal0))
    
    Args:
        tick: The tick value
        decimal0: Decimals of token0
        decimal1: Decimals of token1
        
    Returns:
        Price as a float
    """
    price_base = 1.0001 ** tick
    decimal_diff = decimal1 - decimal0
    return price_base / (10 ** decimal_diff)


def extract_position_data(position: Dict) -> Optional[Dict]:
    """
    Extract position data from a single position record.
    
    Args:
        position: A position record from Bitquery API response
        
    Returns:
        Dictionary with extracted data or None if position doesn't match criteria
    """
    try:
        # Extract token addresses from Arguments
        arguments = position.get("Arguments", [])
        if len(arguments) < 2:
            return None
        
        # Get token0 and token1 addresses (first two arguments)
        token0_address = None
        token1_address = None
        
        for arg in arguments[:2]:
            if arg.get("Index") == 0:
                value = arg.get("Value", {})
                if "address" in value:
                    token0_address = normalize_address(value["address"])
            elif arg.get("Index") == 1:
                value = arg.get("Value", {})
                if "address" in value:
                    token1_address = normalize_address(value["address"])
        
        # Check if both WETH and USDT are present
        weth_normalized = normalize_address(WETH_ADDRESS)
        usdt_normalized = normalize_address(USDT_ADDRESS)
        
        has_weth = (token0_address == weth_normalized or token1_address == weth_normalized)
        has_usdt = (token0_address == usdt_normalized or token1_address == usdt_normalized)
        
        if not (has_weth and has_usdt):
            return None
        
        # Extract tickLower (Index 3) and tickUpper (Index 4)
        tick_lower = None
        tick_upper = None
        
        for arg in arguments:
            index = arg.get("Index")
            if index == 3:
                value = arg.get("Value", {})
                if "bigInteger" in value:
                    tick_lower = int(value["bigInteger"])
            elif index == 4:
                value = arg.get("Value", {})
                if "bigInteger" in value:
                    tick_upper = int(value["bigInteger"])
        
        # Extract NFT ID (tokenId) and amounts from Returns
        returns = position.get("Returns", [])
        nft_id = None
        amount0 = None
        amount1 = None
        
        for ret in returns:
            name = ret.get("Name", "")
            value = ret.get("Value", {})
            
            if name == "tokenId":
                if "bigInteger" in value:
                    nft_id = int(value["bigInteger"])
            elif name == "amount0":
                if "bigInteger" in value:
                    amount0 = int(value["bigInteger"])
            elif name == "amount1":
                if "bigInteger" in value:
                    amount1 = int(value["bigInteger"])
        
        # Fallback: if not found by name, try by index (mint returns: tokenId, liquidity, amount0, amount1)
        if amount0 is None or amount1 is None:
            for i, ret in enumerate(returns):
                value = ret.get("Value", {})
                if "bigInteger" in value:
                    if i == 2:  # amount0 is typically at index 2
                        amount0 = int(value["bigInteger"])
                    elif i == 3:  # amount1 is typically at index 3
                        amount1 = int(value["bigInteger"])
        
        # Extract timestamp (prefer Block.Time, fallback to Transaction.Time)
        timestamp = None
        block = position.get("Block", {})
        transaction = position.get("Transaction", {})
        
        if block and "Time" in block:
            timestamp = block["Time"]
        elif transaction and "Time" in transaction:
            timestamp = transaction["Time"]
        
        # Return None if required fields are missing
        if tick_lower is None or tick_upper is None or nft_id is None or timestamp is None:
            return None
        
        # Determine which token is token0 and token1, and their decimals
        is_weth_token0 = (token0_address == weth_normalized)
        is_usdt_token0 = (token0_address == usdt_normalized)
        
        if is_weth_token0:
            decimal0 = WETH_DECIMALS
            decimal1 = USDT_DECIMALS
        elif is_usdt_token0:
            decimal0 = USDT_DECIMALS
            decimal1 = WETH_DECIMALS
        else:
            # Fallback (shouldn't happen if filtering works correctly)
            decimal0 = 18
            decimal1 = 6
        
        # Calculate prices using both formulas
        # Formula 1: 1.0001^tick
        price_lower_base = calculate_price_from_tick(tick_lower)
        price_upper_base = calculate_price_from_tick(tick_upper)
        
        # Formula 2: (1.0001^tick) / (10^(Decimal1 - Decimal0))
        price_lower_afterdecimals = calculate_price_with_decimals(tick_lower, decimal0, decimal1)
        price_upper_afterdecimals = calculate_price_with_decimals(tick_upper, decimal0, decimal1)
        
        # Apply decimals to amounts
        amount0_afterdecimals = None
        amount1_afterdecimals = None
        if amount0 is not None:
            amount0_afterdecimals = amount0 / (10 ** decimal0)
        if amount1 is not None:
            amount1_afterdecimals = amount1 / (10 ** decimal1)
        
        # Map amounts to WETH and USDT explicitly
        amount_weth = None
        amount_usdt = None
        if is_weth_token0:
            amount_weth = amount0_afterdecimals
            amount_usdt = amount1_afterdecimals
        elif is_usdt_token0:
            amount_weth = amount1_afterdecimals
            amount_usdt = amount0_afterdecimals
        
        return {
            "nft_id": nft_id,
            "tick_lower": tick_lower,
            "tick_upper": tick_upper,
            "timestamp": timestamp,
            "token0": token0_address,
            "token1": token1_address,
            "price_lower": price_lower_base,
            "price_upper": price_upper_base,
            "price_lower_afterdecimals": price_lower_afterdecimals,
            "price_upper_afterdecimals": price_upper_afterdecimals,
            "amount0": amount0,
            "amount1": amount1,
            "amount0_afterdecimals": amount0_afterdecimals,
            "amount1_afterdecimals": amount1_afterdecimals,
            "amount_weth": amount_weth,
            "amount_usdt": amount_usdt
        }
    
    except (KeyError, ValueError, TypeError) as e:
        print(f"Error parsing position: {e}")
        return None


def parse_positions(response_data: Dict) -> List[Dict]:
    """
    Parse Bitquery API response and extract WETH/USDT positions.
    
    Args:
        response_data: The JSON response from Bitquery API
        
    Returns:
        List of parsed position dictionaries
    """
    positions = []
    
    # Handle both string and dict input
    if isinstance(response_data, str):
        try:
            response_data = json.loads(response_data)
        except json.JSONDecodeError:
            print("Error: Invalid JSON string")
            return positions
    
    # Navigate to the Calls data
    try:
        calls = response_data.get("data", {}).get("EVM", {}).get("Calls", [])
    except AttributeError:
        # If response_data is already the Calls list
        calls = response_data if isinstance(response_data, list) else []
    
    for position in calls:
        parsed = extract_position_data(position)
        if parsed:
            positions.append(parsed)
    
    return positions


def parse_liquidity_events(response_data: Dict) -> Dict[int, Dict]:
    """
    Parse IncreaseLiquidity and DecreaseLiquidity events/calls and count occurrences per NFT ID, 
    accumulating amounts (adding for increases, subtracting for decreases).
    
    Args:
        response_data: The JSON response from Bitquery API for IncreaseLiquidity/DecreaseLiquidity events/calls
        
    Returns:
        Dictionary mapping NFT ID to dict with count, total_amount0, and total_amount1
    """
    nft_data = {}
    
    # Handle both string and dict input
    if isinstance(response_data, str):
        try:
            response_data = json.loads(response_data)
        except json.JSONDecodeError:
            print("Error: Invalid JSON string")
            return nft_data
    
    # Try to get Events first (for backward compatibility)
    events = []
    try:
        events = response_data.get("data", {}).get("EVM", {}).get("Events", [])
    except AttributeError:
        pass
    
    # Also try to get Calls (for increaseLiquidity and decreaseLiquidity calls)
    calls = []
    try:
        calls = response_data.get("data", {}).get("EVM", {}).get("Calls", [])
    except AttributeError:
        pass
    
    # If response_data is already a list, use it directly
    if not events and not calls:
        if isinstance(response_data, list):
            # Check if it's events or calls by looking at first item structure
            if response_data and "Log" in response_data[0]:
                events = response_data
            else:
                calls = response_data
    
    # Process Events (for IncreaseLiquidity events)
    for event in events:
        arguments = event.get("Arguments", [])
        # The first argument (Index 0) should be the tokenId (NFT ID)
        for arg in arguments:
            if arg.get("Index") == 0:
                value = arg.get("Value", {})
                if "bigInteger" in value:
                    nft_id = int(value["bigInteger"])
                    if nft_id not in nft_data:
                        nft_data[nft_id] = {"count": 0, "total_amount0": 0, "total_amount1": 0}
                    nft_data[nft_id]["count"] += 1
                break
    
    # Process Calls (for increaseLiquidity and decreaseLiquidity calls)
    for call in calls:
        call_info = call.get("Call", {})
        signature = call_info.get("Signature", {})
        signature_name = signature.get("Name", "")
        
        # Check if this is an increaseLiquidity or decreaseLiquidity call
        if signature_name not in ["increaseLiquidity", "decreaseLiquidity"]:
            continue
        
        is_decrease = signature_name == "decreaseLiquidity"
        
        arguments = call.get("Arguments", [])
        returns = call.get("Returns", [])
        
        # Extract NFT ID from Arguments
        # For both increaseLiquidity and decreaseLiquidity, the first argument (Index 0) is the tokenId in the params struct
        nft_id = None
        for arg in arguments:
            if arg.get("Index") == 0:
                value = arg.get("Value", {})
                if "bigInteger" in value:
                    nft_id = int(value["bigInteger"])
                    break
        
        if nft_id is None:
            continue
        
        # Extract amount0 and amount1 from Returns
        amount0 = None
        amount1 = None
        
        for ret in returns:
            name = ret.get("Name", "")
            value = ret.get("Value", {})
            
            if name == "amount0" and "bigInteger" in value:
                amount0 = int(value["bigInteger"])
            elif name == "amount1" and "bigInteger" in value:
                amount1 = int(value["bigInteger"])
        
        # Fallback: try by index if not found by name
        if amount0 is None or amount1 is None:
            for i, ret in enumerate(returns):
                value = ret.get("Value", {})
                if "bigInteger" in value:
                    if i == 1:  # amount0 is typically at index 1 (after liquidity)
                        amount0 = int(value["bigInteger"])
                    elif i == 2:  # amount1 is typically at index 2
                        amount1 = int(value["bigInteger"])
        
        # Initialize or update NFT data
        if nft_id not in nft_data:
            nft_data[nft_id] = {"count": 0, "total_amount0": 0, "total_amount1": 0}
        
        # For increaseLiquidity: add to count and amounts
        # For decreaseLiquidity: subtract from amounts (count still increments to track events)
        if is_decrease:
            # Decrease liquidity: subtract amounts
            if amount0 is not None:
                nft_data[nft_id]["total_amount0"] -= amount0
            if amount1 is not None:
                nft_data[nft_id]["total_amount1"] -= amount1
            # Still increment count to track that a decrease event occurred
            nft_data[nft_id]["count"] += 1
        else:
            # Increase liquidity: add amounts (original behavior)
            nft_data[nft_id]["count"] += 1
            if amount0 is not None:
                nft_data[nft_id]["total_amount0"] += amount0
            if amount1 is not None:
                nft_data[nft_id]["total_amount1"] += amount1
    
    return nft_data


def create_final_summary(mint_positions: List[Dict], liquidity_data: Dict[int, Dict]) -> List[Dict]:
    """
    Create final summary object combining mint positions and liquidity change events (increases and decreases).
    
    Args:
        mint_positions: List of parsed mint position dictionaries
        liquidity_data: Dictionary mapping NFT ID to dict with count, total_amount0, and total_amount1
                        (amounts are net: increases added, decreases subtracted)
        
    Returns:
        List of final summary dictionaries
    """
    summary = []
    
    for position in mint_positions:
        nft_id = position["nft_id"]
        liquidity_info = liquidity_data.get(nft_id, {"count": 0, "total_amount0": 0, "total_amount1": 0})
        increase_count = liquidity_info.get("count", 0)
        total_positions = 1 + increase_count  # 1 for mint + N for liquidity events (increases/decreases)
        
        # Get token decimals from position
        token0_address = position.get("token0", "")
        is_weth_token0 = normalize_address(token0_address) == normalize_address(WETH_ADDRESS)
        
        if is_weth_token0:
            decimal0 = WETH_DECIMALS
            decimal1 = USDT_DECIMALS
        else:
            decimal0 = USDT_DECIMALS
            decimal1 = WETH_DECIMALS
        
        # Get mint amounts (handle None values)
        mint_amount0 = position.get("amount0") or 0
        mint_amount1 = position.get("amount1") or 0
        
        # Get net liquidity change amounts (increases minus decreases, handle None values)
        net_liquidity_amount0 = liquidity_info.get("total_amount0") or 0
        net_liquidity_amount1 = liquidity_info.get("total_amount1") or 0
        
        # Calculate total amounts (mint + net liquidity changes)
        total_amount0 = mint_amount0 + net_liquidity_amount0
        total_amount1 = mint_amount1 + net_liquidity_amount1
        
        # Apply decimals to total amounts
        total_amount0_afterdecimals = total_amount0 / (10 ** decimal0)
        total_amount1_afterdecimals = total_amount1 / (10 ** decimal1)
        
        # Map total amounts to WETH and USDT
        if is_weth_token0:
            total_amount_weth = total_amount0_afterdecimals
            total_amount_usdt = total_amount1_afterdecimals
        else:
            total_amount_weth = total_amount1_afterdecimals
            total_amount_usdt = total_amount0_afterdecimals
        
        # Validate amounts before adding to summary
        if not validate_amounts(total_amount_weth, total_amount_usdt, nft_id):
            continue
        
        # Create summary item first to validate prices
        summary_item = {
            "nft_id": nft_id,
            "create_time": position["timestamp"],
            "number_of_positions": total_positions,
            "price_lower_afterdecimals": position["price_lower_afterdecimals"],
            "price_upper_afterdecimals": position["price_upper_afterdecimals"],
            "amount_weth": total_amount_weth,
            "amount_usdt": total_amount_usdt
        }
        
        # Validate prices before adding to summary (this will catch extreme outliers)
        if not validate_position_prices(summary_item):
            print(f"Warning: Filtering out NFT {nft_id} with invalid prices in final summary: "
                  f"lower={summary_item['price_lower_afterdecimals']}, "
                  f"upper={summary_item['price_upper_afterdecimals']}")
            continue
        
        summary.append(summary_item)
    
    return summary


def parse_trading_volume(response_data: Dict) -> float:
    """
    Parse trading volume from Bitquery DEXTradeByTokens query response.
    
    Args:
        response_data: The JSON response from Bitquery API
        
    Returns:
        Trading volume as float, or 0.0 if not found or error
    """
    try:
        # Handle both string and dict input
        if isinstance(response_data, str):
            response_data = json.loads(response_data)
        
        # Navigate to the volume data
        dextrade_data = response_data.get("data", {}).get("EVM", {}).get("DEXTradeByTokens", [])
        
        if not dextrade_data:
            return 0.0
        
        # Get the first (and typically only) result
        volume_data = dextrade_data[0] if isinstance(dextrade_data, list) else dextrade_data
        volume = volume_data.get("volume")
        
        if volume is None:
            return 0.0
        
        # Convert to float if it's a string
        if isinstance(volume, str):
            try:
                return float(volume)
            except ValueError:
                return 0.0
        
        return float(volume)
    
    except Exception as e:
        print(f"Error parsing trading volume: {e}")
        return 0.0


if __name__ == "__main__":
    # Example usage
    # You can test with a sample response file or directly with response data
    print("Position Parser - Ready to use")
    print("Use parse_positions(response_data) to parse Bitquery API responses")

