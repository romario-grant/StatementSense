import logging
import re
from pathlib import Path
from typing import List, Optional, Union

import camelot
import pandas as pd
import pdfplumber

logger = logging.getLogger(__name__)


def extract_tables_from_pdf(pdf_path: Union[str, Path]) -> List[pd.DataFrame]:
    pdf_path = Path(pdf_path)
    
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    logger.info(f"Extracting tables from PDF: {pdf_path}")
    
    return extract_tables_locally(pdf_path)


def extract_tables_locally(pdf_path: Path) -> List[pd.DataFrame]:
    logger.info("Using local extraction methods")
    tables = []
    
    tables.extend(_extract_with_pdfplumber(pdf_path))
    
    camelot_tables = _extract_with_camelot(pdf_path)
    for table in camelot_tables:
        if not _is_duplicate_table(table, tables):
            tables.append(table)
    
    cleaned_tables = [
        cleaned for table in tables 
        if (cleaned := _clean_table(table)) is not None
    ]
    
    logger.info(f"Successfully extracted {len(cleaned_tables)} valid tables")
    return cleaned_tables


def _extract_with_pdfplumber(pdf_path: Path) -> List[pd.DataFrame]:
    tables = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                try:
                    for table_data in page.extract_tables() or []:
                        if table_data and len(table_data) > 1:
                            df = pd.DataFrame(table_data[1:], columns=table_data[0])
                            df.attrs['source'] = f'pdfplumber_page_{page_num}'
                            tables.append(df)
                except Exception as e:
                    logger.error(f"Failed to extract from page {page_num}: {e}")
        
        if tables:
            logger.info(f"Found {len(tables)} tables using pdfplumber")
    except Exception as e:
        logger.warning(f"pdfplumber extraction failed: {e}")
    
    return tables


def _extract_with_camelot(pdf_path: Path) -> List[pd.DataFrame]:
    tables = []
    
    try:
        for flavor in ['lattice', 'stream']:
            camelot_tables = camelot.read_pdf(str(pdf_path), flavor=flavor)
            if camelot_tables:
                break
        
        for i, table in enumerate(camelot_tables):
            if len(table.df) > 1:
                df = table.df.copy()
                df.attrs['source'] = f'camelot_table_{i}'
                df.attrs['accuracy'] = getattr(table, 'accuracy', 0)
                tables.append(df)
        
        if tables:
            logger.info(f"Found {len(tables)} tables using camelot")
    except Exception as e:
        logger.warning(f"camelot extraction failed: {e}")
    
    return tables


def _clean_table(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return None
    
    try:
        df = df.dropna(how='all').dropna(axis=1, how='all')
        if df.empty:
            return None
        
        df.columns = [
            str(col).strip().replace('\n', ' ') if col else f'Column_{i}' 
            for i, col in enumerate(df.columns)
        ]
        
        df = df[~df.astype(str).apply(
            lambda x: x.str.strip().isin(['', 'None'])
        ).all(axis=1)]
        
        if len(df) < 2:
            return None
            
        if _is_transaction_table(df):
            df = _format_transaction_table(df)
        
        return df
    except Exception as e:
        logger.error(f"Failed to clean table: {e}")
        return None


def _is_transaction_table(df: pd.DataFrame) -> bool:
    if df.empty or len(df) < 2:
        return False
    
    column_text = ' '.join(str(col).lower() for col in df.columns)
    transaction_keywords = ['date', 'amount', 'balance', 'description', 'debit', 'credit']
    header_matches = sum(1 for keyword in transaction_keywords if keyword in column_text)
    
    sample_text = ' '.join(str(val) for row in df.head(3).values for val in row if pd.notna(val))
    
    date_matches = len(re.findall(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', sample_text))
    amount_matches = len(re.findall(r'\d+[,.]?\d*', sample_text))
    
    return header_matches >= 2 or (date_matches >= 2 and amount_matches >= 2)


def _format_transaction_table(df: pd.DataFrame) -> pd.DataFrame:
    column_mapping = {}
    
    for col in df.columns:
        col_lower = str(col).lower()
        
        if any(keyword in col_lower for keyword in ['date', 'dt']):
            column_mapping[col] = 'Date'
        elif any(keyword in col_lower for keyword in ['description', 'particular', 'narration']):
            column_mapping[col] = 'Description'
        elif any(keyword in col_lower for keyword in ['debit', 'withdrawal', 'dr']):
            column_mapping[col] = 'Debit'
        elif any(keyword in col_lower for keyword in ['credit', 'deposit', 'cr']):
            column_mapping[col] = 'Credit'
        elif any(keyword in col_lower for keyword in ['balance', 'bal']):
            column_mapping[col] = 'Balance'
        elif any(keyword in col_lower for keyword in ['reference', 'ref', 'cheque']):
            column_mapping[col] = 'Reference'
    
    return df.rename(columns=column_mapping) if column_mapping else df


def _is_duplicate_table(new_table: pd.DataFrame, existing_tables: List[pd.DataFrame]) -> bool:
    if not existing_tables or new_table.empty:
        return False
    
    for existing_table in existing_tables:
        if abs(len(new_table) - len(existing_table)) <= 2:
            try:
                new_sample = set(str(new_table.head(3).values).split())
                existing_sample = set(str(existing_table.head(3).values).split())
                
                similarity = len(new_sample & existing_sample) / max(
                    len(new_sample), len(existing_sample), 1
                )
                
                if similarity > 0.7:
                    return True
            except Exception:
                continue
    
    return False
