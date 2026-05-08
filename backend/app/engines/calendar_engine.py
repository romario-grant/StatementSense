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
                    model="gemini-2.5-flash",
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


class SmartTimingEngine:
    """
    Context-aware subscription timing analyzer (v2).
    
    Instead of simplistic "days_away > 14 → cancel" logic, this engine
    analyzes the actual renewal cycle relative to travel dates to produce
    intelligent, actionable recommendations.
    """

    # Minimum trip length to consider any subscription action
    MIN_TRIP_DAYS = 14
    # If the user departs within this many days after renewal, don't recommend cancel
    RECENTLY_RENEWED_WINDOW = 5

    @staticmethod
    def _next_renewal_date(renewal_day: int, after_date: datetime) -> datetime:
        """Calculate the next renewal date on or after `after_date`."""
        # Try the renewal day in the current month
        year, month = after_date.year, after_date.month
        # Clamp to valid day for the month
        import calendar as cal_mod
        max_day = cal_mod.monthrange(year, month)[1]
        day = min(renewal_day, max_day)
        candidate = datetime(year, month, day)
        if candidate >= after_date:
            return candidate
        # Otherwise, try next month
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
        max_day = cal_mod.monthrange(year, month)[1]
        day = min(renewal_day, max_day)
        return datetime(year, month, day)

    @staticmethod
    def _count_renewals_during_travel(renewal_day: int, depart: datetime, return_dt: datetime) -> int:
        """Count how many renewal cycles fall within the travel period."""
        import calendar as cal_mod
        count = 0
        year, month = depart.year, depart.month
        # Iterate month by month from departure to return
        while True:
            max_day = cal_mod.monthrange(year, month)[1]
            day = min(renewal_day, max_day)
            renewal = datetime(year, month, day)
            if renewal > return_dt:
                break
            if renewal >= depart:
                count += 1
            # Advance to next month
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
        return count

    def analyze(self, subscription: dict, away_period: dict, today: datetime | None = None) -> dict | None:
        """
        Analyze a single subscription against a single away period.

        Returns a recommendation dict, or None if no action is needed.

        Decision logic:
        1. Trip < MIN_TRIP_DAYS → KEEP (not worth the hassle)
        2. Subscription just renewed (within RECENTLY_RENEWED_WINDOW before departure)
           AND trip < 30 days → KEEP (already paid, short trip)
        3. Renewal falls during travel → CANCEL BEFORE or PAUSE
        4. Can pause → PAUSE (always preferred over cancel)
        5. Can cancel+rejoin with no penalty → CANCEL before next renewal
        6. Penalty exists but savings > 2x penalty → CANCEL WITH NOTE
        7. Otherwise → KEEP with advisory
        """
        if today is None:
            today = datetime.now()

        monthly_cost = float(subscription.get("monthly_cost", 0))
        if monthly_cost <= 0:
            return None

        depart = datetime.strptime(away_period["departure_date"], "%Y-%m-%d")
        return_dt = datetime.strptime(away_period["return_date"], "%Y-%m-%d")

        # Only count future days
        effective_depart = max(depart, today)
        if return_dt <= effective_depart:
            return None

        days_away = (return_dt - effective_depart).days
        months_away = math.ceil(days_away / 30.0)
        daily_cost = monthly_cost / 30.0

        renewal_day = subscription.get("renewal_day")
        penalty = float(subscription.get("cancellation_penalty", 0))
        can_pause = subscription.get("can_pause", False)
        can_cancel = subscription.get("can_cancel_and_rejoin", False)

        # ── Rule 1: Short trips aren't worth the hassle ──
        if days_away < self.MIN_TRIP_DAYS:
            return None

        # ── Timing analysis ──
        if renewal_day:
            next_renewal = self._next_renewal_date(renewal_day, today)
            renewals_during_travel = self._count_renewals_during_travel(
                renewal_day, effective_depart, return_dt
            )
            days_until_renewal = (next_renewal - today).days
            days_renewal_to_depart = (depart - next_renewal).days  # negative = renewal after departure
            wasted_months = renewals_during_travel
            potential_savings = monthly_cost * wasted_months
        else:
            # No renewal day provided — fall back to daily cost estimate
            next_renewal = None
            renewals_during_travel = months_away
            days_until_renewal = None
            days_renewal_to_depart = None
            wasted_months = months_away
            potential_savings = daily_cost * days_away

        # ── Rule 2: Recently renewed + short trip → KEEP ──
        if (renewal_day and days_renewal_to_depart is not None
                and -self.RECENTLY_RENEWED_WINDOW <= days_renewal_to_depart <= 0
                and days_away < 30):
            return None  # Already paid, trip is short

        # ── Rule 3+4+5+6: Determine action ──
        net_savings = potential_savings - penalty

        if net_savings <= 0:
            return None

        # Determine the optimal action date
        if renewal_day and next_renewal:
            # Cancel/pause BEFORE the next renewal to avoid paying
            if next_renewal > today:
                action_date = (next_renewal - timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                action_date = today.strftime("%Y-%m-%d")
            restart_date = return_dt.strftime("%Y-%m-%d")
        else:
            action_date = (effective_depart - timedelta(days=1)).strftime("%Y-%m-%d")
            restart_date = return_dt.strftime("%Y-%m-%d")

        # Build timing context string
        if renewal_day:
            if days_renewal_to_depart is not None and days_renewal_to_depart < 0:
                timing_context = (
                    f"Renews on day {renewal_day} — "
                    f"{abs(days_renewal_to_depart)} day(s) after departure. "
                    f"{renewals_during_travel} renewal(s) fall during travel."
                )
            elif days_renewal_to_depart is not None and days_renewal_to_depart >= 0:
                timing_context = (
                    f"Renews on day {renewal_day} — "
                    f"{days_renewal_to_depart} day(s) before departure. "
                    f"{renewals_during_travel} renewal(s) fall during travel."
                )
            else:
                timing_context = f"Renews on day {renewal_day}."
        else:
            timing_context = "Renewal day unknown — estimated from daily cost."

        # ── Decision matrix ──
        if can_pause:
            action = "PAUSE"
            detail = f"Pause your membership before {action_date}. Resume on {restart_date}."
            rationale = "Pausing preserves your membership while avoiding charges during travel."
        elif can_cancel and penalty == 0:
            action = "CANCEL & REJOIN"
            detail = f"Cancel before {action_date}. Rejoin after {restart_date}."
            rationale = "No penalty to rejoin — clean cancel saves you the most."
        elif can_cancel and net_savings > penalty * 2:
            action = "CANCEL & REJOIN"
            detail = (
                f"Cancel before {action_date}. Rejoin fee is ${penalty:.2f}, "
                f"but you save ${net_savings:.2f} net."
            )
            rationale = f"Savings outweigh the ${penalty:.2f} rejoin penalty by 2x+."
        else:
            action = "KEEP"
            detail = "The savings don't justify cancellation given the rejoin cost."
            rationale = "Consider asking your provider about a temporary pause option."
            # Still return it so the user sees the analysis, but mark action as KEEP
            if net_savings < 10:
                return None  # Truly not worth mentioning

        return {
            "subscription": subscription["name"],
            "away_reason": away_period["reason"],
            "away_dates": f"{away_period['departure_date']} to {away_period['return_date']}",
            "destination": away_period.get("destination", "Unknown"),
            "days_away": days_away,
            "months_away": months_away,
            "monthly_cost": monthly_cost,
            "renewal_day": renewal_day,
            "next_renewal_date": next_renewal.strftime("%Y-%m-%d") if next_renewal else None,
            "renewals_during_travel": renewals_during_travel,
            "potential_savings": round(potential_savings, 2),
            "penalty": penalty,
            "net_savings": round(net_savings, 2),
            "action": action,
            "action_detail": detail,
            "action_date": action_date,
            "restart_date": restart_date,
            "timing_context": timing_context,
            "rationale": rationale,
            "location_type": subscription.get("location_type", "unknown"),
            "confidence": away_period.get("confidence", "medium"),
        }


class CalendarSenseEngine:
    """Thin wrapper around SmartTimingEngine for backward compatibility."""

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
        """Generate recommendations using SmartTimingEngine."""
        engine = SmartTimingEngine()
        recommendations = []
        for sub in local_subs:
            if not sub.get("is_local"):
                continue
            for away in away_periods:
                rec = engine.analyze(sub, away)
                if rec is not None:
                    recommendations.append(rec)
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


# ══════════════════════════════════════════════════════════════════════════════
# Progressive Loading API — composable functions for phased frontend loading
# ══════════════════════════════════════════════════════════════════════════════

def fetch_events(access_token: str | None = None):
    """
    Phase 1: Fetch calendar events only. Fast (~2s).
    Returns events list + preview for immediate display.
    """
    try:
        calendar = CalendarReader(access_token)
        events = calendar.get_upcoming_events(months_ahead=6)
        print(f"[CalendarSense:Phase1] Fetched {len(events)} events.")

        events_preview = []
        for ev in events[:15]:
            start_str = ev.get('start', '')[:10] if ev.get('start') else '?'
            events_preview.append({
                "date": start_str,
                "summary": ev.get('summary', 'No Title'),
                "location": ev.get('location', ''),
            })

        return {
            "events": events,
            "events_scanned": len(events),
            "events_preview": events_preview,
        }
    except Exception as e:
        print(f"[CalendarSense:Phase1] ERROR: {e}")
        traceback.print_exc()
        return {"error": str(e)}


def classify_and_detect(events: list, home_location: str, subscriptions_list: list):
    """
    Phase 2: Classify subscriptions + detect travel periods in parallel.
    Receives the raw events from Phase 1.
    """
    try:
        analyzer = GeminiCalendarAnalyzer()
    except Exception as e:
        return {"error": f"Gemini initialization failed: {e}"}

    results = {"away_periods": [], "processed_subscriptions": []}

    # Fire travel detection and subscription classification in parallel
    def _detect_travel():
        return analyzer.detect_away_periods(events, home_location)

    def _classify_one(sub):
        sub_name = sub.get("name")
        sub_cost = float(sub.get("cost", 0))
        renewal_day = sub.get("renewal_day")  # v2: carry through for SmartTimingEngine
        classification = analyzer.classify_subscription(sub_name, sub_cost, home_location)
        classification["name"] = sub_name
        if renewal_day is not None:
            classification["renewal_day"] = renewal_day
        return classification

    try:
        with ThreadPoolExecutor(max_workers=min(len(subscriptions_list) + 1, 100)) as pool:
            # Submit travel detection
            travel_future = pool.submit(_detect_travel)

            # Submit all subscription classifications
            classify_futures = {pool.submit(_classify_one, sub): sub for sub in subscriptions_list}

            # Collect travel results
            try:
                results["away_periods"] = travel_future.result()
            except Exception as e:
                print(f"[CalendarSense:Phase2] Travel detection failed: {e}")
                results["away_periods"] = []

            # Collect classification results
            processed_subs = []
            for future in as_completed(classify_futures):
                try:
                    processed_subs.append(future.result())
                except Exception as e:
                    sub = classify_futures[future]
                    processed_subs.append({
                        "name": sub.get("name"), "is_local": False,
                        "location_type": "portable", "reason": f"Classification error: {e}"
                    })

            results["processed_subscriptions"] = processed_subs

        local_subs = [s for s in processed_subs if s.get("is_local")]
        results["local_count"] = len(local_subs)
        results["portable_count"] = len(processed_subs) - len(local_subs)

        print(f"[CalendarSense:Phase2] Classified {len(processed_subs)} subs "
              f"({results['local_count']} local), detected {len(results['away_periods'])} away periods.")

        return results
    except Exception as e:
        print(f"[CalendarSense:Phase2] ERROR: {e}")
        traceback.print_exc()
        return {"error": str(e)}


def compute_savings(away_periods: list, processed_subscriptions: list):
    """
    Phase 3: Calculate savings + search destination alternatives via Places API.
    Only called when local subs AND away periods exist.
    """
    from .places_service import PlacesService

    local_subs = [s for s in processed_subscriptions if s.get("is_local")]

    if not local_subs or not away_periods:
        return {"recommendations": [], "total_savings": 0.0}

    engine = CalendarSenseEngine()
    recommendations = engine.calculate_savings(away_periods, local_subs)

    # Initialize Places API service (falls back gracefully if key missing)
    places = None
    try:
        places = PlacesService()
    except ValueError as e:
        print(f"[CalendarSense:Phase3] Places API not available: {e}")

    # Parallel alternatives search via Google Places API
    def _search_one(rec):
        dest = rec.get("destination", "")
        loc_type = rec.get("location_type", "")
        sub_name = rec.get("subscription", "")
        if dest and dest != "Unknown" and loc_type != "portable" and places:
            try:
                print(f"[CalendarSense:Phase3] Places API search for '{sub_name}' in {dest}...")
                alternatives = places.search_alternatives(sub_name, loc_type, dest)
                rec["alternatives"] = alternatives
            except Exception as e:
                print(f"[CalendarSense:Phase3] Places search failed for '{sub_name}': {e}")
                rec["alternatives"] = {
                    "alternatives_found": False,
                    "destination": dest,
                    "destination_center": None,
                    "options": [],
                    "search_query": "",
                }
        return rec

    if recommendations:
        with ThreadPoolExecutor(max_workers=min(len(recommendations), 5)) as pool:
            futures = [pool.submit(_search_one, rec) for rec in recommendations]
            recommendations = [f.result() for f in futures]

    total_savings = sum(r.get("net_savings", 0) for r in recommendations)

    print(f"[CalendarSense:Phase3] {len(recommendations)} recommendations, total savings: ${total_savings:.2f}")

    return {
        "recommendations": recommendations,
        "total_savings": round(total_savings, 2),
    }


def create_reminders(access_token: str, recommendations: list) -> dict:
    """
    Phase 4: Create Google Calendar reminder events for actionable recommendations.

    For each recommendation with action != 'KEEP', creates:
    1. An action event (cancel/pause) on the optimal action date
    2. A restart event on the return date

    Requires calendar.events scope (read+write).
    """
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if not access_token:
        return {"error": "Access token required for calendar write access."}

    try:
        creds = Credentials(token=access_token)
        service = build('calendar', 'v3', credentials=creds)
    except Exception as e:
        return {"error": f"Calendar authentication failed: {e}"}

    created_events = []

    for rec in recommendations:
        action = rec.get("action", "KEEP")
        if action == "KEEP":
            continue

        sub_name = rec.get("subscription", "Unknown")
        action_date = rec.get("action_date")
        restart_date = rec.get("restart_date")
        destination = rec.get("destination", "")
        net_savings = rec.get("net_savings", 0)

        # ── Event 1: Action reminder (cancel/pause) ──
        if action_date:
            action_verb = "Pause" if action == "PAUSE" else "Cancel"
            action_event = {
                "summary": f"📋 {action_verb} {sub_name}",
                "description": (
                    f"CalendarSense Reminder\n\n"
                    f"Action: {action}\n"
                    f"{rec.get('action_detail', '')}\n\n"
                    f"Reason: {rec.get('away_reason', '')}\n"
                    f"Destination: {destination}\n"
                    f"Estimated savings: ${net_savings:.2f}\n\n"
                    f"— Generated by StatementSense"
                ),
                "start": {"date": action_date},
                "end": {"date": action_date},
                "reminders": {
                    "useDefault": False,
                    "overrides": [
                        {"method": "popup", "minutes": 24 * 60},  # 1 day before
                        {"method": "popup", "minutes": 60},        # 1 hour before
                    ],
                },
            }
            try:
                result = service.events().insert(
                    calendarId='primary', body=action_event
                ).execute()
                created_events.append({
                    "type": "action",
                    "subscription": sub_name,
                    "date": action_date,
                    "summary": action_event["summary"],
                    "event_link": result.get("htmlLink", ""),
                })
                print(f"[CalendarSense:Phase4] Created: {action_event['summary']} on {action_date}")
            except Exception as e:
                print(f"[CalendarSense:Phase4] Failed to create action event: {e}")
                created_events.append({
                    "type": "action",
                    "subscription": sub_name,
                    "date": action_date,
                    "error": str(e),
                })

        # ── Event 2: Restart reminder ──
        if restart_date and action != "KEEP":
            restart_event = {
                "summary": f"🔄 Restart {sub_name}",
                "description": (
                    f"CalendarSense Reminder\n\n"
                    f"You're back from {destination}!\n"
                    f"Re-subscribe to {sub_name} now.\n\n"
                    f"— Generated by StatementSense"
                ),
                "start": {"date": restart_date},
                "end": {"date": restart_date},
                "reminders": {
                    "useDefault": False,
                    "overrides": [
                        {"method": "popup", "minutes": 60},
                    ],
                },
            }
            try:
                result = service.events().insert(
                    calendarId='primary', body=restart_event
                ).execute()
                created_events.append({
                    "type": "restart",
                    "subscription": sub_name,
                    "date": restart_date,
                    "summary": restart_event["summary"],
                    "event_link": result.get("htmlLink", ""),
                })
                print(f"[CalendarSense:Phase4] Created: {restart_event['summary']} on {restart_date}")
            except Exception as e:
                print(f"[CalendarSense:Phase4] Failed to create restart event: {e}")
                created_events.append({
                    "type": "restart",
                    "subscription": sub_name,
                    "date": restart_date,
                    "error": str(e),
                })

    return {
        "created_events": created_events,
        "total_created": len([e for e in created_events if "error" not in e]),
        "total_failed": len([e for e in created_events if "error" in e]),
    }

