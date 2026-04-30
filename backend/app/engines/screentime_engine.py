"""
ScreentimeSense Engine — Pure functions for screentime analysis.
Stripped of CLI code, ready for API integration.
"""

import os
import math
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai

class GeminiClassifier:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            # Fallback: load .env from project root if not already loaded
            from dotenv import load_dotenv
            project_root = os.environ.get("STATEMENTSENSE_ROOT", "")
            if project_root:
                load_dotenv(os.path.join(project_root, ".env"))
            api_key = os.getenv("GEMINI_API_KEY")
        
        if not api_key:
            raise ValueError("CRITICAL: GEMINI_API_KEY not found in your .env file.")
            
        self.client = genai.Client(api_key=api_key)
        
        self.system_rules = """
        You are a financial data classifier with internet access.
        IMPORTANT: You MUST use Google Search to look up the App Name to find out what it actually does and what its official subscription pricing tiers are. 
        Match the user's provided Cost to the correct real-world billing frequency.

        CRITICAL RULE: If you cannot find VERIFIED pricing information from Google Search, you MUST set pricing_verified to false and set ALL pricing_tiers values to 0. NEVER fabricate or guess prices. Only report prices you found from official sources or app store listings.

        Return a strictly formatted JSON object with no markdown block formatting.
        {
            "frequency": "yearly",
            "category": "productivity",
            "value_mode": "time_based",
            "engagement_type": "generative", 
            "is_multi_device": false, 
            "has_free_tier": true,
            "is_shared_plan": false,
            "student_plan_price": 5.99,
            "pricing_verified": true,
            "pricing_tiers": {
                "monthly": 4.99,
                "yearly": 39.99,
                "lifetime": 149.99
            }
        }

        Field definitions:
        - frequency: The exact billing cycle (weekly, monthly, yearly, lifetime) based on your search of the price.
        - category: utility, productivity, entertainment, gaming
        - value_mode: "time_based" (value = time spent, e.g. Netflix), "presence_based" (background utilities like VPNs, iCloud), "outcome_based" (creative/professional tools like Adobe, Figma)
        - engagement_type: "passive" (audio/background), "active" (video/reading/gaming requiring visual attention), "generative" (creative/professional output tools)
        - is_multi_device: true ONLY if the app is PRIMARILY consumed on a TV, Console, or Desktop where mobile screen time would miss most usage.
        - has_free_tier: true if a permanent free version exists
        - is_shared_plan: true if this specific price is a family/duo plan
        - student_plan_price: The monthly cost of a student plan based on your search. Return 0 if no student tier exists.
        - pricing_verified: true ONLY if you found the pricing from a reliable source via Google Search. false if you are guessing or unsure.
        - pricing_tiers: An object with the REAL prices from your search. Set ALL to 0 if pricing_verified is false.
            - monthly: The monthly subscription price
            - yearly: The yearly subscription price (total cost for the full year, NOT per-month)
            - lifetime: The one-time lifetime purchase price. 0 if no lifetime option exists.
        """

    def analyze_app(self, app_name, cost):
        prompt = f"App: {app_name}, Cost: {cost}"
        import time as _time
        
        max_retries = 4
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model="gemini-2.5-flash",
                    config={
                        "tools": [{"google_search": {}}], 
                        "system_instruction": self.system_rules,
                        "temperature": 0.0
                    },
                    contents=prompt
                )
                
                raw_text = response.text.strip()
                if raw_text.startswith("```json"): 
                    raw_text = raw_text[7:]
                elif raw_text.startswith("```"): 
                    raw_text = raw_text[3:]
                    
                if raw_text.endswith("```"): 
                    raw_text = raw_text[:-3]
                
                result = json.loads(raw_text.strip())
                
                pricing = result.get("pricing_tiers", {})
                verified = result.get("pricing_verified", False)
                tier_values = [v for v in pricing.values() if v and v > 0]
                
                if verified and tier_values:
                    cost_float = float(cost)
                    matches_any_tier = any(
                        abs(cost_float - tier) / max(tier, 0.01) < 0.20 
                        for tier in tier_values if isinstance(tier, (int, float)) and tier > 0
                    )
                    if not matches_any_tier:
                        result["pricing_verified"] = False
                elif not verified:
                    result["pricing_tiers"] = {"monthly": 0, "yearly": 0, "lifetime": 0}
                
                return result
                
            except Exception as e:
                error_str = str(e)
                if ("429" in error_str or "RESOURCE_EXHAUSTED" in error_str) and attempt < max_retries - 1:
                    wait_time = 10 * (2 ** attempt)  # 10s, 20s, 40s
                    print(f"[ScreentimeSense] Rate limited (attempt {attempt+1}/{max_retries}). Waiting {wait_time}s...")
                    _time.sleep(wait_time)
                    continue
                print(f"Gemini API Error: {e}")
                return {
                    "frequency": "monthly", "category": "entertainment", "value_mode": "time_based",
                    "engagement_type": "active", "is_multi_device": False, "has_free_tier": False, 
                    "is_shared_plan": False, "student_plan_price": 0,
                    "pricing_verified": False,
                    "pricing_tiers": {"monthly": 0, "yearly": 0, "lifetime": 0}
                }


class SubscriptionAnalyzer:
    def __init__(self, hourly_wage, style_multiplier=0.10):
        self.hourly_wage = hourly_wage
        self.base_cancel_threshold_cph = hourly_wage * style_multiplier 
        self.gamma_map = {"utility": 0.05, "productivity": 0.10, "entertainment": 0.20, "gaming": 0.35}
        self.duration_map = {"weekly": 0.23, "monthly": 1.0, "quarterly": 3.0, "biannual": 6.0, "yearly": 12.0}
        self.engagement_weights = {"passive": 0.33, "active": 1.0, "generative": 1.5}
        self.priority_weights = {"productivity": 1.2, "utility": 1.1, "entertainment": 0.8, "gaming": 0.7}
        self.ema_alpha = 0.3

    def compute_value_risk_score(self, velocity, cph_value, cancel_threshold, months_subscribed, category):
        """
        6.6 Value Risk Score (0-100).
        Combines Usage (U), Cost efficiency (C), Duration (D), Priority (P).
        > 70 = Low Risk (retain), 40-70 = Medium Risk (review), < 40 = High Risk (cancel).
        """
        # U — Usage intensity score (0-100)
        U = min(velocity * 50, 100)
        
        # C — Cost efficiency score (0-100): lower CPH = higher score
        C = max((1 - (cph_value / (cancel_threshold * 2))) * 100, 0) if cancel_threshold > 0 else 50
        
        # D — Duration bonus (0-100): 12+ months = full bonus
        D = min(months_subscribed / 12, 1.0) * 100
        
        # P — Priority weight by category
        P = self.priority_weights.get(category, 1.0)
        
        # Weighted sum: U=35%, C=40%, D=10%, baseline=15%
        raw_score = (0.35 * U) + (0.40 * C) + (0.10 * D) + (0.15 * 50)
        vrs = min(round(raw_score * P), 100)
        vrs = max(vrs, 0)
        
        # Risk label
        if vrs > 70:
            risk_label = "Low Risk"
        elif vrs >= 40:
            risk_label = "Medium Risk"
        else:
            risk_label = "High Risk"
        
        return vrs, risk_label

    def compute_ema(self, data_points):
        if not data_points:
            return 0.0
        ema = data_points[0]
        for value in data_points[1:]:
            ema = self.ema_alpha * value + (1 - self.ema_alpha) * ema
        return ema

    def compute_velocity_ema(self, data_points):
        if not data_points or sum(data_points) == 0:
            return 1.0
        ema = self.compute_ema(data_points)
        avg = sum(data_points) / len(data_points)
        return ema / avg if avg > 0 else 1.0

    def detect_cusum_shift(self, data_points, threshold_factor=1.5):
        if len(data_points) < 3:
            return False, None, 0.0
        
        mean = sum(data_points) / len(data_points)
        std = (sum((x - mean) ** 2 for x in data_points) / len(data_points)) ** 0.5
        
        if std == 0:
            return False, None, 0.0
        
        threshold = threshold_factor * std
        cusum_pos = 0.0
        cusum_neg = 0.0
        max_cusum_pos = 0.0
        max_cusum_neg = 0.0
        
        for value in data_points:
            cusum_pos = max(0, cusum_pos + (value - mean) - 0.5 * std)
            cusum_neg = max(0, cusum_neg + (mean - value) - 0.5 * std)
            max_cusum_pos = max(max_cusum_pos, cusum_pos)
            max_cusum_neg = max(max_cusum_neg, cusum_neg)
        
        if max_cusum_neg > threshold:
            return True, "drop", max_cusum_neg / std
        elif max_cusum_pos > threshold:
            return True, "surge", max_cusum_pos / std
        
        return False, None, 0.0

    def detect_binge(self, data_points):
        if not data_points or sum(data_points) == 0:
            return False
        
        mean = sum(data_points) / len(data_points)
        std = (sum((x - mean) ** 2 for x in data_points) / len(data_points)) ** 0.5
        
        if std == 0:
            return False
        
        max_val = max(data_points)
        z_score = (max_val - mean) / std
        concentration = max_val / sum(data_points)
        
        return z_score > 1.5 and concentration > 0.40

    def compute_plan_recommendation(self, pricing_tiers, months_subscribed, velocity, discount_rate=0.005):
        monthly_price = pricing_tiers.get("monthly", 0)
        yearly_price = pricing_tiers.get("yearly", 0)
        lifetime_price = pricing_tiers.get("lifetime", 0)
        
        if velocity < 0.3:
            projected_months = 3
        elif velocity < 0.5:
            projected_months = 6
        elif velocity < 0.8:
            projected_months = 12
        else:
            projected_months = 36
        
        costs = {}
        
        if monthly_price > 0:
            npv_monthly = sum(monthly_price / (1 + discount_rate) ** t for t in range(1, projected_months + 1))
            costs["monthly"] = round(npv_monthly, 2)
        
        if yearly_price > 0:
            years_needed = math.ceil(projected_months / 12)
            npv_yearly = sum(yearly_price / (1 + discount_rate) ** (12 * y) for y in range(1, years_needed + 1))
            costs["yearly"] = round(npv_yearly, 2)
        
        if lifetime_price > 0:
            costs["lifetime"] = lifetime_price
        
        if not costs:
            return None, {}, {}
        
        best_plan = min(costs, key=costs.get)
        
        breakeven_months_lifetime = 0
        if lifetime_price > 0 and monthly_price > 0:
            breakeven_months_lifetime = math.ceil(lifetime_price / monthly_price)
        
        breakeven_months_yearly = 0
        if yearly_price > 0 and monthly_price > 0:
            breakeven_months_yearly = math.ceil(yearly_price / monthly_price)

        return best_plan, costs, {
            "projected_months": projected_months,
            "breakeven_months_lifetime": breakeven_months_lifetime,
            "breakeven_months_yearly": breakeven_months_yearly,
            "months_subscribed": months_subscribed,
            "plan_costs_npv": costs
        }

    def get_household_divisor(self, app_name, ai_shared_flag):
        name_lower = app_name.lower()
        if "duo" in name_lower or "couple" in name_lower: return 2
        elif "family" in name_lower or "party" in name_lower or "group" in name_lower: return 4
        return 3 if ai_shared_flag else 1

    def evaluate(self, name, raw_cost, weekly_hours, months_subscribed, ai_data):
        total_raw_hours = sum(weekly_hours)
        is_presence_based = (ai_data.get("value_mode") == "presence_based")
        is_outcome_based = (ai_data.get("value_mode") == "outcome_based")
        category = ai_data.get("category", "entertainment")

        freq = ai_data.get("frequency", "monthly").lower()
        time_multiplier = self.duration_map.get(freq, 1.0)
        normalized_monthly_cost = float(raw_cost) / time_multiplier
        
        household_divisor = self.get_household_divisor(name, ai_data.get("is_shared_plan"))
        personal_burden_cost = normalized_monthly_cost / household_divisor

        weight = self.engagement_weights.get(ai_data.get("engagement_type", "active"), 1.0)
        
        if is_presence_based:
            effective_days = 30.0
            cph_value = personal_burden_cost / effective_days
            total_eff_hours = effective_days
            velocity = 1.0
            cancel_threshold = self.base_cancel_threshold_cph * 1.5
        elif is_outcome_based:
            # Outcome-based tools (Adobe, Figma) derive value from output, not time.
            # Force generative weight and relax threshold to avoid penalizing
            # low-hour but high-value professional usage.
            weight = max(weight, 1.5)
            total_eff_hours = total_raw_hours * weight
            cph_value = personal_burden_cost / total_eff_hours if total_eff_hours > 0 else 9999.99
            velocity = self.compute_velocity_ema(weekly_hours)
            cancel_threshold = self.base_cancel_threshold_cph * 2.0
        else:
            total_eff_hours = total_raw_hours * weight
            cph_value = personal_burden_cost / total_eff_hours if total_eff_hours > 0 else 9999.99
            velocity = self.compute_velocity_ema(weekly_hours)
            cancel_threshold = self.base_cancel_threshold_cph

        has_shift, shift_direction, shift_magnitude = self.detect_cusum_shift(weekly_hours)
        is_binge = self.detect_binge(weekly_hours)

        confidence = 1.0
        if ai_data.get("is_multi_device"):
            confidence -= 0.3
        if total_raw_hours < 2 and not is_presence_based:
            confidence -= 0.2
        if velocity < 0.2 or velocity > 2.0:
            confidence -= 0.1
        if len(weekly_hours) < 4:
            confidence -= 0.15

        confidence = max(0.3, confidence)

        if confidence >= 0.8:
            confidence_label = "HIGH"
        elif confidence >= 0.6:
            confidence_label = "MODERATE"
        else:
            confidence_label = "LOW"

        gamma = self.gamma_map.get(category, 0.20)
        time_factor = 1.0 / max(months_subscribed, 1)
        # V3.2: Allow growing usage (velocity > 1.0) to mildly boost break-even prob
        p_be = min(min(velocity, 1.5) * math.exp(-gamma * time_factor), 1.0)

        # 6.6 — Value Risk Score
        vrs, vrs_label = self.compute_value_risk_score(
            velocity, cph_value, cancel_threshold, months_subscribed, category
        )

        pricing_tiers = ai_data.get("pricing_tiers", {"monthly": 0, "yearly": 0, "lifetime": 0})
        best_plan, plan_costs, breakeven_info = self.compute_plan_recommendation(
            pricing_tiers, months_subscribed, velocity
        )
        
        student_price = ai_data.get("student_plan_price", 0)

        metrics = (normalized_monthly_cost, household_divisor, personal_burden_cost, 
                   total_raw_hours, weight, total_eff_hours, cph_value, velocity)

        if total_raw_hours == 0 and not is_presence_based:
            return self._format_return("CANCEL", "Zero usage detected in the tracking period.", *metrics, confidence_label, is_presence_based, best_plan, breakeven_info, vrs, vrs_label)

        if confidence < 0.6 and cph_value > cancel_threshold and not is_presence_based:
            return self._format_return("VERIFY USAGE", "Low confidence in screen-time data. Verify actual usage before canceling.", *metrics, confidence_label, is_presence_based, best_plan, breakeven_info, vrs, vrs_label)

        if has_shift and shift_direction == "drop" and shift_magnitude > 2.0 and not is_presence_based:
            return self._format_return("WARNING: USAGE CLIFF", f"CUSUM detected a significant usage drop (magnitude: {shift_magnitude:.1f}σ). Monitor closely — this may indicate you're about to stop using {name}.", *metrics, confidence_label, is_presence_based, best_plan, breakeven_info, vrs, vrs_label)

        if is_binge and freq == "monthly" and category in ("entertainment", "gaming"):
            return self._format_return("SUBSCRIBE & CHURN", "Statistical binge detected — usage is heavily concentrated. Cancel now and only resubscribe when needed.", *metrics, confidence_label, is_presence_based, best_plan, breakeven_info, vrs, vrs_label)

        if cph_value > cancel_threshold and ai_data.get("is_multi_device"):
            return self._format_return("WARNING: VERIFY USAGE", f"Mobile CPH is high (${cph_value:.2f}/hr), but {name} is a TV/desktop app. Verify total household time.", *metrics, confidence_label, is_presence_based, best_plan, breakeven_info, vrs, vrs_label)

        if (best_plan == "lifetime" and pricing_tiers.get("lifetime", 0) > 0 and velocity >= 0.8):
            lifetime_price = pricing_tiers["lifetime"]
            be_months = breakeven_info.get("breakeven_months_lifetime", 0)
            if be_months > 0 and months_subscribed >= (be_months * 0.6):
                return self._format_return("SWITCH TO LIFETIME", f"Stable usage over {months_subscribed} months. Lifetime (${lifetime_price:.2f}) breaks even at month {be_months}. NPV analysis confirms this is the cheapest long-term option.", *metrics, confidence_label, is_presence_based, best_plan, breakeven_info, vrs, vrs_label)

        yearly_price = pricing_tiers.get("yearly", 0)
        monthly_price = pricing_tiers.get("monthly", 0)
        
        if (best_plan == "yearly" and yearly_price > 0 and monthly_price > 0 and freq == "monthly" and velocity >= 0.7):
            actual_yearly_monthly = yearly_price / 12
            actual_savings_pct = ((monthly_price - actual_yearly_monthly) / monthly_price) * 100
            if actual_savings_pct > 5:
                return self._format_return("UPGRADE TO ANNUAL", f"Yearly billing (${actual_yearly_monthly:.2f}/mo) saves {actual_savings_pct:.0f}% vs monthly (${monthly_price:.2f}/mo). Usage trend supports commitment.", *metrics, confidence_label, is_presence_based, best_plan, breakeven_info, vrs, vrs_label)

        if student_price > 0 and personal_burden_cost > (student_price + 0.05):
            return self._format_return("SWITCH TO STUDENT PLAN", f"Student tier (~${student_price:.2f}/mo) is cheaper than your current {freq} rate.", *metrics, confidence_label, is_presence_based, best_plan, breakeven_info, vrs, vrs_label)

        if cph_value > cancel_threshold:
            action = "DOWNGRADE TO FREE" if ai_data.get("has_free_tier") else "CANCEL"
            unit = "day" if is_presence_based else "hr"
            return self._format_return(action, f"Cost (${cph_value:.2f}/{unit}) exceeds your personal threshold (${cancel_threshold:.2f}).", *metrics, confidence_label, is_presence_based, best_plan, breakeven_info, vrs, vrs_label)

        if velocity < 0.50 and not is_presence_based:
            return self._format_return(f"WATCH {freq.upper()} (DECAYING)", f"Value is okay, but EMA trend shows usage declining (velocity: {velocity:.2f}).", *metrics, confidence_label, is_presence_based, best_plan, breakeven_info, vrs, vrs_label)

        if p_be > 0.80 and total_eff_hours > 5 and freq not in ["yearly", "lifetime"] and not is_binge:
            if student_price > 0 and personal_burden_cost <= (student_price + 0.50):
                return self._format_return(f"KEEP {freq.upper()}", "Already on the best price (Student Tier). Habit is locked in.", *metrics, confidence_label, is_presence_based, best_plan, breakeven_info, vrs, vrs_label)
            if best_plan and best_plan != freq:
                return self._format_return(f"UPGRADE TO {best_plan.upper()}", f"Habit is locked in ({p_be*100:.0f}% break-even prob). NPV analysis shows {best_plan} is the optimal plan.", *metrics, confidence_label, is_presence_based, best_plan, breakeven_info, vrs, vrs_label)
            return self._format_return(f"KEEP {freq.upper()}", f"Locked-in habit ({p_be*100:.0f}% break-even prob). Current plan is already optimal.", *metrics, confidence_label, is_presence_based, best_plan, breakeven_info, vrs, vrs_label)

        unit = "day" if is_presence_based else "hr"
        return self._format_return(f"KEEP {freq.upper()}", f"Satisfactory value (${cph_value:.2f}/{unit}).", *metrics, confidence_label, is_presence_based, best_plan, breakeven_info, vrs, vrs_label)

    def _format_return(self, action, reason, nmc, div, pbc, raw_hrs, wgt, eff_hrs, cph_val, vel, 
                       confidence_label, is_presence, best_plan, breakeven_info, vrs=0, vrs_label="High Risk"):
        return {
            "action": action, 
            "reason": reason, 
            "confidence_label": confidence_label,
            "is_presence": is_presence,
            "best_plan": best_plan,
            "breakeven_info": breakeven_info,
            "value_risk_score": vrs,
            "value_risk_label": vrs_label,
            "math": {
                "normalized_cost": nmc, 
                "divisor": div, 
                "personal_burden": pbc,
                "raw_hours": raw_hrs, 
                "weight": wgt, 
                "eff_hours": eff_hrs, 
                "cph": cph_val, 
                "velocity": vel
            }
        }


def analyze_screentime(app_name: str, cost: float, months_subscribed: int, weekly_hours: list[float], user_wage: float, style_multiplier: float = 0.10):
    """
    Main entry point for API:
    Analyzes single app screentime stats and returns the full risk/NPV report.
    """
    classifier = GeminiClassifier()
    ai_data = classifier.analyze_app(app_name, cost)
    
    analyzer = SubscriptionAnalyzer(hourly_wage=user_wage, style_multiplier=style_multiplier) 
    result = analyzer.evaluate(app_name, cost, weekly_hours, months_subscribed, ai_data)
    
    # Bundle the ai_data into the result so frontend can display what was found
    result["ai_found_data"] = ai_data
    
    return result


def analyze_screentime_batch(subscriptions: list, user_wage: float, style_multiplier: float = 0.10):
    """
    Batch entry point for API:
    Analyzes MULTIPLE subscriptions in parallel — all Gemini classify calls
    fire concurrently, then evaluations (pure math) run instantly.
    
    Each subscription dict should have: app_name, cost, months_subscribed, weekly_hours
    """
    classifier = GeminiClassifier()
    analyzer = SubscriptionAnalyzer(hourly_wage=user_wage, style_multiplier=style_multiplier)
    
    # --- Phase 1: Parallel Gemini classification ---
    def _classify_one(sub):
        app_name = sub["app_name"]
        cost = sub["cost"]
        ai_data = classifier.analyze_app(app_name, cost)
        return sub, ai_data
    
    classified = []
    with ThreadPoolExecutor(max_workers=min(len(subscriptions), 100)) as pool:
        futures = {pool.submit(_classify_one, sub): sub for sub in subscriptions}
        for future in as_completed(futures):
            try:
                sub, ai_data = future.result()
                classified.append((sub, ai_data))
            except Exception as e:
                sub = futures[future]
                # Fallback AI data if classification fails
                classified.append((sub, {
                    "frequency": "monthly", "category": "entertainment", "value_mode": "time_based",
                    "engagement_type": "active", "is_multi_device": False, "has_free_tier": False,
                    "is_shared_plan": False, "student_plan_price": 0,
                    "pricing_verified": False,
                    "pricing_tiers": {"monthly": 0, "yearly": 0, "lifetime": 0}
                }))
    
    # --- Phase 2: Evaluate all (pure math, instant) ---
    results = []
    for sub, ai_data in classified:
        result = analyzer.evaluate(
            sub["app_name"], sub["cost"],
            sub["weekly_hours"], sub["months_subscribed"],
            ai_data
        )
        result["ai_found_data"] = ai_data
        result["app_name"] = sub["app_name"]
        results.append(result)
    
    # --- Phase 3: Portfolio Analysis (cross-subscription intelligence) ---
    portfolio = analyze_portfolio(results)
    
    return {"results": results, "portfolio": portfolio}


def detect_exam_season(results: list):
    """
    6.6 Student Exam Season Advisory.
    Scans Google Calendar for exam/deadline keywords in the next 30 days.
    Cross-references with entertainment/gaming subscriptions from batch results.
    Returns an advisory alert (does NOT modify VRS scores).
    """
    from datetime import timezone
    
    EXAM_KEYWORDS = [
        'exam', 'test', 'quiz', 'final', 'midterm', 'mid-term',
        'assessment', 'assignment due', 'project due', 'submission',
        'presentation', 'defense', 'defence', 'lab practical', 'viva'
    ]
    
    PAUSABLE_CATEGORIES = {'entertainment', 'gaming'}
    
    try:
        from .calendar_engine import CalendarReader
        calendar = CalendarReader()
        # Only look 30 days ahead for exams
        events = calendar.get_upcoming_events(months_ahead=1)
    except Exception as e:
        print(f"[ExamDetection] Could not access calendar: {e}")
        return None
    
    # Find exam-like events
    exam_events = []
    for event in events:
        summary = event.get('summary', '').lower()
        description = event.get('description', '').lower()
        combined = summary + ' ' + description
        
        for keyword in EXAM_KEYWORDS:
            if keyword in combined:
                exam_events.append({
                    "name": event.get('summary', 'Unnamed Event'),
                    "date": event.get('start', ''),
                    "keyword_matched": keyword
                })
                break
    
    if not exam_events:
        return None
    
    # Find entertainment/gaming subscriptions from batch results
    pausable_subs = []
    total_pausable_cost = 0.0
    
    for r in results:
        category = r.get("ai_found_data", {}).get("category", "")
        if category in PAUSABLE_CATEGORIES:
            cost = r.get("math", {}).get("personal_burden", 0)
            pausable_subs.append({
                "name": r.get("app_name", "Unknown"),
                "category": category,
                "monthly_cost": round(cost, 2)
            })
            total_pausable_cost += cost
    
    if not pausable_subs:
        return {
            "exam_detected": True,
            "exam_count": len(exam_events),
            "exams": exam_events,
            "pausable_subscriptions": [],
            "total_monthly_savings": 0,
            "message": f"📚 {len(exam_events)} exam(s) detected in the next 30 days, but none of your subscriptions are entertainment or gaming."
        }
    
    sub_names = ", ".join(s["name"] for s in pausable_subs)
    
    return {
        "exam_detected": True,
        "exam_count": len(exam_events),
        "exams": exam_events,
        "pausable_subscriptions": pausable_subs,
        "total_monthly_savings": round(total_pausable_cost, 2),
        "message": f"🎓 {len(exam_events)} exam(s) detected in the next 30 days. Consider pausing {sub_names} to save ${total_pausable_cost:.2f}/mo during this period."
    }


def analyze_portfolio(results):
    """
    Phase 3: Portfolio Analysis
    
    Groups evaluated subscriptions by category, detects saturation,
    ranks within each category by value, and recommends consolidation.
    
    This is the cross-subscription intelligence that individual evaluation
    cannot provide — e.g., "you have 4 streaming subs, drop the worst 2."
    """
    if not results or len(results) < 2:
        return {"saturated_categories": 0, "total_potential_savings_monthly": 0, 
                "total_potential_savings_annual": 0, "category_insights": []}
    
    # --- Group by category ---
    categories = {}
    for r in results:
        cat = r.get("ai_found_data", {}).get("category", "other")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r)
    
    portfolio_insights = []
    
    for cat, subs in categories.items():
        if len(subs) < 2:
            continue  # No saturation with a single sub
        
        # Rank by CPH — lower = better value (more hours per dollar)
        ranked = sorted(subs, key=lambda s: s.get("math", {}).get("cph", float('inf')))
        
        total_monthly = sum(s.get("math", {}).get("personal_burden", 0) for s in subs)
        total_hours = sum(s.get("math", {}).get("raw_hours", 0) for s in subs)
        
        best = ranked[0]
        worst = ranked[-1]
        
        # Savings calculations: what if user keeps only top N?
        savings_keep_1 = sum(s.get("math", {}).get("personal_burden", 0) for s in ranked[1:])
        savings_drop_worst = worst.get("math", {}).get("personal_burden", 0)
        
        # Build ranked list for frontend
        ranked_list = []
        for i, s in enumerate(ranked):
            cph = s.get("math", {}).get("cph", 0)
            burden = s.get("math", {}).get("personal_burden", 0)
            ranked_list.append({
                "app_name": s.get("app_name", "Unknown"),
                "rank": i + 1,
                "cph": round(cph, 2),
                "monthly_cost": round(burden, 2),
                "raw_hours": round(s.get("math", {}).get("raw_hours", 0), 1),
                "action": s.get("action", "UNKNOWN"),
                "is_best_value": i == 0,
                "is_worst_value": i == len(ranked) - 1
            })
        
        insight = {
            "category": cat,
            "category_label": cat.replace("_", " ").title(),
            "subscription_count": len(subs),
            "is_saturated": True,
            "total_monthly_cost": round(total_monthly, 2),
            "total_weekly_hours": round(total_hours, 1),
            "ranked_subscriptions": ranked_list,
            "best_value": {
                "name": best.get("app_name", "Unknown"),
                "cph": round(best.get("math", {}).get("cph", 0), 2)
            },
            "worst_value": {
                "name": worst.get("app_name", "Unknown"),
                "cph": round(worst.get("math", {}).get("cph", 0), 2)
            },
            "savings_drop_worst": round(savings_drop_worst, 2),
            "savings_drop_worst_annual": round(savings_drop_worst * 12, 2),
            "savings_keep_best_only": round(savings_keep_1, 2),
            "savings_keep_best_only_annual": round(savings_keep_1 * 12, 2),
            "recommendation": (
                f"You have {len(subs)} {cat.replace('_', ' ')} subscriptions "
                f"costing ${total_monthly:.2f}/mo total. "
                f"{best.get('app_name', 'Unknown')} is your best value "
                f"at ${best.get('math', {}).get('cph', 0):.2f}/hr. "
                f"Dropping {worst.get('app_name', 'Unknown')} alone "
                f"saves ${savings_drop_worst:.2f}/mo (${savings_drop_worst * 12:.2f}/yr)."
            )
        }
        
        portfolio_insights.append(insight)
    
    # Sort by total cost (most expensive saturated categories first)
    portfolio_insights.sort(key=lambda x: x["total_monthly_cost"], reverse=True)
    
    total_potential_savings = sum(i["savings_drop_worst"] for i in portfolio_insights)
    
    return {
        "saturated_categories": len(portfolio_insights),
        "total_potential_savings_monthly": round(total_potential_savings, 2),
        "total_potential_savings_annual": round(total_potential_savings * 12, 2),
        "category_insights": portfolio_insights
    }

