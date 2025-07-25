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
)

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
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
FIRESTORE_COLLECTION_NAME = 'hasta_bilgileri'
BOT_PASSWORD = os.getenv("BOT_PASSWORD", "sifre123")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Arka plan çalışanı için PORT ve WEBHOOK_URL artık kullanılmayacak

if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN ortam değişkeni ayarlanmamış. Lütfen .env dosyasını kontrol edin.")
    exit(1)
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY ortam değişkeni ayarlanmamış. Lütfen .env dosyasını kontrol edin ve bir API anahtarı alın.")
    exit(1)
if not FIREBASE_SERVICE_ACCOUNT_JSON:
    logger.error("FIREBASE_SERVICE_ACCOUNT_JSON ortam değişkeni ayarlanmamış. Lütfen Render'da Firebase servis hesabı JSON içeriğini ayarlayın.")
    exit(1)

# --- Firebase Başlatma ---
db = None

def initialize_firebase():
    """Firebase Admin SDK'yı başlatır ve Firestore istemcisini döndürür."""
    global db
    if db is None:
        try:
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
gemini_model = None

def initialize_gemini():
    """Gemini API'yi başlatır."""
    global gemini_model
    if gemini_model is None:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            gemini_model = genai.GenerativeModel('gemini-1.5-flash')
            logger.info("Gemini API başarıyla başlatıldı.")
            return gemini_model
        except Exception as e:
            logger.error(f"Gemini API başlatılırken bir hata oluştu: {e}")
            return None
    return gemini_model

# --- Kullanıcı Kimlik Doğrulama Durumu ---
user_authenticated = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kullanıcı /start komutunu gönderdiğinde mesaj gönderir ve kimlik doğrulama başlatır."""
    user = update.effective_user
    user_authenticated[user.id] = False
    await update.message.reply_html(
        f"Merhaba {user.mention_html()}! Ben hasta verileri botuyum. Lütfen devam etmek için şifreyi girin."
    )

async def authenticate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kullanıcının girdiği şifreyi kontrol eder."""
    user = update.effective_user
    text = update.message.text

    if text == BOT_PASSWORD:
        user_authenticated[user.id] = True
        await update.message.reply_text("Giriş başarılı! Şimdi hasta verilerini sorgulayabilirsiniz. Örneğin: 'Ayşe'nin gebelik durumu nedir?' veya '/hastalar'")
    else:
        await update.message.reply_text("Yanlış şifre. Lütfen tekrar deneyin.")

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
        docs = db_client.collection(FIRESTORE_COLLECTION_NAME).get()
        all_patient_data = []
        for doc in docs:
            all_patient_data.append(doc.to_dict())

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
        docs = db_client.collection(FIRESTORE_COLLECTION_NAME).limit(5).get()
        if not docs:
            await update.message.reply_text("Veritabanında hasta bilgisi bulunamadı.")
            return

        response_message = "İşte ilk 5 hasta bilgisi:\n\n"
        for doc in docs:
            data = doc.to_dict()
            hasta_adi = data.get('NAME', 'Bilinmeyen Hasta') # Kendi Excel kolon başlığınıza göre burayı güncelleyin!
            response_message += f"**Hasta Adı:** {hasta_adi}\n"
            # Diğer bilgileri de ekleyebilirsiniz, örneğin:
            # response_message += f"  Yumurta Sayısı: {data.get('Toplanan Yumurta Sayısı', 'Yok')}\n"
            # response_message += f"  Gebelik Durumu: {data.get('Gebelik', 'Yok')}\n"
            response_message += "--------------------\n"

        await update.message.reply_text(response_message)

    except Exception as e:
        logger.error(f"Hasta verileri çekilirken bir hata oluştu: {e}")
        await update.message.reply_text("Hasta verileri çekilirken bir hata oluştu. Lütfen tekrar deneyin.")

async def general_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Komut olmayan metin mesajlarını işler.
    Kullanıcının kimlik doğrulama durumuna göre farklı aksiyonlar alır.
    """
    user_id = update.effective_user.id

    if not user_authenticated.get(user_id, False):
        await authenticate(update, context)
    else:
        await handle_authenticated_message(update, context)


# Ana fonksiyon (Polling modunda çalışacak)
def main() -> None:
    global application # Global application nesnesini burada kullanacağımızı belirtiyoruz

    # Firebase'i başlat
    initialize_firebase()
    # Gemini'yi başlat
    initialize_gemini()

    # ApplicationBuilder ile bot uygulamasını oluştur
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Komut işleyicilerini ekleyin
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("hastalar", get_patients))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, general_text_handler))

    # Arka plan çalışanı için sadece polling modunda çalıştırıyoruz.
    logger.info("Bot polling modunda başlatılıyor (Arka plan çalışanı).")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot durduruldu.")

if __name__ == "__main__":
    main()

