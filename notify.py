from datetime import datetime
from supabase import create_client
import os

url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_API_KEY"]
supabase = create_client(url, key)

now = datetime.now().isoformat()

# INSERT ping
supabase.table("heartbeat").insert({
    "executed_at": now,
    "note": "Daily GitHub Actions ping"
}).execute()
