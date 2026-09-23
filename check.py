import os
import re
import io
import time
import threading
import requests
import xml.etree.ElementTree as ET
from pypdf import PdfReader
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "Diavgeia Bot is running 24/7 non-stop!"

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FEED_URL = 'https://diavgeia.gov.gr/luminapi/api/feed/rss?q=q%3A%5B%22%CE%A3%CF%85%CE%B3%CE%BA%CF%81%CF%8C%CF%84%CE%B7%CF%83%CE%B7%22%2C%22%CF%84%CF%81%CE%B9%CE%BC%CE%B5%CE%BB%CE%BF%CF%8D%CF%82%22%2C%22%CE%BA%CE%BB%CE%B9%CE%BC%CE%B1%CE%BA%CE%AF%CE%BF%CF%85%22%5D%20AND%20decisionType%3A%22%CE%9B%CE%9F%CE%99%CE%A0%CE%95%CE%A3%20%CE%91%CE%A4%CE%9F%CE%9C%CE%99%CE%9A%CE%95%CE%A3%20%CE%94%CE%99%CE%9F%CE%99%CE%9A%CE%97%CE%A4%CE%99%CE%9A%CE%95%CE%A3%20%CE%A0%CE%A1%CE%91%CE%9E%CE%95%CE%99%CE%A3%22%20AND%20organizationUid%3A%22100081880%22%20AND%20signerUid%3A%5B%22100035856%22%2C%22100046000%22%5D'

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

def extract_audited_entities(link, title):
    entities = set()
    
    # 1. Αναζήτηση στον τίτλο (π.χ. "...ΣΤΗΝ ΕΝΩΣΗ ΠΟΔΟΣΦΑΙΡΙΚΩΝ ΣΩΜΑΤΕΙΩΝ...")
    match_title = re.search(r'(?:ΣΤΗΝ|ΣΤΟ|ΣΤΟΝ|ΣΤΑ)\s+([^()]+)', title, re.IGNORECASE)
    if match_title:
        candidate = match_title.group(1).strip()
        if len(candidate) > 4 and "ΑΘΛΗΤΙΚΑ ΣΩΜΑΤΕΙΑ" not in candidate.upper():
            entities.add(candidate)

    # 2. Ανάγνωση του επίσημου PDF της απόφασης
    ada_match = re.search(r'view/([^/]+)', link)
    if ada_match:
        ada = ada_match.group(1)
        pdf_url = f"https://diavgeia.gov.gr/doc/{ada}"
        try:
            resp = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if resp.status_code == 200:
                reader = PdfReader(io.BytesIO(resp.content))
                full_text = "\n".join([page.extract_text() or "" for page in reader.pages])
                
                # Αναζήτηση σωματείων με προθέματα Α.Σ., Α.Ο., Ένωση, Όμιλος κ.λπ.
                pattern = r'(?:Α\.?\s*Σ\.?|Α\.?\s*Ο\.?|Α\.?\s*Π\.?\s*Σ\.?|Α\.?\s*Ε\.?|Γ\.?\s*Σ\.?|ΑΘΛΗΤΙΚ\w+|ΝΑΥΤΙΚ\w+|ΟΜΙΛ\w+|ΣΥΛΛΟΓ\w+|ΕΝΩΣ\w+)\s+["«]?[A-ZΑ-ΩΆΈΉΊΌΎΏ\s\d\-]+["»]?'
                found = re.findall(pattern, full_text)
                for f in found:
                    cleaned = f.strip().strip('"«»').strip()
                    if 5 < len(cleaned) < 60 and not any(skip in cleaned.upper() for skip in ["ΑΘΛΗΤΙΚΑ ΣΩΜΑΤΕΙΑ", "ΑΘΛΗΤΙΣΜΟΥ", "ΓΕΝΙΚΗ ΓΡΑΜΜΑΤΕΙΑ", "ΥΠΟΥΡΓΕΙΟ"]):
                        entities.add(cleaned)
        except Exception as e:
            print("PDF reading error:", e)
            
    return list(entities)

def monitor_loop():
    print("Ξεκίνησε η παρακολούθηση όλων των αποφάσεων...")
    seen_guids = set()

    # Αρχικοποίηση
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
                        upper_title = title.upper()
                        
                        # Έλεγχος αν πρόκειται για απόφαση ελέγχου / κλιμακίου
                        is_audit = ("ΕΛΕΓΧ" in upper_title or "ΚΛΙΜΑΚΙ" in upper_title) and ("ΑΝΑΚΛΗΣ" not in upper_title)
                        
                        audit_info = ""
                        if is_audit:
                            print(f"Εντοπίστηκε απόφαση ελέγχου: {title}")
                            entities = extract_audited_entities(link, title)
                            if entities:
                                list_text = "\n".join([f"• <b>{ent}</b>" for ent in entities])
                                audit_info = f"\n\n🏢 <b>ΠΟΙΟΣ ΕΛΕΓΧΕΤΑΙ:</b>\n{list_text}"
                            else:
                                audit_info = "\n\n🏢 <b>ΠΟΙΟΣ ΕΛΕΓΧΕΤΑΙ:</b>\n• <i>Δεν αναφέρονται συγκεκριμένα ονόματα στον τίτλο (δείτε το PDF)</i>"
                        
                        # Σύνταξη ενιαίου μηνύματος
                        msg = (
                            f"🚨 <b>ΝΕΑ ΑΝΑΡΤΗΣΗ ΣΤΗ ΔΙΑΥΓΕΙΑ!</b>\n\n"
                            f"📋 <b>Θέμα:</b> {title}"
                            f"{audit_info}\n\n"
                            f"🔗 <a href='{link}'>Πατήστε εδώ για προβολή</a>"
                        )
                        
                        send_telegram(msg)
        except Exception as e:
            print("Loop error:", e)

t = threading.Thread(target=monitor_loop, daemon=True)
t.start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
