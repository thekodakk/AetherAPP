# AetherAPP

Flask, Socket.IO ve pywebview tabanlı mesajlaşma uygulaması.

## Çalıştırma

Python 3.10+ ile `python -m venv .venv` oluşturun, ortamı etkinleştirin ve
`pip install -r requirements.txt` çalıştırın. `.env.example` dosyasını `.env`
olarak kopyalayıp kendinize ait SMTP ayarlarını ve rastgele bir SECRET_KEY girin.
Masaüstü arayüzünü açmak için `python app.py` kullanın.

`versions/aetherAPP-2` daha eski, farklı kaynak sürümünü korur; bu sürümü kendi
klasöründe, kökteki gereksinimleri yüklediğiniz ortamla çalıştırabilirsiniz.
Veritabanı, yüklenen dosyalar ve yerel kimlik bilgileri depoya dahil edilmez.
