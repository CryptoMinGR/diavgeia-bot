import os
import time
import threading
import requests
import xml.etree.ElementTree as ET
from flask import Flask

# Μικρός web server για να κρατάει την υπηρεσία ενεργή 24/7 στο Cloud
app = Flask(__name__)

@app.route('/')
def home():
    return "Diavgeia Bot is running 24/7 non-stop!"

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FEED_URL = 'https://diavgeia.gov.gr/luminapi/api/feed/rss?q=q%3A%5B%22%CE%A3%CF%85%CE%B3%CE%BA%CF%81%CF%8C%CF%84%CE%B7%CF%83%CE%B7%22%2C%22%CF%84%CF%81%CE%B9%CE%BC%CE%B5%CE%BB%CE%BF%CF%8D%CF%82%22%2C%22%CE%BA%CE%BB%CE%B9%CE%BC%CE%B1%CE%BA%CE%AF%CE%BF%CF%85%22%5D%20AND%20decisionType%3A%22%CE%9B%CE%9F%CE%99%CE%A0%CE%95%CE%A3%20%CE%91%CE%A4%CE%9F%CE%9C%CE%99%CE%9A%CE%95%CE%A3%20%CE%94%CE%99%CE%9F%CE%99%CE%9A%CE%97%CE%A4%CE%99%CE%9A%CE%95%CE%A3%20%CE%A0%CE%A1%CE%91%CE%9E%CE%95%CE%99%CE%A3%22%20AND%20organizationUid%3A%22100081880%22%20AND%20signerUid%3A%5B%22100035856%22%2C%22100046000%22%5D'

# ΕΛΕΓΧΟΣ ΑΝΑ 30 ΔΕΥΤΕΡΟΛΕΠΤΑ
CHECK_INTERVAL = 30

def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

def monitor_loop():
    print("Ξεκίνησε η ασταμάτητη παρακολούθηση της Διαύγειας (κάθε 30s)...")
    seen_guids = set()

    # Αρχική ανάκτηση για να μην στείλει τα ήδη υπάρχοντα
    try:
        resp = requests.get(FEED_URL, timeout=15)
        root = ET.fromstring(resp.content)
        for item in root.findall(".//item"):
            guid = item.find("guid").text if item.find("guid") is not None else item.find("link").text
            if guid:
                seen_guids.add(guid)
        print(f"Αρχικοποιήθηκε με {len(seen_guids)} αποφάσεις.")
    except Exception as e:
        print("Init error:", e)

    while True:
        try:
            time.sleep(CHECK_INTERVAL)
            resp = requests.get(FEED_URL, timeout=15)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item"):
                    guid = item.find("guid").text if item.find("guid") is not None else item.find("link").text
                    title = item.find("title").text if item.find("title") is not None else ""
                    link = item.find("link").text if item.find("link") is not None else guid
                    
                    if guid and guid not in seen_guids:
                        seen_guids.add(guid)
                        msg = (
                            f"🚨 <b>ΝΕΑ ΑΝΑΡΤΗΣΗ ΣΤΗ ΔΙΑΥΓΕΙΑ!</b>\n\n"
                            f"📋 <b>Θέμα:</b> {title}\n\n"
                            f"🔗 <a href='{link}'>Πατήστε εδώ για προβολή</a>"
                        )
                        print(f"Νέα απόφαση: {title}")
                        send_telegram(msg)
        except Exception as e:
            print("Loop error:", e)

# Ξεκινάει το loop στο παρασκήνιο
t = threading.Thread(target=monitor_loop, daemon=True)
t.start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
