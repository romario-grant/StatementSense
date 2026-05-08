import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text.strip())
    text = re.sub(r'[^\w\s@.,()-/:]', ' ', text)
    return text


def extract_account_holder_patterns(text: str) -> Dict[str, str]:
    patterns = {
        "name": [
            r'(?:account\s*holder|customer\s*name|name)[:\s]*([A-Za-z][A-Za-z\s\.\'-]{2,50})',
            r'\b(?:mr|ms|miss|mrs)\.?\s*([A-Za-z][A-Za-z\s\.\'-]{2,50})',
            r'dear\s+([A-Za-z][A-Za-z\s\.\'-]{2,50})',
        ],
        "address": [
            r'(?:address|residential\s*address|addr)[:\s]*([A-Za-z0-9\s,.\-\/#]{10,120})',
            r'(?:correspondence\s*address|permanent\s*address)[:\s]*([A-Za-z0-9\s,.\-\/#]{10,120})',
        ],
        "contact": [
            r'(?:mobile|phone|contact|tel|telephone)[:\s]*([\+\(]?\d{1,4}[\)\-\s]?\d{2,5}[\-\s]?\d{4,10})',
            r'\b(\+?\d{10,15})\b',
        ],
        "email": [
            r'(?:email|e-mail|mail)[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b',
        ]
    }

    result = {}
    for field, field_patterns in patterns.items():
        found = False
        for pattern in field_patterns:
            flags = re.IGNORECASE if field != "email" else 0
            matches = re.findall(pattern, text, flags)
            if matches:
                value = matches[0].strip()
                if field == "email":
                    result[field] = value
                elif field == "contact":
                    result[field] = value
                else:
                    result[field] = value.title()
                found = True
                break
        if not found:
            result[field] = ""

    return result


def extract_bank_account_patterns(text: str) -> Dict[str, str]:
    patterns = {
        "account_number": [
            r'(?:account\s*(?:no\.?|number|#|num|a/c|a\/c|ac)\s*[:\-]?\s*)(\d{8,20})',
            r'\b(\d{8,20})\b'
        ],
        "ifsc_code": [
            r'(?:ifsc\s*(?:code)?\s*[:\-]?\s*)([A-Z]{4}0[A-Z0-9]{6})',
            r'\b([A-Z]{4}0[A-Z0-9]{6})\b'
        ],
        "branch_address": [
            r'(?:branch\s*(?:address)?\s*[:\-]?\s*)([A-Za-z0-9\s,.\-\/#]{10,120})',
            r'(?:located\s+at|address\s*[:\-]?)\s*([A-Za-z0-9\s,.\-\/#]{10,120})'
        ],
        "bank_name": [
            r'\b((?:state\s+bank|hdfc|icici|axis|kotak|yes\s+bank|pnb|bank\s+of\s+india|canara|union|sbi|indusind|idfc|rbl|federal|central\s+bank|uco|bank\s+of\s+baroda|bank\s+of\s+maharashtra|south\s+indian|dcb|citi|hsbc|standard\s+chartered|deutsche|dbs|bandhan|au\s+small\s+finance|idbi|karur\s+vysya|tamilnad\s+mercantile|city\s+union|jammu\s+and\s+kashmir|punjab\s+and\s+sind)\s*bank?)\b'
        ]
    }

    result = {}

    text_clean = re.sub(r'[^\w\s@.,()-/:#]', ' ', text)
    text_clean = re.sub(r'\s+', ' ', text_clean)
    text_lower = text_clean.lower()

    acc_found = False
    for pattern in patterns["account_number"]:
        match = re.search(pattern, text_clean, re.IGNORECASE)
        if match:
            acc_num = match.group(1)
            acc_num = re.sub(r'[\s\-]', '', acc_num)
            if acc_num.isdigit() and 8 <= len(acc_num) <= 20:
                result["account_number"] = acc_num
                acc_found = True
                break
    if not acc_found:
        result["account_number"] = ""

    ifsc_found = False
    for pattern in patterns["ifsc_code"]:
        match = re.search(pattern, text_clean, re.IGNORECASE)
        if match:
            ifsc = match.group(1).upper()
            if re.match(r'^[A-Z]{4}0[A-Z0-9]{6}$', ifsc):
                result["ifsc_code"] = ifsc
                ifsc_found = True
                break
    if not ifsc_found:
        result["ifsc_code"] = ""

    branch_found = False
    for pattern in patterns["branch_address"]:
        match = re.search(pattern, text_clean, re.IGNORECASE)
        if match:
            address = match.group(1).strip()
            if len(address) >= 10 and any(word in address.lower() for word in ["road", "street", "block", "sector", "colony", "market", "lane", "complex", "village", "city", "town", "dist", "district", "state", "pin", "pincode", "zip"]):
                result["branch_address"] = address.title()
                branch_found = True
                break
    if not branch_found:
        result["branch_address"] = ""

    bank_found = False
    for pattern in patterns["bank_name"]:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            bank_name = match.group(1).strip()
            bank_name = re.sub(r'\s+', ' ', bank_name)
            result["bank_name"] = bank_name.title()
            bank_found = True
            break
    if not bank_found:
        result["bank_name"] = ""

    return result


def detect_table_patterns(text: str) -> List[str]:
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    table_lines = []

    date_pattern = r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b'
    amount_pattern = r'\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b'
    balance_pattern = r'\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b'
    txn_type_pattern = r'\b(?:credit|debit|cr|dr)\b'
    narration_pattern = r'[A-Za-z0-9\s,.\-]+'

    for line in lines:
        date_match = re.search(date_pattern, line)
        amounts = re.findall(amount_pattern, line)
        txn_type_match = re.search(txn_type_pattern, line, re.IGNORECASE)

        if date_match and len(amounts) >= 1:
            if txn_type_match or re.search(narration_pattern, line):
                table_lines.append(line)
            else:
                if len(amounts) >= 2 or len(line.split()) > 4:
                    table_lines.append(line)

    filtered_lines = []
    for line in table_lines:
        if re.match(r'^(date|particulars|narration|amount|balance|credit|debit|dr|cr)[\s\|,]*$', line, re.IGNORECASE):
            continue
        filtered_lines.append(line)

    return filtered_lines


def format_extracted_data(account_holder: Dict, bank_account: Dict, transactions: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    result = {
        "account_holder_details": {
            "name": account_holder.get("name", ""),
            "address": account_holder.get("address", ""),
            "contact_nr": account_holder.get("contact", ""),
            "email": account_holder.get("email", "")
        },
        "bank_account_details": {
            "bank_account_nr": bank_account.get("account_number", ""),
            "ifsc_code": bank_account.get("ifsc_code", ""),
            "bank_branch_address": bank_account.get("branch_address", ""),
            "bank_name": bank_account.get("bank_name", "")
        },
        "has_transaction_table": transactions is not None and len(transactions) > 0,
        "transaction_count": len(transactions) if transactions is not None else 0
    }
    
    return result


def validate_extracted_data(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    warnings = []
    
    ah_details = data.get("account_holder_details", {})
    if not ah_details.get("name"):
        warnings.append("Account holder name not found")
    
    ba_details = data.get("bank_account_details", {})
    if not ba_details.get("bank_account_nr"):
        warnings.append("Bank account number not found")
    if not ba_details.get("ifsc_code"):
        warnings.append("IFSC code not found")
    
    ifsc = ba_details.get("ifsc_code", "")
    if ifsc and not re.match(r'^[A-Z]{4}0[A-Z0-9]{6}$', ifsc):
        warnings.append("IFSC code format appears invalid")
    
    is_valid = len(warnings) == 0
    return is_valid, warnings
