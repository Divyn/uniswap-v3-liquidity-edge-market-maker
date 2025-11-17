import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BITQUERY_API_KEY = os.getenv("BITQUERY_API_KEY")

# Default number of bins for liquidity distribution analysis
NUM_BINS = 50