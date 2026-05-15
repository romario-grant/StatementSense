"""Vertex AI Gemini classifier for extracting account-holder and bank-account fields from statement text. Falls back to the regex-based extractor when the Vertex AI SDK or its credentials are unavailable."""

import json
import logging
import os
import tempfile
from typing import Any, Dict, Optional

from dotenv import load_dotenv

try:
    import streamlit as st
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False

try:
    import vertexai
    from vertexai.generative_models import GenerativeModel
    VERTEX_AI_AVAILABLE = True
except ImportError:
    VERTEX_AI_AVAILABLE = False
    logging.warning("Vertex AI SDK not available. Falling back to rule-based extraction.")

from .utils import extract_account_holder_patterns, extract_bank_account_patterns, format_extracted_data

load_dotenv()
logger = logging.getLogger(__name__)

def classify_blobs(blobs: Dict[str, str]) -> Dict[str, Any]:
    """Classify a dictionary of statement text blobs and return the canonical extraction result. Uses Vertex AI when available; otherwise falls back to deterministic regex extraction."""
    logger.info("Starting text classification and information extraction")
    full_text = blobs.get("full_text", "")
    header_text = blobs.get("header", "")
    if not full_text:
        logger.warning("No text provided for classification")
        return create_empty_result()
    if should_use_gemini_api():
        try:
            return classify_with_gemini_api(blobs)
        except Exception as e:
            logger.error(f"Gemini API classification failed: {e}")
            logger.info("Falling back to rule-based extraction")
    return classify_with_rules(full_text, header_text)

def setup_gcp_credentials() -> Optional[str]:
    """Resolve Vertex AI credentials from the active runtime environment."""
    try:
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if credentials_path and os.path.exists(credentials_path):
            logger.info("Using GCP credentials from file")
            return credentials_path
        
        # Hosted notebook/demo environments can provide service-account data as secrets.
        if STREAMLIT_AVAILABLE and hasattr(st, 'secrets'):
            try:
                gcp_secrets = st.secrets.get("gcp_service_account", {})
                if gcp_secrets:
                    # Vertex AI expects a file path, so materialize the secret as JSON.
                    credentials_dict = dict(gcp_secrets)
                    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
                    json.dump(credentials_dict, temp_file, indent=2)
                    temp_file.close()
                    
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_file.name
                    logger.info("Using GCP credentials from Streamlit secrets")
                    return temp_file.name
            except Exception as e:
                logger.warning(f"Could not load Streamlit secrets: {e}")
        
        return None
    except Exception as e:
        logger.error(f"Error setting up GCP credentials: {e}")
        return None

def should_use_gemini_api() -> bool:
    """Return ``True`` when Vertex AI is installed, enabled, and has valid credentials available in the current environment."""
    if not VERTEX_AI_AVAILABLE:
        logger.info("Vertex AI SDK not available")
        return False
    
    if os.getenv("DISABLE_VERTEX_AI", "").lower() in ["true", "1", "yes"]:
        logger.info("Vertex AI disabled by environment variable")
        return False
    
    credentials_path = setup_gcp_credentials()
    if not credentials_path:
        logger.info("No valid GCP credentials found")
        return False
    
    logger.info("GCP credentials found, will use Gemini API")
    return True

def get_project_id_from_credentials() -> Optional[str]:
    """Resolve the GCP project ID from Streamlit secrets, a credentials file, or the ``GOOGLE_CLOUD_PROJECT`` environment variable."""
    try:
        if STREAMLIT_AVAILABLE and hasattr(st, 'secrets'):
            try:
                gcp_secrets = st.secrets.get("gcp_service_account", {})
                if gcp_secrets and "project_id" in gcp_secrets:
                    project_id = gcp_secrets["project_id"]
                    logger.info(f"Got project ID from Streamlit secrets: {project_id}")
                    return project_id
            except Exception as e:
                logger.warning(f"Could not get project ID from Streamlit secrets: {e}")
        
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if credentials_path and os.path.exists(credentials_path):
            with open(credentials_path, 'r') as f:
                credentials = json.load(f)
            project_id = credentials.get("project_id")
            logger.info(f"Got project ID from credentials file: {project_id}")
            return project_id
    except Exception as e:
        logger.warning(f"Could not extract project ID from credentials: {e}")
    
    # Use the configured project ID when credentials do not include one.
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "dogwood-reality-469112-v9")
    logger.info(f"Using fallback project ID: {project_id}")
    return project_id

def classify_with_gemini_api(blobs: Dict[str, str]) -> Dict[str, Any]:
    """Invoke Vertex AI Gemini against the supplied statement blobs and return the parsed JSON extraction result."""
    logger.info("Using Vertex AI Gemini for classification")
    project_id = get_project_id_from_credentials()
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    
    logger.info(f"Initializing Vertex AI with project: {project_id}, location: {location}")
    vertexai.init(project=project_id, location=location)
    model_name = "gemini-2.5-flash"
    model = GenerativeModel(model_name)
    logger.info(f"Using model: {model_name}")
    prompt = create_extraction_prompt(blobs)
    response = model.generate_content(
        prompt,
        generation_config={
            "max_output_tokens": 2048,
            "temperature": 0.1,
            "top_p": 0.8,
            "top_k": 40
        }
    )
    if not response.text:
        raise Exception("Empty response from Vertex AI")
    result = parse_gemini_response(response.text)
    result.update({
        "extraction_method": "vertex_ai_gemini",
        "model_used": model_name
    })
    return result

def classify_with_rules(full_text: str, header_text: str) -> Dict[str, Any]:
    """Extract account-holder and bank-account fields using regex rules over the full text and header. Used as the deterministic fallback when Vertex AI is unavailable."""
    logger.info("Using rule-based extraction")
    account_holder = {**extract_account_holder_patterns(full_text), **extract_account_holder_patterns(header_text)}
    bank_account = {**extract_bank_account_patterns(full_text), **extract_bank_account_patterns(header_text)}
    result = format_extracted_data(account_holder, bank_account)
    result.update({
        "extraction_method": "rule_based",
        "transaction_data": []
    })
    return result

def create_extraction_prompt(blobs: Dict[str, str]) -> str:
    """Build the Gemini prompt for extracting statement fields. The prompt is extended to request transaction rows when the caller signals that table extraction did not succeed."""
    needs_transaction_extraction = "extraction_context" in blobs and "transaction" in blobs.get("extraction_context", "").lower()
    if needs_transaction_extraction:
        return f"""You are an expert at extracting structured information from Indian bank statements. 
Since table extraction failed, extract BOTH account/bank details AND transaction data from the text.
Extract information ONLY if you are confident it's present. Return empty string "" for unclear fields.

REQUIRED JSON FORMAT:
{{
    "account_holder_details": {{
        "name": "",
        "address": "",
        "contact_nr": "",
        "email": ""
    }},
    "bank_account_details": {{
        "bank_account_nr": "",
        "ifsc_code": "",
        "bank_branch_address": "",
        "bank_name": ""
    }},
    "transaction_data": [
        {{
            "date": "",
            "description": "",
            "amount": "",
            "balance": "",
            "type": "debit/credit"
        }}
    ]
}}

BANK STATEMENT TEXT:

Header: {blobs.get("header", "")}

Full Text: {blobs.get("full_text", "")[:10000]}

Context: {blobs.get("extraction_context", "")}

Return ONLY the JSON response:"""
    else:
        return f"""You are an expert at extracting structured information from Indian bank statements. 
Extract information ONLY if you are confident it's present. Return empty string "" for unclear fields.

REQUIRED JSON FORMAT:
{{
    "account_holder_details": {{
        "name": "",
        "address": "",
        "contact_nr": "",
        "email": ""
    }},
    "bank_account_details": {{
        "bank_account_nr": "",
        "ifsc_code": "",
        "bank_branch_address": "",
        "bank_name": ""
    }}
}}

BANK STATEMENT TEXT:

Header: {blobs.get("header", "")}

Full Text: {blobs.get("full_text", "")[:8000]}

Return ONLY the JSON response:"""

def parse_gemini_response(response_text: str) -> Dict[str, Any]:
    """Parse the JSON object embedded in a Gemini text response and return it. An empty result is returned when no JSON object can be located or parsed."""
    try:
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}') + 1
        if start_idx != -1 and end_idx > start_idx:
            json_str = response_text[start_idx:end_idx]
            return json.loads(json_str)
        else:
            return create_empty_result()
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini response as JSON: {e}")
        return create_empty_result()

def create_empty_result(error_message: str = "No information could be extracted") -> Dict[str, Any]:
    """Return a fully populated extraction result with empty fields, used when no information could be parsed."""
    return {
        "account_holder_details": {
            "name": "",
            "address": "",
            "contact_nr": "",
            "email": ""
        },
        "bank_account_details": {
            "bank_account_nr": "",
            "ifsc_code": "",
            "bank_branch_address": "",
            "bank_name": ""
        },
        "transaction_data": [],
        "extraction_method": "failed",
        "error": error_message
    }
