import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
import os

# --- YAPILANDIRMA AYARLARI ---
# 1. Firebase Servis Hesabı Anahtarınızın Yolu
#    Bu JSON dosyasını Firebase konsolundan indirdiniz.
#    Dosyayı bu betiğin çalıştığı dizine yerleştirin veya tam yolunu belirtin.
#    Örnek: 'C:/Users/KullaniciAdiniz/Downloads/serviceAccountKey.json'
SERVICE_ACCOUNT_KEY_PATH = 'serviceAccountKey.json'

# 2. Excel Dosyanızın Yolu
#    Hasta datalarınızın olduğu Excel dosyasının tam yolu.
#    Örnek: 'C:/Users/KullaniciAdiniz/Belgelerim/hasta_datalari.xlsx'
EXCEL_FILE_PATH = 'data.xlsx'

# 3. Firestore Koleksiyon Adı
#    Verilerin aktarılacağı Firestore koleksiyonunun adı.
#    Örnek: 'hasta_bilgileri'
FIRESTORE_COLLECTION_NAME = 'hasta_bilgileri'
# -----------------------------

def initialize_firebase():
    """Firebase Admin SDK'yı başlatır."""
    if not os.path.exists(SERVICE_ACCOUNT_KEY_PATH):
        print(f"Hata: Firebase servis hesabı anahtar dosyası bulunamadı: {SERVICE_ACCOUNT_KEY_PATH}")
        print("Lütfen Firebase konsolundan 'serviceAccountKey.json' dosyasını indirin ve doğru yolu belirtin.")
        return None

    try:
        cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("Firebase başarıyla başlatıldı.")
        return db
    except Exception as e:
        print(f"Firebase başlatılırken bir hata oluştu: {e}")
        return None

def read_excel_data(file_path):
    """Excel dosyasını okur ve bir Pandas DataFrame döndürür."""
    try:
        # header=1 demek, 2. satırı başlık olarak kullan (Python'da indeks 0'dan başlar)
        df = pd.read_excel(file_path, header=1)
        print(f"'{file_path}' Excel dosyası başarıyla okundu. Toplam {len(df)} satır.")
        return df
    except FileNotFoundError:
        print(f"Hata: Excel dosyası bulunamadı: {file_path}")
        return None
    except Exception as e:
        print(f"Excel dosyası okunurken bir hata oluştu: {e}")
        return None

def upload_to_firestore(db_client, dataframe, collection_name):
    """DataFrame'deki verileri Firestore'a yükler."""
    print(f"Veriler '{collection_name}' koleksiyonuna aktarılıyor...")
    success_count = 0
    fail_count = 0

    for index, row in dataframe.iterrows():
        # Pandas DataFrame satırını bir Python sözlüğüne dönüştürür.
        # NaN (Not a Number) değerleri None'a çevirerek Firestore'un kabul etmesini sağlar.
        # Firestore, None değerlerini null olarak kaydeder.
        data = row.where(pd.notnull(row), None).to_dict()

        try:
            # Her satırı yeni bir belge olarak Firestore'a ekler.
            # Firestore otomatik olarak benzersiz bir belge ID'si oluşturacaktır.
            doc_ref = db_client.collection(collection_name).add(data)
            print(f"Satır {index+1} aktarıldı. Belge ID: {doc_ref[1].id}")
            success_count += 1
        except Exception as e:
            print(f"Hata: Satır {index+1} aktarılırken bir hata oluştu: {e} - Veri: {data}")
            fail_count += 1

    print("\n--- Veri Aktarımı Tamamlandı ---")
    print(f"Başarıyla aktarılan belge sayısı: {success_count}")
    print(f"Hata oluşan belge sayısı: {fail_count}")
    print(f"Firestore'daki '{collection_name}' koleksiyonunuzu kontrol edebilirsiniz.")

if __name__ == "__main__":
    db = initialize_firebase()
    if db:
        df = read_excel_data(EXCEL_FILE_PATH)
        if df is not None:
            upload_to_firestore(db, df, FIRESTORE_COLLECTION_NAME)

