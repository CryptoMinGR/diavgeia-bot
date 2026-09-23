import os
import time
import requests
import xml.etree.ElementTree as ET

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FEED_URL = 'https://diavgeia.gov.gr/luminapi/api/feed/rss?q=q%3A%5B%22%CE%A3%CF%85%CE%B3%CE%BA%CF%81%CF%8C%CF%84%CE%B7%CF%83%CE%B7%22%2C%22%CF%84%CF%81%CE%B9%CE%BC%CE%B5%CE%BB%CE%BF%CF%8D%CF%82%22%2C%22%CE%BA%CE%BB%CE%B9%CE%BC%CE%B1%CE%BA%CE%AF%CE%BF%CF%85%22%5D%20AND%20decisionType%3A%22%CE%9B%CE%9F%CE%99%CE%A0%CE%95%CE%A3%20%CE%91%CE%A4%CE%9F%CE%9C%CE%99%CE%9A%CE%95%CE%A3%20%CE%94%CE%99%CE%9F%CE%99%CE%9A%CE%97%CE%A4%CE%99%CE%9A%CE%95%CE%A3%20%CE%A0%CE%A1%CE%91%CE%9E%CE%95%CE%99%CE%A3%22%20AND%20organizationUid%3A%22100081880%22%20AND%20signerUid%3A%5B%22100035856%22%2C%22100046000%22%5D'
STATE_FILE = "seen_guids.txt"

# Εκτελείται για περίπου 9 λεπτά, κάνοντας έλεγχο κάθε 60 δευτερόλεπτα (9 επαναλήψεις)
TOTAL_CYCLES = 9
SLEEP_SECONDS = 60

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

def fetch_items():
    try:
        resp = requests.get(FEED_URL, timeout=15)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            items = []
            for item in root.findall(".//item"):
                title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                guid = item.find("guid").text if item.find("guid") is not None else link
                items.append({"title": title, "link": link, "guid": guid})
            return items
    except Exception as e:
        print("Fetch error:", e)
    return []

def main():
    seen = set()
    first_run = not os.path.exists(STATE_FILE)
    if not first_run:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            seen = set(line.strip() for line in f if line.strip())

    print(f"Εκκίνηση κύκλου. Υπάρχουσες αποφάσεις στη μνήμη: {len(seen)}")

    for cycle in range(TOTAL_CYCLES):
        print(f"Έλεγχος {cycle + 1}/{TOTAL_CYCLES}...")
        items = fetch_items()
        
        for it in items:
            if not first_run and it["guid"] not in seen:
                print(f"ΝΕΑ ΑΝΑΡΤΗΣΗ: {it['title']}")
                msg = (
                    f"🚨 <b>ΝΕΑ ΑΝΑΡΤΗΣΗ ΣΤΗ ΔΙΑΥΓΕΙΑ!</b>\n\n"
                    f"📋 <b>Θέμα:</b> {it['title']}\n\n"
                    f"🔗 <a href='{it['link']}'>Πατήστε εδώ για προβολή</a>"
                )
                send_telegram(msg)
                seen.add(it["guid"])
            elif first_run:
                seen.add(it["guid"])

        first_run = False

        # Αποθήκευση κατάστασης στο αρχείο
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            for g in seen:
                f.write(f"{g}\n")

        # Αν δεν είναι ο τελευταίος κύκλος, περίμενε 1 λεπτό
        if cycle < TOTAL_CYCLES - 1:
            time.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    main()
