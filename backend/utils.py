# utils.py
from datetime import datetime, timedelta
import pytz

def get_gmt_window(ist_date_str: str):
    """Convert IST date to GMT window (24 hours from midnight IST)."""
    ist_tz = pytz.timezone('Asia/Kolkata')
    gmt_tz = pytz.UTC
    ist_date = datetime.strptime(ist_date_str, "%Y-%m-%d")
    ist_start = ist_tz.localize(ist_date)  # Midnight IST on the given date
    gmt_start = ist_start.astimezone(gmt_tz)  # Convert to GMT
    gmt_end = gmt_start + timedelta(hours=24)  # 24 hours later in GMT
    return gmt_start, gmt_end
