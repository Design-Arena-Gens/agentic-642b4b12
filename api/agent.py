from http.server import BaseHTTPRequestHandler
import json
import re
from urllib.parse import urlencode, quote_plus
from datetime import datetime, timedelta
try:
    from dateutil import parser as date_parser
except Exception:
    date_parser = None

# Basic in-repo contacts. You can customize this by editing data/contacts.json
DEFAULT_CONTACTS = {
    "daddy": "+18005551212",
    "mom": "+18005551337",
    "mother": "+18005551337",
    "dad": "+18005551212",
    "office": "+18005559876",
}


def load_contacts():
    try:
        with open("data/contacts.json", "r", encoding="utf-8") as f:
            out = json.load(f)
            # Lowercase keys for fuzzy match convenience
            return {k.lower(): v for k, v in out.items()}
    except Exception:
        return DEFAULT_CONTACTS


CONTACTS = load_contacts()


def parse_datetime(text: str):
    if date_parser is None:
        return None
    try:
        # Assume current year when not specified; don't require timezone
        dt = date_parser.parse(text, fuzzy=True, dayfirst=False)
        return dt
    except Exception:
        return None


class handler(BaseHTTPRequestHandler):
    def _set_headers(self, status=200, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(204)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            payload = json.loads(body.decode("utf-8"))
            query = (payload.get("query") or "").strip()
            if not query:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Missing query"}).encode("utf-8"))
                return

            result = route_intent(query)
            self._set_headers(200)
            self.wfile.write(json.dumps(result).encode("utf-8"))
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))


def route_intent(query: str):
    q = query.lower().strip()

    # CALL intent: "call <name>"
    m_call = re.search(r"\bcall\s+([a-z\s]+)\b", q)
    if m_call:
        name = m_call.group(1).strip()
        # Remove common fillers like 'my', 'the'
        name = re.sub(r"\b(my|the|to)\b", "", name).strip()
        tel = CONTACTS.get(name) or CONTACTS.get(name.replace(" ", ""))
        steps = [
            "Understand contact name from your request",
            "Look up the phone number in your contacts",
            "Initiate call via the device dialer"
        ]
        if tel:
            tel_link = f"tel:{tel}"
            return {
                "intent": "call",
                "contactName": name,
                "telLink": tel_link,
                "steps": steps,
                "speechResponse": f"Calling {name} on {tel}."
            }
        else:
            return {
                "intent": "call",
                "contactName": name,
                "steps": steps + ["Contact not found; ask user to confirm number"],
                "speechResponse": f"I couldn't find {name} in your contacts. Please provide the number.",
            }

    # MAPS intent: open maps and search / start directions
    # Examples: "open google map and search sadar bazaar chatgali and start the direction"
    # We'll extract destination text after keywords 'to' or 'search'
    if "google map" in q or "google maps" in q or q.startswith("maps") or q.startswith("open map"):
        # try to find a phrase after 'to' or 'search'
        dest = None
        m_to = re.search(r"\b(?:to|search|for)\s+([^,]+)$", q)
        if m_to:
            dest = m_to.group(1).strip()
        # fallback: remove control words and use remainder
        if not dest:
            dest = re.sub(r"(open|google|maps?|and|start|the|direction|directions)", " ", q)
            dest = re.sub(r"\s+", " ", dest).strip()
        if dest:
            maps_url = build_google_maps_directions_url(destination=dest)
            steps = [
                "Parse destination from your request",
                "Open Google Maps with navigation",
                "Start directions from your current location"
            ]
            return {
                "intent": "maps",
                "destination": dest,
                "mapsUrl": maps_url,
                "steps": steps,
                "speechResponse": f"Opening directions to {dest} in Google Maps."
            }
        else:
            return {
                "intent": "maps",
                "steps": ["Could not determine destination"],
                "speechResponse": "I couldn't determine the destination. Please say it again.",
            }

    # APPOINTMENT intent: hair salon booking
    if "appointment" in q or "book" in q:
        when_text = extract_when_text(q)
        dt = parse_datetime(when_text) if when_text else parse_datetime(q)
        # default duration
        end_dt = None
        start_dt = None
        if dt:
            start_dt = dt
            end_dt = dt + timedelta(hours=1)
        title = "Hair Salon Appointment" if "hair" in q or "salon" in q else "Appointment"
        steps = [
            "Extract the target service and venue",
            "Parse requested date and time",
            "Check availability (requires provider integration)",
            "If available, create a calendar invite and reminders"
        ]
        calendar_url = None
        if start_dt and end_dt:
            calendar_url = build_google_calendar_link(title=title, start=start_dt, end=end_dt, location="Hair Salon", details=query)
        speech = f"I prepared a calendar link for {title}." if calendar_url else "I can prepare a calendar link once you confirm the time."
        return {
            "intent": "appointment",
            "title": title,
            "start": start_dt.isoformat() if start_dt else None,
            "end": end_dt.isoformat() if end_dt else None,
            "calendarUrl": calendar_url,
            "steps": steps,
            "speechResponse": speech
        }

    # Fallback: perform a web search
    search_url = f"https://www.google.com/search?q={quote_plus(query)}"
    return {
        "intent": "search",
        "openUrl": search_url,
        "steps": [
            "Understand your request",
            "No direct action matched; falling back to web search"
        ],
        "speechResponse": "I didn't find a direct action. I opened a web search for you."
    }


def build_google_maps_directions_url(destination: str):
    params = {
        "api": 1,
        "destination": destination,
        "travelmode": "driving"
    }
    return f"https://www.google.com/maps/dir/?{urlencode(params)}"


def build_google_calendar_link(title: str, start: datetime, end: datetime, location: str = "", details: str = ""):
    # Format as UTC naive Z times for simplicity
    def fmt(dt: datetime):
        # Ensure UTC-like format without timezone conversion
        return dt.strftime("%Y%m%dT%H%M%SZ")

    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{fmt(start)}/{fmt(end)}",
        "details": details,
        "location": location,
    }
    return f"https://calendar.google.com/calendar/render?{urlencode(params)}"


def extract_when_text(q: str):
    # Simple heuristic to extract date/time phrases after 'on' or 'at'
    m_on = re.search(r"\bon\s+([^.,;]+)", q)
    m_at = re.search(r"\bat\s+([^.,;]+)", q)
    if m_on and m_at:
        return f"{m_on.group(1)} {m_at.group(1)}"
    if m_on:
        return m_on.group(1)
    if m_at:
        return m_at.group(1)
    return None
