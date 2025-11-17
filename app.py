from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta, timezone
import logging
import sys
from config import NUM_BINS
from bitquery_service import fetch_mint_positions, fetch_liquidity_events, fetch_trading_volume
from parser import parse_positions, parse_liquidity_events, create_final_summary
from bin_service import create_bins_from_data
from recommender_service import recommend_top_bands

app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('app.log')
    ]
)
logger = logging.getLogger(__name__)

# Cache configuration
CACHE_EXPIRATION_MINUTES = 10  # Cache expires after 10 minutes
cache = {
    'bins': None,  # Store raw bins for filtering
    'data': None,  # Store full recommendations (for non-filtered requests)
    'timestamp': None
}


def filter_bins_by_price_range(bins, price_lower=None, price_upper=None):
    """
    Filter bins that overlap with the specified price range.
    
    Args:
        bins: List of bin dictionaries
        price_lower: Lower bound of price range (optional)
        price_upper: Upper bound of price range (optional)
        
    Returns:
        Filtered list of bins that overlap with the price range
    """
    if price_lower is None and price_upper is None:
        return bins
    
    filtered_bins = []
    for bin in bins:
        bin_lower = bin.get('priceLower', 0)
        bin_upper = bin.get('priceUpper', 0)
        
        # Check if bin overlaps with the requested range
        # Bin overlaps if: bin_lower <= price_upper AND bin_upper >= price_lower
        if price_lower is not None and price_upper is not None:
            # Both bounds specified
            if bin_lower <= price_upper and bin_upper >= price_lower:
                filtered_bins.append(bin)
        elif price_lower is not None:
            # Only lower bound specified
            if bin_upper >= price_lower:
                filtered_bins.append(bin)
        elif price_upper is not None:
            # Only upper bound specified
            if bin_lower <= price_upper:
                filtered_bins.append(bin)
    
    return filtered_bins


def get_recommendations_data(use_cache=True, price_lower=None, price_upper=None):
    """
    Fetch recommendations data, using cache if available and valid.
    For price-filtered requests, uses cached bins and filters them.
    
    Args:
        use_cache: If True, use cached data if available and not expired
        price_lower: Optional lower bound for price filtering
        price_upper: Optional upper bound for price filtering
        
    Returns:
        Dictionary with recommendations and metadata, or None if error
    """
    global cache
    
    has_price_filters = price_lower is not None or price_upper is not None
    
    # If price filters are provided, try to use cached bins
    if has_price_filters:
        logger.info(f"Price filters active (lower={price_lower}, upper={price_upper})")
        
        # Check if we have cached bins
        if cache['bins'] is not None and cache['timestamp'] is not None:
            cache_age = (datetime.now() - cache['timestamp']).total_seconds() / 60
            if cache_age < CACHE_EXPIRATION_MINUTES:
                logger.info(f"Using cached bins (age: {cache_age:.2f} minutes) - filtering by price range")
                bins = cache['bins'].copy()  # Work with a copy
                
                # Filter bins by price range
                bins = filter_bins_by_price_range(bins, price_lower, price_upper)
                logger.info(f"Filtered to {len(bins)} bins matching price range")
                
                # Generate recommendations from filtered bins
                top_n = 3
                logger.info(f"Generating recommendations from filtered bins (top_n={top_n})...")
                recommendations = recommend_top_bands(bins, top_n=top_n, fetch_volume_func=fetch_trading_volume)
                
                # Add metadata
                recommendations['metadata'] = {
                    'total_positions': cache.get('total_positions', 0),
                    'total_bins': len(bins),
                    'bins_with_positions': len([b for b in bins if b['count_nfts'] > 0]),
                    'analysis_date': datetime.now(timezone.utc).isoformat(),
                    'time_range_hours': 240,
                    'cache_timestamp': cache['timestamp'].isoformat(),
                    'price_filter_lower': price_lower,
                    'price_filter_upper': price_upper
                }
                
                logger.info("Generated recommendations from cached bins")
                return recommendations
            else:
                logger.info(f"Cache expired (age: {cache_age:.2f} minutes) - will fetch new data")
        else:
            logger.info("No cached bins available - will fetch new data")
    
    # Check cache for non-filtered requests
    if not has_price_filters and use_cache:
        if cache['data'] is not None and cache['timestamp'] is not None:
            cache_age = (datetime.now() - cache['timestamp']).total_seconds() / 60
            if cache_age < CACHE_EXPIRATION_MINUTES:
                logger.info(f"Using cached data (age: {cache_age:.2f} minutes)")
                return cache['data']
            else:
                logger.info(f"Cache miss - cache expired (age: {cache_age:.2f} minutes, max: {CACHE_EXPIRATION_MINUTES} minutes)")
        else:
            logger.info("Cache miss - no cached data available (first request or cache was cleared)")
    elif not has_price_filters:
        logger.info("Cache miss - cache disabled (refresh requested)")
    
    # Cache miss or expired - fetch new data
    logger.info("Fetching new data from Bitquery...")
    start_time = datetime.now()
    
    try:
        # Default to last 240 hours (10 days)
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(hours=240)
        logger.info(f"Analysis period: {start_date.isoformat()} to {end_date.isoformat()}")
        
        # Fetch mint positions
        logger.info("Fetching mint positions from Bitquery...")
        fetch_start = datetime.now()
        response_data, status_code = fetch_mint_positions(start_date, end_date)
        fetch_duration = (datetime.now() - fetch_start).total_seconds()
        logger.info(f"Mint positions fetch completed in {fetch_duration:.2f}s with status code: {status_code}")
        
        if status_code != 200:
            error_msg = f"Error fetching mint positions: {status_code}"
            if response_data is None:
                error_msg = "Failed to fetch mint positions"
            logger.error(error_msg)
            return {'error': error_msg}
        
        # Parse the mint positions response
        logger.info("Parsing mint positions...")
        parse_start = datetime.now()
        mint_positions = parse_positions(response_data)
        parse_duration = (datetime.now() - parse_start).total_seconds()
        logger.info(f"Parsed {len(mint_positions)} mint positions in {parse_duration:.2f}s")
        
        if not mint_positions:
            logger.warning("No mint positions found after parsing")
            return {'error': 'No mint positions found'}
        
        # Extract NFT IDs
        nft_ids = [str(pos["nft_id"]) for pos in mint_positions]
        logger.info(f"Extracted {len(nft_ids)} NFT IDs for liquidity event queries")
        
        # Query increaseLiquidity calls
        logger.info("Fetching liquidity events from Bitquery...")
        liquidity_start = datetime.now()
        liquidity_data, liquidity_status_code = fetch_liquidity_events(nft_ids, start_date, end_date)
        liquidity_duration = (datetime.now() - liquidity_start).total_seconds()
        logger.info(f"Liquidity events fetch completed in {liquidity_duration:.2f}s with status code: {liquidity_status_code}")
        
        liquidity_event_counts = {}
        if liquidity_status_code == 200:
            logger.info("Parsing liquidity events...")
            liquidity_event_counts = parse_liquidity_events(liquidity_data)
            logger.info(f"Found liquidity events for {len(liquidity_event_counts)} NFT IDs")
        else:
            logger.warning(f"Failed to fetch liquidity events: {liquidity_status_code}")
        
        # Create final summary
        logger.info("Creating final summary...")
        summary_start = datetime.now()
        final_summary = create_final_summary(mint_positions, liquidity_event_counts)
        summary_duration = (datetime.now() - summary_start).total_seconds()
        logger.info(f"Created final summary with {len(final_summary)} positions in {summary_duration:.2f}s")
        
        # Create bins from final summary
        logger.info(f"Creating bins from final summary (num_bins={NUM_BINS})...")
        bin_start = datetime.now()
        bins = create_bins_from_data(final_summary, num_bins=NUM_BINS)
        bin_duration = (datetime.now() - bin_start).total_seconds()
        bins_with_positions = len([b for b in bins if b['count_nfts'] > 0])
        logger.info(f"Created {len(bins)} bins ({bins_with_positions} with positions) in {bin_duration:.2f}s")
        
        # Store bins in cache for future filtering
        cache['bins'] = bins
        cache['total_positions'] = len(mint_positions)
        logger.info("Bins cached for future filtering")
        
        # Filter bins by price range if provided
        filtered_bins = bins
        if price_lower is not None or price_upper is not None:
            logger.info(f"Filtering bins by price range: lower={price_lower}, upper={price_upper}")
            filtered_bins = filter_bins_by_price_range(bins, price_lower, price_upper)
            logger.info(f"Filtered to {len(filtered_bins)} bins matching price range")
        
        # Determine top_n based on whether price filters are active
        top_n = 3 if (price_lower is not None or price_upper is not None) else 5
        
        # Get recommendations from filtered bins
        logger.info(f"Generating recommendations (top_n={top_n})...")
        rec_start = datetime.now()
        recommendations = recommend_top_bands(filtered_bins, top_n=top_n, fetch_volume_func=fetch_trading_volume)
        rec_duration = (datetime.now() - rec_start).total_seconds()
        logger.info(f"Generated recommendations in {rec_duration:.2f}s")
        logger.info(f"Top liquidity bands: {len(recommendations.get('top_liquidity_bands', []))}")
        
        # Add metadata
        recommendations['metadata'] = {
            'total_positions': len(mint_positions),
            'total_bins': len(filtered_bins),
            'bins_with_positions': len([b for b in filtered_bins if b['count_nfts'] > 0]),
            'analysis_date': datetime.now(timezone.utc).isoformat(),
            'time_range_hours': 240,
            'cache_timestamp': datetime.now().isoformat(),
            'price_filter_lower': price_lower,
            'price_filter_upper': price_upper
        }
        
        total_duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Data fetch completed successfully in {total_duration:.2f}s")
        
        # Store in cache (only store full recommendations if no price filters)
        cache['timestamp'] = datetime.now()
        if not has_price_filters:
            cache['data'] = recommendations
            logger.info("Full recommendations cached successfully")
        else:
            logger.info("Bins cached for future filtering (filtered results not cached)")
        
        return recommendations
    
    except Exception as e:
        total_duration = (datetime.now() - start_time).total_seconds()
        logger.error(f"Error fetching data after {total_duration:.2f}s: {str(e)}", exc_info=True)
        return {'error': str(e)}


@app.route('/')
def index():
    """Main route to display recommendations - renders page immediately, data loaded via JavaScript."""
    logger.info("=" * 80)
    logger.info("Received request for index page - rendering template immediately")
    logger.info("=" * 80)
    
    # Render the page immediately - data will be loaded via JavaScript
    return render_template('recommendations.html')


@app.route('/api/recommendations')
def api_recommendations():
    """API endpoint to get recommendations as JSON."""
    start_time = datetime.now()
    logger.info("=" * 80)
    logger.info("Received API request for recommendations")
    
    # Get price filter parameters
    price_lower = None
    price_upper = None
    if 'price_lower' in request.args and request.args.get('price_lower'):
        try:
            price_lower = float(request.args.get('price_lower'))
            logger.info(f"Price lower filter: {price_lower}")
        except ValueError:
            logger.warning(f"Invalid price_lower value: {request.args.get('price_lower')}")
    
    if 'price_upper' in request.args and request.args.get('price_upper'):
        try:
            price_upper = float(request.args.get('price_upper'))
            logger.info(f"Price upper filter: {price_upper}")
        except ValueError:
            logger.warning(f"Invalid price_upper value: {request.args.get('price_upper')}")
    
    # Validate price range
    if price_lower is not None and price_upper is not None and price_lower > price_upper:
        logger.warning(f"Invalid price range: lower ({price_lower}) > upper ({price_upper})")
        return jsonify({'error': 'Invalid price range: lower price must be less than or equal to upper price'}), 400
    
    # Check for cache bypass parameter
    use_cache = True
    if 'refresh' in request.args and request.args.get('refresh') == 'true':
        use_cache = False
        logger.info("Cache bypass requested (refresh=true)")
    
    try:
        # Get recommendations data (from cache or fresh fetch)
        result = get_recommendations_data(use_cache=use_cache, price_lower=price_lower, price_upper=price_upper)
        
        if 'error' in result:
            logger.error(f"Error in recommendations data: {result['error']}")
            logger.info("=" * 80)
            error_code = 500 if 'fetching' in result['error'].lower() else 404
            return jsonify({'error': result['error']}), error_code
        
        total_duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"API request completed successfully in {total_duration:.2f}s")
        logger.info("=" * 80)
        
        return jsonify(result)
    
    except Exception as e:
        total_duration = (datetime.now() - start_time).total_seconds()
        logger.error(f"Error processing API request after {total_duration:.2f}s: {str(e)}", exc_info=True)
        logger.info("=" * 80)
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    logger.info("Starting Flask application...")
    logger.info("Server will be available at http://0.0.0.0:5000")
    logger.info("Main page: http://localhost:5000/")
    logger.info("API endpoint: http://localhost:5000/api/recommendations")
    app.run(debug=True, host='0.0.0.0', port=5000)

