"""
Utility script to check and cancel open orders for a specific symbol.
Usage: python check_orders.py SYMBOL

Example:
  python check_orders.py UNIUSDT
  python check_orders.py BTCUSDT
"""

import sys
from binance.client import Client
from config.secrets import API_KEY, API_SECRET

def check_and_cancel_orders(symbol):
    """Check for open orders and optionally cancel them."""
    client = Client(API_KEY, API_SECRET)
    
    try:
        # Sync time with Binance servers
        server_time = client.get_server_time()
        local_time = int(__import__('time').time() * 1000)
        time_offset = server_time['serverTime'] - local_time
        client.timestamp_offset = time_offset
    except Exception:
        pass
    
    try:
        # Get all open orders for the symbol
        open_orders = client.futures_get_open_orders(symbol=symbol)
        
        if not open_orders:
            print(f"✅ No open orders found for {symbol}")
            return
        
        print(f"\n📋 Found {len(open_orders)} open order(s) for {symbol}:\n")
        
        for i, order in enumerate(open_orders, 1):
            order_id = order.get('orderId', 'N/A')
            order_type = order.get('type', 'UNKNOWN')
            side = order.get('side', 'UNKNOWN')
            price = order.get('price', order.get('stopPrice', order.get('triggerprice', 'N/A')))
            quantity = order.get('origQty', 'N/A')
            status = order.get('status', 'UNKNOWN')
            
            print(f"{i}. Order ID: {order_id}")
            print(f"   Type: {order_type}")
            print(f"   Side: {side}")
            print(f"   Price: {price}")
            print(f"   Quantity: {quantity}")
            print(f"   Status: {status}")
            print()
        
        # Ask if user wants to cancel all orders
        response = input(f"Do you want to cancel ALL {len(open_orders)} order(s)? (yes/no): ").strip().lower()
        
        if response == 'yes' or response == 'y':
            print(f"\n🔄 Cancelling all orders for {symbol}...\n")
            
            for order in open_orders:
                order_id = order.get('orderId')
                order_type = order.get('type', 'UNKNOWN')
                
                try:
                    client.futures_cancel_order(symbol=symbol, orderId=order_id)
                    print(f"✅ Cancelled {order_type} order {order_id}")
                except Exception as e:
                    print(f"❌ Failed to cancel order {order_id}: {e}")
            
            print(f"\n✅ Done! All orders cancelled for {symbol}")
        else:
            print("❌ Cancelled. No orders were deleted.")
    
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_orders.py SYMBOL")
        print("Example: python check_orders.py UNIUSDT")
        sys.exit(1)
    
    symbol = sys.argv[1].upper()
    check_and_cancel_orders(symbol)
