import os
import requests
from dotenv import load_dotenv

# Ortam değişkenlerini .env dosyasından yükleyin
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Webhook'u kaldırmak için URL'yi boş bırakıyoruz
WEBHOOK_URL = "" # Burayı boş string olarak ayarlayın!

if not TELEGRAM_BOT_TOKEN:
    print("Hata: TELEGRAM_BOT_TOKEN ortam değişkeni ayarlanmamış. Lütfen .env dosyasını kontrol edin.")
    exit(1)

# Telegram Bot API endpoint'i
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"

# Webhook ayarlama isteği (URL boş olduğu için kaldırır)
params = {'url': WEBHOOK_URL}

print(f"Mevcut Webhook kaldırılıyor...")
try:
    response = requests.post(TELEGRAM_API_URL, params=params)
    response_json = response.json()

    if response_json.get("ok"):
        print("Webhook başarıyla kaldırıldı!")
        print(f"Yanıt: {response_json}")
    else:
        print(f"Webhook kaldırılırken hata oluştu: {response_json.get('description', 'Bilinmeyen hata')}")
        print(f"Tam Yanıt: {response_json}")

except requests.exceptions.RequestException as e:
    print(f"Ağ hatası veya API isteği gönderilirken hata oluştu: {e}")
except Exception as e:
    print(f"Beklenmeyen bir hata oluştu: {e}")

