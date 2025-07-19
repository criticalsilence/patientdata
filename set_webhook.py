import os
import requests
from dotenv import load_dotenv

# Ortam değişkenlerini .env dosyasından yükleyin
load_dotenv()

# Telegram bot token'ını ortam değişkenlerinden alın
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# Render uygulamanızın URL'si (Render'dan kopyalayacağınız URL)
# ÖNEMLİ: Bu URL'yi Render dashboard'unuzdan alacaksınız!
RENDER_APP_URL = "https://patientdata-ee3q.onrender.com" # Burayı kendi Render URL'nizle değiştirin!

# Webhook URL'si (Telegram'a bildirilecek tam URL)
WEBHOOK_URL = f"{RENDER_APP_URL}/webhook"

if not TELEGRAM_BOT_TOKEN:
    print("Hata: TELEGRAM_BOT_TOKEN ortam değişkeni ayarlanmamış. Lütfen .env dosyasını kontrol edin.")
    exit(1)

if RENDER_APP_URL == "https://your-render-app-name.onrender.com":
    print("Hata: RENDER_APP_URL'yi kendi Render uygulamanızın URL'si ile güncelleyin.")
    exit(1)

# Telegram Bot API endpoint'i
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"

# Webhook ayarlama isteği
params = {'url': WEBHOOK_URL}

print(f"Webhook URL'si ayarlanıyor: {WEBHOOK_URL}")
try:
    response = requests.post(TELEGRAM_API_URL, params=params)
    response_json = response.json()

    if response_json.get("ok"):
        print("Webhook başarıyla ayarlandı!")
        print(f"Yanıt: {response_json}")
    else:
        print(f"Webhook ayarlanırken hata oluştu: {response_json.get('description', 'Bilinmeyen hata')}")
        print(f"Tam Yanıt: {response_json}")

except requests.exceptions.RequestException as e:
    print(f"Ağ hatası veya API isteği gönderilirken hata oluştu: {e}")
except Exception as e:
    print(f"Beklenmeyen bir hata oluştu: {e}")