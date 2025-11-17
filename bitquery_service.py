import requests
import json
from datetime import datetime, timedelta, timezone
from config import BITQUERY_API_KEY

url = "https://streaming.bitquery.io/graphql"

query = """query Positions($startDate: DateTime!, $endDate: DateTime!) {
  EVM(dataset: archive, network: eth) {
    Calls(
      where: {Call: {Signature: {Name: {is: "mint"}}, To: {is: "0xC36442b4a4522E871399CD717aBDD847Ab11FE88"}}, Arguments: {includes: {Value: {Address: {in: ["0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", "0xdac17f958d2ee523a2206206994597c13d831ec7"]}}}}, Block: {Time: {since: $startDate, till: $endDate}}}
      limit: {count: 10000}
      orderBy: {descending: Block_Number}
    ) {
      Arguments {
        Index
        Name
        Type
        Path {
          Name
          Index
        }
        Value {
          ... on EVM_ABI_Address_Value_Arg {
            address
          }
          ... on EVM_ABI_BigInt_Value_Arg {
            bigInteger
          }
          ... on EVM_ABI_Bytes_Value_Arg {
            hex
          }
          ... on EVM_ABI_Boolean_Value_Arg {
            bool
          }
          ... on EVM_ABI_String_Value_Arg {
            string
          }
          ... on EVM_ABI_Integer_Value_Arg {
            integer
          }
        }
      }
      Call {
        Signature {
          Name
        }
        To
        Value
        ValueInUSD
        From
      }
      Transaction {
        position_creator: From
        To
        Hash
        ValueInUSD
        Value
        Time
      }
      Block {
        Number
        Time
      }
      Returns {
        Value {
          ... on EVM_ABI_Boolean_Value_Arg {
            bool
          }
          ... on EVM_ABI_Bytes_Value_Arg {
            hex
          }
          ... on EVM_ABI_BigInt_Value_Arg {
            bigInteger
          }
          ... on EVM_ABI_Address_Value_Arg {
            address
          }
          ... on EVM_ABI_String_Value_Arg {
            string
          }
          ... on EVM_ABI_Integer_Value_Arg {
            integer
          }
        }
        Type
        Name
      }
    }
  }
}

"""

liquidity_query = """query LiquidityCalls($nftIds: [String!], $startDate: DateTime!, $endDate: DateTime!) {
  EVM(dataset: archive, network: eth) {
    Calls(
      orderBy: {descending: Block_Number}
      where: {
        Call: {
          Signature: {Name: {in: ["increaseLiquidity", "decreaseLiquidity"]}}
          To: {is: "0xC36442b4a4522E871399CD717aBDD847Ab11FE88"}
        }
        Arguments: {includes: {Value: {BigInteger: {in: $nftIds}}}}
        Block: {Time: {since: $startDate, till: $endDate}}
      }
      limit: {count: 10000}
    ) {
      Arguments {
        Index
        Name
        Type
        Path {
          Name
          Index
        }
        Value {
          ... on EVM_ABI_Address_Value_Arg {
            address
          }
          ... on EVM_ABI_BigInt_Value_Arg {
            bigInteger
          }
          ... on EVM_ABI_Bytes_Value_Arg {
            hex
          }
          ... on EVM_ABI_Boolean_Value_Arg {
            bool
          }
          ... on EVM_ABI_String_Value_Arg {
            string
          }
          ... on EVM_ABI_Integer_Value_Arg {
            integer
          }
        }
      }
      Call {
        Signature {
          Name
        }
        To
        Value
        ValueInUSD
        From
      }
      Transaction {
        From
        To
        Hash
        ValueInUSD
        Value
        Time
      }
      Block {
        Number
        Time
      }
      Returns {
        Value {
          ... on EVM_ABI_Boolean_Value_Arg {
            bool
          }
          ... on EVM_ABI_Bytes_Value_Arg {
            hex
          }
          ... on EVM_ABI_BigInt_Value_Arg {
            bigInteger
          }
          ... on EVM_ABI_Address_Value_Arg {
            address
          }
          ... on EVM_ABI_String_Value_Arg {
            string
          }
          ... on EVM_ABI_Integer_Value_Arg {
            integer
          }
        }
        Type
        Name
      }
    }
  }
}
"""

trading_volume_query = """query TradingVolume($priceLow: Float, $priceHigh: Float, $startDate: DateTime!, $endDate: DateTime!) {
    EVM(network: eth, dataset: archive) {
        DEXTradeByTokens(
            where: {
                Trade: {
                    Currency: {SmartContract: {is: "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"}}
                    Side: {Currency: {SmartContract: {is: "0xdac17f958d2ee523a2206206994597c13d831ec7"}}}
                    Dex: {ProtocolFamily: {is: "Uniswap"}}
                    PriceInUSD: {ge: $priceLow, le: $priceHigh}
                }
                Block: {Time: {since: $startDate, till: $endDate}}
                TransactionStatus: {Success: true}
            }
        ) {
            volume: sum(of: Trade_AmountInUSD)
        }
    }
}
"""

def fetch_trading_volume(price_low: float, price_high: float, start_date: datetime, end_date: datetime):
    """
    Fetch trading volume for a given price range and date range.
    
    Args:
        price_low: Lower bound of price range in USD
        price_high: Upper bound of price range in USD
        start_date: Start date (datetime object)
        end_date: End date (datetime object)
    
    Returns:
        dict: Response data from Bitquery API, or None if error
    """
    variables = {
        "priceLow": str(price_low),
        "priceHigh": str(price_high),
        "startDate": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endDate": end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    
    payload = json.dumps({
        "query": trading_volume_query,
        "variables": variables
    })
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {BITQUERY_API_KEY}"
    }
    
    response = requests.post(url, headers=headers, data=payload)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error fetching trading volume: {response.status_code}")
        print(response.text)
        return None

def fetch_mint_positions(start_date: datetime, end_date: datetime):
    """
    Fetch mint positions from Bitquery API.
    
    Args:
        start_date: Start date (datetime object)
        end_date: End date (datetime object)
    
    Returns:
        tuple: (response_data, response_status_code) or (None, status_code) if error
    """
    variables = {
        "startDate": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endDate": end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    
    payload = json.dumps({
        "query": query,
        "variables": variables
    })
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {BITQUERY_API_KEY}"
    }
    
    response = requests.post(url, headers=headers, data=payload)
    
    if response.status_code == 200:
        return response.json(), response.status_code
    else:
        return None, response.status_code


def fetch_liquidity_events(nft_ids: list, start_date: datetime, end_date: datetime):
    """
    Fetch liquidity events (increaseLiquidity calls) from Bitquery API.
    
    Args:
        nft_ids: List of NFT IDs to query
        start_date: Start date (datetime object)
        end_date: End date (datetime object)
    
    Returns:
        tuple: (response_data, response_status_code) or (None, status_code) if error
    """
    liquidity_variables = {
        "nftIds": nft_ids,
        "startDate": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endDate": end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    
    liquidity_payload = json.dumps({
        "query": liquidity_query,
        "variables": liquidity_variables
    })
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {BITQUERY_API_KEY}"
    }
    
    liquidity_response = requests.post(url, headers=headers, data=liquidity_payload)
    
    if liquidity_response.status_code == 200:
        return liquidity_response.json(), liquidity_response.status_code
    else:
        return None, liquidity_response.status_code
