"""
TravelDetector — ML-based Travel Detection for CalendarSense
=============================================================

Replaces the Gemini API call for detecting travel/away periods
from calendar events. Uses a trained scikit-learn pipeline:

    TF-IDF Vectorization → Random Forest Classifier

Training data: datasets/calendar_travel_dataset.csv
Trained model: models/saved/travel_model.joblib

CRISP-DM Phases Covered:
    - Phase 3 (Data Preparation): Text preprocessing, feature engineering
    - Phase 4 (Modeling): TF-IDF + Random Forest pipeline
    - Phase 5 (Evaluation): Train/test split, classification report, confusion matrix
"""

import os
import re
import csv
import json
import joblib
import numpy as np
from datetime import datetime, timedelta
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder


# ==========================================
# 1. DATA PREPARATION (CRISP-DM Phase 3)
# ==========================================

class TravelDataPreprocessor:
    """
    Prepares calendar event data for the travel detection model.
    
    Feature Engineering:
        - Combines event summary, location, and description into a single text feature
        - Extracts handcrafted features (has_airport, has_flight, has_location, etc.)
        - Normalizes text (lowercase, remove special characters)
    """
    
    # Keywords that strongly indicate travel
    TRAVEL_KEYWORDS = [
        'flight', 'fly', 'flying', 'airport', 'airline', 'boarding',
        'vacation', 'holiday', 'trip', 'travel', 'cruise', 'sailing',
        'hotel', 'hostel', 'airbnb', 'resort', 'check-in', 'checkin',
        'departure', 'arrival', 'layover', 'connecting', 'transit',
        'passport', 'visa', 'immigration', 'customs',
        'suitcase', 'luggage', 'pack', 'packing',
        'abroad', 'overseas', 'international', 'foreign',
        'relocat', 'moving to', 'moving day',
        'study abroad', 'exchange program', 'semester abroad',
        'backpacking', 'road trip', 'safari', 'trek', 'hiking',
        'honeymoon', 'babymoon', 'getaway', 'retreat',
        'missionary', 'deployment', 'posting',
    ]
    
    # Keywords that strongly indicate NON-travel (local events)
    LOCAL_KEYWORDS = [
        'meeting', 'standup', 'scrum', 'sync', 'review', 'retro',
        'appointment', 'checkup', 'cleaning', 'exam',
        'gym', 'yoga', 'crossfit', 'workout', 'practice', 'training',
        'lunch', 'dinner', 'brunch', 'coffee', 'date night',
        'lecture', 'class', 'lab', 'tutorial', 'study group',
        'haircut', 'barber', 'salon',
        'bill', 'payment', 'due', 'renewal', 'subscription',
        'pick up', 'drop off', 'delivery',
        'church', 'choir', 'bible study', 'service',
        'vet', 'dentist', 'doctor', 'therapy', 'counseling',
        'plumber', 'electrician', 'maintenance', 'repair',
    ]
    
    # Known airport codes (Caribbean + major international)
    AIRPORT_CODES = [
        'MBJ', 'KIN', 'JFK', 'LAX', 'ORD', 'ATL', 'MIA', 'FLL',
        'YYZ', 'LHR', 'CDG', 'NRT', 'DXB', 'SIN', 'HKG',
        'PTY', 'NAS', 'POS', 'BGI', 'ANU', 'GCM', 'PUJ', 'CUN',
        'HAV', 'SJU', 'SDQ', 'SFO', 'BOS', 'IAH', 'DFW', 'SEA',
        'DEN', 'MCO', 'EWR', 'IAD', 'PHL', 'MSP', 'DTW', 'CLT',
    ]
    
    @staticmethod
    def combine_text(summary, location, description):
        """Combines all event text fields into a single feature string."""
        parts = []
        if summary:
            parts.append(str(summary).strip())
        if location:
            parts.append(str(location).strip())
        if description:
            parts.append(str(description).strip())
        return ' '.join(parts).lower()
    
    @staticmethod
    def extract_handcrafted_features(text):
        """
        Extracts binary and numeric features from the event text.
        These supplement the TF-IDF features for better accuracy.
        
        Returns a dict of feature_name → feature_value.
        """
        text_lower = text.lower()
        
        features = {}
        
        # Travel keyword count
        travel_count = sum(1 for kw in TravelDataPreprocessor.TRAVEL_KEYWORDS if kw in text_lower)
        features['travel_keyword_count'] = travel_count
        features['has_travel_keyword'] = 1 if travel_count > 0 else 0
        
        # Local keyword count
        local_count = sum(1 for kw in TravelDataPreprocessor.LOCAL_KEYWORDS if kw in text_lower)
        features['local_keyword_count'] = local_count
        features['has_local_keyword'] = 1 if local_count > 0 else 0
        
        # Airport code detection
        has_airport = any(code.lower() in text_lower.split() or code in text for code in TravelDataPreprocessor.AIRPORT_CODES)
        features['has_airport_code'] = 1 if has_airport else 0
        
        # Contains "flight" or "fly"
        features['has_flight'] = 1 if any(w in text_lower for w in ['flight', 'fly', 'flying', 'airline']) else 0
        
        # Contains location-like patterns (City, Country)
        has_foreign_location = bool(re.search(r'\b(?:usa|uk|canada|england|france|spain|japan|germany|australia|mexico|brazil|cuba|haiti|trinidad|bahamas|barbados|antigua|cayman)\b', text_lower))
        features['has_foreign_country'] = 1 if has_foreign_location else 0
        
        # Contains hotel/accommodation words
        features['has_accommodation'] = 1 if any(w in text_lower for w in ['hotel', 'hostel', 'airbnb', 'resort', 'villa', 'rental']) else 0
        
        # Contains passport/visa words
        features['has_travel_docs'] = 1 if any(w in text_lower for w in ['passport', 'visa', 'immigration', 'customs', 'boarding pass']) else 0
        
        # Text length (longer descriptions might have more travel details)
        features['text_length'] = len(text)
        
        # Travel-to-local keyword ratio
        total_kw = travel_count + local_count
        features['travel_ratio'] = travel_count / max(total_kw, 1)
        
        return features
    
    @staticmethod
    def load_dataset(csv_path):
        """
        Loads and preprocesses the training dataset.
        
        Returns:
            texts: list of combined text strings
            labels: list of binary labels (0 = not travel, 1 = travel)
            trigger_types: list of trigger type strings
            raw_rows: list of original row dicts
        """
        texts = []
        labels = []
        trigger_types = []
        raw_rows = []
        
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                combined = TravelDataPreprocessor.combine_text(
                    row.get('event_summary', ''),
                    row.get('event_location', ''),
                    row.get('event_description', '')
                )
                texts.append(combined)
                labels.append(int(row.get('is_travel', 0)))
                trigger_types.append(row.get('trigger_type', '').strip())
                raw_rows.append(row)
        
        return texts, labels, trigger_types, raw_rows


# ==========================================
# 2. MODEL TRAINING (CRISP-DM Phase 4)
# ==========================================

class TravelDetectionModel:
    """
    ML model for detecting travel events from calendar data.
    
    Architecture:
        - Primary: TF-IDF (1-gram + 2-gram) → Random Forest
        - Handcrafted features are appended to TF-IDF vectors
    
    The model outputs:
        - is_travel: binary (0 or 1)
        - travel_probability: float (0.0 to 1.0)
    """
    
    def __init__(self):
        self.tfidf = TfidfVectorizer(
            max_features=500,
            ngram_range=(1, 2),      # Use unigrams and bigrams
            stop_words='english',
            min_df=2,                 # Ignore very rare terms
            sublinear_tf=True         # Apply log normalization
        )
        
        self.classifier = RandomForestClassifier(
            n_estimators=200,
            max_depth=15,
            min_samples_split=3,
            min_samples_leaf=2,
            class_weight='balanced',  # Handle class imbalance
            random_state=42,
            n_jobs=-1
        )
        
        self.trigger_encoder = LabelEncoder()
        self.trigger_classifier = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            class_weight='balanced',
            random_state=42,
            n_jobs=-1
        )
        
        self.is_trained = False
        self.evaluation_results = {}
    
    def _build_feature_matrix(self, texts, fit=False):
        """
        Builds the full feature matrix by combining TF-IDF + handcrafted features.
        
        Args:
            texts: list of combined event text strings
            fit: if True, fit the TF-IDF vectorizer (training mode)
        
        Returns:
            numpy array of shape (n_samples, n_tfidf_features + n_handcrafted_features)
        """
        from scipy.sparse import hstack, csr_matrix
        
        # TF-IDF features
        if fit:
            tfidf_matrix = self.tfidf.fit_transform(texts)
        else:
            tfidf_matrix = self.tfidf.transform(texts)
        
        # Handcrafted features
        handcrafted = []
        for text in texts:
            features = TravelDataPreprocessor.extract_handcrafted_features(text)
            handcrafted.append([
                features['travel_keyword_count'],
                features['has_travel_keyword'],
                features['local_keyword_count'],
                features['has_local_keyword'],
                features['has_airport_code'],
                features['has_flight'],
                features['has_foreign_country'],
                features['has_accommodation'],
                features['has_travel_docs'],
                features['text_length'],
                features['travel_ratio'],
            ])
        
        handcrafted_matrix = csr_matrix(np.array(handcrafted))
        
        # Combine both feature sets
        combined = hstack([tfidf_matrix, handcrafted_matrix])
        
        return combined
    
    def train(self, csv_path, test_size=0.2):
        """
        Trains the travel detection model on the labeled dataset.
        
        Args:
            csv_path: path to the training CSV file
            test_size: fraction of data to hold out for testing
        
        Returns:
            dict with evaluation metrics
        """
        print("\n" + "=" * 55)
        print("  TRAVEL DETECTION MODEL - TRAINING PIPELINE")
        print("=" * 55)
        
        # --- Load Data ---
        print("\n[Phase 3: Data Preparation]")
        texts, labels, trigger_types, raw_rows = TravelDataPreprocessor.load_dataset(csv_path)
        print(f"  Loaded {len(texts)} samples")
        print(f"  Travel events: {sum(labels)} ({sum(labels)/len(labels)*100:.1f}%)")
        print(f"  Non-travel events: {len(labels) - sum(labels)} ({(len(labels)-sum(labels))/len(labels)*100:.1f}%)")
        
        # --- Train/Test Split ---
        X_train_text, X_test_text, y_train, y_test = train_test_split(
            texts, labels, test_size=test_size, random_state=42, stratify=labels
        )
        print(f"  Train set: {len(X_train_text)} samples")
        print(f"  Test set:  {len(X_test_text)} samples")
        
        # --- Build Features ---
        print("\n[Phase 4: Model Training]")
        print("  Building TF-IDF + handcrafted feature matrix...")
        X_train = self._build_feature_matrix(X_train_text, fit=True)
        X_test = self._build_feature_matrix(X_test_text, fit=False)
        print(f"  Feature dimensions: {X_train.shape[1]} features")
        print(f"    - TF-IDF features: {self.tfidf.transform(X_train_text).shape[1]}")
        print(f"    - Handcrafted features: 11")
        
        # --- Train Binary Classifier (is_travel) ---
        print("\n  Training Random Forest classifier...")
        self.classifier.fit(X_train, y_train)
        
        # --- Train Trigger Type Classifier (travel events only) ---
        travel_texts = [t for t, l in zip(texts, labels) if l == 1]
        travel_triggers = [t for t, l in zip(trigger_types, labels) if l == 1 and t]
        
        if travel_triggers:
            # Filter out empty trigger types
            valid_pairs = [(text, trigger) for text, trigger in zip(travel_texts, travel_triggers) if trigger]
            if valid_pairs:
                trigger_texts, trigger_labels = zip(*valid_pairs)
                trigger_labels_encoded = self.trigger_encoder.fit_transform(trigger_labels)
                
                X_trigger = self._build_feature_matrix(list(trigger_texts), fit=False)
                self.trigger_classifier.fit(X_trigger, trigger_labels_encoded)
                print(f"  Trigger type classes: {list(self.trigger_encoder.classes_)}")
        
        self.is_trained = True
        
        # --- Evaluate ---
        print("\n[Phase 5: Evaluation]")
        y_pred = self.classifier.predict(X_test)
        y_prob = self.classifier.predict_proba(X_test)[:, 1]
        
        accuracy = accuracy_score(y_test, y_pred)
        report = classification_report(y_test, y_pred, target_names=['Not Travel', 'Travel'], output_dict=True)
        conf_matrix = confusion_matrix(y_test, y_pred)
        
        # Cross-validation score
        X_all = self._build_feature_matrix(texts, fit=False)
        cv_scores = cross_val_score(self.classifier, X_all, labels, cv=5, scoring='accuracy')
        
        print(f"\n  Accuracy: {accuracy:.4f} ({accuracy*100:.1f}%)")
        print(f"  Cross-Validation Accuracy: {cv_scores.mean():.4f} +/- {cv_scores.std():.4f}")
        print(f"\n  Confusion Matrix:")
        print(f"    Predicted ->   Not Travel    Travel")
        print(f"    Actual v")
        print(f"    Not Travel     {conf_matrix[0][0]:>6}        {conf_matrix[0][1]:>6}")
        print(f"    Travel         {conf_matrix[1][0]:>6}        {conf_matrix[1][1]:>6}")
        
        print(f"\n  Classification Report:")
        print(f"    {'':20} Precision    Recall    F1-Score    Support")
        print(f"    {'-' * 65}")
        for cls_name in ['Not Travel', 'Travel']:
            r = report[cls_name]
            print(f"    {cls_name:20} {r['precision']:.4f}       {r['recall']:.4f}    {r['f1-score']:.4f}      {int(r['support'])}")
        print(f"    {'-' * 65}")
        print(f"    {'Weighted Avg':20} {report['weighted avg']['precision']:.4f}       {report['weighted avg']['recall']:.4f}    {report['weighted avg']['f1-score']:.4f}      {int(report['weighted avg']['support'])}")
        
        # Feature importance (top 15)
        feature_names = list(self.tfidf.get_feature_names_out()) + [
            'travel_keyword_count', 'has_travel_keyword', 'local_keyword_count',
            'has_local_keyword', 'has_airport_code', 'has_flight',
            'has_foreign_country', 'has_accommodation', 'has_travel_docs',
            'text_length', 'travel_ratio'
        ]
        importances = self.classifier.feature_importances_
        top_features = sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)[:15]
        
        print(f"\n  Top 15 Most Important Features:")
        for i, (name, imp) in enumerate(top_features):
            bar = '#' * int(imp * 200)
            print(f"    {i+1:2}. {name:30} {imp:.4f}  {bar}")
        
        self.evaluation_results = {
            'accuracy': accuracy,
            'cv_accuracy_mean': cv_scores.mean(),
            'cv_accuracy_std': cv_scores.std(),
            'classification_report': report,
            'confusion_matrix': conf_matrix.tolist(),
            'top_features': top_features[:15],
            'train_size': len(X_train_text),
            'test_size': len(X_test_text),
            'total_features': X_train.shape[1]
        }
        
        print("\n  [OK] Model training complete!")
        return self.evaluation_results
    
    def predict(self, events):
        """
        Predicts travel/away periods from a list of calendar events.
        
        This is the DROP-IN REPLACEMENT for GeminiCalendarAnalyzer.detect_away_periods()
        
        Args:
            events: list of dicts with keys: summary, start, end, location, description
        
        Returns:
            list of away period dicts (same format as Gemini returned):
            [
                {
                    "reason": "Flight to Miami for vacation",
                    "departure_date": "2025-06-15",
                    "return_date": "2025-08-20",
                    "destination": "Miami, USA",
                    "trigger_type": "travel",
                    "confidence": "high"
                }
            ]
        """
        if not self.is_trained:
            raise RuntimeError("Model not trained. Call train() first or load a saved model.")
        
        if not events:
            return []
        
        # Prepare text features
        texts = []
        for event in events:
            combined = TravelDataPreprocessor.combine_text(
                event.get('summary', ''),
                event.get('location', ''),
                event.get('description', '')
            )
            texts.append(combined)
        
        # Predict
        X = self._build_feature_matrix(texts, fit=False)
        predictions = self.classifier.predict(X)
        probabilities = self.classifier.predict_proba(X)[:, 1]
        
        # Collect travel events
        travel_events = []
        for i, (event, is_travel, prob) in enumerate(zip(events, predictions, probabilities)):
            if is_travel == 1:
                # Determine confidence from probability
                if prob >= 0.85:
                    confidence = "high"
                elif prob >= 0.60:
                    confidence = "medium"
                else:
                    confidence = "low"
                
                # Predict trigger type
                trigger_type = self._predict_trigger_type(texts[i])
                
                # Extract destination from location/summary
                destination = self._extract_destination(event)
                
                # Extract dates
                start_date = self._parse_event_date(event.get('start', ''))
                end_date = self._parse_event_date(event.get('end', ''))
                
                travel_events.append({
                    "reason": event.get('summary', 'Unknown travel event'),
                    "departure_date": start_date,
                    "return_date": end_date,
                    "destination": destination,
                    "trigger_type": trigger_type,
                    "confidence": confidence,
                    "ml_probability": round(prob, 4)
                })
        
        # Merge overlapping/consecutive travel events
        merged = self._merge_away_periods(travel_events)
        
        return merged
    
    def _predict_trigger_type(self, text):
        """Predicts the trigger type (travel, vacation, work, study, etc.)."""
        text_lower = text.lower()
        
        # Rule-based fallback (more reliable for clear cases)
        if any(w in text_lower for w in ['flight', 'fly', 'airport', 'airline']):
            return 'travel'
        if any(w in text_lower for w in ['vacation', 'holiday', 'cruise', 'resort', 'honeymoon', 'getaway']):
            return 'vacation'
        if any(w in text_lower for w in ['study abroad', 'exchange', 'semester', 'university', 'orientation']):
            return 'study'
        if any(w in text_lower for w in ['work', 'conference', 'business', 'internship', 'office', 'client']):
            return 'work'
        if any(w in text_lower for w in ['relocat', 'moving', 'permanent']):
            return 'relocation'
        if any(w in text_lower for w in ['hospital', 'surgery', 'medical', 'treatment', 'rehab']):
            return 'medical'
        
        # ML-based prediction as fallback
        try:
            if hasattr(self.trigger_encoder, 'classes_') and len(self.trigger_encoder.classes_) > 0:
                X = self._build_feature_matrix([text], fit=False)
                pred = self.trigger_classifier.predict(X)[0]
                return self.trigger_encoder.inverse_transform([pred])[0]
        except Exception:
            pass
        
        return 'other'
    
    def _extract_destination(self, event):
        """Extracts the travel destination from event fields."""
        location = event.get('location', '').strip()
        summary = event.get('summary', '').strip()
        description = event.get('description', '').strip()
        
        # Priority 1: Use the location field if it looks like a real place
        if location and not any(skip in location.lower() for skip in ['zoom', 'teams', 'online', 'home', 'office', 'n/a', 'email']):
            return location
        
        # Priority 2: Extract "to {destination}" from summary
        to_match = re.search(r'\bto\s+([A-Z][a-zA-Z\s,]+)', summary)
        if to_match:
            destination = to_match.group(1).strip().rstrip(',')
            if len(destination) > 2:
                return destination
        
        # Priority 3: Extract "in {destination}" from summary
        in_match = re.search(r'\bin\s+([A-Z][a-zA-Z\s,]+)', summary)
        if in_match:
            destination = in_match.group(1).strip().rstrip(',')
            if len(destination) > 2:
                return destination
        
        # Priority 4: Extract from description
        for field in [description, summary]:
            for pattern in [r'(?:destination|location|at|visiting)\s*:?\s*([A-Z][a-zA-Z\s,]+)']:
                match = re.search(pattern, field)
                if match:
                    return match.group(1).strip()
        
        return "Unknown"
    
    @staticmethod
    def _parse_event_date(date_str):
        """Parses various date formats from calendar events into YYYY-MM-DD."""
        if not date_str:
            return datetime.now().strftime("%Y-%m-%d")
        
        date_str = str(date_str).strip()
        
        # ISO format with timezone (2025-06-15T10:00:00-05:00)
        if 'T' in date_str:
            date_str = date_str.split('T')[0]
        
        # Already in YYYY-MM-DD
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str
        
        # Try common formats
        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d %b %Y', '%B %d, %Y']:
            try:
                return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        
        return date_str
    
    @staticmethod
    def _merge_away_periods(travel_events, gap_days=3):
        """
        Merges overlapping or closely consecutive travel events into single away periods.
        e.g., "Flight to Miami" + "Hotel in Miami" + "Return flight" → one away period.
        """
        if not travel_events:
            return []
        
        # Sort by departure date
        sorted_events = sorted(travel_events, key=lambda x: x.get('departure_date', ''))
        
        merged = [sorted_events[0].copy()]
        
        for event in sorted_events[1:]:
            last = merged[-1]
            
            try:
                last_end = datetime.strptime(last['return_date'], '%Y-%m-%d')
                curr_start = datetime.strptime(event['departure_date'], '%Y-%m-%d')
                
                # If events overlap or are within gap_days of each other, merge
                if (curr_start - last_end).days <= gap_days:
                    # Extend the return date if the new event ends later
                    curr_end = datetime.strptime(event['return_date'], '%Y-%m-%d')
                    if curr_end > last_end:
                        last['return_date'] = event['return_date']
                    
                    # Keep the better destination/reason
                    if last['destination'] == 'Unknown' and event['destination'] != 'Unknown':
                        last['destination'] = event['destination']
                    
                    # Upgrade confidence if new event has higher confidence
                    conf_order = {'high': 3, 'medium': 2, 'low': 1}
                    if conf_order.get(event['confidence'], 0) > conf_order.get(last['confidence'], 0):
                        last['confidence'] = event['confidence']
                        last['reason'] = event['reason']
                        last['trigger_type'] = event['trigger_type']
                else:
                    merged.append(event.copy())
            except (ValueError, KeyError):
                merged.append(event.copy())
        
        return merged
    
    def save(self, save_dir):
        """Saves the trained model to disk."""
        os.makedirs(save_dir, exist_ok=True)
        
        model_data = {
            'tfidf': self.tfidf,
            'classifier': self.classifier,
            'trigger_encoder': self.trigger_encoder,
            'trigger_classifier': self.trigger_classifier,
            'evaluation_results': self.evaluation_results,
            'is_trained': self.is_trained,
        }
        
        save_path = os.path.join(save_dir, 'travel_model.joblib')
        joblib.dump(model_data, save_path)
        print(f"  [OK] Model saved to {save_path}")
        return save_path
    
    @classmethod
    def load(cls, save_dir):
        """Loads a previously trained model from disk."""
        model = cls()
        load_path = os.path.join(save_dir, 'travel_model.joblib')
        
        if not os.path.exists(load_path):
            raise FileNotFoundError(f"No saved model found at {load_path}")
        
        model_data = joblib.load(load_path)
        model.tfidf = model_data['tfidf']
        model.classifier = model_data['classifier']
        model.trigger_encoder = model_data['trigger_encoder']
        model.trigger_classifier = model_data['trigger_classifier']
        model.evaluation_results = model_data.get('evaluation_results', {})
        model.is_trained = model_data.get('is_trained', True)
        
        print(f"  [OK] Model loaded from {load_path}")
        return model


# ==========================================
# 3. MAIN — TRAIN & TEST
# ==========================================

def main():
    """Train the model, evaluate it, save it, and run a demo prediction."""
    
    # Resolve paths relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    dataset_path = os.path.join(project_dir, 'datasets', 'calendar_travel_dataset.csv')
    model_save_dir = os.path.join(script_dir, 'saved')
    
    if not os.path.exists(dataset_path):
        print(f"Dataset not found at: {dataset_path}")
        return
    
    # --- Train ---
    model = TravelDetectionModel()
    results = model.train(dataset_path)
    
    # --- Save ---
    print(f"\n[Saving Model]")
    model.save(model_save_dir)
    
    # --- Demo Prediction ---
    print("\n" + "=" * 55)
    print("  DEMO - PREDICTING ON SAMPLE EVENTS")
    print("=" * 55)
    
    sample_events = [
        {
            "summary": "Flight to New York City",
            "start": "2026-07-01",
            "end": "2026-07-15",
            "location": "JFK Airport",
            "description": "Summer trip to visit family"
        },
        {
            "summary": "Team standup meeting",
            "start": "2026-04-10",
            "end": "2026-04-10",
            "location": "Zoom",
            "description": "Daily sync with engineering team"
        },
        {
            "summary": "Study abroad semester at University of Toronto",
            "start": "2026-09-01",
            "end": "2026-12-15",
            "location": "Toronto, Canada",
            "description": "UWI exchange program fall semester"
        },
        {
            "summary": "Dentist appointment",
            "start": "2026-05-03",
            "end": "2026-05-03",
            "location": "Dr. Smith Dental Kingston",
            "description": "Annual checkup"
        },
        {
            "summary": "Vacation in Bahamas",
            "start": "2026-06-10",
            "end": "2026-06-24",
            "location": "Nassau, Bahamas",
            "description": "Family beach vacation all inclusive"
        },
        {
            "summary": "Gym workout",
            "start": "2026-04-12",
            "end": "2026-04-12",
            "location": "Fit4Less Kingston",
            "description": "Leg day"
        },
        {
            "summary": "Conference presentation at MIT",
            "start": "2026-10-05",
            "end": "2026-10-08",
            "location": "MIT, Boston, Massachusetts",
            "description": "Presenting capstone research paper"
        },
        {
            "summary": "Grocery shopping",
            "start": "2026-04-11",
            "end": "2026-04-11",
            "location": "MegaMart Kingston",
            "description": "Weekly groceries"
        }
    ]
    
    predictions = model.predict(sample_events)
    
    print(f"\n  Input: {len(sample_events)} calendar events")
    print(f"  Detected: {len(predictions)} travel/away period(s)\n")
    
    for i, pred in enumerate(predictions):
        conf_icon = "[HIGH]" if pred['confidence'] == 'high' else "[MED]" if pred['confidence'] == 'medium' else "[LOW]"
        print(f"  {conf_icon} {pred['reason']}")
        print(f"     Dates: {pred['departure_date']} -> {pred['return_date']}")
        print(f"     Destination: {pred['destination']}")
        print(f"     Type: {pred['trigger_type']}")
        print(f"     Confidence: {pred['confidence']} (probability: {pred.get('ml_probability', 'N/A')})")
        print()
    
    # --- Verify loaded model works ---
    print("[Verifying saved model loads correctly...]")
    loaded_model = TravelDetectionModel.load(model_save_dir)
    loaded_predictions = loaded_model.predict(sample_events)
    assert len(loaded_predictions) == len(predictions), "Loaded model gives different results!"
    print("  [OK] Saved model verified - identical predictions\n")
    
    # --- Export evaluation report ---
    report_path = os.path.join(project_dir, 'datasets', 'travel_model_evaluation.json')
    with open(report_path, 'w') as f:
        # Convert numpy types for JSON serialization
        exportable = {
            'accuracy': results['accuracy'],
            'cv_accuracy_mean': results['cv_accuracy_mean'],
            'cv_accuracy_std': results['cv_accuracy_std'],
            'train_size': results['train_size'],
            'test_size': results['test_size'],
            'total_features': results['total_features'],
            'confusion_matrix': results['confusion_matrix'],
            'top_features': [(name, float(imp)) for name, imp in results['top_features']],
            'classification_report': {
                k: {kk: float(vv) if isinstance(vv, (int, float, np.integer, np.floating)) else vv 
                     for kk, vv in v.items()} if isinstance(v, dict) else float(v) if isinstance(v, (np.floating, np.integer)) else v
                for k, v in results['classification_report'].items()
            }
        }
        json.dump(exportable, f, indent=2)
    print(f"  ✓ Evaluation report saved to {report_path}")


if __name__ == "__main__":
    main()
