import os
import math
import json
from dotenv import load_dotenv
from google import genai

# Load environment variables (Security Patch)
load_dotenv()

# ==========================================
# 1. GEMINI AI CLASSIFIER (SEARCH ENABLED)
# ==========================================
class GeminiClassifier:
    def __init__(self):
        # Securely fetch the key from the .env file
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("CRITICAL: GEMINI_API_KEY not found in your .env file.")
            
        self.client = genai.Client(api_key=api_key)
        
        # V3 UPGRADE: Now requests actual pricing tiers for NPV comparison
        # V3.1: Added pricing_verified hallucination guard
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
        try:
            response = self.client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                config={
                    "tools": [{"google_search": {}}], 
                    "system_instruction": self.system_rules,
                    "temperature": 0.0
                },
                contents=prompt
            )
            
            # --- THE PARSER FIX ---
            raw_text = response.text.strip()
            if raw_text.startswith("```json"): 
                raw_text = raw_text[7:]
            elif raw_text.startswith("```"): 
                raw_text = raw_text[3:]
                
            if raw_text.endswith("```"): 
                raw_text = raw_text[:-3]
            
            result = json.loads(raw_text.strip())
            
            # --- V3.1: HALLUCINATION GUARD ---
            # Cross-check: if Gemini says pricing is verified, validate that
            # the user's reported cost actually matches one of the returned tiers.
            pricing = result.get("pricing_tiers", {})
            verified = result.get("pricing_verified", False)
            tier_values = [v for v in pricing.values() if v and v > 0]
            
            if verified and tier_values:
                # Check if user's cost is close to any returned tier (within 20% tolerance)
                cost_float = float(cost)
                matches_any_tier = any(
                    abs(cost_float - tier) / max(tier, 0.01) < 0.20 
                    for tier in tier_values if isinstance(tier, (int, float)) and tier > 0
                )
                if not matches_any_tier:
                    print(f"  ⚠ Warning: Your cost (${cost}) doesn't match any returned tier. Prices may be inaccurate.")
                    result["pricing_verified"] = False
            elif not verified:
                # Gemini admitted it couldn't find pricing — zero out tiers
                result["pricing_tiers"] = {"monthly": 0, "yearly": 0, "lifetime": 0}
                print(f"  ⚠ Warning: Gemini could not verify pricing for {app_name}. Plan optimization disabled.")
            
            return result
            
        except Exception as e:
            print(f"Gemini API Error: {e}")
            return {
                "frequency": "monthly", "category": "entertainment", "value_mode": "time_based",
                "engagement_type": "active", "is_multi_device": False, "has_free_tier": False, 
                "is_shared_plan": False, "student_plan_price": 0,
                "pricing_verified": False,
                "pricing_tiers": {"monthly": 0, "yearly": 0, "lifetime": 0}
            }
 
# ==========================================
# 2. THE MATHEMATICAL ENGINE (V3)
# ==========================================

class SubscriptionAnalyzer:
    def __init__(self, hourly_wage, style_multiplier=0.10):
        self.hourly_wage = hourly_wage
        
        # ---------------------------------------------------------
        # DERIVATION 1: The Discretionary Time Threshold
        # CPH limit = hourly_wage × style_multiplier
        # Strict (7%), Balanced (10%), Lenient (15%)
        # ---------------------------------------------------------
        self.base_cancel_threshold_cph = hourly_wage * style_multiplier 
        
        # ---------------------------------------------------------
        # DERIVATION 2: SaaS Churn Rate (Gamma Map) — V3: NOW WIRED TO BREAK-EVEN
        # Represents the base exponential decay (churn probability) by software sector.
        # Lower gamma = more "sticky" (user less likely to churn).
        # ---------------------------------------------------------
        self.gamma_map = {"utility": 0.05, "productivity": 0.10, "entertainment": 0.20, "gaming": 0.35}
        
        # ---------------------------------------------------------
        # DERIVATION 3: Time Normalization (Duration Map)
        # Converts all billing cycles into a flat Monthly Cost (Base 1.0).
        # ---------------------------------------------------------
        self.duration_map = {"weekly": 0.23, "monthly": 1.0, "quarterly": 3.0, "biannual": 6.0, "yearly": 12.0}
        
        # ---------------------------------------------------------
        # DERIVATION 4: Cognitive Load Theory (Engagement Weights)
        # - Passive (0.33): "Multitasking Divisor" — 100% / 3 concurrent tasks.
        # - Active (1.00): Control Group. 1 hour = 1 hour of utility.
        # - Generative (1.50): "ROI Premium". Generative tools create compounding assets.
        # ---------------------------------------------------------
        self.engagement_weights = {"passive": 0.33, "active": 1.0, "generative": 1.5}

        # ---------------------------------------------------------
        # V3: EMA Smoothing Factor
        # Alpha controls how much weight recent data gets.
        # 0.3 = balanced between stability and reactivity.
        # ---------------------------------------------------------
        self.ema_alpha = 0.3

    # ==================================================================
    # V3 NEW: Exponential Moving Average (replaces crude 2-half velocity)
    # ==================================================================
    def compute_ema(self, data_points):
        """
        Computes the Exponential Moving Average over a time series.
        EMA_t = α × value_t + (1 − α) × EMA_(t−1)
        
        Returns the final EMA value (trend-weighted toward recent data).
        """
        if not data_points:
            return 0.0
        ema = data_points[0]
        for value in data_points[1:]:
            ema = self.ema_alpha * value + (1 - self.ema_alpha) * ema
        return ema

    def compute_velocity_ema(self, data_points):
        """
        Velocity as ratio of EMA trend to overall average.
        > 1.0 = usage trending UP (recent weeks are above average)
        < 1.0 = usage trending DOWN (recent weeks are below average)
        = 1.0 = perfectly stable
        """
        if not data_points or sum(data_points) == 0:
            return 1.0
        ema = self.compute_ema(data_points)
        avg = sum(data_points) / len(data_points)
        return ema / avg if avg > 0 else 1.0

    # ==================================================================
    # V3 NEW: CUSUM Change-Point Detection
    # Detects sudden, significant shifts in usage patterns.
    # ==================================================================
    def detect_cusum_shift(self, data_points, threshold_factor=1.5):
        """
        Cumulative Sum (CUSUM) control chart for detecting abrupt usage changes.
        
        How it works:
        1. Calculate the mean and std of the data.
        2. Walk through each data point, accumulating deviations from the mean.
        3. If the cumulative deviation exceeds a threshold (1.5× std), flag a shift.

        Returns: (has_shift, shift_direction, shift_magnitude)
        - has_shift: True if a significant change was detected
        - shift_direction: "drop" (usage falling) or "surge" (usage spiking)
        - shift_magnitude: How dramatic the change is (in units of standard deviation)
        """
        if len(data_points) < 3:
            return False, None, 0.0
        
        mean = sum(data_points) / len(data_points)
        std = (sum((x - mean) ** 2 for x in data_points) / len(data_points)) ** 0.5
        
        if std == 0:
            return False, None, 0.0
        
        threshold = threshold_factor * std
        cusum_pos = 0.0  # Tracks upward shifts
        cusum_neg = 0.0  # Tracks downward shifts
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

    # ==================================================================
    # V3 NEW: Statistical Binge Detection (replaces arbitrary 70% cutoff)
    # ==================================================================
    def detect_binge(self, data_points):
        """
        Uses z-score + concentration to detect binge patterns.
        
        A "binge" means:
        1. The peak week has a z-score > 1.5 (statistically unusual)
        2. The peak week accounts for > 40% of total usage (concentrated)
        
        This is more robust than the old "70% of total" rule because it adapts
        to the distribution of the data rather than using a fixed cutoff.
        """
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

    # ==================================================================
    # V3 NEW: Lifetime Breakeven Calculator (Net Present Value)
    # ==================================================================
    def compute_plan_recommendation(self, pricing_tiers, months_subscribed, velocity, discount_rate=0.005):
        """
        Net Present Value (NPV) comparison of subscription plans.
        
        Projects the user's future usage horizon based on their velocity (trend),
        then calculates the total cost of each plan over that horizon,
        discounted for the time-value of money.

        NPV_monthly = Σ (monthly_price / (1 + r)^t) for t = 1 to projected_months
        NPV_yearly  = Σ (yearly_price / (1 + r)^(12*y)) for each year
        NPV_lifetime = lifetime_price (paid once, today)

        Returns: (best_plan, plan_costs, breakeven_info)
        """
        monthly_price = pricing_tiers.get("monthly", 0)
        yearly_price = pricing_tiers.get("yearly", 0)
        lifetime_price = pricing_tiers.get("lifetime", 0)
        
        # Project usage horizon based on EMA velocity (usage trend)
        if velocity < 0.3:
            projected_months = 3    # Likely to churn soon
        elif velocity < 0.5:
            projected_months = 6    # Declining usage
        elif velocity < 0.8:
            projected_months = 12   # Moderate user
        else:
            projected_months = 36   # Stable long-term user
        
        # Calculate NPV for each available plan
        costs = {}
        
        if monthly_price > 0:
            npv_monthly = sum(
                monthly_price / (1 + discount_rate) ** t 
                for t in range(1, projected_months + 1)
            )
            costs["monthly"] = round(npv_monthly, 2)
        
        if yearly_price > 0:
            years_needed = math.ceil(projected_months / 12)
            npv_yearly = sum(
                yearly_price / (1 + discount_rate) ** (12 * y) 
                for y in range(1, years_needed + 1)
            )
            costs["yearly"] = round(npv_yearly, 2)
        
        if lifetime_price > 0:
            costs["lifetime"] = lifetime_price  # One-time cost, no discounting needed
        
        if not costs:
            return None, {}, {}
        
        best_plan = min(costs, key=costs.get)
        
        # Calculate breakeven month for lifetime vs monthly
        breakeven_months_lifetime = 0
        if lifetime_price > 0 and monthly_price > 0:
            breakeven_months_lifetime = math.ceil(lifetime_price / monthly_price)
        
        # Calculate breakeven month for yearly vs monthly
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
        # ---------------------------------------------------------
        # DERIVATION 5: The "Conservative Floor" for Shared Plans
        # ---------------------------------------------------------
        name_lower = app_name.lower()
        if "duo" in name_lower or "couple" in name_lower: return 2
        elif "family" in name_lower or "party" in name_lower or "group" in name_lower: return 4
        return 3 if ai_shared_flag else 1

    def evaluate(self, name, raw_cost, weekly_hours, months_subscribed, ai_data):
        total_raw_hours = sum(weekly_hours)
        
        is_presence_based = (ai_data.get("value_mode") == "presence_based")
        is_outcome_based = (ai_data.get("value_mode") == "outcome_based")
        category = ai_data.get("category", "entertainment")

        # --- 1. Universal Normalization & Cost Amortization ---
        freq = ai_data.get("frequency", "monthly").lower()
        time_multiplier = self.duration_map.get(freq, 1.0)
        normalized_monthly_cost = float(raw_cost) / time_multiplier
        
        household_divisor = self.get_household_divisor(name, ai_data.get("is_shared_plan"))
        personal_burden_cost = normalized_monthly_cost / household_divisor

        # --- 2. Cognitive Load Weighing & VALUE MODES ---
        weight = self.engagement_weights.get(ai_data.get("engagement_type", "active"), 1.0)
        
        if is_presence_based:
            effective_days = 30.0
            cph_value = personal_burden_cost / effective_days
            total_eff_hours = effective_days
            velocity = 1.0  # Presence apps are always-on by definition
            cancel_threshold = self.base_cancel_threshold_cph * 1.5
        elif is_outcome_based:
            # ---------------------------------------------------------
            # V3.2: Outcome-Based Value Mode (Adobe, Figma, etc.)
            # Creative/professional tools derive value from OUTPUT, not TIME.
            # A 2-hour Figma session can produce a $500 design.
            # We force generative weight (1.5) and relax the cancel threshold
            # to avoid penalizing low-hour but high-value usage.
            # ---------------------------------------------------------
            weight = max(weight, 1.5)  # Ensure at least generative-level weight
            total_eff_hours = total_raw_hours * weight
            cph_value = personal_burden_cost / total_eff_hours if total_eff_hours > 0 else float('inf')
            velocity = self.compute_velocity_ema(weekly_hours)
            cancel_threshold = self.base_cancel_threshold_cph * 2.0  # 2x more lenient for professional tools
        else:
            total_eff_hours = total_raw_hours * weight
            cph_value = personal_burden_cost / total_eff_hours if total_eff_hours > 0 else float('inf')
            
            # V3: EMA-based velocity (replaces crude front-half / back-half split)
            velocity = self.compute_velocity_ema(weekly_hours)
            
            cancel_threshold = self.base_cancel_threshold_cph

        # --- 3. V3: CUSUM Change-Point Detection ---
        has_shift, shift_direction, shift_magnitude = self.detect_cusum_shift(weekly_hours)

        # --- 4. V3: Statistical Binge Detection (replaces 70% arbitrary cutoff) ---
        is_binge = self.detect_binge(weekly_hours)

        # --- 5. Confidence Score ---
        confidence = 1.0

        if ai_data.get("is_multi_device"):
            confidence -= 0.3
        if total_raw_hours < 2 and not is_presence_based:
            confidence -= 0.2
        if velocity < 0.2 or velocity > 2.0:
            confidence -= 0.1
        if len(weekly_hours) < 4:
            confidence -= 0.15  # V3: Penalize very short data windows

        confidence = max(0.3, confidence)

        if confidence >= 0.8:
            confidence_label = "HIGH"
        elif confidence >= 0.6:
            confidence_label = "MODERATE"
        else:
            confidence_label = "LOW"

        # ---------------------------------------------------------
        # DERIVATION 6: V3 FIX — Category-Aware Break-Even Probability
        # 
        # BUG #1 FIX: gamma_map is now USED here.
        # BUG #2 FIX: The decay constant scales by category AND subscription age.
        #
        # Formula: p_be = min(velocity, 1.0) × e^(−γ / months)
        #
        # - γ (gamma) = category-specific churn rate from gamma_map
        # - months = how long the user has been subscribed
        # - Longer subscriptions → smaller exponent → higher p_be (more likely to keep)
        # - Gaming (γ=0.35) decays much faster than Utility (γ=0.05)
        # ---------------------------------------------------------
        gamma = self.gamma_map.get(category, 0.20)
        time_factor = 1.0 / max(months_subscribed, 1)
        # V3.2: Allow growing usage (velocity > 1.0) to mildly boost break-even prob
        p_be = min(min(velocity, 1.5) * math.exp(-gamma * time_factor), 1.0)

        # ---------------------------------------------------------
        # V3: Plan Optimization using NPV (replaces 20% annual guess)
        # ---------------------------------------------------------
        pricing_tiers = ai_data.get("pricing_tiers", {"monthly": 0, "yearly": 0, "lifetime": 0})
        best_plan, plan_costs, breakeven_info = self.compute_plan_recommendation(
            pricing_tiers, months_subscribed, velocity
        )
        
        student_price = ai_data.get("student_plan_price", 0)

        # Build metrics tuple
        metrics = (normalized_monthly_cost, household_divisor, personal_burden_cost, 
                   total_raw_hours, weight, total_eff_hours, cph_value, velocity)

        # ==========================================
        # THE LOGIC GATES (V3 Enhanced)
        # ==========================================

        # Gate 0: Dead Weight
        if total_raw_hours == 0 and not is_presence_based:
            return self._format_return(
                "CANCEL", "Zero usage detected in the tracking period.",
                *metrics, confidence_label, is_presence_based, best_plan, breakeven_info)

        # Gate 1: Confidence Safety Net (protects against false cancels)
        if confidence < 0.6 and cph_value > cancel_threshold and not is_presence_based:
            return self._format_return(
                "VERIFY USAGE", "Low confidence in screen-time data. Verify actual usage before canceling.",
                *metrics, confidence_label, is_presence_based, best_plan, breakeven_info)

        # Gate 2 (V3 NEW): CUSUM Cliff Drop Detector
        if has_shift and shift_direction == "drop" and shift_magnitude > 2.0 and not is_presence_based:
            return self._format_return(
                "WARNING: USAGE CLIFF",
                f"CUSUM detected a significant usage drop (magnitude: {shift_magnitude:.1f}σ). "
                f"Monitor closely — this may indicate you're about to stop using {name}.",
                *metrics, confidence_label, is_presence_based, best_plan, breakeven_info)

        # Gate 3: Binge Catcher (V3: now statistical z-score + concentration)
        if is_binge and freq == "monthly" and category in ("entertainment", "gaming"):
            return self._format_return(
                "SUBSCRIBE & CHURN",
                "Statistical binge detected — usage is heavily concentrated. "
                "Cancel now and only resubscribe when needed.",
                *metrics, confidence_label, is_presence_based, best_plan, breakeven_info)

        # Gate 4: Multi-Device Safety Net
        if cph_value > cancel_threshold and ai_data.get("is_multi_device"):
            return self._format_return(
                "WARNING: VERIFY USAGE",
                f"Mobile CPH is high (${cph_value:.2f}/hr), but {name} is a TV/desktop app. Verify total household time.",
                *metrics, confidence_label, is_presence_based, best_plan, breakeven_info)

        # Gate 5 (V3 NEW): Lifetime Plan Optimizer — THE LAMPA USE CASE
        if (best_plan == "lifetime" 
            and pricing_tiers.get("lifetime", 0) > 0 
            and velocity >= 0.8):
            
            lifetime_price = pricing_tiers["lifetime"]
            be_months = breakeven_info.get("breakeven_months_lifetime", 0)
            
            # Recommend if user is within 60% of breakeven point OR already past it
            if be_months > 0 and months_subscribed >= (be_months * 0.6):
                return self._format_return(
                    "SWITCH TO LIFETIME",
                    f"Stable usage over {months_subscribed} months. "
                    f"Lifetime (${lifetime_price:.2f}) breaks even at month {be_months}. "
                    f"NPV analysis confirms this is the cheapest long-term option.",
                    *metrics, confidence_label, is_presence_based, best_plan, breakeven_info)

        # Gate 6 (V3 UPGRADED): Annual Upgrade using REAL pricing from Gemini
        yearly_price = pricing_tiers.get("yearly", 0)
        monthly_price = pricing_tiers.get("monthly", 0)
        
        if (best_plan == "yearly" 
            and yearly_price > 0 and monthly_price > 0 
            and freq == "monthly" 
            and velocity >= 0.7):
            
            actual_yearly_monthly = yearly_price / 12
            actual_savings_pct = ((monthly_price - actual_yearly_monthly) / monthly_price) * 100
            
            if actual_savings_pct > 5:  # Only recommend if savings exceed 5%
                return self._format_return(
                    "UPGRADE TO ANNUAL",
                    f"Yearly billing (${actual_yearly_monthly:.2f}/mo) saves {actual_savings_pct:.0f}% "
                    f"vs monthly (${monthly_price:.2f}/mo). Usage trend supports commitment.",
                    *metrics, confidence_label, is_presence_based, best_plan, breakeven_info)

        # Gate 7: Student Plan Resolver
        if student_price > 0 and personal_burden_cost > (student_price + 0.05):
            return self._format_return(
                "SWITCH TO STUDENT PLAN",
                f"Student tier (~${student_price:.2f}/mo) is cheaper than your current {freq} rate.",
                *metrics, confidence_label, is_presence_based, best_plan, breakeven_info)

        # Gate 8: Value/Cost Threshold
        if cph_value > cancel_threshold:
            action = "DOWNGRADE TO FREE" if ai_data.get("has_free_tier") else "CANCEL"
            unit = "day" if is_presence_based else "hr"
            return self._format_return(
                action,
                f"Cost (${cph_value:.2f}/{unit}) exceeds your personal threshold (${cancel_threshold:.2f}).",
                *metrics, confidence_label, is_presence_based, best_plan, breakeven_info)

        # Gate 9: Habit Decay (V3: uses EMA-based velocity)
        if velocity < 0.50 and not is_presence_based:
            return self._format_return(
                f"WATCH {freq.upper()} (DECAYING)",
                f"Value is okay, but EMA trend shows usage declining (velocity: {velocity:.2f}).",
                *metrics, confidence_label, is_presence_based, best_plan, breakeven_info)

        # Gate 10: Stable Keep / Plan Upgrade Shield
        if p_be > 0.80 and total_eff_hours > 5 and freq not in ["yearly", "lifetime"] and not is_binge:
            if student_price > 0 and personal_burden_cost <= (student_price + 0.50):
                return self._format_return(
                    f"KEEP {freq.upper()}",
                    "Already on the best price (Student Tier). Habit is locked in.",
                    *metrics, confidence_label, is_presence_based, best_plan, breakeven_info)
            
            # Check if NPV suggests a better plan exists
            if best_plan and best_plan != freq:
                return self._format_return(
                    f"UPGRADE TO {best_plan.upper()}",
                    f"Habit is locked in ({p_be*100:.0f}% break-even prob). "
                    f"NPV analysis shows {best_plan} is the optimal plan.",
                    *metrics, confidence_label, is_presence_based, best_plan, breakeven_info)
            
            return self._format_return(
                f"KEEP {freq.upper()}",
                f"Locked-in habit ({p_be*100:.0f}% break-even prob). Current plan is already optimal.",
                *metrics, confidence_label, is_presence_based, best_plan, breakeven_info)

        unit = "day" if is_presence_based else "hr"
        return self._format_return(
            f"KEEP {freq.upper()}", f"Satisfactory value (${cph_value:.2f}/{unit}).",
            *metrics, confidence_label, is_presence_based, best_plan, breakeven_info)

    def _format_return(self, action, reason, nmc, div, pbc, raw_hrs, wgt, eff_hrs, cph_val, vel, 
                       confidence_label, is_presence, best_plan, breakeven_info):
        """Standardized response format — V3 includes plan optimization data."""
        return {
            "action": action, 
            "reason": reason, 
            "confidence_label": confidence_label,
            "is_presence": is_presence,
            "best_plan": best_plan,
            "breakeven_info": breakeven_info,
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
    
# ==========================================
# 3. INTERACTIVE CLI (V3)
# ==========================================

def run_app():
    print("=========================================")
    print("   StatementSense Active Terminal (V3)   ")
    print("=========================================")
    
    try: 
        classifier = GeminiClassifier()
    except ValueError as e: 
        print(e)
        return

    # V2 Feature: Global Preference Onboarding
    print("\nBefore we begin, StatementSense needs your baseline.")
    while True:
        try:
            wage_input = input("What is your estimated hourly wage? (e.g., 20): $")
            user_wage = float(wage_input)
            if user_wage <= 0: 
                print("Wage must be greater than zero. Try again.")
                continue
            break
        except ValueError: 
            print("Please enter a valid number.")

    print("\nWhat is your budgeting style?")
    print("1. Strict (Ruthless cutting - 7% threshold)")
    print("2. Balanced (Normal - 10% threshold)")
    print("3. Lenient (Lifestyle-first - 15% threshold)")
    
    style_map = {"1": 0.07, "2": 0.10, "3": 0.15}
    while True:
        style_choice = input("Choose 1, 2, or 3: ")
        style_multiplier = style_map.get(style_choice)
        if style_multiplier: 
            break
        print("Invalid choice. Enter 1, 2, or 3.")

    analyzer = SubscriptionAnalyzer(hourly_wage=user_wage, style_multiplier=style_multiplier) 
    print(f"\n[Settings Saved: Baseline set to ${user_wage:.2f}/hr. Core Threshold is ${analyzer.base_cancel_threshold_cph:.2f}/hr]")
    
    while True:
        app_name = input("\nEnter the App Name (or 'q' to quit): ")
        if app_name.lower() == 'q': break
        
        try:
            cost = float(input(f"Enter the price you paid for {app_name} (e.g., 14.99): $"))
            
            # V3: Ask how long they've been subscribed (for NPV breakeven)
            months_sub = int(input(f"How many months have you been subscribed to {app_name}? "))
            
            print("Enter screen time (in hours) for the last 4 weeks:")
            w1 = float(input("  Week 1 (oldest):      ")) 
            w2 = float(input("  Week 2:               "))
            w3 = float(input("  Week 3:               "))
            w4 = float(input("  Week 4 (most recent): "))
        except ValueError:
            print("Please enter valid numbers.")
            continue
            
        weekly_hours = [w1, w2, w3, w4]
        if any(h < 0 for h in weekly_hours):
            print("  ⚠ Negative hours detected — clamped to 0.")
            weekly_hours = [max(0, h) for h in weekly_hours]
        print("\n[StatementSense V3 is analyzing...]")
        
        # Step 1: Gemini fetches real-world data + pricing tiers via Google Search
        ai_data = classifier.analyze_app(app_name, cost)
        
        # Step 2: Mathematical Analysis (V3 Engine)
        result = analyzer.evaluate(app_name, cost, weekly_hours, months_sub, ai_data)
        m = result["math"]
        
        is_presence = result.get("is_presence", False)
        
        print("\n--- BEHAVIORAL MATH BREAKDOWN ---")
        print(f"1. Cost Split:    ${m['normalized_cost']:.2f}/mo split {m['divisor']} ways = ${m['personal_burden']:.2f} (Your Burden)")
        
        if is_presence:
            print(f"2. Engagement:    Presence-Based Utility (Normalized to 30 Days)")
            print(f"3. Value Score:   Calculated Cost Per Day is ${m['cph']:.2f}/day")
        else:
            print(f"2. Engagement:    {m['raw_hours']:.1f} Total Hrs x {m['weight']} weight = {m['eff_hours']:.1f} Eff. Hours")
            print(f"3. Value Score:   Calculated Cost Per Hour is ${m['cph']:.2f}/hr")
        
        # V3: Show EMA velocity
        vel = m['velocity']
        if vel > 1.05:
            trend_label = "↑ INCREASING"
        elif vel < 0.95:
            trend_label = "↓ DECLINING"
        else:
            trend_label = "→ STABLE"
        print(f"4. EMA Velocity:  {vel:.2f} ({trend_label})")
        
        # V3: Show Plan Optimization (NPV) if pricing data exists AND is verified
        breakeven = result.get("breakeven_info", {})
        best = result.get("best_plan")
        pricing_verified = ai_data.get("pricing_verified", False)
        pricing = ai_data.get("pricing_tiers", {})
        
        if best and breakeven and breakeven.get("plan_costs_npv") and pricing_verified:
            print(f"\n--- PLAN OPTIMIZATION (NPV Analysis) ---")
            print(f"Source:            Verified via Google Search ✓")
            print(f"Months Subscribed: {breakeven.get('months_subscribed', '?')}")
            print(f"Projected Horizon: {breakeven.get('projected_months', '?')} months")
            
            # Show actual tier prices AND NPV projected totals
            print(f"\n  {'Plan':>10}  {'Tier Price':>12}  {'Projected Cost':>15}")
            print(f"  {'─'*10}  {'─'*12}  {'─'*15}")
            
            npv_costs = breakeven.get("plan_costs_npv", {})
            for plan, npv_val in sorted(npv_costs.items(), key=lambda x: x[1]):
                tier_price = pricing.get(plan, 0)
                if plan == "monthly":
                    price_label = f"${tier_price:.2f}/mo"
                elif plan == "yearly":
                    price_label = f"${tier_price:.2f}/yr"
                elif plan == "lifetime":
                    price_label = f"${tier_price:.2f}"
                else:
                    price_label = f"${tier_price:.2f}"
                
                marker = " ← BEST" if plan == best else ""
                npv_label = f"${npv_val:.2f}"
                print(f"  {plan.capitalize():>10}  {price_label:>12}  {npv_label:>15}{marker}")
            
            be_lt = breakeven.get("breakeven_months_lifetime", 0)
            if be_lt > 0:
                months_so_far = breakeven.get("months_subscribed", 0)
                print(f"\n  Lifetime Breakeven: Month {be_lt} (you're at month {months_so_far})")
        
        elif not pricing_verified and any(v > 0 for v in pricing.values()):
            print(f"\n--- PLAN OPTIMIZATION ---")
            print(f"  ⚠ Pricing could not be verified. Plan comparison disabled.")
            print(f"  Tip: Double-check the app's official pricing and re-run.")
        
        print("\n--- SYSTEM RECOMMENDATION ---")
        print(f"App:          {app_name}")
        print(f"Category:     {ai_data.get('category', 'unknown').title()}")
        print(f"Value Mode:   {ai_data.get('value_mode', 'time_based').replace('_', ' ').title()}")
        print(f"Multi-Device: {'Yes' if ai_data.get('is_multi_device') else 'No'}")
        print(f"ACTION:       {result['action']} ({result['confidence_label']} Confidence)")
        print(f"DETAILS:      {result['reason']}")
        print("-" * 40)

if __name__ == "__main__":
    run_app()
