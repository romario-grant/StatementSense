"""
CalendarSense Engine — Pure functions for calendar travel analysis.
Stripped of CLI code, ready for API integration.
"""

import os
import json
import math
from datetime import datetime, timedelta, timezone
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
# NOTE: Google Calendar OAuth imports (google_auth_oauthlib, googleapiclient)
# are loaded lazily inside CalendarReader._authenticate() to prevent
# the container from crashing on startup when credentials are missing.

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

class CalendarReader:
    def __init__(self, access_token: str | None = None):
        self.access_token = access_token
        self.service = self._authenticate()
    
    def _authenticate(self):
        # Lazy imports — only load when calendar is actually needed
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        
        creds = None
        
        # 1. Serverless web flow: Use the access token passed from the frontend
        if self.access_token:
            creds = Credentials(token=self.access_token)
            return build('calendar', 'v3', credentials=creds)

        # 2. Local CLI flow: Fallback to token.json / credentials.json
        # Use the project root set by main.py to find credential files
        project_root = os.environ.get("STATEMENTSENSE_ROOT", "")
        if project_root:
            token_path = os.path.join(project_root, 'token.json')
            creds_path = os.path.join(project_root, 'credentials.json')
        else:
            # Fallback: try current directory, then parent
            token_path = 'token.json'
            creds_path = 'credentials.json'
            if not os.path.exists(creds_path) and os.path.exists('../credentials.json'):
                creds_path = '../credentials.json'
                token_path = '../token.json'

        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(creds_path):
                    raise FileNotFoundError(
                        f"CRITICAL: {creds_path} not found.\n"
                        "Download it from Google Cloud Console → APIs & Services → Credentials.\n"
                        "Note: For web usage, please log in via the frontend."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                # This will open a local browser window to authenticate
                creds = flow.run_local_server(port=0)
            
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
        
        return build('calendar', 'v3', credentials=creds)
    
    def get_upcoming_events(self, months_ahead=6):
        now = datetime.now(timezone.utc)
        future = now + timedelta(days=int(months_ahead * 30.44))
        
        time_min = now.isoformat()
        time_max = future.isoformat()
        
        all_events = []
        page_token = None
        
        try:
            while True:
                events_result = self.service.events().list(
                    calendarId='primary',
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=100,
                    singleEvents=True,
                    orderBy='startTime',
                    pageToken=page_token
                ).execute()
                
                events = events_result.get('items', [])
                
                for event in events:
                    start = event.get('start', {})
                    end = event.get('end', {})
                    
                    start_str = start.get('dateTime', start.get('date', ''))
                    end_str = end.get('dateTime', end.get('date', ''))
                    
                    all_events.append({
                        'summary': event.get('summary', 'No Title'),
                        'start': start_str,
                        'end': end_str,
                        'location': event.get('location', ''),
                        'description': event.get('description', '')
                    })
                
                page_token = events_result.get('nextPageToken')
                if not page_token:
                    break
        except Exception as e:
            print(f"[CalendarSense] Google Calendar API Error: {e}")
            # Return empty list rather than crashing
            return []
            
        return all_events


class GeminiCalendarAnalyzer:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            # Fallback: try loading from project root .env
            from dotenv import load_dotenv
            project_root = os.environ.get("STATEMENTSENSE_ROOT", "")
            if project_root:
                load_dotenv(os.path.join(project_root, ".env"))
            else:
                load_dotenv('../.env')
            api_key = os.getenv("GEMINI_API_KEY")
            
        if not api_key:
            raise ValueError("CRITICAL: GEMINI_API_KEY not found.")
        self.client = genai.Client(api_key=api_key)
    
    def _call_gemini(self, prompt, use_search=False, max_retries=4):
        """Call Gemini API. Search enabled for accuracy as per user request."""
        config = {"temperature": 0.0}
        if use_search:
            config["tools"] = [{"google_search": {}}]
        
        call_label = "grounded-search" if use_search else "standard"
        print(f"[CalendarSense] Calling gemini-3.1-pro-preview ({call_label})...")
        
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model="gemini-3.1-pro-preview",
                    config=config,
                    contents=prompt
                )
                raw_text = response.text.strip()
                print(f"[CalendarSense] [+] Got response ({call_label}, attempt {attempt+1})")
                if raw_text.startswith("```json"): raw_text = raw_text[7:]
                elif raw_text.startswith("```"): raw_text = raw_text[3:]
                if raw_text.endswith("```"): raw_text = raw_text[:-3]
                return json.loads(raw_text.strip())
            except Exception as e:
                error_str = str(e)
                print(f"[CalendarSense] [!] Error ({call_label}, attempt {attempt+1}/{max_retries}): {error_str[:200]}")
                if attempt == max_retries - 1:
                    raise
                
                # If rate limited, wait 2s
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    import time
                    time.sleep(2)
                continue
    
    def detect_away_periods(self, events, user_home_location):
        if not events:
            return []
        
        events_text = json.dumps(events, indent=2)
        
        prompt = f"""Analyze these calendar events for a person who lives in {user_home_location}.

CALENDAR EVENTS:
{events_text}

Identify ALL periods where this person will be AWAY from {user_home_location}.
Look for: flights, travel, vacations, trips, hospital stays, study abroad, work relocations, 
conferences, visiting family, moving, or any event that suggests extended absence from home.

IMPORTANT RULES:
- Only flag periods where the person will be PHYSICALLY AWAY from {user_home_location}
- Combine overlapping or consecutive travel events into single away periods
- If you see a departing flight but no explicit return flight, INFER the return date based on the last event that occurs in that destination (e.g., if there's a flight to Kansas City in May and a concert in Kansas City in June, the away period lasts until the concert).
- If you see a departing flight with no subsequent events, estimate a 7-day trip.
- DO NOT ignore one-way flights or single events in another city; these are strong indicators of travel.

Return a JSON array (no markdown formatting) of away periods:
[
    {{
        "reason": "Flight to Miami for vacation",
        "departure_date": "2025-06-15",
        "return_date": "2025-08-20",
        "destination": "Miami, USA",
        "trigger_type": "travel",
        "confidence": "high"
    }}
]

trigger_type must be one of: travel, medical, study, work, relocation, vacation, other
confidence must be: high, medium, or low

If NO away periods are found, return an empty array: []
"""
        try:
            return self._call_gemini(prompt, use_search=False)
        except Exception as e:
            print(f"Gemini Error (travel detection): {e}")
            return []

    def classify_subscription(self, sub_name, sub_cost, user_home_location):
        prompt = f"""The user lives in {user_home_location} and pays ${sub_cost} for "{sub_name}".
Use Google Search to look up what "{sub_name}" is, then classify it.

Return a JSON object (no markdown formatting):
{{
    "is_local": true,
    "location_type": "physical",
    "can_pause": true,
    "can_cancel_and_rejoin": true,
    "cancellation_penalty": 0,
    "monthly_cost": {sub_cost},
    "reason": "Brief explanation of why this is local or portable"
}}
"""
        try:
            return self._call_gemini(prompt, use_search=True)
        except Exception as e:
            print(f"Gemini Error (subscription classification): {e}")
            return {
                "is_local": False, "location_type": "portable", "can_pause": False,
                "can_cancel_and_rejoin": True, "cancellation_penalty": 0,
                "monthly_cost": sub_cost, "reason": f"API check failed ({str(e)[:50]}) — assuming portable."
            }

    def search_destination_alternatives(self, sub_name, location_type, destination, sub_reason=""):
        prompt = f"""The user has a subscription called "{sub_name}" which is a {location_type} service.
Context about this subscription: {sub_reason}

The user is traveling to {destination}. Search for SIMILAR services or temporary alternatives to "{sub_name}" available in {destination}.

IMPORTANT: The alternatives must be the SAME TYPE of service as "{sub_name}". 
For example:
- If "{sub_name}" is a mobile data plan, search for prepaid SIM cards, temporary data plans, or eSIM options
- If "{sub_name}" is a gym membership, search for gyms with day passes
- If "{sub_name}" is a streaming service, note if it works internationally

Return a JSON object (no markdown formatting):
{{
    "alternatives_found": true,
    "destination": "{destination}",
    "options": [
        {{
            "name": "Service Name",
            "type": "day pass / short-term / prepaid",
            "estimated_cost": "$X/day or $Y/month",
            "estimated_monthly_cost": 25.00,
            "url": "https://www.example.com",
            "notes": "Brief description"
        }}
    ],
    "best_value_option": "Service Name",
    "tip": "A short practical tip for the traveler"
}}

Rules:
- url MUST be the official website URL of the alternative service. Use Google Search to find it.
"""
        try:
            return self._call_gemini(prompt, use_search=True)
        except Exception:
            return None


class CalendarSenseEngine:
    @staticmethod
    def calculate_overlap_days(away_start, away_end, today=None):
        if today is None:
            today = datetime.now()
        
        start = datetime.strptime(away_start, "%Y-%m-%d")
        end = datetime.strptime(away_end, "%Y-%m-%d")
        
        if start < today: start = today
        if end <= start: return 0
        
        return (end - start).days
    
    @staticmethod
    def calculate_savings(away_periods, local_subs):
        recommendations = []
        for sub in local_subs:
            if not sub.get("is_local"): continue
            
            monthly_cost = float(sub.get("monthly_cost", 0))
            if monthly_cost <= 0: continue
            daily_cost = monthly_cost / 30.0
            
            for away in away_periods:
                days_away = CalendarSenseEngine.calculate_overlap_days(
                    away["departure_date"], away["return_date"]
                )
                
                if days_away < 14: continue
                
                potential_savings = daily_cost * days_away
                penalty = float(sub.get("cancellation_penalty", 0))
                net_savings = potential_savings - penalty
                
                if net_savings <= 0: continue
                
                if sub.get("can_pause"):
                    action = "PAUSE MEMBERSHIP"
                    detail = "Freeze your membership during this period."
                elif sub.get("can_cancel_and_rejoin") and penalty == 0:
                    action = "CANCEL & REJOIN"
                    detail = "Cancel before you leave, resubscribe when you return."
                elif sub.get("can_cancel_and_rejoin") and net_savings > penalty * 2:
                    action = "CANCEL & REJOIN (WITH PENALTY)"
                    detail = f"Rejoin fee is ${penalty:.2f}, but you still save ${net_savings:.2f} net."
                else:
                    action = "CONSIDER CANCELING"
                    detail = "Check with the provider about pause options."
                
                months_away = math.ceil(days_away / 30.0)
                recommendations.append({
                    "subscription": sub["name"],
                    "away_reason": away["reason"],
                    "away_dates": f"{away['departure_date']} to {away['return_date']}",
                    "destination": away.get("destination", "Unknown"),
                    "days_away": days_away,
                    "months_away": months_away,
                    "monthly_cost": monthly_cost,
                    "potential_savings": round(potential_savings, 2),
                    "penalty": penalty,
                    "net_savings": round(net_savings, 2),
                    "action": action,
                    "action_detail": detail,
                    "location_type": sub.get("location_type", "unknown"),
                    "confidence": away.get("confidence", "medium")
                })
        return recommendations


import traceback

def analyze_calendar(home_location: str, subscriptions_list: list, access_token: str | None = None):
    """
    Main entry point for API.
    Connects to calendar, fetches events, queries Gemini, returns savings recommendations.
    """
    try:
        try:
            calendar = CalendarReader(access_token)
        except Exception as e:
            print(f"[CalendarSense] Calendar Reader Init Failed: {e}")
            return {"error": f"Calendar connection failed: {e}"}
            
        try:
            analyzer = GeminiCalendarAnalyzer()
        except Exception as e:
            print(f"[CalendarSense] Gemini Analyzer Init Failed: {e}")
            return {"error": f"Gemini initialization failed: {e}"}
            
        events = calendar.get_upcoming_events(months_ahead=6)
        print(f"[CalendarSense] Fetched {len(events)} events.")
        # Build event preview for frontend display (like the CLI shows)
        events_preview = []
        for ev in events[:15]:  # Show first 15 events
            start_str = ev.get('start', '')[:10] if ev.get('start') else '?'
            events_preview.append({
                "date": start_str,
                "summary": ev.get('summary', 'No Title'),
                "location": ev.get('location', ''),
            })
        
        away_periods = analyzer.detect_away_periods(events, home_location)
        
        # --- Parallel classification: fire all at once ---
        def _classify_one(sub):
            sub_name = sub.get("name")
            sub_cost = float(sub.get("cost", 0))
            classification = analyzer.classify_subscription(sub_name, sub_cost, home_location)
            classification["name"] = sub_name
            return classification
        
        with ThreadPoolExecutor(max_workers=min(len(subscriptions_list), 100)) as pool:
            futures = {pool.submit(_classify_one, sub): sub for sub in subscriptions_list}
            processed_subs = []
            for future in as_completed(futures):
                try:
                    processed_subs.append(future.result())
                except Exception as e:
                    sub = futures[future]
                    processed_subs.append({
                        "name": sub.get("name"), "is_local": False,
                        "location_type": "portable", "reason": f"Classification error: {e}"
                    })
        
        local_subs = [s for s in processed_subs if s.get("is_local")]
        
        recommendations = []
        if local_subs and away_periods:
            engine = CalendarSenseEngine()
            recommendations = engine.calculate_savings(away_periods, local_subs)
            
            # --- Parallel alternatives search: fire all at once ---
            def _search_one(rec):
                dest = rec.get("destination", "")
                loc_type = rec.get("location_type", "")
                sub_name = rec.get("subscription", "")
                if dest and dest != "Unknown" and loc_type != "portable":
                    try:
                        print(f"[CalendarSense] Searching alternatives for '{sub_name}' in {dest}...")
                        alternatives = analyzer.search_destination_alternatives(
                            sub_name, loc_type, dest,
                            sub_reason=next((s.get('reason','') for s in processed_subs if s.get('name') == sub_name), '')
                        )
                        if alternatives:
                            rec["alternatives"] = alternatives
                        else:
                            print(f"[CalendarSense] No alternatives returned for '{sub_name}' (Gemini returned None)")
                            rec["alternatives"] = {"alternatives_found": False, "options": [], "tip": "Could not find alternatives — try again."}
                    except Exception as e:
                        print(f"[CalendarSense] Alternatives search failed for '{sub_name}': {e}")
                        rec["alternatives"] = {"alternatives_found": False, "options": [], "tip": f"Search failed: {str(e)[:100]}"}
                return rec
            
            with ThreadPoolExecutor(max_workers=min(len(recommendations), 100)) as pool:
                futures = [pool.submit(_search_one, rec) for rec in recommendations]
                recommendations = [f.result() for f in futures]

        total_savings = sum(r.get("net_savings", 0) for r in recommendations)
        
        return {
            "events_scanned": len(events),
            "events_preview": events_preview,
            "away_periods": away_periods,
            "processed_subscriptions": processed_subs,
            "recommendations": recommendations,
            "total_savings": round(total_savings, 2),
            "home_location": home_location,
            "local_count": len(local_subs),
            "portable_count": len(processed_subs) - len(local_subs)
        }
    except Exception as e:
        print("[CalendarSense] CRITICAL ERROR IN ENGINE:")
        traceback.print_exc()
        return {"error": f"Internal Engine Error: {str(e)}"}

