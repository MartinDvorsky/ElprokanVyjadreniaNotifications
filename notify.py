import os
from datetime import date, timedelta
from supabase import create_client

# 🔐 Načíta tajné premenné z GitHub Secrets
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_API_KEY")

# 🔗 Pripojenie na Supabase
supabase = create_client(url, key)

# 📅 Vygeneruj dnešný a notifikačné dátumy
today = date.today()
first_notification = today + timedelta(days=30)
second_notification = today + timedelta(days=60)

# 📄 Údaje pre vloženie
data = {
    "znacka": "98765/TEST",
    "nazovstavby": "Testovacia stavba",
    "created_at": today.isoformat(),
    "firstnotification": first_notification.isoformat(),
    "secondnotification": second_notification.isoformat(),
    "test": True,
    "done": False,
    "notifications_enabled": True
}

# 📨 INSERT do databázy
response = supabase.table("notifications").insert(data).execute()

print("✅ Záznam vložený:")
print(response.data)
