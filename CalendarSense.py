import os
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from google import genai
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()

# ==========================================
# 1. GOOGLE CALENDAR READER
# ==========================================

# Read-only access to the user's calendar
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

class CalendarReader:
    """Connects to Google Calendar via OAuth2 and reads upcoming events."""
    
    def __init__(self):
        self.service = self._authenticate()
    
    def _authenticate(self):
        """Handles OAuth2 flow — opens browser on first run, caches token after."""
        creds = None
        
        # Resolve credential paths relative to this script's directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        token_path = os.path.join(script_dir, 'token.json')
        creds_path = os.path.join(script_dir, 'credentials.json')
        
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        
        # If no valid credentials, run the OAuth flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(creds_path):
                    raise FileNotFoundError(
                        "CRITICAL: credentials.json not found.\n"
                        "Download it from Google Cloud Console → APIs & Services → Credentials.\n"
                        "Save it in your StatementSense folder."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Cache the credentials for future runs
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
        
        return build('calendar', 'v3', credentials=creds)
    
    def get_upcoming_events(self, months_ahead=6):
        """Fetches all events from now to N months in the future."""
        now = datetime.now(timezone.utc)
        future = now + timedelta(days=int(months_ahead * 30.44))
        
        time_min = now.isoformat()
        time_max = future.isoformat()
        
        all_events = []
        page_token = None
        
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
                
                # Handle all-day events vs timed events
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
        
        return all_events

# ==========================================
# 2. GEMINI AI — TRAVEL & SUBSCRIPTION ANALYZER
# ==========================================

class GeminiCalendarAnalyzer:
    """Uses Gemini to detect travel periods and classify subscriptions."""
    
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("CRITICAL: GEMINI_API_KEY not found in your .env file.")
        self.client = genai.Client(api_key=api_key)
    
    def _call_gemini(self, prompt, use_search=False, max_retries=4):
        """Call Gemini API with automatic retry on 429 RESOURCE_EXHAUSTED."""
        config = {"temperature": 0.0}
        if use_search:
            config["tools"] = [{"google_search": {}}]
        
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model="gemini-2.5-flash",
                    config=config,
                    contents=prompt
                )
                raw_text = response.text.strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                elif raw_text.startswith("```"):
                    raw_text = raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                return json.loads(raw_text.strip())
            except Exception as e:
                error_str = str(e)
                if ("429" in error_str or "RESOURCE_EXHAUSTED" in error_str) and attempt < max_retries - 1:
                    wait_time = 10 * (2 ** attempt)
                    print(f"  [Rate limited — waiting {wait_time}s before retry...]")
                    time.sleep(wait_time)
                    continue
                raise
    
    def detect_away_periods(self, events, user_home_location):
        """
        Sends calendar events to Gemini to identify periods 
        where the user will be away from their home location.
        """
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
- If you cannot determine whether an event involves travel, DO NOT include it
- Be conservative — only include events that clearly indicate being away

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
        """
        Uses Gemini + Google Search to determine if a subscription 
        is local (location-dependent) or portable (works anywhere).
        """
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

Field definitions:
- is_local: true if this subscription REQUIRES the user to be in {user_home_location} to use it. false if it works from anywhere in the world.
- location_type: "physical" (gym, parking, local club), "regional_service" (local data plan, local ISP, local cable), "location_locked_digital" (geo-restricted streaming), or "portable" (works globally like Netflix, Spotify)
- can_pause: true if the service typically allows pausing/freezing the membership
- can_cancel_and_rejoin: true if the user can cancel and re-subscribe later without penalty
- cancellation_penalty: estimated cost in $ to cancel and rejoin (0 if no penalty, e.g. joining fee)
- monthly_cost: the normalized monthly cost of the subscription
- reason: 1-sentence explanation

CRITICAL: If you cannot find what "{sub_name}" is via search, set is_local to false and reason to "Could not verify — assuming portable."
"""
        try:
            return self._call_gemini(prompt, use_search=True)
        except Exception as e:
            print(f"Gemini Error (subscription classification): {e}")
            return {
                "is_local": False, "location_type": "portable", "can_pause": False,
                "can_cancel_and_rejoin": True, "cancellation_penalty": 0,
                "monthly_cost": sub_cost, "reason": f"API error — assuming portable."
            }

    def search_destination_alternatives(self, sub_name, location_type, destination):
        """
        When a local subscription is recommended for cancellation,
        search for alternatives at the travel destination.
        e.g., if canceling a gym in Jamaica, find gyms in Kansas City.
        """
        # Map subscription types to search terms
        search_map = {
            "physical": {
                "gym": "gyms with day passes or short-term memberships",
                "fitness": "gyms with day passes or short-term memberships",
                "pool": "public pools or pool day passes",
                "parking": "parking options",
                "club": "similar clubs or social venues",
                "yoga": "yoga studios with drop-in classes",
                "crossfit": "CrossFit gyms with drop-in rates",
                "studio": "fitness studios with day passes",
                "cowork": "coworking spaces with day passes",
                "workspace": "coworking spaces with day passes",
                "storage": "short-term storage facilities"
            },
            "regional_service": {
                "data": "prepaid SIM cards or mobile data plans for visitors",
                "flow": "prepaid SIM cards or mobile data plans for visitors",
                "digicel": "prepaid SIM cards or mobile data plans for visitors",
                "mobile": "prepaid SIM cards or eSIM data plans for visitors",
                "cell": "prepaid SIM cards or mobile data plans for visitors",
                "internet": "short-term internet or WiFi options",
                "cable": "streaming alternatives",
                "tv": "streaming alternatives"
            }
        }
        
        # Find the best search term
        sub_lower = sub_name.lower()
        search_category = search_map.get(location_type, {})
        search_term = None
        for keyword, term in search_category.items():
            if keyword in sub_lower:
                search_term = term
                break
        
        if not search_term:
            if location_type == "physical":
                search_term = f"alternatives to {sub_name}"
            elif location_type == "regional_service":
                search_term = f"visitor {sub_name} options"
            else:
                return None

        prompt = f"""Search for {search_term} in {destination}.

Return a JSON object (no markdown formatting):
{{
    "alternatives_found": true,
    "destination": "{destination}",
    "options": [
        {{
            "name": "Planet Fitness",
            "type": "day pass / short-term",
            "estimated_cost": "$10/day or $25/month",
            "estimated_monthly_cost": 25.00,
            "url": "https://www.planetfitness.com",
            "notes": "No commitment, cancel anytime"
        }}
    ],
    "best_value_option": "Planet Fitness",
    "tip": "A short practical tip for the traveler"
}}

Rules:
- Find 2-4 real options available in {destination}
- Focus on SHORT-TERM or VISITOR-FRIENDLY options (day passes, weekly plans, no-contract)
- Include estimated costs from your search
- estimated_monthly_cost MUST be a number representing the estimated monthly cost in USD
- url MUST be the official website URL of the alternative service. Use Google Search to find it.
- best_value_option should be the name of the cheapest monthly option
- If no alternatives found, set alternatives_found to false and options to empty array
"""
        try:
            return self._call_gemini(prompt, use_search=True)
        except Exception as e:
            print(f"  [Alternatives search warning: {e}]")
            return None

# ==========================================
# 3. OVERLAP ENGINE — SAVINGS CALCULATOR
# ==========================================

class CalendarSenseEngine:
    """Cross-references away periods with local subscriptions to find savings."""
    
    @staticmethod
    def calculate_overlap_days(away_start, away_end, today=None):
        """Calculates how many days the user will be away."""
        if today is None:
            today = datetime.now()
        
        start = datetime.strptime(away_start, "%Y-%m-%d")
        end = datetime.strptime(away_end, "%Y-%m-%d")
        
        # Only count future days
        if start < today:
            start = today
        
        if end <= start:
            return 0
        
        return (end - start).days
    
    @staticmethod
    def calculate_savings(away_periods, local_subs, min_days_away=14):
        """
        For each local subscription, calculates how much money
        the user would save by canceling/pausing during away periods.
        """
        recommendations = []
        
        for sub in local_subs:
            if not sub.get("is_local"):
                continue
            
            monthly_cost = float(sub.get("monthly_cost", 0))
            if monthly_cost <= 0:
                continue
            
            daily_cost = monthly_cost / 30.0
            
            for away in away_periods:
                days_away = CalendarSenseEngine.calculate_overlap_days(
                    away["departure_date"], away["return_date"]
                )
                
                if days_away < min_days_away:  # Only recommend for extended absence
                    continue
                
                potential_savings = daily_cost * days_away
                penalty = float(sub.get("cancellation_penalty", 0))
                net_savings = potential_savings - penalty
                
                if net_savings <= 0:
                    continue
                
                # Determine best action
                if sub.get("can_pause"):
                    action = "PAUSE MEMBERSHIP"
                    action_detail = "Freeze your membership during this period."
                elif sub.get("can_cancel_and_rejoin") and penalty == 0:
                    action = "CANCEL & REJOIN"
                    action_detail = "Cancel before you leave, resubscribe when you return."
                elif sub.get("can_cancel_and_rejoin") and net_savings > penalty * 2:
                    action = "CANCEL & REJOIN (WITH PENALTY)"
                    action_detail = f"Rejoin fee is ${penalty:.2f}, but you still save ${net_savings:.2f} net."
                else:
                    action = "CONSIDER CANCELING"
                    action_detail = "Check with the provider about pause options."
                
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
                    "action_detail": action_detail,
                    "location_type": sub.get("location_type", "unknown"),
                    "confidence": away.get("confidence", "medium")
                })
        
        return recommendations

# ==========================================
# 4. INTERACTIVE CLI
# ==========================================

def run_app():
    print("=========================================")
    print("  CalendarSense — Smart Travel Savings   ")
    print("=========================================")
    
    # --- Step 1: Connect to Google Calendar ---
    print("\n[Step 1: Connecting to Google Calendar...]")
    try:
        calendar = CalendarReader()
        print("  ✓ Connected to Google Calendar")
    except FileNotFoundError as e:
        print(e)
        return
    except Exception as e:
        print(f"  ✗ Calendar connection failed: {e}")
        return
    
    # --- Step 2: Initialize Gemini ---
    try:
        analyzer = GeminiCalendarAnalyzer()
        print("  ✓ Gemini AI ready")
    except ValueError as e:
        print(e)
        return
    
    # --- Step 3: Get user's home location ---
    print("\n[Step 2: Where do you live?]")
    home_location = input("Enter your home city/country (e.g., Kingston, Jamaica): ").strip()
    if not home_location:
        home_location = "Jamaica"
    
    # --- Step 4: Fetch calendar events ---
    print("\n[Step 3: Scanning your calendar for the next 6 months...]")
    events = calendar.get_upcoming_events(months_ahead=6)
    print(f"  Found {len(events)} upcoming events")
    
    if not events:
        print("  No upcoming events found. Add some events to your Google Calendar and try again.")
        return
    
    # Show preview of events found
    print("\n  Recent upcoming events:")
    for i, event in enumerate(events[:10]):
        start = event['start'][:10] if event['start'] else '?'
        print(f"    {i+1}. [{start}] {event['summary']}")
    if len(events) > 10:
        print(f"    ... and {len(events) - 10} more")
    
    # --- Step 5: Detect away periods ---
    print("\n[Step 4: Analyzing events for travel/away periods...]")
    away_periods = analyzer.detect_away_periods(events, home_location)
    
    if not away_periods:
        print("  No travel or away periods detected in your calendar.")
        print("  Tip: Make sure travel events have clear names like 'Flight to Miami' or 'Vacation in Bahamas'.")
        return
    
    print(f"\n  Detected {len(away_periods)} away period(s):\n")
    for i, away in enumerate(away_periods):
        conf_icon = "🟢" if away.get("confidence") == "high" else "🟡" if away.get("confidence") == "medium" else "🔴"
        print(f"  {conf_icon} {away['reason']}")
        print(f"     Dates: {away['departure_date']} → {away['return_date']}")
        print(f"     Destination: {away.get('destination', 'Unknown')}")
        days = CalendarSenseEngine.calculate_overlap_days(away['departure_date'], away['return_date'])
        print(f"     Duration: {days} days ({days/30:.1f} months)")
        print()
    
    # --- Step 6: Collect subscriptions ---
    print("[Step 5: Enter your local subscriptions]")
    print("(Enter subscription name and cost. Type 'done' when finished.)\n")
    
    subscriptions_raw = []
    while True:
        sub_name = input("  Subscription name (or 'done'): ").strip()
        if sub_name.lower() == 'done':
            break
        
        try:
            sub_cost = float(input(f"  Monthly cost for {sub_name}: $"))
        except ValueError:
            print("  Please enter a valid number.")
            continue
        
        subscriptions_raw.append({"name": sub_name, "cost": sub_cost})
        print()
    
    if not subscriptions_raw:
        print("\nNo subscriptions entered.")
        return
    
    # --- Parallel classification: fire all at once ---
    print(f"\n[Classifying {len(subscriptions_raw)} subscription(s) in parallel...]")
    
    def _classify_one(sub):
        classification = analyzer.classify_subscription(sub["name"], sub["cost"], home_location)
        classification["name"] = sub["name"]
        return classification
    
    subscriptions = []
    with ThreadPoolExecutor(max_workers=min(len(subscriptions_raw), 100)) as pool:
        future_to_sub = {pool.submit(_classify_one, sub): sub for sub in subscriptions_raw}
        for future in as_completed(future_to_sub):
            try:
                classification = future.result()
                local_label = "LOCAL" if classification.get("is_local") else "PORTABLE"
                print(f"  → {classification['name']}: {local_label} — {classification.get('reason', '')}")
                subscriptions.append(classification)
            except Exception as e:
                sub = future_to_sub[future]
                print(f"  → {sub['name']}: Error — {e}")
                subscriptions.append({
                    "name": sub["name"], "is_local": False,
                    "location_type": "portable", "can_pause": False,
                    "can_cancel_and_rejoin": True, "cancellation_penalty": 0,
                    "monthly_cost": sub["cost"], "reason": f"Classification error: {e}"
                })
    
    # --- Step 7: Calculate savings ---
    local_subs = [s for s in subscriptions if s.get("is_local")]
    
    if not local_subs:
        print("\n=========================================")
        print("  ✓ None of your subscriptions are location-dependent.")
        print("  No action needed — all your subscriptions work while traveling!")
        print("=========================================")
        return
    
    print(f"\n[Step 6: Calculating savings for {len(local_subs)} local subscription(s)...]")
    
    engine = CalendarSenseEngine()
    recommendations = engine.calculate_savings(away_periods, local_subs)
    
    if not recommendations:
        print("\n=========================================")
        print("  ✓ No actionable savings found.")
        print("  Your away periods are too short (<14 days) to justify canceling.")
        print("=========================================")
        return
    
    # --- Step 8: Display recommendations ---
    total_savings = sum(r["net_savings"] for r in recommendations)
    
    print("\n=========================================")
    print("  CALENDARSENSE RECOMMENDATIONS")
    print("=========================================")
    
    for i, rec in enumerate(recommendations):
        conf = rec.get("confidence", "medium")
        if conf == "high":
            conf_label = "HIGH"
        elif conf == "medium":
            conf_label = "MODERATE"
        else:
            conf_label = "LOW"
        
        print(f"\n  --- Recommendation {i+1} ({conf_label} Confidence) ---")
        print(f"  Subscription:  {rec['subscription']} (${rec['monthly_cost']:.2f}/mo)")
        print(f"  Type:          {rec['location_type'].replace('_', ' ').title()}")
        print(f"  Travel:        {rec['away_reason']}")
        print(f"  Away Dates:    {rec['away_dates']}")
        print(f"  Duration:      {rec['days_away']} days ({rec['months_away']} months)")
        print(f"  Savings:       ${rec['potential_savings']:.2f}")
        if rec['penalty'] > 0:
            print(f"  Rejoin Fee:    ${rec['penalty']:.2f}")
            print(f"  Net Savings:   ${rec['net_savings']:.2f}")
        print(f"  ACTION:        {rec['action']}")
        print(f"  DETAILS:       {rec['action_detail']}")
        
    # V2: Search for alternatives at ALL destinations in parallel
    recs_needing_alts = [
        rec for rec in recommendations
        if rec.get("destination", "") and rec.get("destination") != "Unknown" and rec.get("location_type") != "portable"
    ]
    
    if recs_needing_alts:
        print(f"\n  [Searching for alternatives at {len(recs_needing_alts)} destination(s) in parallel...]")
        
        def _search_one(rec):
            return rec, analyzer.search_destination_alternatives(
                rec['subscription'], rec.get('location_type', ''), rec.get('destination', '')
            )
        
        with ThreadPoolExecutor(max_workers=min(len(recs_needing_alts), 100)) as pool:
            futures = [pool.submit(_search_one, rec) for rec in recs_needing_alts]
            for future in as_completed(futures):
                try:
                    rec, alternatives = future.result()
                    if alternatives and alternatives.get("alternatives_found"):
                        print(f"\n  ┌─ ALTERNATIVES FOR {rec['subscription'].upper()} AT {rec.get('destination', '').upper()} ─────────")
                        for opt in alternatives.get("options", []):
                            print(f"  │  {opt.get('name', '?')}")
                            print(f"  │    Cost: {opt.get('estimated_cost', '?')}")
                            print(f"  │    Type: {opt.get('type', '?')}")
                            if opt.get("notes"):
                                print(f"  │    Note: {opt['notes']}")
                            print(f"  │")
                        if alternatives.get("tip"):
                            print(f"  └─ TIP: {alternatives['tip']}")
                        
                        # Cost comparison
                        best_option = alternatives.get("best_value_option", "")
                        cheapest_monthly = None
                        for opt in alternatives.get("options", []):
                            cost_val = opt.get("estimated_monthly_cost")
                            if cost_val and isinstance(cost_val, (int, float)):
                                if cheapest_monthly is None or cost_val < cheapest_monthly:
                                    cheapest_monthly = cost_val
                        
                        if cheapest_monthly and cheapest_monthly > 0:
                            months_away = rec['months_away']
                            cancel_savings = rec['potential_savings']
                            alt_total_cost = cheapest_monthly * months_away
                            net_impact = cancel_savings - alt_total_cost
                            
                            print(f"  │")
                            print(f"  │  ─── COST COMPARISON ({months_away} months) ───")
                            print(f"  │  Cancel {rec['subscription']}:  +${cancel_savings:.2f} saved")
                            print(f"  │  {best_option or 'Alt'} cost:      -${alt_total_cost:.2f}")
                            if net_impact >= 0:
                                print(f"  │  NET SAVINGS:            ${net_impact:.2f} ✓")
                            else:
                                print(f"  │  NET COST:              -${abs(net_impact):.2f}")
                                print(f"  │  (Still worth it for coverage while abroad)")
                        
                        print(f"  └──────────────────────────────────────")
                    else:
                        print(f"  No alternatives found in {rec.get('destination', '')}.")
                except Exception as e:
                    print(f"  [Alternatives search error: {e}]")
    
    print(f"\n  ─────────────────────────────────────")
    print(f"  TOTAL POTENTIAL SAVINGS: ${total_savings:.2f}")
    print(f"  ─────────────────────────────────────")
    print()

if __name__ == "__main__":
    run_app()