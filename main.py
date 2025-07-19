import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ApplicationBuilder,
    CallbackContext,
)
from flask import Flask, request # Flask için import

# Firebase Admin SDK için gerekli import'lar
import firebase_admin
from firebase_admin import credentials, firestore
import json # JSON kütüphanesini ekle

# Gemini API için gerekli import
import google.generativeai as genai

# Ortam değişkenlerini .env dosyasından yükleyin
load_dotenv()

# Günlük kaydı (logging) yapılandırması
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- YAPILANDIRMA AYARLARI ---
# Telegram bot token'ını ortam değişkenlerinden alın
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# Firebase servis hesabı anahtarının JSON içeriği (dosya yolu yerine)
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON") # Yeni ortam değişkeni adı
# Firestore koleksiyon adı (excel_to_firestore.py ile aynı olmalı)
FIRESTORE_COLLECTION_NAME = 'hasta_bilgileri' # Daha önce kullandığınız isimle aynı olduğundan emin olun!
# Bot için basit bir şifre (güvenli bir yerde saklayın!)
BOT_PASSWORD = os.getenv("BOT_PASSWORD", "sifre123") # Varsayılan şifre, .env'den alınacak.
# Gemini API Anahtarı
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Render'dan alınacak webhook URL'si (Render otomatik olarak PORT'u ayarlar)
PORT = int(os.environ.get('PORT', '8443')) # Render'ın atadığı portu kullan
WEBHOOK_URL = os.environ.get('WEBHOOK_URL') # Render'da bu ortam değişkenini ayarlayacağız

# Eğer token veya API anahtarı veya Firebase JSON yoksa hata verin
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN ortam değişkeni ayarlanmamış. Lütfen .env dosyasını kontrol edin.")
    exit(1)
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY ortam değişkeni ayarlanmamış. Lütfen .env dosyasını kontrol edin ve bir API anahtarı alın.")
    exit(1)
if not FIREBASE_SERVICE_ACCOUNT_JSON: # Yeni kontrol
    logger.error("FIREBASE_SERVICE_ACCOUNT_JSON ortam değişkeni ayarlanmamış. Lütfen Render'da Firebase servis hesabı JSON içeriğini ayarlayın.")
    exit(1)

# --- Firebase Başlatma ---
db = None # Firestore istemcisi global olarak tanımlanacak

def initialize_firebase():
    """Firebase Admin SDK'yı başlatır ve Firestore istemcisini döndürür."""
    global db
    if db is None:
        try:
            # Ortam değişkeninden JSON içeriğini oku
            cred_json = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
            cred = credentials.Certificate(cred_json)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            logger.info("Firebase başarıyla başlatıldı.")
            return db
        except Exception as e:
            logger.error(f"Firebase başlatılırken bir hata oluştu: {e}")
            logger.error("FIREBASE_SERVICE_ACCOUNT_JSON ortam değişkeninin doğru JSON formatında olduğundan emin olun.")
            return None
    return db

# --- Gemini Başlatma ---
gemini_model = None # Gemini modeli global olarak tanımlanacak

def initialize_gemini():
    """Gemini API'yi başlatır."""
    global gemini_model
    if gemini_model is None:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            # Metin tabanlı sorgular için uygun bir model seçin
            gemini_model = genai.GenerativeModel('gemini-1.5-flash')
            logger.info("Gemini API başarıyla başlatıldı.")
            return gemini_model
        except Exception as e:
            logger.error(f"Gemini API başlatılırken bir hata oluştu: {e}")
            return None
    return gemini_model

# --- Kullanıcı Kimlik Doğrulama Durumu ---
user_authenticated = {} # {user_id: True/False}

# /start komutu için işleyici fonksiyonu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kullanıcı /start komutunu gönderdiğinde mesaj gönderir ve kimlik doğrulama başlatır."""
    user = update.effective_user
    user_authenticated[user.id] = False # Başlangıçta kimliği doğrulanmamış
    await update.message.reply_html(
        f"Merhaba {user.mention_html()}! Ben hasta verileri botuyum. Lütfen devam etmek için şifreyi girin."
    )

# Şifre kontrolü ve kimlik doğrulama
async def authenticate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kullanıcının girdiği şifreyi kontrol eder."""
    user = update.effective_user
    text = update.message.text

    if text == BOT_PASSWORD:
        user_authenticated[user.id] = True
        await update.message.reply_text("Giriş başarılı! Şimdi hasta verilerini sorgulayabilirsiniz. Örneğin: 'Ayşe'nin gebelik durumu nedir?' veya '/hastalar'")
    else:
        await update.message.reply_text("Yanlış şifre. Lütfen tekrar deneyin.")

# Kimliği doğrulanmış kullanıcılar için genel mesaj işleyicisi (Şimdi Gemini ile)
async def handle_authenticated_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kimliği doğrulanmış kullanıcılardan gelen metin mesajlarını işler ve Gemini'ye iletir."""
    user_query = update.message.text
    gemini = initialize_gemini()
    db_client = initialize_firebase()

    if not gemini:
        await update.message.reply_text("Yapay zeka servisi başlatılamadı. Lütfen yöneticinizle iletişime geçin.")
        return
    if not db_client:
        await update.message.reply_text("Veritabanı bağlantısı kurulamadı. Lütfen yöneticinizle iletişime geçin.")
        return

    await update.message.reply_text("Sorgunuz işleniyor, lütfen bekleyin...")

    try:
        # Tüm hasta verilerini çek (büyük veri setleri için optimize edilebilir)
        docs = db_client.collection(FIRESTORE_COLLECTION_NAME).get()
        all_patient_data = []
        for doc in docs:
            all_patient_data.append(doc.to_dict())

        # Gemini'ye gönderilecek prompt'u oluştur
        data_string = ""
        for i, patient in enumerate(all_patient_data):
            data_string += f"Hasta {i+1}:\n"
            for key, value in patient.items():
                data_string += f"  {key}: {value}\n"
            data_string += "---\n"

        prompt = f"""
        Aşağıda hasta bilgilerini içeren bir veri kümesi bulunmaktadır.
        Her hasta, farklı alanlara (sütun başlıkları) sahip bir JSON nesnesi olarak temsil edilmektedir.
        Lütfen kullanıcının sorusunu bu verilere dayanarak cevaplayın.
        Eğer bir bilgi mevcut değilse veya soruyu cevaplamak için yeterli veri yoksa, bunu belirtin.
        Cevaplarınızı kısa, net ve anlaşılır tutun.

        Hasta Verileri:
        {data_string}

        Kullanıcının Sorusu: "{user_query}"

        Cevap:
        """

        response = gemini.generate_content(prompt)

        if response and response.candidates:
            await update.message.reply_text(response.candidates[0].content.parts[0].text)
        else:
            await update.message.reply_text("Üzgünüm, sorunuzu yanıtlayamadım. Lütfen daha açık bir ifade kullanın.")

    except Exception as e:
        logger.error(f"Gemini ile iletişimde veya veri işlemede hata oluştu: {e}")
        await update.message.reply_text("Üzgünüm, bir hata oluştu. Lütfen tekrar deneyin.")


# /hastalar komutu için işleyici fonksiyonu (kimlik doğrulaması gerektirir)
async def get_patients(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Firestore'dan hasta verilerini çeker ve gönderir."""
    user = update.effective_user

    if not user_authenticated.get(user.id):
        await update.message.reply_text("Bu komutu kullanmak için önce giriş yapmalısınız. Lütfen şifreyi girin.")
        return

    db_client = initialize_firebase()
    if not db_client:
        await update.message.reply_text("Veritabanı bağlantısı kurulamadı. Lütfen yöneticinizle iletişime geçin.")
        return

    try:
        docs = db_client.collection(FIRESTORE_COLLECTION_NAME).limit(5).get() # İlk 5 hastayı çek
        if not docs:
            await update.message.reply_text("Veritabanında hasta bilgisi bulunamadı.")
            return

        response_message = "İşte ilk 5 hasta bilgisi:\n\n"
        for doc in docs:
            data = doc.to_dict()
            # Her hastanın adını veya benzersiz bir tanımlayıcısını alın
            # Excel dosyanızdaki ilgili sütun adını buraya yazın, örneğin 'Hasta Adı'
            # ÖNEMLİ: Kendi Excel kolon başlığınıza göre burayı güncelleyin!
            hasta_adi = data.get('NAME', 'Bilinmeyen Hasta') # 'NAME' yerine kendi kolon adınızı yazın
            response_message += f"**Hasta Adı:** {hasta_adi}\n"
            # Diğer bilgileri de ekleyebilirsiniz, örneğin:
            # response_message += f"  Yumurta Sayısı: {data.get('Toplanan Yumurta Sayısı', 'Yok')}\n"
            # response_message += f"  Gebelik Durumu: {data.get('Gebelik', 'Yok')}\n"
            response_message += "--------------------\n"

        await update.message.reply_text(response_message)

    except Exception as e:
        logger.error(f"Hasta verileri çekilirken bir hata oluştu: {e}")
        await update.message.reply_text("Hasta verileri çekilirken bir hata oluştu. Lütfen tekrar deneyin.")

# Tüm metin mesajlarını işleyecek ana dağıtıcı (dispatcher) fonksiyonu
async def general_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Komut olmayan metin mesajlarını işler.
    Kullanıcının kimlik doğrulama durumuna göre farklı aksiyonlar alır.
    """
    user_id = update.effective_user.id

    if not user_authenticated.get(user_id, False):
        # Kullanıcı kimliği doğrulanmamışsa, şifre girişi olarak kabul et
        await authenticate(update, context)
    else:
        # Kullanıcı kimliği doğrulanmışsa, normal mesaj işleme (şimdi Gemini ile)
        await handle_authenticated_message(update, context)


# --- Flask Uygulaması ---
# Flask uygulamasını oluştur (main fonksiyonunun dışında global olarak tanımlandı)
app = Flask(__name__)

# Telegram bot uygulama nesnesi (global olarak tanımlanır)
# main() içinde oluşturulacak ve buraya atanacak
application_instance = None # application yerine application_instance kullandık

@app.route('/')
def hello():
    return "Telegram Hasta Botu çalışıyor!"

@app.route('/webhook', methods=['POST'])
async def webhook():
    """Telegram'dan gelen webhook güncellemelerini işler."""
    # Global application_instance'ı kullan
    if application_instance is None:
        logger.error("Telegram Application instance not initialized for webhook.")
        return "Error: Bot not initialized", 500

    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), application_instance.bot)
        await application_instance.process_update(update)
    return "ok"

# Ana fonksiyon
def main() -> None:
    """Botu başlatır."""
    global application_instance # Global değişkeni burada kullanacağımızı belirtiyoruz

    # Firebase'i başlat
    initialize_firebase()
    # Gemini'yi başlat
    initialize_gemini()

    # ApplicationBuilder ile bot uygulamasını oluştur
    application_instance = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Komut işleyicilerini ekleyin
    application_instance.add_handler(CommandHandler("start", start))
    application_instance.add_handler(CommandHandler("hastalar", get_patients))

    # Tüm komut olmayan metin mesajlarını işleyecek genel işleyici
    application_instance.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, general_text_handler))

    # Webhook URL'sini ayarla
    if WEBHOOK_URL:
        logger.info(f"Webhook URL'si ayarlanıyor: {WEBHOOK_URL}")
        application_instance.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="webhook", # Bu, WEBHOOK_URL'nin sonuna eklenecek yol
            webhook_url=WEBHOOK_URL + "/webhook" # Telegram'a bildirilecek tam URL
        )
        logger.info("Bot webhook modunda çalışıyor.")
    else:
        logger.warning("WEBHOOK_URL ortam değişkeni ayarlanmamış. Bot polling modunda başlatılıyor (sadece yerel test için).")
        application_instance.run_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Bot polling modunda çalışıyor.")

# Gunicorn'un Flask uygulamasını çalıştırması için ana giriş noktası
if __name__ == "__main__":
    # main() fonksiyonunu çağırarak botu başlat (webhook veya polling modunda)
    # Bu kısım, Gunicorn tarafından çağrıldığında Flask uygulamasının çalışmasını sağlar.
    # Eğer doğrudan 'python main.py' ile çalıştırırsanız, polling modu devreye girer.
    # Render'da 'gunicorn main:app' komutu ile çalıştırılacak.
    main()

