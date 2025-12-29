from iqoptionapi.stable_api import IQ_Option
import logging
import time

logging.basicConfig(level=logging.INFO)

email = "prospermenge55@gmail.com"
password = "Password@123"

api = IQ_Option(email, password)
api.connect()

print("Connected:", api.check_connect())

if api.check_connect():
    print("Getting open time...")
    all_assets = api.get_all_open_time()
    
    open_turbo = []
    if 'turbo' in all_assets:
        for pair, data in all_assets['turbo'].items():
            if data['open']:
                open_turbo.append(pair)
    
    print(f"Open Turbo (Schedule): {open_turbo[:10]}")
    
    print("Getting all profit...")
    all_profit = api.get_all_profit()
    print(f"Profit Data Type: {type(all_profit)}")
    if isinstance(all_profit, dict):
        # Print a sample
        keys = list(all_profit.keys())
        print(f"Profit Keys sample: {keys[:5]}")
        if 'EURUSD' in all_profit:
            print(f"EURUSD Profit: {all_profit['EURUSD']}")
        if 'EURUSD-OTC' in all_profit:
             print(f"EURUSD-OTC Profit: {all_profit['EURUSD-OTC']}")
