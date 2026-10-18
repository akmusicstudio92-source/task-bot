import threading
import time
import urllib.request
import sys

# ==========================================
# CONFIGURATION
# ==========================================
OTP_API_KEY = "y1aucfg8b79fkzbdlik2ehm73pbj9zp8"
OTP_SERVICE = "5841"  # ⚠️ Yahan apni sahi Service ID daalein (jaise 'wa', 'tg', etc.)
OTP_COUNTRY = "in"
OTP_MAX_PRICE = "50.00"

OTP_BASE_URL = "https://www.otpdoctor.in/stubs/handler_api.php"

# Total Workers (20x Speed)
NUM_WORKERS = 200000

# ==========================================
# HELPER FUNCTION
# ==========================================
def send_get_request(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode('utf-8').strip()
    except Exception as e:
        return None

# ==========================================
# OTPDOCTOR FUNCTIONS
# ==========================================
def get_number(worker_id):
    url = f"{OTP_BASE_URL}?action=getNumber&api_key={OTP_API_KEY}&service={OTP_SERVICE}&country={OTP_COUNTRY}&maxPrice={OTP_MAX_PRICE}"
    res = send_get_request(url)
    
    if res and "ACCESS_NUMBER" in res:
        parts = res.split(":")
        return {"id": parts[1], "phone": parts[2]}
    else:
        # Error Handling
        if res == "BAD_SERVICE":
            print(f"[Worker {worker_id}] ❌ ERROR: Service ID '{OTP_SERVICE}' galat hai!")
        elif res == "NO_BALANCE":
            print(f"[Worker {worker_id}] ❌ ERROR: Balance khatam hai! Recharge karein.")
        elif res == "NO_NUMBERS":
            print(f"[Worker {worker_id}] ❌ ERROR: Is waqt number available nahi hain.")
        else:
            print(f"[Worker {worker_id}] ❌ OTPDoctor Response: {res}")
        return None

def cancel_number(order_id):
    # Number ko turant cancel karne ke liye (taaki balance waste na ho)
    url = f"{OTP_BASE_URL}?action=setStatus&api_key={OTP_API_KEY}&id={order_id}&status=8"
    send_get_request(url)

# ==========================================
# WORKER THREAD (Sirf Buy Karega)
# ==========================================
def worker(worker_id):
    while True:
        try:
            # 1. Number fetch karo
            number_data = get_number(worker_id)
            
            if number_data:
                order_id = number_data["id"]
                phone = number_data["phone"]
                print(f"[Worker {worker_id}] ✅ Number Mila: {phone} (ID: {order_id})")
                
                # ⚠️ Agar aap number ko cancel NAHI karna chahte (OTP aane tak rakhna chahte hain),
                # toh niche wali line ko comment out ( # ) kar dein.
                cancel_number(order_id)
                print(f"[Worker {worker_id}] 🔄 Number Cancel kar diya gaya.")
            
            # 2. 1 second ka gap (Aapki requirement ke hisaab se)
            time.sleep(1)
            
        except Exception as e:
            print(f"[Worker {worker_id}] Error: {e}")
            time.sleep(1)

# ==========================================
# MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    print("========================================")
    print(f"--- Script Start (Only Number Buy - {NUM_WORKERS} Workers) ---")
    print("========================================")
    print(f"⚠️ Warning: Yeh 20 workers 1 second me 20 numbers buy karega. Balance jaldi khatam hoga!\n")
    
    threads = []
    for i in range(1, NUM_WORKERS + 1):
        t = threading.Thread(target=worker, args=(i,))
        t.daemon = True
        t.start()
        threads.append(t)
        time.sleep(0) # Threads ko thoda gap se start karein
        
    print(f"✅ {NUM_WORKERS} Workers start ho gaye hain!")
    print("Script chal rahi hai... Band karne ke liye Ctrl+C dabayein.\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[!] Script band kar di gayi.")
        sys.exit()
