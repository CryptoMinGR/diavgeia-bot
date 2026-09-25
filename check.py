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
    return "Diavgeia Bot (with Newton Alerts) is running 24/7 non-stop!"

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# ΡΟΗ 1: Αποφάσεις κλιμακίων ελέγχου ΓΓΑ
FEED_AUDITS = 'https://diavgeia.gov.gr/luminapi/api/feed/rss?q=q%3A%5B%22%CE%A3%CF%85%CE%B3%CE%BA%CF%81%CF%8C%CF%84%CE%B7%CF%83%CE%B7%22%2C%22%CF%84%CF%81%CE%B9%CE%BC%CE%B5%CE%BB%CE%BF%CF%8D%CF%82%22%2C%22%CE%BA%CE%BB%CE%B9%CE%BC%CE%B1%CE%BA%CE%AF%CE%BF%CF%85%22%5D%20AND%20decisionType%3A%22%CE%9B%CE%9F%CE%99%CE%A0%CE%95%CE%A3%20%CE%91%CE%A4%CE%9F%CE%9C%CE%99%CE%9A%CE%95%CE%A3%20%CE%94%CE%99%CE%9F%CE%99%CE%9A%CE%97%CE%A4%CE%99%CE%9A%CE%95%CE%A3%20%CE%A0%CE%A1%CE%91%CE%9E%CE%95%CE%99%CE%A3%22%20AND%20organizationUid%3A%22100081880%22%20AND%20signerUid%3A%5B%22100035856%22%2C%22100046000%22%5D'

# ΡΟΗ 2: Οποιαδήποτε απόφαση στη Διαύγεια για ΦΦ73 ή ΝΕΥΤΩΝ
FEED_NEWTON = 'https://diavgeia.gov.gr/luminapi/api/feed/rss?q=q%3A%5B%22%CE%A6%CE%A673%22%2C%22%CE%9D%CE%95%CE%A5%CE%A4%CE%A9%CE%9D%22%5D'

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
    entities = []
    seen_names = set()
    is_newton_targeted = False

    # 1. Έλεγχος αν αναφέρεται συγκεκριμένο σωματείο/ένωση στον τίτλο
    match_title = re.search(r'(?:ΣΤΗΝ|ΣΤΟ|ΣΤΟΝ|ΣΤΑ)\s+([^()]+)', title, re.IGNORECASE)
    if match_title:
        candidate = " ".join(match_title.group(1).split()).strip()
        if len(candidate) > 4 and "ΑΘΛΗΤΙΚΑ ΣΩΜΑΤΕΙΑ" not in candidate.upper():
            entities.append(candidate)
            seen_names.add(candidate.upper())

    if "ΝΕΥΤΩΝ" in title.upper() or "ΦΦ73" in title.upper():
        is_newton_targeted = True

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
                upper_pdf = full_text.upper()

                if "ΝΕΥΤΩΝ" in upper_pdf or "ΦΦ73" in upper_pdf:
                    is_newton_targeted = True

                # Εντοπισμός σωματείων με ανάγνωση των γραμμών πριν τον κωδικό τους (π.χ. (ΚΓ74), (ΦΦ73))
                lines = [l.strip() for l in full_text.split('\n')]
                for i, l in enumerate(lines):
                    m = re.search(r'\(([A-ZΑ-Ω0-9]{2,6})\)$', l)
                    if m:
                        code = m.group(1)
                        name_parts = []
                        for prev_idx in range(i-1, max(-1, i-4), -1):
                            prev_l = lines[prev_idx]
                            if any(skip in prev_l.upper() for skip in ['ΑΘΛΗΤΙΣΜΟΥ', 'ΥΠΑΛΛΗΛΩΝ', 'ΚΛΑΔΟΣ', 'ΔΙΕΥΘΥΝΣΗ', 'ΦΟΡΕΑΣ', 'ΗΜΕΡΟΜΗΝΙΑ', 'ΚΛΙΜΑΚΙΟ', 'ΕΛΕΓΧ']):
                                break
                            if prev_l:
                                name_parts.insert(0, prev_l)
                        if name_parts:
                            clean_name = " ".join(name_parts)
                            entry = f"{clean_name} ({code})"
                            if clean_name.upper() not in seen_names and len(clean_name) > 3:
                                entities.append(entry)
                                seen_names.add(clean_name.upper())

                # Εφεδρικός καθαρός έλεγχος αν δεν βρέθηκαν κωδικοί
                if not entities:
                    backup_pattern = r'(?:\bΑ\.?\s*Σ\.?|\bΑ\.?\s*Ο\.?|\bΑΘΛΗΤΙΚΟΣ\s+ΣΥΛΛΟΓΟΣ|\bΑΘΛΗΤΙΚΟΣ\s+ΟΜΙΛΟΣ|\bΟΜΙΛΟΣ\s+ΑΝΤΙΣΦΑΙΡΙΣΗΣ|\bΕΝΩΣΗ)\s+["«]?[A-ZΑ-ΩΆΈΉΊΌΎΏ\s\d\-]+["»]?'
                    found_backup = re.findall(backup_pattern, full_text)
                    blacklist = ["ΑΘΛΗΤΙΚΑ ΣΩΜΑΤΕΙΑ", "ΑΘΛΗΤΙΚΩΝ ΦΟΡΕΩΝ", "ΣΥΓΚΡΟΤΗΣΗ", "ΚΛΙΜΑΚΙ", "ΥΠΟΥΡΓΕΙΟ", "ΓΕΝΙΚΗ ΓΡΑΜΜΑΤΕΙΑ"]
                    for fb in found_backup:
                        c_name = " ".join(fb.split()).strip().strip('"«»')
                        if 5 < len(c_name) < 55 and not any(b in c_name.upper() for b in blacklist):
                            if c_name.upper() not in seen_names:
                                entities.append(c_name)
                                seen_names.add(c_name.upper())

        except Exception as e:
            print("PDF reading error:", e)

    return entities, is_newton_targeted

def fetch_feed_items(url):
    try:
        resp = requests.get(url, timeout=15)
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

def monitor_loop():
    print("Ξεκίνησε η παρακολούθηση...")
    seen_guids = set()

    for feed in [FEED_AUDITS, FEED_NEWTON]:
        items = fetch_feed_items(feed)
        for it in items:
            seen_guids.add(it["guid"])
    print(f"Αρχικοποιήθηκε με {len(seen_guids)} υπάρχουσες αναρτήσεις.")

    while True:
        try:
            time.sleep(CHECK_INTERVAL)

            # --- ΡΟΗ 1: ΑΠΟΦΑΣΕΙΣ ΓΓΑ ---
            audit_items = fetch_feed_items(FEED_AUDITS)
            for it in audit_items:
                if it["guid"] not in seen_guids:
                    seen_guids.add(it["guid"])
                    title = it["title"]
                    link = it["link"]
                    upper_title = title.upper()

                    # Έλεγχος αν πρόκειται για Απόφαση Σύστασης/Συγκρότησης Κλιμακίου Ελέγχου
                    is_audit = ("ΣΥΓΚΡΟΤΗΣ" in upper_title and "ΚΛΙΜΑΚΙ" in upper_title) or \
                               ("ΕΛΕΓΧ" in upper_title and "ΚΛΙΜΑΚΙ" in upper_title and "ΑΝΑΚΛΗΣ" not in upper_title)

                    if is_audit:
                        header = "🚨 <b>ΑΠΟΦΑΣΗ ΕΛΕΓΧΟΥ (ΤΡΙΜΕΛΕΣ ΚΛΙΜΑΚΙΟ)</b>"
                        entities, is_newton = extract_audited_entities(link, title)
                        
                        newton_alert = ""
                        if is_newton:
                            newton_alert = "\n\n🚨🚨 <b>ΠΡΟΣΟΧΗ: ΕΝΤΟΠΙΣΤΗΚΕ ΕΛΕΓΧΟΣ ΣΤΟ ΣΩΜΑΤΕΙΟ «ΝΕΥΤΩΝ» (ΦΦ73)!</b> 🚨🚨"
                        
                        if entities:
                            list_text = "\n".join([f"• <b>{e}</b>" for e in entities])
                            audit_info = f"\n\n🏢 <b>ΠΟΙΟΣ ΕΛΕΓΧΕΤΑΙ:</b>\n{list_text}"
                        else:
                            audit_info = "\n\n🏢 <b>ΠΟΙΟΣ ΕΛΕΓΧΕΤΑΙ:</b>\n• <i>Δεν αναφέρονται συγκεκριμένα ονόματα (δείτε το PDF)</i>"

                        msg = (
                            f"{header}\n\n"
                            f"📋 <b>Θέμα:</b> {title}"
                            f"{newton_alert}"
                            f"{audit_info}\n\n"
                            f"🔗 <a href='{link}'>Πατήστε εδώ για προβολή</a>"
                        )
                    else:
                        # ΧΩΡΙΣ κόκκινο λαμπάκι για τις απλές αποφάσεις (π.χ. ανακλήσεις)
                        header = "📄 <b>ΝΕΑ ΑΝΑΡΤΗΣΗ ΣΤΗ ΔΙΑΥΓΕΙΑ</b>"
                        msg = (
                            f"{header}\n\n"
                            f"📋 <b>Θέμα:</b> {title}\n\n"
                            f"🔗 <a href='{link}'>Πατήστε εδώ για προβολή</a>"
                        )

                    send_telegram(msg)

            # --- ΡΟΗ 2: ΑΠΟΦΑΣΕΙΣ ΓΙΑ ΦΦ73 / ΝΕΥΤΩΝ ---
            newton_items = fetch_feed_items(FEED_NEWTON)
            for it in newton_items:
                if it["guid"] not in seen_guids:
                    seen_guids.add(it["guid"])
                    title = it["title"]
                    link = it["link"]

                    msg = (
                        f"⭐ <b>ΕΙΔΙΚΗ ΕΝΗΜΕΡΩΣΗ: ΣΩΜΑΤΕΙΟ «ΝΕΥΤΩΝ» (ΦΦ73)</b>\n\n"
                        f"📋 <b>Θέμα:</b> {title}\n\n"
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
