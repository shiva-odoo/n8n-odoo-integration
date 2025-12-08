"""
Transaction Matching Agentic Workflow - PRODUCTION VERSION 7
============================================================

A battle-tested, production-grade multi-agent system for automated transaction reconciliation.

CRITICAL FIXES IN V7 (Based on Production Audit):
==================================================
1. Ghost Document Rejection - REJECT matches with hallucinated/missing IDs (not accept)
2. Configurable Tolerance - Support bank fees, rounding with tracked differences
3. Batched Processing - Process transactions in small batches to avoid context explosion
4. Parallel Scoring Architecture - Score candidates individually, then select best
5. Enhanced Validation Pipeline - Multi-stage validation with clear rejection reasons

ARCHITECTURE:
=============
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ORCHESTRATOR                                       │
│  - Coordinates all agents with BATCHED processing                           │
│  - Maintains state with segregated ID registries                            │
│  - Applies Python-side validation with STRICT rejection                     │
│  - Handles rollback on validation failure                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                          [BATCH PROCESSING]
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────┐         ┌─────────────────┐         ┌─────────────────┐
│ Data Enrichment│   →    │ Duplicate       │   →    │ Exact Match     │
│ Agent          │         │ Detection Agent │         │ Agent (BATCHED) │
└───────────────┘         └─────────────────┘         └─────────────────┘

TOLERANCE LEVELS:
=================
- EXACT: 0.00 (zero tolerance) - for exact matches
- BANK_FEE: 5.00 (max €5 difference) - common wire transfer fees
- ROUNDING: 0.05 (5 cents) - split payment rounding
- PERCENTAGE: 2% of amount - for larger transactions
"""

import json
import os
import re
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple, Set, Union
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from dataclasses import dataclass, field
from enum import Enum
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from anthropic import Anthropic

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class MatchingConfig:
    """Configuration for matching behavior - tune for your business rules."""
    
    # Tolerance settings
    exact_tolerance: Decimal = Decimal("0.00")  # Zero tolerance for exact matches
    bank_fee_tolerance: Decimal = Decimal("5.00")  # Max bank fee difference
    rounding_tolerance: Decimal = Decimal("0.05")  # Split payment rounding
    percentage_tolerance: Decimal = Decimal("0.02")  # 2% for large transactions
    
    # Processing settings
    batch_size: int = 5  # Transactions per LLM call (prevents context explosion)
    max_candidates_per_txn: int = 15  # Max documents to consider per transaction
    max_documents_per_type: int = 50  # Max documents per type in context
    
    # Date ranges (days)
    exact_match_date_range: int = 30
    fuzzy_match_date_range: int = 180
    max_date_range: int = 365
    
    # Retry settings
    max_retries: int = 3
    base_temperature: float = 0.0
    retry_temperature_increment: float = 0.15
    
    # Validation settings
    reject_hallucinated_ids: bool = True  # CRITICAL: Must be True in production
    require_currency_match: bool = True
    max_combination_size: int = 5
    
    # Model settings
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 8000  # Reduced for faster responses


# Default configuration
DEFAULT_CONFIG = MatchingConfig()


# =============================================================================
# CUSTOM JSON ENCODER
# =============================================================================

class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder for Decimal, set, datetime objects."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def safe_json_dumps(data: Any, indent: int = 2) -> str:
    """Safely serialize data to JSON string."""
    return json.dumps(data, indent=indent, cls=DecimalEncoder, ensure_ascii=False)


# =============================================================================
# ENUMS AND TYPES
# =============================================================================

class MatchType(Enum):
    EXACT = "exact"
    NEAR = "near"  # NEW: For matches within tolerance
    FUZZY = "fuzzy"
    COMBINATION_BATCH = "combination_batch"
    COMBINATION_SPLIT = "combination_split"
    SUSPENSE_SINGLE = "suspense_single"
    SUSPENSE_COMBINATION = "suspense_combination"


class ToleranceType(Enum):
    EXACT = "exact"
    BANK_FEE = "bank_fee"
    ROUNDING = "rounding"
    PERCENTAGE = "percentage"


class RejectionReason(Enum):
    HALLUCINATED_TRANSACTION_ID = "HALLUCINATED_TRANSACTION_ID"
    HALLUCINATED_DOCUMENT_ID = "HALLUCINATED_DOCUMENT_ID"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    DUPLICATE_MATCH = "DUPLICATE_MATCH"
    INVALID_COMBINATION = "INVALID_COMBINATION"
    ACCOUNT_INCONSISTENCY = "ACCOUNT_INCONSISTENCY"
    EXCEEDS_MAX_TOLERANCE = "EXCEEDS_MAX_TOLERANCE"


class ConfidenceLevel(Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# =============================================================================
# DECIMAL MATH UTILITIES (Enhanced with Tolerance)
# =============================================================================

def to_decimal(value: Any) -> Decimal:
    """Convert any numeric value to Decimal with error handling."""
    try:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        if isinstance(value, str):
            cleaned = re.sub(r'[€$£¥\s,]', '', value)
            if not cleaned or cleaned == '-':
                return Decimal('0')
            return Decimal(cleaned)
        return Decimal('0')
    except (InvalidOperation, ValueError) as e:
        logger.warning(f"Failed to convert '{value}' to Decimal: {e}")
        return Decimal('0')


def amounts_equal(
    amount1: Any, 
    amount2: Any, 
    tolerance: Decimal = Decimal("0.00")
) -> Tuple[bool, Decimal]:
    """
    Compare two amounts with configurable tolerance.
    
    Returns:
        Tuple of (is_equal, difference)
    """
    dec1 = abs(to_decimal(amount1))
    dec2 = abs(to_decimal(amount2))
    difference = abs(dec1 - dec2)
    
    is_equal = difference <= tolerance
    return is_equal, difference


def calculate_tolerance(
    amount: Any,
    tolerance_type: ToleranceType,
    config: MatchingConfig = DEFAULT_CONFIG
) -> Decimal:
    """
    Calculate appropriate tolerance based on type and amount.
    
    Args:
        amount: The transaction/document amount
        tolerance_type: Type of tolerance to apply
        config: Matching configuration
    
    Returns:
        Decimal tolerance value
    """
    dec_amount = abs(to_decimal(amount))
    
    if tolerance_type == ToleranceType.EXACT:
        return config.exact_tolerance
    elif tolerance_type == ToleranceType.BANK_FEE:
        return config.bank_fee_tolerance
    elif tolerance_type == ToleranceType.ROUNDING:
        return config.rounding_tolerance
    elif tolerance_type == ToleranceType.PERCENTAGE:
        return dec_amount * config.percentage_tolerance
    
    return Decimal("0.00")


def sum_amounts(amounts: List[Any]) -> Decimal:
    """Sum a list of amounts using Decimal arithmetic."""
    return sum((to_decimal(amt) for amt in amounts), Decimal('0'))


def format_decimal(value: Union[Decimal, Any], places: int = 2) -> str:
    """Format Decimal for display."""
    dec = to_decimal(value) if not isinstance(value, Decimal) else value
    quantize_str = '0.' + '0' * places
    return str(dec.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP))


# =============================================================================
# DATA MINIFICATION (Enhanced)
# =============================================================================

def minify_transaction(txn: Dict) -> Dict:
    """Minify transaction for LLM context - keeps only essential fields."""
    return {
        "transaction_id": txn.get("transaction_id") or str(txn.get("odoo_id")),
        "odoo_id": txn.get("odoo_id"),
        "date": txn.get("date"),
        "amount": format_decimal(txn.get("amount", 0)),
        "currency": txn.get("currency", "EUR"),
        "partner": (txn.get("partner_name") or txn.get("normalized_partner") or "")[:50],
        "description": _truncate(txn.get("description") or txn.get("normalized_description"), 80),
        "account_name": txn.get("account_name"),
        "category": txn.get("category"),
        "is_suspense": txn.get("is_suspense", False),
        "keywords": txn.get("keywords", [])[:3],
    }


def minify_document(doc: Dict, doc_type: str) -> Dict:
    """Minify document for LLM context."""
    id_field = f"{doc_type}_id"
    doc_id = doc.get(id_field) or doc.get("id")
    
    return {
        "id": str(doc_id) if doc_id else None,
        "date": doc.get("date"),
        "amount": format_decimal(doc.get("amount", 0)),
        "currency": doc.get("currency", "EUR"),
        "partner": (doc.get("partner_name") or doc.get("normalized_partner") or "")[:50],
        "ref": doc.get("vendor_ref") or doc.get("invoice_ref") or doc.get("ref"),
    }


def minify_documents_dict(
    documents: Dict, 
    max_per_type: int = 50
) -> Dict:
    """Minify all documents in a dictionary structure."""
    minified = {}
    for doc_type, docs_list in documents.items():
        type_key = doc_type.rstrip('s') if doc_type.endswith('s') else doc_type
        minified[doc_type] = [
            minify_document(doc, type_key) 
            for doc in docs_list[:max_per_type]
        ]
    return minified


def _truncate(text: str, max_length: int) -> str:
    """Truncate text to max length."""
    if not text:
        return ""
    text = str(text)
    return text[:max_length - 3] + "..." if len(text) > max_length else text


# =============================================================================
# STATE MANAGEMENT
# =============================================================================

@dataclass
class MatchingState:
    """Enhanced state management with segregated ID registries."""
    
    matched_document_ids: Dict[str, Set[str]] = field(default_factory=lambda: {
        'bill': set(), 'invoice': set(), 'credit_note': set(),
        'payroll': set(), 'share': set()
    })
    matched_transaction_ids: Set[str] = field(default_factory=set)
    duplicate_transaction_ids: Set[str] = field(default_factory=set)
    current_step: int = 0
    completed_steps: List[int] = field(default_factory=list)
    all_matches: List[Dict] = field(default_factory=list)
    rejected_matches: List[Dict] = field(default_factory=list)
    
    def mark_document_matched(self, document_type: str, document_id: str):
        """Mark a document as matched."""
        doc_type_key = self._normalize_doc_type(document_type)
        if doc_type_key in self.matched_document_ids:
            self.matched_document_ids[doc_type_key].add(str(document_id))
    
    def mark_transaction_matched(self, transaction_id: str):
        """Mark a transaction as matched."""
        self.matched_transaction_ids.add(str(transaction_id))
    
    def mark_transaction_duplicate(self, transaction_id: str):
        """Mark a transaction as duplicate."""
        self.duplicate_transaction_ids.add(str(transaction_id))
    
    def is_document_matched(self, document_type: str, document_id: str) -> bool:
        """Check if document is already matched."""
        doc_type_key = self._normalize_doc_type(document_type)
        return str(document_id) in self.matched_document_ids.get(doc_type_key, set())
    
    def is_transaction_matched(self, transaction_id: str) -> bool:
        """Check if transaction is already matched."""
        return str(transaction_id) in self.matched_transaction_ids
    
    def is_transaction_duplicate(self, transaction_id: str) -> bool:
        """Check if transaction is marked as duplicate."""
        return str(transaction_id) in self.duplicate_transaction_ids
    
    def rollback_match(self, match: Dict):
        """Rollback a rejected match."""
        # Unmark transaction(s)
        if txn_id := match.get('transaction_id'):
            self.matched_transaction_ids.discard(str(txn_id))
        for txn_id in match.get('transaction_ids', []):
            self.matched_transaction_ids.discard(str(txn_id))
        
        # Unmark document(s)
        doc_type = match.get('document_type', 'bill')
        doc_type_key = self._normalize_doc_type(doc_type)
        
        if doc_id := match.get('document_id'):
            self.matched_document_ids[doc_type_key].discard(str(doc_id))
        for doc_id in match.get('document_ids', []):
            self.matched_document_ids[doc_type_key].discard(str(doc_id))
    
    def _normalize_doc_type(self, doc_type: str) -> str:
        """Normalize document type to registry key."""
        if not doc_type:
            return 'bill'
        doc_type = doc_type.lower()
        mapping = {
            'bills': 'bill', 'bill': 'bill',
            'invoices': 'invoice', 'invoice': 'invoice',
            'credit_notes': 'credit_note', 'credit_note': 'credit_note',
            'payroll': 'payroll', 'payroll_transactions': 'payroll',
            'shares': 'share', 'share': 'share',
        }
        return mapping.get(doc_type, 'bill')


# =============================================================================
# DOCUMENT FILTERING
# =============================================================================

def filter_candidate_documents(
    transaction: Dict,
    all_documents: Dict,
    config: MatchingConfig = DEFAULT_CONFIG,
    date_range_days: Optional[int] = None,
    for_combination: bool = False
) -> Dict:
    """
    Pre-filter documents by date/amount range.

    CRITICAL FOR COMBINATION MATCHING:
    - BATCH payments (1→N): Transaction pays multiple SMALLER documents
      Example: €3200 txn → [€1200, €800, €1200] bills
      
    - SPLIT payments (N→1): Multiple SMALLER transactions pay one LARGER document  
      Example: [€20, €40] txns → €60 bill
      
    For combination matching, we use a VERY PERMISSIVE amount range (0 to 10x)
    to ensure candidates are available for both scenarios.
    """ 

    txn_date_str = transaction.get('date')
    txn_amount = to_decimal(transaction.get('amount', 0))

    if not txn_date_str or txn_amount == 0:
        return all_documents

    try:
        txn_datetime = datetime.strptime(txn_date_str, "%Y-%m-%d")
    except ValueError:
        return all_documents

    # Use provided date range or default
    date_range = date_range_days or config.exact_match_date_range
    min_date = txn_datetime - timedelta(days=date_range)
    max_date = txn_datetime + timedelta(days=date_range)

    abs_amount = abs(txn_amount)

    # -----------------------------
    # AMOUNT FILTER LOGIC (UPDATED)
    # -----------------------------
    if for_combination:
        # Combination matching needs *all* bills <= transaction amount
        min_amount = Decimal("0")
        max_amount = abs_amount * Decimal("10.0")
    else:
        # Original logic for exact and fuzzy matching
        min_amount = abs_amount * Decimal("0.5")
        max_amount = abs_amount * Decimal("1.5")

    filtered = {}
    for doc_type, docs_list in all_documents.items():
        filtered[doc_type] = []

        for doc in docs_list[:config.max_documents_per_type]:

            # ---- DATE FILTER ----
            if doc_date_str := doc.get('date'):
                try:
                    doc_dt = datetime.strptime(doc_date_str, "%Y-%m-%d")
                    if doc_dt < min_date or doc_dt > max_date:
                        continue
                except ValueError:
                    pass

            # ---- AMOUNT FILTER (UPDATED LOGIC) ----
            doc_amount = abs(to_decimal(doc.get('amount', 0)))
            if not (min_amount <= doc_amount <= max_amount):
                continue

            filtered[doc_type].append(doc)

            # Respect per-type candidate cap
            if len(filtered[doc_type]) >= config.max_candidates_per_txn:
                break

    return filtered



# =============================================================================
# VALIDATION UTILITIES (FIXED: Reject hallucinated IDs)
# =============================================================================

def build_lookup_tables(
    transactions: List[Dict],
    documents: Dict
) -> Tuple[Dict[str, Dict], Dict[str, Dict]]:
    """
    Build lookup tables for transactions and documents.
    
    Returns:
        Tuple of (transaction_lookup, document_lookup)
    """
    # Transaction lookup
    txn_lookup = {}
    for t in transactions:
        txn_id = str(t.get("transaction_id") or t.get("odoo_id") or "")
        if txn_id:
            txn_lookup[txn_id] = t
    
    # Document lookup
    doc_lookup = {}
    for doc_type, docs in documents.items():
        type_key = doc_type.rstrip('s') if doc_type.endswith('s') else doc_type
        id_field = f"{type_key}_id"
        
        for doc in docs:
            doc_id = str(doc.get(id_field) or doc.get("id") or "")
            if doc_id:
                doc_lookup[doc_id] = {**doc, "_doc_type": doc_type}
    
    return txn_lookup, doc_lookup


def validate_match_integrity(
    transactions: Union[Dict, List[Dict]],
    documents: List[Dict],
    match_type: str = 'single',
    tolerance_type: ToleranceType = ToleranceType.EXACT,
    config: MatchingConfig = DEFAULT_CONFIG
) -> Tuple[bool, str, Optional[Dict]]:
    """
    Comprehensive match validation with tolerance support.
    
    Returns:
        Tuple of (is_valid, error_message, metadata)
        metadata includes: difference, tolerance_used, etc.
    """
    if not documents:
        return False, "No documents provided", None
    
    # Normalize transactions to list
    txn_list = [transactions] if isinstance(transactions, dict) else transactions
    if not txn_list:
        return False, "No transactions provided", None
    
    # Calculate totals
    total_txn_amount = sum_amounts([t.get('amount', 0) for t in txn_list])
    total_doc_amount = sum_amounts([d.get('amount', 0) for d in documents])
    
    # Calculate tolerance
    tolerance = calculate_tolerance(total_txn_amount, tolerance_type, config)
    
    # Amount validation with tolerance
    is_equal, difference = amounts_equal(total_txn_amount, total_doc_amount, tolerance)
    
    metadata = {
        "transaction_amount": format_decimal(total_txn_amount),
        "document_amount": format_decimal(total_doc_amount),
        "difference": format_decimal(difference),
        "tolerance_used": format_decimal(tolerance),
        "tolerance_type": tolerance_type.value
    }
    
    if not is_equal:
        return False, f"Amount mismatch: txn {format_decimal(total_txn_amount)} vs doc {format_decimal(total_doc_amount)} (diff: {format_decimal(difference)}, tolerance: {format_decimal(tolerance)})", metadata
    
    # Currency validation
    if config.require_currency_match:
        currencies = set()
        for t in txn_list:
            if curr := (t.get('currency') or 'EUR').upper():
                currencies.add(curr)
        for d in documents:
            if curr := (d.get('currency') or 'EUR').upper():
                currencies.add(curr)
        
        if len(currencies) > 1:
            return False, f"Currency mismatch: {currencies}", metadata
    
    return True, "", metadata


def validate_exact_matches(
    matches: List[Dict],
    transactions: List[Dict],
    documents: Dict,
    config: MatchingConfig = DEFAULT_CONFIG
) -> Tuple[List[Dict], List[Dict]]:
    """
    Python-side validation of exact matches.
    FIXED: Rejects hallucinated/missing IDs instead of accepting them.
    
    Returns:
        Tuple of (valid_matches, rejected_matches)
    """
    valid = []
    rejected = []
    
    txn_lookup, doc_lookup = build_lookup_tables(transactions, documents)
    
    for match in matches:
        txn_id = str(match.get("transaction_id") or "")
        doc_id = str(match.get("document_id") or "")
        
        # CRITICAL FIX: Reject hallucinated IDs
        txn = txn_lookup.get(txn_id)
        doc = doc_lookup.get(doc_id)
        
        if not txn:
            logger.error(f"REJECTING match: Hallucinated transaction ID '{txn_id}'")
            match["rejection_reason"] = RejectionReason.HALLUCINATED_TRANSACTION_ID.value
            match["python_validated"] = False
            rejected.append(match)
            continue
        
        if not doc:
            logger.error(f"REJECTING match: Hallucinated document ID '{doc_id}'")
            match["rejection_reason"] = RejectionReason.HALLUCINATED_DOCUMENT_ID.value
            match["python_validated"] = False
            rejected.append(match)
            continue
        
        # Determine tolerance type based on match characteristics
        tolerance_type = ToleranceType.EXACT
        # SUSPENSE MATCHES: Always use bank_fee tolerance (they may have fees/rounding)
        if match.get("match_type", "").startswith("suspense"):
            tolerance_type = ToleranceType.BANK_FEE
        elif match.get("has_bank_fee") or "fee" in (match.get("match_details", {}).get("reasoning", "") or "").lower():
            tolerance_type = ToleranceType.BANK_FEE
        
        # Validate match integrity
        is_valid, error, metadata = validate_match_integrity(
            txn, [doc], 
            match_type='single',
            tolerance_type=tolerance_type,
            config=config
        )
        
        if is_valid:
            match["python_validated"] = True
            match["validation_metadata"] = metadata
            valid.append(match)
        else:
            match["rejection_reason"] = error
            match["python_validated"] = False
            match["validation_metadata"] = metadata
            rejected.append(match)
            logger.warning(f"Match rejected: {error}")
    
    return valid, rejected


def validate_combination_matches(
    matches: List[Dict],
    transactions: List[Dict],
    documents: Dict,
    config: MatchingConfig = DEFAULT_CONFIG
) -> Tuple[List[Dict], List[Dict]]:
    """
    Python-side validation of combination matches.
    FIXED: Rejects hallucinated/missing IDs.
    
    Returns:
        Tuple of (valid_matches, rejected_matches)
    """
    valid = []
    rejected = []
    
    txn_lookup, doc_lookup = build_lookup_tables(transactions, documents)
    
    for match in matches:
        try:
            # Determine match type and gather items
            if match.get("transaction_ids"):
                # Split payment (N→1)
                txn_ids = [str(tid) for tid in match.get("transaction_ids", [])]
                txns = []
                for tid in txn_ids:
                    if txn := txn_lookup.get(tid):
                        txns.append(txn)
                    else:
                        logger.error(f"REJECTING combo: Hallucinated transaction ID '{tid}'")
                        match["rejection_reason"] = RejectionReason.HALLUCINATED_TRANSACTION_ID.value
                        match["python_validated"] = False
                        rejected.append(match)
                        break
                else:
                    # All transaction IDs valid
                    doc_id = str(match.get("document_id") or "")
                    if doc := doc_lookup.get(doc_id):
                        docs = [doc]
                    else:
                        logger.error(f"REJECTING combo: Hallucinated document ID '{doc_id}'")
                        match["rejection_reason"] = RejectionReason.HALLUCINATED_DOCUMENT_ID.value
                        match["python_validated"] = False
                        rejected.append(match)
                        continue
                    
                    match_type = 'combination_split'
            else:
                # Batch payment (1→N)
                txn_id = str(match.get("transaction_id") or "")
                if txn := txn_lookup.get(txn_id):
                    txns = [txn]
                else:
                    logger.error(f"REJECTING combo: Hallucinated transaction ID '{txn_id}'")
                    match["rejection_reason"] = RejectionReason.HALLUCINATED_TRANSACTION_ID.value
                    match["python_validated"] = False
                    rejected.append(match)
                    continue
                
                doc_ids = [str(did) for did in match.get("document_ids", [])]
                docs = []
                for did in doc_ids:
                    if doc := doc_lookup.get(did):
                        docs.append(doc)
                    else:
                        logger.error(f"REJECTING combo: Hallucinated document ID '{did}'")
                        match["rejection_reason"] = RejectionReason.HALLUCINATED_DOCUMENT_ID.value
                        match["python_validated"] = False
                        rejected.append(match)
                        break
                else:
                    match_type = 'combination_batch'
            
            # Skip if already rejected
            if match.get("python_validated") == False:
                continue
            
            # Check combination size
            if len(docs) > config.max_combination_size or len(txns) > config.max_combination_size:
                match["rejection_reason"] = RejectionReason.INVALID_COMBINATION.value
                match["python_validated"] = False
                rejected.append(match)
                continue
            
            # Use rounding tolerance for combinations (split payments often have rounding)
            tolerance_type = ToleranceType.ROUNDING
            
            # Validate
            is_valid, error, metadata = validate_match_integrity(
                txns, docs,
                match_type=match_type,
                tolerance_type=tolerance_type,
                config=config
            )
            
            if is_valid:
                match["python_validated"] = True
                match["validation_metadata"] = metadata
                valid.append(match)
            else:
                match["rejection_reason"] = error
                match["python_validated"] = False
                match["validation_metadata"] = metadata
                rejected.append(match)
                logger.warning(f"Combination match rejected: {error}")
                
        except Exception as e:
            logger.error(f"Error validating combination match: {e}")
            match["rejection_reason"] = f"Validation error: {str(e)}"
            match["python_validated"] = False
            rejected.append(match)
    
    return valid, rejected


def extract_matched_ids(matches: List[Dict]) -> Tuple[Dict[str, Set[str]], Set[str]]:
    """Extract transaction and document IDs from matches."""
    doc_ids = {k: set() for k in ['bill', 'invoice', 'credit_note', 'payroll', 'share']}
    txn_ids = set()
    
    for match in matches:
        # Transaction IDs
        if tid := match.get('transaction_id'):
            txn_ids.add(str(tid))
        for tid in match.get('transaction_ids', []):
            txn_ids.add(str(tid))
        
        # Document IDs
        doc_type = (match.get('document_type') or 'bill').lower()
        doc_type_key = doc_type.rstrip('s') if doc_type.endswith('s') else doc_type
        if doc_type_key not in doc_ids:
            doc_type_key = 'bill'
        
        if did := match.get('document_id'):
            doc_ids[doc_type_key].add(str(did))
        for did in match.get('document_ids', []):
            doc_ids[doc_type_key].add(str(did))
    
    return doc_ids, txn_ids


# =============================================================================
# TEXT UTILITIES
# =============================================================================

def normalize_text(text: str) -> str:
    """Normalize text for matching."""
    if not text:
        return ""
    text = str(text).lower().strip()
    # Greek diacritics
    for acc, plain in [('ά','α'),('έ','ε'),('ή','η'),('ί','ι'),('ό','ο'),('ύ','υ'),('ώ','ω')]:
        text = text.replace(acc, plain)
    text = re.sub(r'[^\w\sαβγδεζηθικλμνξοπρστυφχψω]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\b(ltd|limited|inc|corp|co|llc)\b', '', text)
    return text.strip()


def calculate_date_difference(date1: str, date2: str) -> int:
    """Calculate days between two dates."""
    try:
        d1 = datetime.strptime(date1, "%Y-%m-%d")
        d2 = datetime.strptime(date2, "%Y-%m-%d")
        return abs((d1 - d2).days)
    except (ValueError, TypeError):
        return 9999


# =============================================================================
# AGENT PROMPTS (Optimized for batched processing)
# =============================================================================

DATA_ENRICHMENT_PROMPT = """You are the Data Enrichment Agent - the critical first step in transaction matching.

========================================
CRITICAL OUTPUT REQUIREMENTS
========================================
1. MUST return ONLY valid JSON (no markdown, no explanation)
2. ALL required fields MUST be present for each transaction
3. Boolean fields (is_suspense, is_internal_transfer) MUST be actual booleans (true/false), NOT strings
4. Amount fields MUST be formatted as "1000.00" strings with exactly 2 decimal places
5. transaction_id MUST use odoo_id converted to string

========================================
REQUIRED OUTPUT FIELDS (EACH TRANSACTION)
========================================
- transaction_id: string (from odoo_id)
- odoo_id: integer (original ID)
- date: string (YYYY-MM-DD format)
- amount: string (formatted as "1000.00")
- currency: string (default "EUR" if missing)
- partner_name: string (original partner name)
- normalized_partner: string (lowercase, cleaned)
- account_name: string (non-bank account from line_items)
- category: string (bill_payment|invoice_receipt|payroll_payment|internal_transfer|suspense)
- is_suspense: boolean (true/false, NOT string "true"/"false")
- is_internal_transfer: boolean (true/false)
- description: string (original description)
- keywords: array of strings (max 3)

========================================
CATEGORY CLASSIFICATION RULES
========================================

1. SUSPENSE (Highest Priority)
   Conditions (ANY of these):
   - Account contains "suspense" (case-insensitive)
   - Partner contains: "suspense", "unknown", "unidentified", "pending"
   - Description suggests unidentified payment
   
   Required:
   - category: "suspense"
   - is_suspense: true (BOOLEAN, not string)

2. INTERNAL_TRANSFER
   Conditions (ALL must match):
   - Line items contain BOTH "Credit card" AND "Bank" accounts
   - Amount appears in both debit and credit
   
   Required:
   - category: "internal_transfer"
   - is_internal_transfer: true

3. PAYROLL_PAYMENT
   Conditions (ANY):
   - Account contains: "payroll", "wages", "salary"
   - Partner contains: "employee", "payroll"
   - Description contains: "salary", "wages"
   
   Required:
   - category: "payroll_payment"

4. INVOICE_RECEIPT (Revenue)
   Conditions:
   - Positive amount AND
   - Account contains: "accounts receivable", "revenue", "sales"
   
   Required:
   - category: "invoice_receipt"

5. BILL_PAYMENT (Expense)
   Conditions:
   - Account contains: "accounts payable", "expense"
   - OR default for payments
   
   Required:
   - category: "bill_payment"

========================================
ACCOUNT_NAME EXTRACTION RULES
========================================
From line_items array, extract the FIRST account that is NOT:
- "Bank"
- "Cash"
- Any bank/cash account

Example:
line_items: [
  {"account": "Accounts payable", "debit": 1000, "credit": 0},
  {"account": "Bank", "debit": 0, "credit": 1000}
]
→ account_name: "Accounts payable"

========================================
EXAMPLES
========================================

Example 1: SUSPENSE Transaction
Input:
{
  "odoo_id": 1008,
  "date": "2025-06-20",
  "amount": 1200.00,
  "partner_name": "Suspense - Transfer",
  "description": "Unidentified payment",
  "line_items": [
    {"account": "Suspense account", "debit": 1200, "credit": 0},
    {"account": "Bank", "debit": 0, "credit": 1200}
  ]
}

Output:
{
  "transaction_id": "1008",
  "odoo_id": 1008,
  "date": "2025-06-20",
  "amount": "1200.00",
  "currency": "EUR",
  "partner_name": "Suspense - Transfer",
  "normalized_partner": "suspense transfer",
  "account_name": "Suspense account",
  "category": "suspense",
  "is_suspense": true,
  "is_internal_transfer": false,
  "description": "Unidentified payment",
  "keywords": ["unidentified", "payment", "suspense"]
}

Example 2: INTERNAL TRANSFER
Input:
{
  "odoo_id": 1004,
  "date": "2025-06-12",
  "amount": 5000.00,
  "partner_name": "Credit card payment",
  "line_items": [
    {"account": "Credit card", "debit": 5000, "credit": 0},
    {"account": "Bank", "debit": 0, "credit": 5000}
  ]
}

Output:
{
  "transaction_id": "1004",
  "odoo_id": 1004,
  "date": "2025-06-12",
  "amount": "5000.00",
  "currency": "EUR",
  "partner_name": "Credit card payment",
  "normalized_partner": "credit card payment",
  "account_name": "Credit card",
  "category": "internal_transfer",
  "is_suspense": false,
  "is_internal_transfer": true,
  "description": "",
  "keywords": ["credit", "card", "payment"]
}

Example 3: BILL PAYMENT
Input:
{
  "odoo_id": 1001,
  "date": "2025-06-05",
  "amount": 2500.00,
  "partner_name": "ABC Property Management",
  "description": "Office rent payment June 2025",
  "line_items": [
    {"account": "Accounts payable", "debit": 2500, "credit": 0},
    {"account": "Bank", "debit": 0, "credit": 2500}
  ]
}

Output:
{
  "transaction_id": "1001",
  "odoo_id": 1001,
  "date": "2025-06-05",
  "amount": "2500.00",
  "currency": "EUR",
  "partner_name": "ABC Property Management",
  "normalized_partner": "abc property management",
  "account_name": "Accounts payable",
  "category": "bill_payment",
  "is_suspense": false,
  "is_internal_transfer": false,
  "description": "Office rent payment June 2025",
  "keywords": ["office", "rent", "payment"]
}

========================================
DOCUMENT ENRICHMENT
========================================
For bills, invoices, credit_notes, payroll, shares:
- Keep all existing fields
- Add normalized_partner (lowercase cleaned)
- Ensure all IDs are preserved
- Format amounts as "1000.00"

========================================
OUTPUT FORMAT
========================================
```json
{
  "enriched_transactions": [
    {
      "transaction_id": "string",
      "odoo_id": integer,
      "date": "YYYY-MM-DD",
      "amount": "1000.00",
      "currency": "EUR",
      "partner_name": "string",
      "normalized_partner": "string",
      "account_name": "string",
      "category": "bill_payment|invoice_receipt|payroll_payment|internal_transfer|suspense",
      "is_suspense": boolean,
      "is_internal_transfer": boolean,
      "description": "string",
      "keywords": ["string"]
    }
  ],
  "enriched_bills": [...],
  "enriched_invoices": [...],
  "enriched_credit_notes": [...],
  "enriched_payroll": [...],
  "enriched_shares": [],
  "enrichment_summary": {
    "transactions_processed": integer,
    "suspense_count": integer,
    "internal_transfer_count": integer
  }
}
```

========================================
VALIDATION CHECKLIST
========================================
Before returning, verify:
☑ All transactions have transaction_id as STRING
☑ is_suspense is BOOLEAN (true/false), not string
☑ is_internal_transfer is BOOLEAN (true/false), not string
☑ Amounts are formatted as "1000.00" strings
☑ Categories are valid enum values
☑ Account names extracted correctly
☑ All required fields present
☑ Valid JSON syntax
"""


DUPLICATE_DETECTION_PROMPT = """You are the Duplicate Detection Agent.

## TASK
Find duplicate internal transfer transactions.

## CRITERIA (ALL must match)
1. Both have line_items with "Credit card" AND "Bank"
2. Amounts EXACTLY equal
3. Same date or within 1 day

========================================
CRITICAL INSTRUCTIONS
========================================
1. Return ONLY valid JSON - no markdown, no preamble, no explanation
2. ALL required fields MUST be present
3. Use ONLY IDs that exist in the provided input
4. NEVER fabricate or hallucinate IDs
5. Follow the exact output format specified below

========================================

## OUTPUT FORMAT
```json
{
  "duplicate_pairs": [
    {
      "transaction_1": "1004",
      "transaction_2": "1005",
      "keep": "1005",
      "mark_for_deletion": "1004",
      "odoo_id_to_delete": 1004,
      "reason": "Internal transfer duplicate",
      "confidence": "HIGH"
    }
  ],
  "non_duplicate_transaction_ids": ["1001", "1002", "1003"],
  "summary": {"duplicates_found": 1}
}
```"""


EXACT_MATCH_PROMPT = """You are the Exact Match Agent.

========================================
CRITICAL INSTRUCTIONS
========================================
1. Return ONLY valid JSON - no markdown, no preamble, no explanation
2. ALL required fields MUST be present
3. Use ONLY IDs that exist in the provided input
4. NEVER fabricate or hallucinate IDs
5. Follow the exact output format specified below

========================================

## TASK
Match transactions to documents. Process ONLY the transactions provided.

## MATCHING RULES
1. Amount: Must match exactly (or within €5 if bank fee suspected)
2. Currency: Must match
3. Partner: Exact or substring match
4. Date: Within 7 days

## IMPORTANT
- Only return matches for transaction IDs that exist in the input
- Only use document IDs that exist in the candidate list
- If no match found, include in unmatched list

## OUTPUT FORMAT
```json
{
  "matched": [
    {
      "transaction_id": "1001",
      "document_type": "bill",
      "document_id": "BILL_2025_001",
      "match_type": "exact",
      "has_bank_fee": false,
      "match_details": {
        "amount_match": "exact",
        "partner_match": "substring",
        "date_diff_days": 4,
        "reasoning": "Amount exact, partner substring match"
      },
      "confidence": "HIGH"
    }
  ],
  "unmatched_transaction_ids": ["1003"]
}
```"""


CONTEXT_ANALYSIS_PROMPT = """You are the Context Analysis Agent.

========================================
CRITICAL INSTRUCTIONS
========================================
1. Return ONLY valid JSON - no markdown, no preamble, no explanation
2. ALL required fields MUST be present
3. Use ONLY IDs that exist in the provided input
4. NEVER fabricate or hallucinate IDs
5. Follow the exact output format specified below

## TASK
Determine date ranges for unmatched transactions based on business context.

## CONTEXTS
- STANDARD: 60 days (default)
- PROFESSIONAL_SERVICES: 180 days (engineering, legal, surveys)
- GOVERNMENT: 120 days
- CONSTRUCTION: 365 days

## OUTPUT FORMAT
```json
{
  "context_analysis": [
    {
      "transaction_id": "1005",
      "business_context": "PROFESSIONAL_SERVICES",
      "date_range_days": 180,
      "reasoning": "Engineering survey service"
    }
  ]
}
```"""


PARTNER_RESOLUTION_PROMPT = """You are the Partner Resolution Agent.

========================================
CRITICAL INSTRUCTIONS
========================================
1. Return ONLY valid JSON - no markdown, no preamble, no explanation
2. ALL required fields MUST be present
3. Use ONLY IDs that exist in the provided input
4. NEVER fabricate or hallucinate IDs
5. Follow the exact output format specified below

## TASK
Match transactions using fuzzy partner matching. Amount must still be exact.

## PARTNER MATCHING TECHNIQUES
- Substring: "ABC" matches "ABC Corporation Ltd"
- Abbreviation: "Corp" = "Corporation"
- Variations: "Co" = "Company"

## OUTPUT FORMAT
```json
{
  "matched": [
    {
      "transaction_id": "1002",
      "document_type": "bill",
      "document_id": "BILL_2025_002",
      "match_type": "fuzzy",
      "match_details": {
        "partner_match": "substring",
        "partner_similarity": 0.85,
        "date_diff_days": 14
      },
      "confidence": "MEDIUM"
    }
  ],
  "unmatched_transaction_ids": []
}
```"""


COMBINATION_MATCH_PROMPT = """You are the Combination Match Agent - specialized in finding batch and split payment matches.

========================================
CRITICAL OUTPUT REQUIREMENTS
========================================
1. MUST return ONLY valid JSON
2. ONLY use transaction IDs and document IDs that exist in the provided input
3. NEVER fabricate or hallucinate IDs
4. Amounts must sum exactly (within 0.05 rounding tolerance)
5. Maximum 5 items per combination

========================================
MATCHING SCENARIOS
========================================

SCENARIO A: BATCH PAYMENT (1 Transaction → N Documents)
Definition: One transaction pays multiple bills/invoices
Logic:
  - Transaction amount = SUM(document amounts)
  - All documents must be same type (all bills OR all invoices)
  - All documents must be same currency
  - Preferably same partner (but not required)
  - Documents dated within 90 days of transaction

Example:
  Transaction: 3200.00 on 2025-06-10 "Multiple Vendors Payment"
  Documents:
    BILL_001: 1200.00
    BILL_002: 800.00
    BILL_003: 1200.00
  Match: 1200 + 800 + 1200 = 3200 ✓

SCENARIO B: SPLIT PAYMENT (N Transactions → 1 Document)
Definition: Multiple transactions pay one invoice/bill
Logic:
  - SUM(transaction amounts) = Document amount
  - All transactions within 30 days of each other
  - All transactions same currency
  - Document dated within 60 days of transactions

Example:
  Document: INV_001: 5000.00 on 2025-06-01
  Transactions:
    TXN_101: 2000.00 on 2025-06-05
    TXN_102: 1500.00 on 2025-06-08
    TXN_103: 1500.00 on 2025-06-10
  Match: 2000 + 1500 + 1500 = 5000 ✓

========================================
MATCHING RULES
========================================

1. AMOUNT VALIDATION (CRITICAL)
   - Calculate sum with Decimal precision
   - Allow tolerance: ±0.05 (5 cents for rounding)
   - Difference must be ≤ 0.05 or reject match

2. CURRENCY VALIDATION
   - All items in combination must have same currency
   - If any currency differs, reject match

3. SIZE LIMITS
   - Minimum: 2 items (otherwise it's single match)
   - Maximum: 5 items (prevents combinatorial explosion)
   - If more than 5 needed, leave unmatched

4. DATE PROXIMITY
   - For batch: All documents within 90 days of transaction
   - For split: All transactions within 30 days of each other
   - Document within 60 days of transaction dates

5. TYPE CONSISTENCY
   - Batch: All documents must be same type
   - Cannot mix bills and invoices in one combination

6. PARTNER PREFERENCE (Not Required)
   - Prefer combinations with same partner
   - But different partners OK if amounts match exactly

========================================
DECISION PROCESS
========================================

For EACH unmatched transaction:

Step 1: Check if amount suggests combination
  - Amount > 1000? More likely to be batch
  - Description contains "multiple", "consolidated", "batch"? Likely batch
  - Otherwise, check both scenarios

Step 2: Find candidate combinations
  FOR BATCH (1→N):
    a) Filter documents: same type, within date range
    b) Find all subsets of 2-5 documents
    c) Calculate sum for each subset
    d) If sum matches transaction ±0.05, candidate found
    e) Select combination with closest date proximity

  FOR SPLIT (N→1):
    a) Find documents with amount > transaction amount
    b) Find other unmatched transactions
    c) Try combinations that sum to document amount
    d) Validate dates and currency

Step 3: Validate selected match
  - Verify IDs exist in input
  - Verify amounts sum correctly
  - Verify currency matches
  - Verify size limits (2-5 items)

Step 4: Calculate confidence
  - Exact sum (0.00 diff) → Higher confidence
  - Same partner → Higher confidence
  - Close dates → Higher confidence
  - Fewer items → Higher confidence

========================================
EXAMPLES
========================================

Example 1: BATCH PAYMENT (Success)
Input:
{
  "transaction": {
    "transaction_id": "1003",
    "amount": "3200.00",
    "date": "2025-06-10",
    "partner": "Multiple Vendors Payment"
  },
  "candidates": {
    "bills": [
      {"id": "BILL_2025_003", "amount": "1200.00", "date": "2025-06-03"},
      {"id": "BILL_2025_004", "amount": "800.00", "date": "2025-06-05"},
      {"id": "BILL_2025_005", "amount": "1200.00", "date": "2025-06-07"}
    ]
  }
}

Analysis:
- Transaction: 3200.00
- BILL_003 + BILL_004 + BILL_005 = 1200 + 800 + 1200 = 3200 ✓
- All same type (bills) ✓
- All within 90 days ✓
- Currency matches (assumed EUR) ✓
- Size: 3 items ✓

Output:
{
  "transaction_id": "1003",
  "document_type": "bill",
  "document_ids": ["BILL_2025_003", "BILL_2025_004", "BILL_2025_005"],
  "match_type": "combination_batch",
  "match_details": {
    "document_amounts": ["1200.00", "800.00", "1200.00"],
    "sum": "3200.00",
    "transaction_amount": "3200.00",
    "difference": "0.00",
    "reasoning": "Exact sum match (1200+800+1200=3200). All bills from same vendor dated within 7 days of transaction.",
    "combination_type": "batch_payment",
    "documents_count": 3
  },
  "confidence": "MEDIUM"
}

Example 2: SPLIT PAYMENT (Success)
Input:
{
  "transactions": [
    {"transaction_id": "2001", "amount": "1500.00", "date": "2025-06-05"},
    {"transaction_id": "2002", "amount": "1500.00", "date": "2025-06-08"},
    {"transaction_id": "2003", "amount": "2000.00", "date": "2025-06-10"}
  ],
  "document": {
    "id": "INV_2025_050",
    "amount": "5000.00",
    "date": "2025-06-01"
  }
}

Analysis:
- Document: 5000.00
- TXN_2001 + TXN_2002 + TXN_2003 = 1500 + 1500 + 2000 = 5000 ✓
- All within 30 days of each other ✓
- All within 60 days of document ✓

Output:
{
  "transaction_ids": ["2001", "2002", "2003"],
  "document_type": "invoice",
  "document_id": "INV_2025_050",
  "match_type": "combination_split",
  "match_details": {
    "transaction_amounts": ["1500.00", "1500.00", "2000.00"],
    "sum": "5000.00",
    "document_amount": "5000.00",
    "difference": "0.00",
    "reasoning": "Split payment: Three transactions sum exactly to invoice amount (1500+1500+2000=5000). All within 10 days.",
    "combination_type": "split_payment",
    "transactions_count": 3
  },
  "confidence": "MEDIUM"
}

Example 3: REJECTION (Amount Mismatch)
Scenario:
- Transaction: 3200.00
- Available: BILL_A (1000), BILL_B (1000), BILL_C (1100)
- Sum: 3100 (diff = 100, exceeds 0.05 tolerance)
→ DO NOT MATCH, add to unmatched_transaction_ids

Example 4: REJECTION (Too Many Items)
Scenario:
- Transaction: 10000.00
- Need to combine 7 bills to reach amount
→ DO NOT MATCH (exceeds max 5 items)

========================================
CONFIDENCE LEVELS
========================================

MEDIUM Confidence:
- Exact sum (0.00-0.02 difference)
- Same partner across documents
- Dates within 30 days
- 2-3 items

LOW Confidence:
- Near tolerance (0.03-0.05 difference)
- Different partners
- Dates within 60-90 days
- 4-5 items

========================================
OUTPUT FORMAT
========================================
```json
{
  "matched": [
    {
      "transaction_id": "string",
      "document_type": "bill|invoice",
      "document_ids": ["id1", "id2"],
      "match_type": "combination_batch",
      "match_details": {
        "document_amounts": ["1200.00", "800.00"],
        "sum": "2000.00",
        "transaction_amount": "2000.00",
        "difference": "0.00",
        "reasoning": "detailed explanation",
        "combination_type": "batch_payment",
        "documents_count": 2
      },
      "confidence": "MEDIUM|LOW"
    }
  ],
  "unmatched_transaction_ids": ["string"]
}
```

========================================
IMPORTANT REMINDERS
========================================
1. ALWAYS verify IDs exist in input before creating match
2. NEVER create combinations with >5 items
3. Check tolerance: difference must be ≤0.05
4. Provide detailed reasoning explaining why this combination was selected
5. If no valid combination found, add to unmatched list
6. Do not be overly conservative - combinations are valid matching patterns
"""


VALIDATION_PROMPT = """You are the Validation Agent - the critical quality gate before reconciliation.

========================================
MISSION
========================================
Validate ALL matches to prevent:
1. Hallucinated/missing IDs
2. Amount mismatches
3. Currency mismatches
4. Duplicate usage of documents/transactions
5. Logic errors in account types

========================================
CRITICAL OUTPUT REQUIREMENTS
========================================
1. MUST return ONLY valid JSON
2. Each match must have clear rejection_reason if rejected
3. Use exact error messages from validation checks
4. will_be_rolled_back: true for all rejected matches

========================================
VALIDATION CHECKS (IN ORDER)
========================================

CHECK 1: ID EXISTENCE ★★★★★ CRITICAL
For EACH match:
  1.1: Verify transaction_id exists in original input
  1.2: Verify document_id(s) exist in original input
  1.3: If ANY ID missing → REJECT with "HALLUCINATED_ID"

Why Critical: Prevents matching to non-existent records

Example Rejection:
{
  "rejection_reason": "Hallucinated document ID 'BILL_9999' - not found in input",
  "will_be_rolled_back": true
}

CHECK 2: AMOUNT VALIDATION ★★★★★ CRITICAL
For single matches:
  - Transaction amount MUST equal document amount (within tolerance)
  - Tolerance: 0.00 for exact, 5.00 for bank_fee, 0.05 for rounding
  - Calculate: |txn_amount - doc_amount|
  - If difference > tolerance → REJECT

For combination matches:
  - SUM(amounts) must equal target amount (within 0.05)
  - Verify sum calculation is correct
  - If mismatch → REJECT

Example Rejection:
{
  "rejection_reason": "Amount mismatch: txn 1000.00 vs doc 1050.00 (diff: 50.00, tolerance: 5.00)",
  "will_be_rolled_back": true
}

CHECK 3: CURRENCY VALIDATION ★★★★☆ HIGH PRIORITY
For ALL matches:
  - Extract currency from transaction
  - Extract currency from document(s)
  - Compare currencies (default EUR if missing)
  - If currencies differ → REJECT

Example Rejection:
{
  "rejection_reason": "Currency mismatch: transaction EUR vs document USD",
  "will_be_rolled_back": true
}

CHECK 4: DUPLICATE DETECTION ★★★★☆ HIGH PRIORITY
Track used IDs across all matches:
  - Maintain set of matched transaction_ids
  - Maintain set of matched document_ids per type
  - If ID appears twice → REJECT second occurrence

Example Rejection:
{
  "rejection_reason": "Duplicate usage: BILL_2025_001 already matched in another match",
  "will_be_rolled_back": true
}

CHECK 5: COMBINATION LOGIC ★★★☆☆ MEDIUM PRIORITY
For combination matches:
  5.1: Verify 2-5 items (min 2, max 5)
  5.2: Verify all same document type
  5.3: Verify all same currency
  5.4: Verify amounts sum correctly

Example Rejection:
{
  "rejection_reason": "Invalid combination: 6 documents exceeds maximum of 5",
  "will_be_rolled_back": true
}

CHECK 6: ACCOUNT LOGIC ★★☆☆☆ LOW PRIORITY
For specific categories:
  - Payroll: Should match to payroll documents
  - Invoice_receipt: Should match to invoices (revenue)
  - Bill_payment: Should match to bills (expense)
  
Not strictly enforced, but flag inconsistencies

========================================
VALIDATION DECISION TREE
========================================

For EACH match in input:
├─ IDs exist? 
│  ├─ NO → REJECT (HALLUCINATED_ID)
│  └─ YES → Continue
├─ Amount matches (within tolerance)?
│  ├─ NO → REJECT (AMOUNT_MISMATCH)
│  └─ YES → Continue
├─ Currency matches?
│  ├─ NO → REJECT (CURRENCY_MISMATCH)
│  └─ YES → Continue
├─ Already matched (duplicate)?
│  ├─ YES → REJECT (DUPLICATE_MATCH)
│  └─ NO → Continue
├─ Combination logic valid? (if applicable)
│  ├─ NO → REJECT (INVALID_COMBINATION)
│  └─ YES → Continue
└─ ACCEPT → Add to validated_matches

========================================
TOLERANCE GUIDELINES
========================================

EXACT matches:
- Tolerance: 0.00
- Must be exactly equal

BANK_FEE matches (has_bank_fee: true OR match_type contains "suspense"):
- Tolerance: 5.00
- Allows common wire transfer fees

ROUNDING matches (combinations):
- Tolerance: 0.05
- Allows split payment rounding errors

Example tolerance application:
- Match says has_bank_fee: false
- Amount diff: 3.50
- Tolerance: 0.00 (exact)
- 3.50 > 0.00 → REJECT

========================================
EXAMPLES
========================================

Example 1: VALID Match
Input:
{
  "transaction_id": "1001",
  "document_type": "bill",
  "document_id": "BILL_2025_001",
  "match_type": "exact",
  "has_bank_fee": false,
  "match_details": {...}
}

Validation Steps:
1. Check IDs exist: ✓ Both found
2. Check amount: txn=2500, doc=2500, diff=0 ✓
3. Check currency: Both EUR ✓
4. Check duplicates: Not used before ✓
5. Account logic: bill_payment → bill ✓

Output: Add to validated_matches

Example 2: REJECTED - Amount Mismatch
Input:
{
  "transaction_id": "1005",
  "document_id": "BILL_003",
  "match_type": "exact",
  "has_bank_fee": false
}

Validation Steps:
1. Check IDs: ✓
2. Check amount: txn=1000.00, doc=1000.50, diff=0.50
   - Tolerance: 0.00 (exact match, no bank_fee)
   - 0.50 > 0.00 → FAIL
   
Output:
{
  "transaction_id": "1005",
  "document_id": "BILL_003",
  "rejection_reason": "Amount mismatch: txn 1000.00 vs doc 1000.50 (diff: 0.50, tolerance: 0.00)",
  "will_be_rolled_back": true
}

Example 3: REJECTED - Hallucinated ID
Input:
{
  "transaction_id": "9999",
  "document_id": "BILL_2025_001",
  "match_type": "exact"
}

Validation Steps:
1. Check IDs: 
   - Transaction "9999" NOT in input → FAIL
   
Output:
{
  "transaction_id": "9999",
  "document_id": "BILL_2025_001",
  "rejection_reason": "Hallucinated transaction ID '9999' - not found in input",
  "will_be_rolled_back": true
}

Example 4: VALID Combination with Rounding
Input:
{
  "transaction_id": "1003",
  "document_ids": ["BILL_003", "BILL_004", "BILL_005"],
  "match_type": "combination_batch"
}

Validation Steps:
1. Check IDs: ✓ All exist
2. Check amounts: 
   - Transaction: 3200.00
   - Sum: 1200.00 + 800.00 + 1200.02 = 3200.02
   - Diff: 0.02
   - Tolerance: 0.05 (combination)
   - 0.02 ≤ 0.05 ✓
3. Check currency: All EUR ✓
4. Check combination: 3 items, all bills ✓

Output: Add to validated_matches

========================================
OUTPUT FORMAT
========================================
```json
{
  "validated_matches": [
    {
      "transaction_id": "string",
      "document_id": "string",
      "match_type": "exact|fuzzy|combination_batch|...",
      "validation_passed": true,
      "validation_checks": {
        "id_existence": "pass",
        "amount_match": "pass",
        "currency_match": "pass",
        "no_duplicates": "pass"
      }
    }
  ],
  "rejected_matches": [
    {
      "transaction_id": "string",
      "document_id": "string",
      "rejection_reason": "specific reason with details",
      "will_be_rolled_back": true,
      "validation_checks": {
        "id_existence": "pass",
        "amount_match": "FAIL",
        "currency_match": "pass",
        "no_duplicates": "pass"
      }
    }
  ],
  "summary": {
    "total_matches": integer,
    "validated": integer,
    "rejected": integer,
    "rejection_reasons": {
      "HALLUCINATED_ID": integer,
      "AMOUNT_MISMATCH": integer,
      "CURRENCY_MISMATCH": integer,
      "DUPLICATE_MATCH": integer,
      "INVALID_COMBINATION": integer
    }
  }
}
```

========================================
REJECTION REASON TEMPLATES
========================================
Use these exact formats:

Hallucinated ID:
"Hallucinated transaction ID '{id}' - not found in input"
"Hallucinated document ID '{id}' - not found in input"

Amount Mismatch:
"Amount mismatch: txn {txn_amt} vs doc {doc_amt} (diff: {diff}, tolerance: {tol})"

Currency Mismatch:
"Currency mismatch: transaction {txn_curr} vs document {doc_curr}"

Duplicate:
"Duplicate usage: {id} already matched in another match"

Invalid Combination:
"Invalid combination: {count} documents exceeds maximum of 5"
"Invalid combination: documents must be same type"
"Invalid combination: sum mismatch {sum} vs {target}"

========================================
IMPORTANT REMINDERS
========================================
1. Be thorough but not overly strict
2. Suspense matches can have bank_fee tolerance (5.00)
3. Combinations can have rounding tolerance (0.05)
4. Always provide specific rejection reasons
5. Track duplicate usage across ALL matches
6. Validate EVERY match, even if confidence is HIGH
"""


CONFIDENCE_SCORING_PROMPT = """You are the Confidence Scoring Agent.

========================================
CRITICAL INSTRUCTIONS
========================================
1. Return ONLY valid JSON - no markdown, no preamble, no explanation
2. ALL required fields MUST be present
3. Use ONLY IDs that exist in the provided input
4. NEVER fabricate or hallucinate IDs
5. Follow the exact output format specified below

## TASK
Assign confidence scores to validated matches.

## SCORING (weighted average)
- Amount (30%): Exact=100%, Near=90%, Diff>0=80%
- Currency (10%): Match=100%
- Partner (30%): Exact=100%, Substring=85%, Fuzzy=70%
- Date (20%): 0-7d=100%, 8-30d=90%, 31-60d=80%, 61-180d=70%
- Context (10%): Single=100%, 2docs=85%, 3+docs=75%

## LEVELS
- HIGH: 95%+ → AUTO_RECONCILE
- MEDIUM: 75-94% → REVIEW
- LOW: <75% → MANUAL

## OUTPUT FORMAT
`````json
{
  "scored_matches": [
    {
      "transaction_id": "1001",
      "confidence_level": "HIGH",
      "confidence_score": 98.5,
      "recommendation": "AUTO_RECONCILE"
    }
  ],
  "summary": {"HIGH": 5, "MEDIUM": 2, "LOW": 1}
}
````"""



CONFIDENCE_SCORING_PROMPT = """You are the Confidence Scoring Agent.

========================================
CRITICAL INSTRUCTIONS
========================================
1. Return ONLY valid JSON - no markdown, no preamble, no explanation
2. ALL required fields MUST be present
3. Use ONLY IDs that exist in the provided input
4. NEVER fabricate or hallucinate IDs
5. Follow the exact output format specified below

========================================
TASK
========================================
Assign confidence scores to validated matches, including:
- Single matches (1 transaction → 1 document)
- Combination matches (N transactions → 1 document OR 1 transaction → N documents)

========================================
SCORING RULES
========================================

FOR SINGLE MATCHES (has "transaction_id" and "document_id"):
Weighted average:
- Amount (30%): Exact=100%, Near=90%, Diff>0=80%
- Currency (10%): Match=100%
- Partner (30%): Exact=100%, Substring=85%, Fuzzy=70%
- Date (20%): 0-7d=100%, 8-30d=90%, 31-60d=80%, 61-180d=70%
- Context (10%): Single doc=100%

FOR COMBINATION MATCHES (has "transaction_ids" OR "document_ids"):
Base scoring:
- Amount (40%): Exact sum (diff ≤0.01)=100%, Near (diff ≤0.05)=90%, Otherwise=80%
- Currency (10%): All match=100%
- Date (30%): Average date proximity
  - All within 7 days=100%
  - All within 14 days=90%
  - All within 30 days=80%
  - All within 60 days=70%
- Combination size (20%): 
  - 2 items=100%
  - 3 items=90%
  - 4 items=85%
  - 5 items=80%

Special rules for combinations:
- Split payments (N→1): Start at MEDIUM (85%), upgrade to HIGH if perfect
- Batch payments (1→N): Start at MEDIUM (80%), upgrade to HIGH if perfect
- "Perfect" = exact amount sum (0.00 diff) + all dates within 14 days + same partner

========================================
CONFIDENCE LEVELS
========================================
- HIGH: 95%+ → AUTO_RECONCILE
- MEDIUM: 75-94% → REVIEW
- LOW: <75% → MANUAL

========================================
OUTPUT FORMAT
========================================

For SINGLE matches, return:
```json
{
  "transaction_id": "1001",
  "confidence_level": "HIGH",
  "confidence_score": 98.5,
  "recommendation": "AUTO_RECONCILE"
}
```

For COMBINATION matches (split payment N→1), return:
```json
{
  "transaction_ids": ["1001", "1002"],
  "document_id": "BILL_001",
  "confidence_level": "MEDIUM",
  "confidence_score": 85.0,
  "recommendation": "REVIEW"
}
```

For COMBINATION matches (batch payment 1→N), return:
```json
{
  "transaction_id": "1001",
  "document_ids": ["BILL_001", "BILL_002"],
  "confidence_level": "MEDIUM",
  "confidence_score": 80.0,
  "recommendation": "REVIEW"
}
```

Complete output structure:
```json
{
  "scored_matches": [
    {
      "transaction_id": "string",  // For single/batch matches
      "transaction_ids": ["string"],  // For split matches (mutually exclusive with transaction_id)
      "document_id": "string",  // For single/split matches
      "document_ids": ["string"],  // For batch matches (mutually exclusive with document_id)
      "confidence_level": "HIGH|MEDIUM|LOW",
      "confidence_score": 85.0,
      "recommendation": "AUTO_RECONCILE|REVIEW|MANUAL"
    }
  ],
  "summary": {"HIGH": 5, "MEDIUM": 2, "LOW": 1}
}
```

========================================
EXAMPLES
========================================

Example 1: Single Match
Input:
{
  "transaction_id": "1001",
  "document_id": "BILL_001",
  "match_type": "exact",
  "match_details": {
    "amount_match": "exact",
    "partner_match": "exact",
    "date_diff_days": 3
  }
}

Output:
{
  "transaction_id": "1001",
  "confidence_level": "HIGH",
  "confidence_score": 98.5,
  "recommendation": "AUTO_RECONCILE"
}

Example 2: Split Payment (N→1)
Input:
{
  "transaction_ids": ["2092", "2094"],
  "document_id": "BILL_001",
  "match_type": "combination_split",
  "match_details": {
    "transaction_amounts": ["20.00", "40.00"],
    "document_amount": "60.00",
    "difference": "0.00",
    "date_diff_days": 4
  }
}

Output:
{
  "transaction_ids": ["2092", "2094"],
  "document_id": "BILL_001",
  "confidence_level": "HIGH",
  "confidence_score": 95.0,
  "recommendation": "AUTO_RECONCILE"
}
Reasoning: Exact sum (0.00 diff) + dates within 7 days + only 2 items = HIGH confidence

Example 3: Batch Payment (1→N)
Input:
{
  "transaction_id": "1003",
  "document_ids": ["BILL_001", "BILL_002", "BILL_003"],
  "match_type": "combination_batch",
  "match_details": {
    "document_amounts": ["1200.00", "800.00", "1200.00"],
    "transaction_amount": "3200.00",
    "difference": "0.00"
  }
}

Output:
{
  "transaction_id": "1003",
  "document_ids": ["BILL_001", "BILL_002", "BILL_003"],
  "confidence_level": "MEDIUM",
  "confidence_score": 88.0,
  "recommendation": "REVIEW"
}
Reasoning: Exact sum but 3 documents = MEDIUM confidence

========================================
IMPORTANT NOTES
========================================
1. Always preserve the match structure (transaction_id vs transaction_ids)
2. For combinations, be slightly more conservative with confidence
3. Exact amount sums (0.00 difference) significantly boost confidence
4. Larger combinations (4-5 items) should rarely get HIGH confidence
5. Score ALL matches in the input, including combinations
"""


SUSPENSE_MATCH_PROMPT = """You are the Suspense Resolution Agent, a specialized component in a financial reconciliation system.

========================================
CRITICAL INSTRUCTIONS
========================================
1. Return ONLY valid JSON - no markdown, no preamble, no explanation
2. ALL required fields MUST be present
3. Use ONLY IDs that exist in the provided input
4. NEVER fabricate or hallucinate IDs
5. Follow the exact output format specified below

CORE OBJECTIVE:
Match suspense transactions to their corresponding documents (bills, invoices, credit notes, payroll, shares) using amount, date, and contextual analysis. Suspense transactions have placeholder partner names that MUST be ignored.

WHAT ARE SUSPENSE TRANSACTIONS:
Suspense transactions are bank entries where the partner/vendor was unknown at time of recording. They are temporarily posted to suspense accounts with meaningless partner names such as "Suspense - Transfer", "Unknown Vendor", "Unidentified Payment", or any variation containing "suspense", "unknown", "unidentified", or "pending". The partner name in a suspense transaction provides ZERO matching value and must be completely disregarded.

MATCHING METHODOLOGY:

1. AMOUNT MATCHING (PRIMARY CRITERION - MANDATORY)

Amount matching is the foundation of suspense resolution. A match is valid only if amounts align within specified tolerances.

Tolerance Levels:
- Exact: 0.00 difference (preferred)
- Bank Fee: up to 5.00 difference (common for wire transfers, international payments)
- Rounding: up to 0.05 difference (split payments, decimal rounding)
- Reject: anything beyond 5.00 difference for single matches

Rules:
- For single document matches: document amount must equal transaction amount within tolerance
- For combination matches: sum of document amounts must equal transaction amount within 0.05 rounding tolerance
- Always prefer exact matches (0.00 difference) over tolerance matches
- If multiple documents have exact amount match, use date proximity as tiebreaker

2. DATE PROXIMITY (SECONDARY CRITERION - IMPORTANT)

Date proximity indicates likelihood of correct match. Closer dates are strongly preferred.

Date Scoring Priority:
- 0-7 days: Excellent match probability, strong indicator
- 8-14 days: Very good match probability
- 15-30 days: Good match probability
- 31-60 days: Acceptable match probability
- 61-180 days: Possible match, requires strong amount match
- 181+ days: Low probability, use only if no alternative exists

Rules:
- When multiple candidates have identical amounts, always select the one with the closest date
- Do not reject matches solely on date if amount is exact and within 180 days
- Date difference of 2 days is significantly better than 20 days - prioritize accordingly
- Documents dated before or after the transaction are equally valid

3. CONTEXTUAL ANALYSIS (TERTIARY - CONFIRMATORY ONLY)

Context from descriptions and line items can confirm likely matches but should never be used to exclude potential matches.

Context Indicators:
- Utilities: "internet", "phone", "electricity", "water", "gas", "telecom" suggest utility bills
- Professional Services: "consulting", "engineering", "legal", "survey", "professional" suggest service bills
- Supplies: "office", "supplies", "stationery", "equipment", "materials" suggest supply bills
- Rent: "rent", "lease", "property", "premises" suggest rental bills
- Payroll: "salary", "wages", "payroll", "employee" suggest payroll transactions

Rules:
- Use context to increase confidence when it aligns with a match
- Never reject a perfect amount/date match because context doesn't align
- If transaction description is generic ("payment", "transfer"), rely purely on amount and date
- Context is helpful but not required for high-confidence matches

DECISION PROCESS:

For each suspense transaction, execute this process:

Step 1: Filter candidates by amount
- Find all documents where: abs(document_amount - transaction_amount) <= 5.00
- If no candidates found, attempt combination matching (see below)
- If candidates found, proceed to Step 2

Step 2: Evaluate date proximity
- For each candidate, calculate: abs(transaction_date - document_date) in days
- Rank candidates by date proximity (closest first)
- Select candidate with closest date

Step 3: Validate selected match
- Verify amount difference is within tolerance
- Verify currency matches (if currency data available)
- Verify date is within 180 days (preferably within 30 days)
- Check context for confirmation (optional)

Step 4: Assign confidence
- Calculate confidence score based on amount exactness and date proximity
- Assign confidence level: HIGH (85-100), MEDIUM (70-84), LOW (50-69)

COMBINATION MATCHING:

If no single document matches the transaction amount, attempt to find multiple documents whose amounts sum to the transaction amount.

When to Use Combination Matching:
- Transaction amount is larger (typically > 1000)
- Description suggests consolidated/batch payment
- Multiple small documents exist with amounts that could sum to transaction

Combination Requirements (ALL must be satisfied):
- Minimum 2 documents, maximum 5 documents
- All documents must be the same type (all bills, or all invoices, etc.)
- All documents must be the same currency
- Sum of document amounts must equal transaction amount within 0.05 rounding tolerance
- All documents must be dated within 90 days of the transaction date
- Preferably from the same partner (but not required)

Combination Process:
- Identify all documents dated within 90 days of transaction
- Find combinations of 2-5 documents whose amounts sum to transaction amount (±0.05)
- If multiple valid combinations exist, prefer:
  1. Combination with fewest documents
  2. Combination with closest average date proximity
  3. Combination with same partner (if applicable)

CONFIDENCE SCORING:

Confidence Level Criteria:

HIGH Confidence (85-100):
- Amount: Exact match (0.00 difference) OR within 1.00 with clear bank fee evidence
- Date: Within 14 days
- Context: Supporting evidence present OR no conflicting signals
- Use: Suitable for automatic reconciliation

MEDIUM Confidence (70-84):
- Amount: Within tolerance (0.01 to 5.00 difference)
- Date: 15-60 days
- Context: Some supporting evidence or neutral
- Use: Requires human review before reconciliation

LOW Confidence (50-69):
- Amount: Near upper tolerance limit (4.00-5.00 difference)
- Date: 61-180 days
- Context: Weak evidence or no contextual support
- Use: Flag for manual verification

Confidence Score Calculation:
confidence_score = (amount_component × 0.40) + (date_component × 0.35) + (context_component × 0.25)

Where:
- amount_component: 100 if exact, 90 if ≤1.00, 80 if ≤3.00, 70 if ≤5.00
- date_component: 100 if ≤7 days, 90 if ≤14 days, 80 if ≤30 days, 70 if ≤60 days, 50 if ≤180 days
- context_component: 100 if strong supporting evidence, 75 if neutral, 50 if conflicting or absent

CRITICAL RULES:

Mandatory Actions:
1. Ignore all partner names in suspense transactions completely
2. Prioritize exact amount matches above all other factors
3. Prefer documents with closer dates when amounts are equal
4. Attempt combination matching when no single match exists
5. Provide detailed reasoning for every match in the match_details field
6. Only use document IDs that appear in the provided candidates list
7. Only use transaction IDs that appear in the provided input list

Prohibited Actions:
1. Do not require partner name matching for suspense transactions
2. Do not reject matches solely due to unclear descriptions
3. Do not create matches with amount differences exceeding 5.00 (single match) or 0.05 (combination)
4. Do not use documents outside the provided candidates list
5. Do not fabricate or hallucinate document IDs or transaction IDs
6. Do not match documents that have already been used in previous matches
7. Do not be overly conservative - suspense accounts exist to be resolved

Matching Prioritization:
- First priority: Exact amount match with date within 7 days
- Second priority: Exact amount match with date within 30 days
- Third priority: Amount within bank fee tolerance (≤5.00) with date within 14 days
- Fourth priority: Exact amount match with date within 180 days
- Fifth priority: Combination match with sum exact and dates within 30 days
- Last priority: Amount within tolerance with date within 60 days

OUTPUT FORMAT:

Return a JSON object with this exact structure:

{
  "matched": [
    {
      "transaction_id": "string",
      "document_type": "string",
      "document_id": "string",
      "match_type": "suspense_single",
      "match_details": {
        "amount_match": "exact|with_tolerance",
        "amount_difference": "decimal_string",
        "date_diff_days": integer,
        "partner_ignored": true,
        "reasoning": "detailed_explanation_minimum_50_chars",
        "tolerance_type": "exact|bank_fee|rounding"
      },
      "confidence": "HIGH|MEDIUM|LOW",
      "confidence_score": number
    }
  ],
  "unmatched_transaction_ids": ["string"]
}

For combination matches, use this structure:

{
  "transaction_id": "string",
  "document_type": "string",
  "document_ids": ["string", "string"],
  "match_type": "suspense_combination",
  "match_details": {
    "document_amounts": ["decimal_string"],
    "sum": "decimal_string",
    "transaction_amount": "decimal_string",
    "difference": "decimal_string",
    "date_diff_days": integer,
    "reasoning": "detailed_explanation",
    "combination_type": "batch_payment",
    "documents_count": integer
  },
  "confidence": "MEDIUM|LOW",
  "confidence_score": number
}

Field Requirements:
- transaction_id: Must exactly match an input transaction ID
- document_id: Required for single matches (use document_ids for combinations)
- document_ids: Required for combination matches (array of 2-5 document IDs)
- match_type: Must be "suspense_single" or "suspense_combination"
- reasoning: Must be specific and explain why this match was selected over alternatives
- confidence_score: Must align with confidence level thresholds
- unmatched_transaction_ids: List all suspense transaction IDs that could not be matched

REASONING REQUIREMENTS:

Your reasoning field must address:
1. Why the amount match is valid (exact or within which tolerance)
2. Why the date proximity supports this match
3. If multiple candidates existed with same amount, why this specific document was chosen
4. Any contextual evidence that confirms the match
5. For combinations: why these specific documents were selected as a set

Minimal example of good reasoning:
"Amount exact match (1200.00 = 1200.00, difference 0.00). Date proximity excellent (2 days). Selected BILL_2025_006 over BILL_2025_008 (also 1200.00) due to closer date (2 days vs 41 days). Context supports match: utilities bill aligns with monthly payment pattern."

EXECUTION INSTRUCTION:

Process each suspense transaction in the input systematically. For each transaction:
1. Extract the amount and date
2. Search candidates for exact amount matches
3. If multiple exact matches exist, select by closest date
4. If no exact match, search within tolerance (≤5.00)
5. If no single match, attempt combination matching
6. If match found, calculate confidence and create match record with detailed reasoning
7. If no valid match found, add transaction_id to unmatched list

Ensure every match you create has:
- Valid transaction_id from input
- Valid document_id(s) from candidates
- Accurate amount_difference calculation
- Accurate date_diff_days calculation
- Meaningful reasoning that explains the match selection
- Appropriate confidence level and score

Return only valid matches with strong justification. It is better to leave a transaction unmatched than to create a questionable match."""


# =============================================================================
# AGENT EXECUTOR (Enhanced with batching)
# =============================================================================

class AgentExecutor:
    """Executes LLM agents with retry logic and batching support."""
    
    def __init__(self, config: MatchingConfig = DEFAULT_CONFIG):
        self.client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        self.config = config
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.api_calls = 0
    
    def execute(
        self,
        agent_name: str,
        system_prompt: str,
        user_message: str
    ) -> Dict:
        """Execute an agent with retry and temperature jitter."""
        for attempt in range(self.config.max_retries):
            try:
                temperature = self.config.base_temperature + (attempt * self.config.retry_temperature_increment)
                
                logger.debug(f"[{agent_name}] Attempt {attempt + 1}/{self.config.max_retries}")
                
                response = self.client.messages.create(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}]
                )
                
                self.total_input_tokens += response.usage.input_tokens
                self.total_output_tokens += response.usage.output_tokens
                self.api_calls += 1
                
                # Extract text
                result_text = "".join(
                    block.text for block in response.content if block.type == "text"
                )
                
                # Extract JSON
                if result_json := self._extract_json(result_text):
                    logger.info(f"[{agent_name}] ✓ Success")
                    return {"success": True, "result": result_json}
                
                logger.warning(f"[{agent_name}] JSON extraction failed, retrying...")
                
            except Exception as e:
                logger.error(f"[{agent_name}] Error: {e}")
                if attempt == self.config.max_retries - 1:
                    return {"success": False, "error": str(e)}
        
        return {"success": False, "error": "Max retries exceeded"}
    
    def _extract_json(self, text: str) -> Optional[Dict]:
        """Robust JSON extraction with multiple strategies."""
        # Strategy 1: ```json blocks
        if match := re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL):
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Strategy 2: ``` blocks
        if match := re.search(r'```\s*(.*?)\s*```', text, re.DOTALL):
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Strategy 3: Direct JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Strategy 4: Find JSON objects
        for match in re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL):
            try:
                parsed = json.loads(match.group())
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
        
        return None
    
    def get_stats(self) -> Dict:
        """Get execution statistics."""
        return {
            "api_calls": self.api_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens
        }


# =============================================================================
# BATCHED AGENT FUNCTIONS (FIX: Context explosion prevention)
# =============================================================================

# In run_data_enrichment function, after line ~1725
def run_data_enrichment(executor: AgentExecutor, input_data: Dict) -> Dict:
    user_message = f"""Enrich this data:

{safe_json_dumps(input_data)}

Return enriched data with all required fields."""

    result = executor.execute("DataEnrichment", DATA_ENRICHMENT_PROMPT, user_message)
    
    # ADD PYTHON-SIDE SUSPENSE DETECTION FALLBACK
    if result["success"]:
        enriched = result["result"]
        enriched_txns = enriched.get("enriched_transactions", [])
        
        # Fallback: Check each transaction for suspense indicators
        for txn in enriched_txns:
            # Check if LLM missed setting is_suspense
            should_be_suspense = False
            
            # Check account_name
            account = str(txn.get("account_name", "")).lower()
            if "suspense" in account:
                should_be_suspense = True
            
            # Check partner_name
            partner = str(txn.get("partner_name", "")).lower()
            if any(word in partner for word in ["suspense", "unknown", "unidentified", "pending"]):
                should_be_suspense = True
            
            # Check category
            category = str(txn.get("category", "")).lower()
            if category == "suspense":
                should_be_suspense = True
            
            # Check original line_items from input
            original_txn = next(
                (t for t in input_data.get("bank_transactions", []) 
                 if t.get("odoo_id") == txn.get("odoo_id")),
                None
            )
            if original_txn:
                for line_item in original_txn.get("line_items", []):
                    if "suspense" in str(line_item.get("account", "")).lower():
                        should_be_suspense = True
                        break
            
            # Apply correction if needed
            if should_be_suspense and not txn.get("is_suspense"):
                logger.warning(f"CORRECTING: Transaction {txn.get('transaction_id')} should be suspense but was not marked")
                txn["is_suspense"] = True
                if txn.get("category") != "suspense":
                    txn["category"] = "suspense"
        
        # LOG suspense transactions
        logger.info("=" * 70)
        logger.info("DATA ENRICHMENT - SUSPENSE CHECK:")
        suspense_count = 0
        for txn in enriched_txns:
            if txn.get("is_suspense") is True:
                suspense_count += 1
                logger.info(f"  ✓ TXN {txn.get('transaction_id')} MARKED AS SUSPENSE:")
                logger.info(f"      category: {txn.get('category')}")
                logger.info(f"      is_suspense: {txn.get('is_suspense')} (type: {type(txn.get('is_suspense'))})")
                logger.info(f"      account_name: {txn.get('account_name')}")
                logger.info(f"      partner: {txn.get('partner_name')}")
        logger.info(f"  TOTAL SUSPENSE: {suspense_count}")
        logger.info("=" * 70)
    
    return result


def run_duplicate_detection(executor: AgentExecutor, transactions: List[Dict]) -> Dict:
    """Run Duplicate Detection Agent."""
    minified = [minify_transaction(t) for t in transactions]
    
    user_message = f"""Find duplicates in these {len(minified)} transactions:

{safe_json_dumps(minified)}"""

    return executor.execute("DuplicateDetection", DUPLICATE_DETECTION_PROMPT, user_message)


def run_exact_match_batched(
    executor: AgentExecutor,
    transactions: List[Dict],
    documents: Dict,
    config: MatchingConfig = DEFAULT_CONFIG
) -> Dict:
    """
    Run Exact Match Agent with BATCHED processing.
    Processes transactions in small batches to prevent context explosion.
    """
    all_matched = []
    all_unmatched_ids = []
    batch_size = config.batch_size
    
    logger.info(f"Processing {len(transactions)} transactions in batches of {batch_size}")
    
    for i in range(0, len(transactions), batch_size):
        batch = transactions[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(transactions) + batch_size - 1) // batch_size
        
        logger.info(f"  Batch {batch_num}/{total_batches}: {len(batch)} transactions")
        
        # Prepare batch data
        batch_data = []
        for txn in batch:
            filtered = filter_candidate_documents(txn, documents, config)
            minified_docs = minify_documents_dict(filtered, config.max_candidates_per_txn)
            
            batch_data.append({
                "transaction": minify_transaction(txn),
                "candidates": minified_docs
            })
        
        user_message = f"""Match these {len(batch)} transactions:

{safe_json_dumps(batch_data)}

Return matches and unmatched IDs."""

        result = executor.execute("ExactMatch", EXACT_MATCH_PROMPT, user_message)
        
        if result["success"]:
            all_matched.extend(result["result"].get("matched", []))
            all_unmatched_ids.extend(result["result"].get("unmatched_transaction_ids", []))
        else:
            # On failure, mark all batch transactions as unmatched
            all_unmatched_ids.extend([str(t.get("transaction_id")) for t in batch])
    
    return {
        "success": True,
        "result": {
            "matched": all_matched,
            "unmatched_transaction_ids": all_unmatched_ids
        }
    }


def run_context_analysis(executor: AgentExecutor, transactions: List[Dict]) -> Dict:
    """Run Context Analysis Agent."""
    minified = [minify_transaction(t) for t in transactions]
    
    user_message = f"""Analyze {len(transactions)} transactions:

{safe_json_dumps(minified)}"""

    return executor.execute("ContextAnalysis", CONTEXT_ANALYSIS_PROMPT, user_message)


def run_partner_resolution_batched(
    executor: AgentExecutor,
    transactions: List[Dict],
    documents: Dict,
    context_analysis: Dict,
    config: MatchingConfig = DEFAULT_CONFIG
) -> Dict:
    """Run Partner Resolution with batching."""
    # Build context lookup
    ctx_lookup = {
        c.get("transaction_id"): c.get("date_range_days", 60)
        for c in context_analysis.get("context_analysis", [])
    }
    
    all_matched = []
    all_unmatched_ids = []
    batch_size = config.batch_size
    
    for i in range(0, len(transactions), batch_size):
        batch = transactions[i:i + batch_size]
        
        batch_data = []
        for txn in batch:
            txn_id = txn.get("transaction_id")
            date_range = ctx_lookup.get(txn_id, config.fuzzy_match_date_range)
            
            filtered = filter_candidate_documents(txn, documents, config, date_range, for_combination = True)
            minified_docs = minify_documents_dict(filtered, config.max_candidates_per_txn)
            
            batch_data.append({
                "transaction": minify_transaction(txn),
                "date_range_days": date_range,
                "candidates": minified_docs
            })
        
        user_message = f"""Match {len(batch)} transactions with fuzzy partner matching:

{safe_json_dumps(batch_data)}"""

        result = executor.execute("PartnerResolution", PARTNER_RESOLUTION_PROMPT, user_message)
        
        if result["success"]:
            all_matched.extend(result["result"].get("matched", []))
            all_unmatched_ids.extend(result["result"].get("unmatched_transaction_ids", []))
        else:
            all_unmatched_ids.extend([str(t.get("transaction_id")) for t in batch])
    
    return {
        "success": True,
        "result": {
            "matched": all_matched,
            "unmatched_transaction_ids": all_unmatched_ids
        }
    }


def run_combination_match_batched(
    executor: AgentExecutor,
    transactions: List[Dict],
    documents: Dict,
    context_analysis: Dict,
    config: MatchingConfig = DEFAULT_CONFIG
) -> Dict:
    """Run Combination Match with batching."""
    ctx_lookup = {
        c.get("transaction_id"): c.get("date_range_days", 60)
        for c in context_analysis.get("context_analysis", [])
    }
    
    all_matched = []
    all_unmatched_ids = []
    batch_size = config.batch_size
    
    for i in range(0, len(transactions), batch_size):
        batch = transactions[i:i + batch_size]
        
        batch_data = []
        for txn in batch:
            txn_id = txn.get("transaction_id")
            date_range = ctx_lookup.get(txn_id, config.fuzzy_match_date_range)
            
            filtered = filter_candidate_documents(txn, documents, config, date_range, for_combination = True)
            minified_docs = minify_documents_dict(filtered, config.max_candidates_per_txn * 2)
            
            batch_data.append({
                "transaction": minify_transaction(txn),
                "candidates": minified_docs
            })
        
        # Also include all unmatched for split detection
        all_txns_mini = [minify_transaction(t) for t in transactions]
        
        user_message = f"""Find combination matches for {len(batch)} transactions:

BATCH:
{safe_json_dumps(batch_data)}

ALL UNMATCHED (for split detection):
{safe_json_dumps(all_txns_mini)}"""

        result = executor.execute("CombinationMatch", COMBINATION_MATCH_PROMPT, user_message)
        
        if result["success"]:
            all_matched.extend(result["result"].get("matched", []))
            all_unmatched_ids.extend(result["result"].get("unmatched_transaction_ids", []))
        else:
            all_unmatched_ids.extend([str(t.get("transaction_id")) for t in batch])
    
    return {
        "success": True,
        "result": {
            "matched": all_matched,
            "unmatched_transaction_ids": all_unmatched_ids
        }
    }
def filter_suspense_candidates(
    transaction: Dict,
    all_documents: Dict,
    config: MatchingConfig = DEFAULT_CONFIG,
    date_range_days: Optional[int] = None  # ADD THIS PARAMETER
) -> Dict:
    """
    Special filtering for suspense transactions with permissive amount matching.
    """
    txn_amount = to_decimal(transaction.get('amount', 0))
    if txn_amount == 0:
        return all_documents
    
    abs_amount = abs(txn_amount)
    
    # For suspense: allow documents from 0 to transaction_amount + bank_fee_tolerance
    min_amount = Decimal("0")
    max_amount = abs_amount + config.bank_fee_tolerance  # e.g., 1200 + 5 = 1205
    
    # Use provided date range or default to max_date_range (1 year)
    date_range = date_range_days if date_range_days is not None else config.max_date_range
    
    # Wide date range for suspense
    txn_date_str = transaction.get('date')
    if txn_date_str:
        try:
            txn_datetime = datetime.strptime(txn_date_str, "%Y-%m-%d")
            min_date = txn_datetime - timedelta(days=date_range)
            max_date = txn_datetime + timedelta(days=date_range)
        except ValueError:
            min_date = max_date = None
    else:
        min_date = max_date = None
    
    filtered = {}
    for doc_type, docs_list in all_documents.items():
        filtered[doc_type] = []
        
        for doc in docs_list[:config.max_documents_per_type]:
            # Date filter
            if min_date and max_date:
                if doc_date_str := doc.get('date'):
                    try:
                        doc_dt = datetime.strptime(doc_date_str, "%Y-%m-%d")
                        if doc_dt < min_date or doc_dt > max_date:
                            continue
                    except ValueError:
                        pass
            
            # Amount filter - permissive for suspense
            doc_amount = abs(to_decimal(doc.get('amount', 0)))
            if not (min_amount <= doc_amount <= max_amount):
                continue
            
            filtered[doc_type].append(doc)
            
            if len(filtered[doc_type]) >= config.max_candidates_per_txn * 2:  # More candidates for suspense
                break
    
    return filtered

def run_suspense_resolution(
    executor: AgentExecutor,
    suspense_transactions: List[Dict],
    documents: Dict,
    config: MatchingConfig = DEFAULT_CONFIG
) -> Dict:
    """
    Run Suspense Resolution Agent with partner-agnostic matching.
    Uses wide date ranges and focuses on amount + date + context.
    """
    if not suspense_transactions:
        return {"success": True, "result": {"matched": [], "unmatched_transaction_ids": []}}
    
    all_matched = []
    all_unmatched_ids = []
    batch_size = config.batch_size
    
    logger.info(f"Processing {len(suspense_transactions)} suspense transactions with partner-agnostic matching")
    
    # LOG: Suspense transaction details
    logger.info("=" * 70)
    logger.info("SUSPENSE TRANSACTIONS TO MATCH:")
    for txn in suspense_transactions:
        logger.info(f"  TXN {txn.get('transaction_id')}: "
                   f"amount={txn.get('amount')}, "
                   f"date={txn.get('date')}, "
                   f"partner={txn.get('partner_name', 'N/A')}")
    
    # LOG: Available documents before filtering
    logger.info("=" * 70)
    logger.info("AVAILABLE DOCUMENTS (before filtering):")
    total_docs = 0
    for doc_type, docs in documents.items():
        logger.info(f"  {doc_type}: {len(docs)} documents")
        total_docs += len(docs)
        # Show first 3 of each type
        for doc in docs[:3]:
            doc_id_field = f"{doc_type.rstrip('s')}_id"
            doc_id = doc.get(doc_id_field) or doc.get("id")
            logger.info(f"    - {doc_id}: amount={doc.get('amount')}, date={doc.get('date')}, partner={doc.get('partner_name', 'N/A')}")
        if len(docs) > 3:
            logger.info(f"    ... and {len(docs) - 3} more")
    logger.info(f"  TOTAL: {total_docs} documents available")
    logger.info("=" * 70)
    
    for i in range(0, len(suspense_transactions), batch_size):
        batch = suspense_transactions[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(suspense_transactions) + batch_size - 1) // batch_size
        
        logger.info(f"\nProcessing batch {batch_num}/{total_batches}: {len(batch)} suspense transactions")
        
        batch_data = []
        for txn in batch:
            txn_id = txn.get('transaction_id')
            txn_amount = txn.get('amount')
            txn_date = txn.get('date')
            
            # Use WIDE date range for suspense (max_date_range = 365 days)
            filtered = filter_suspense_candidates(
                txn, 
                documents, 
                config, 
                date_range_days=config.max_date_range
            )
            
            # LOG: What candidates survived filtering for THIS transaction
            total_candidates = sum(len(docs) for docs in filtered.values())
            logger.info(f"\n  Transaction {txn_id} (amount={txn_amount}, date={txn_date}):")
            logger.info(f"    Candidates after filtering: {total_candidates} documents")
            
            for doc_type, docs in filtered.items():
                if docs:
                    logger.info(f"      {doc_type}: {len(docs)} candidates")
                    for doc in docs[:5]:  # Show first 5
                        doc_id_field = f"{doc_type.rstrip('s')}_id"
                        doc_id = doc.get(doc_id_field) or doc.get("id")
                        doc_amount = doc.get('amount')
                        doc_date = doc.get('date')
                        amount_diff = abs(to_decimal(txn_amount) - to_decimal(doc_amount))
                        
                        # Calculate date difference
                        try:
                            date_diff = calculate_date_difference(txn_date, doc_date)
                        except:
                            date_diff = "N/A"
                        
                        logger.info(f"        • {doc_id}: amount={doc_amount} (diff={format_decimal(amount_diff)}), "
                                   f"date={doc_date} (diff={date_diff} days)")
                    
                    if len(docs) > 5:
                        logger.info(f"        ... and {len(docs) - 5} more")
            
            if total_candidates == 0:
                logger.warning(f"    ⚠️  NO CANDIDATES found for transaction {txn_id}! Check filtering logic.")
            
            minified_docs = minify_documents_dict(filtered, config.max_candidates_per_txn * 2)
            
            batch_data.append({
                "transaction": minify_transaction(txn),
                "candidates": minified_docs,
                "note": "SUSPENSE - ignore partner names"
            })
        
        logger.info(f"\n  Sending batch {batch_num} to LLM for matching...")
        
        user_message = f"""Match these {len(batch)} SUSPENSE transactions:

{safe_json_dumps(batch_data)}

CRITICAL: Partner names are placeholders - match ONLY on amount, date, and context clues."""

        result = executor.execute("SuspenseResolution", SUSPENSE_MATCH_PROMPT, user_message)
        
        if result["success"]:
            matched_in_batch = result["result"].get("matched", [])
            unmatched_in_batch = result["result"].get("unmatched_transaction_ids", [])
            
            logger.info(f"  ✓ Batch {batch_num} complete: {len(matched_in_batch)} matched, {len(unmatched_in_batch)} unmatched")
            
            # LOG: What was matched in this batch
            if matched_in_batch:
                for match in matched_in_batch:
                    if match.get("document_ids"):
                        logger.info(f"    Matched TXN {match.get('transaction_id')} → "
                                   f"COMBINATION {match.get('document_ids')} "
                                   f"(confidence: {match.get('confidence', 'N/A')})")
                    else:
                        logger.info(f"    Matched TXN {match.get('transaction_id')} → "
                                   f"{match.get('document_id')} "
                                   f"(confidence: {match.get('confidence', 'N/A')})")
            
            all_matched.extend(matched_in_batch)
            all_unmatched_ids.extend(unmatched_in_batch)
        else:
            logger.error(f"  ✗ Batch {batch_num} FAILED: {result.get('error', 'Unknown error')}")
            all_unmatched_ids.extend([str(t.get("transaction_id")) for t in batch])
    
    logger.info("=" * 70)
    logger.info(f"SUSPENSE RESOLUTION COMPLETE: {len(all_matched)} matched, {len(all_unmatched_ids)} unmatched")
    logger.info("=" * 70)
    
    return {
        "success": True,
        "result": {
            "matched": all_matched,
            "unmatched_transaction_ids": all_unmatched_ids
        }
    }


def run_validation(executor: AgentExecutor, matches: List[Dict]) -> Dict:
    """Run Validation Agent."""
    user_message = f"""Validate {len(matches)} matches:

{safe_json_dumps(matches)}"""

    return executor.execute("Validation", VALIDATION_PROMPT, user_message)


def run_confidence_scoring(executor: AgentExecutor, matches: List[Dict]) -> Dict:
    """Run Confidence Scoring Agent."""
    user_message = f"""Score {len(matches)} matches:

{safe_json_dumps(matches)}"""

    return executor.execute("ConfidenceScoring", CONFIDENCE_SCORING_PROMPT, user_message)


# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================

def orchestrate_matching(
    input_data: Dict,
    config: MatchingConfig = DEFAULT_CONFIG
) -> Dict:
    """
    Main orchestrator - coordinates all agents with batched processing.
    """
    logger.info("=" * 70)
    logger.info("TRANSACTION MATCHING WORKFLOW V7 - START")
    logger.info("=" * 70)
    
    executor = AgentExecutor(config)
    state = MatchingState()
    
    results = {
        "success": False,
        "workflow_completed": False,
        "matched_transactions": [],
        "unmatched_transactions": [],
        "duplicate_transactions": [],
        "errors": [],
        "summary": {
            "total_transactions": 0,
            "duplicates_found": 0,
            "available_for_matching": 0,
            "matched": 0,
            "unmatched": 0,
            "rejected_hallucinated": 0,
            "rejected_amount_mismatch": 0,
            "match_rate": "0%",
            "confidence_breakdown": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
            "match_type_breakdown": {
                "exact": 0, "near": 0, "fuzzy": 0,
                "combination_batch": 0, "combination_split": 0,
                "suspense_single": 0, "suspense_combination": 0
            },
            "workflow_steps_completed": [],
            "api_stats": {}
        }
    }
    
    try:
        # Handle input format
        company_data = normalize_input_format(input_data)
        
        total_txns = len(company_data.get("bank_transactions", []))
        results["summary"]["total_transactions"] = total_txns
        
        logger.info(f"Processing {total_txns} transactions (batch_size={config.batch_size})")
        
        # =====================================================================
        # STEP 1: Data Enrichment
        # =====================================================================
        logger.info("\n[STEP 1/9] Data Enrichment")
        enrich_result = run_data_enrichment(executor, company_data)
        
        if not enrich_result["success"]:
            results["errors"].append({"step": 1, "error": enrich_result.get("error")})
            return results
        
        enriched = enrich_result["result"]
        enriched_txns = enriched.get("enriched_transactions", [])
        
        # Ensure transaction_id exists
        for i, txn in enumerate(enriched_txns):
            if not txn.get("transaction_id"):
                txn["transaction_id"] = str(txn.get("odoo_id", i))
        
        all_docs = {
            "bills": enriched.get("enriched_bills", []),
            "invoices": enriched.get("enriched_invoices", []),
            "credit_notes": enriched.get("enriched_credit_notes", []),
            "payroll": enriched.get("enriched_payroll", []),
            "shares": enriched.get("enriched_shares", [])
        }
        
        state.completed_steps.append(1)
        results["summary"]["workflow_steps_completed"].append(1)
        logger.info(f"✓ Enriched {len(enriched_txns)} transactions")
        
        # =====================================================================
        # STEP 2: Duplicate Detection
        # =====================================================================
        logger.info("\n[STEP 2/9] Duplicate Detection")
        dup_result = run_duplicate_detection(executor, enriched_txns)
        
        if dup_result["success"]:
            dup_data = dup_result["result"]
            dup_pairs = dup_data.get("duplicate_pairs", [])
            
            # Mark duplicates
            for pair in dup_pairs:
                dup_id = str(pair.get("mark_for_deletion"))
                state.mark_transaction_duplicate(dup_id)
                
                txn_data = next((t for t in enriched_txns if str(t.get("transaction_id")) == dup_id), {})
                results["duplicate_transactions"].append({
                    "transaction_id": dup_id,
                    "duplicate_of": pair.get("keep"),
                    "reason": pair.get("reason"),
                    "action": "DELETE",
                    "odoo_id": pair.get("odoo_id_to_delete")
                })
            
            # Filter to non-duplicates
            non_dup_ids = set(str(t.get("transaction_id")) for t in enriched_txns) - \
                         set(str(p.get("mark_for_deletion")) for p in dup_pairs)
            non_dup_txns = [t for t in enriched_txns if str(t.get("transaction_id")) in non_dup_ids]
            
            results["summary"]["duplicates_found"] = len(dup_pairs)
        else:
            non_dup_txns = enriched_txns
        
        results["summary"]["available_for_matching"] = len(non_dup_txns)
        state.completed_steps.append(2)
        results["summary"]["workflow_steps_completed"].append(2)
        logger.info(f"✓ Found {results['summary']['duplicates_found']} duplicates, {len(non_dup_txns)} available")
        
        # =====================================================================
        # STEP 3: Exact Match (BATCHED)
        # =====================================================================
        logger.info("\n[STEP 3/9] Exact Match (Batched)")
        exact_result = run_exact_match_batched(executor, non_dup_txns, all_docs, config)
        
        if exact_result["success"]:
            raw_exact = exact_result["result"].get("matched", [])
            
            # Python-side validation (REJECTS hallucinated IDs)
            exact_matches, rejected_exact = validate_exact_matches(
                raw_exact, non_dup_txns, all_docs, config
            )
            
            # Track rejections
            hallucinated = len([r for r in rejected_exact if "HALLUCINATED" in (r.get("rejection_reason") or "")])
            results["summary"]["rejected_hallucinated"] += hallucinated
            
            # Update state
            doc_ids, txn_ids = extract_matched_ids(exact_matches)
            for doc_type, ids in doc_ids.items():
                for did in ids:
                    state.mark_document_matched(doc_type, did)
            for tid in txn_ids:
                state.mark_transaction_matched(tid)
            
            # Get unmatched
            unmatched_ids = set(exact_result["result"].get("unmatched_transaction_ids", []))
            matched_ids = {str(m.get("transaction_id")) for m in exact_matches}
            all_ids = {str(t.get("transaction_id")) for t in non_dup_txns}
            unmatched_ids = (all_ids - matched_ids) | unmatched_ids
            
            unmatched_after_exact = [t for t in non_dup_txns if str(t.get("transaction_id")) in unmatched_ids]
            
            results["summary"]["match_type_breakdown"]["exact"] = len(exact_matches)
        else:
            exact_matches = []
            unmatched_after_exact = non_dup_txns
        
        all_matches = exact_matches.copy()
        state.completed_steps.append(3)
        results["summary"]["workflow_steps_completed"].append(3)
        logger.info(f"✓ Exact: {len(exact_matches)} matched, {len(unmatched_after_exact)} unmatched")
        
        # =====================================================================
        # STEPS 4-6: Fuzzy Matching (if needed)
        # =====================================================================
        match_rate = len(exact_matches) / len(non_dup_txns) if non_dup_txns else 0
        
        if match_rate <= 0.8 and unmatched_after_exact:
            logger.info(f"\n[Match rate {match_rate*100:.1f}% < 80%, continuing fuzzy matching]")
            
            # STEP 4: Context Analysis
            logger.info("\n[STEP 4/9] Context Analysis")
            ctx_result = run_context_analysis(executor, unmatched_after_exact)
            context_analysis = ctx_result["result"] if ctx_result["success"] else {"context_analysis": []}
            state.completed_steps.append(4)
            results["summary"]["workflow_steps_completed"].append(4)
            
            # STEP 5: Partner Resolution (BATCHED)
            logger.info("\n[STEP 5/9] Partner Resolution (Batched)")
            avail_docs = {dt: [d for d in docs if not state.is_document_matched(dt, str(d.get(f"{dt.rstrip('s')}_id") or d.get("id")))]
                        for dt, docs in all_docs.items()}
            
            partner_result = run_partner_resolution_batched(
                executor, unmatched_after_exact, avail_docs, context_analysis, config
            )
            
            if partner_result["success"]:
                raw_fuzzy = partner_result["result"].get("matched", [])
                fuzzy_matches, rejected_fuzzy = validate_exact_matches(
                    raw_fuzzy, unmatched_after_exact, all_docs, config
                )
                
                # Update state
                doc_ids, txn_ids = extract_matched_ids(fuzzy_matches)
                for doc_type, ids in doc_ids.items():
                    for did in ids:
                        state.mark_document_matched(doc_type, did)
                for tid in txn_ids:
                    state.mark_transaction_matched(tid)
                
                all_matches.extend(fuzzy_matches)
                
                # Get unmatched
                unmatched_ids = set(partner_result["result"].get("unmatched_transaction_ids", []))
                matched_ids = {str(m.get("transaction_id")) for m in fuzzy_matches}
                remaining_ids = {str(t.get("transaction_id")) for t in unmatched_after_exact}
                unmatched_ids = (remaining_ids - matched_ids) | unmatched_ids
                
                unmatched_after_partner = [t for t in unmatched_after_exact if str(t.get("transaction_id")) in unmatched_ids]
                
                results["summary"]["match_type_breakdown"]["fuzzy"] = len(fuzzy_matches)
            else:
                fuzzy_matches = []
                unmatched_after_partner = unmatched_after_exact
            
            state.completed_steps.append(5)
            results["summary"]["workflow_steps_completed"].append(5)
            logger.info(f"✓ Fuzzy: {len(fuzzy_matches)} matched")
            
            # IMPORTANT: Ensure unmatched_after_partner is always defined
            if 'unmatched_after_partner' not in locals():
                unmatched_after_partner = unmatched_after_exact
            
            # STEP 6: Combination Match (BATCHED)
# STEP 6: Combination Match (BATCHED)
            if unmatched_after_partner:
                logger.info("\n[STEP 6/9] Combination Match (Batched)")
                avail_docs = {dt: [d for d in docs if not state.is_document_matched(dt, str(d.get(f"{dt.rstrip('s')}_id") or d.get("id")))]
                            for dt, docs in all_docs.items()}
                
                combo_result = run_combination_match_batched(
                    executor, unmatched_after_partner, avail_docs, context_analysis, config
                )
                
                # Initialize counters (in case combo_matches ends up empty)
                batch_ct = 0
                split_ct = 0
                
                if combo_result["success"]:
                    raw_combo = combo_result["result"].get("matched", [])
                    combo_matches, rejected_combo = validate_combination_matches(
                        raw_combo, unmatched_after_partner, all_docs, config
                    )
                    
                    # Update state
                    doc_ids, txn_ids = extract_matched_ids(combo_matches)
                    for doc_type, ids in doc_ids.items():
                        for did in ids:
                            state.mark_document_matched(doc_type, did)
                    for tid in txn_ids:
                        state.mark_transaction_matched(tid)
                    
                    all_matches.extend(combo_matches)
                    
                    # Count types
                    batch_ct = sum(1 for m in combo_matches if "document_ids" in m)
                    split_ct = sum(1 for m in combo_matches if "transaction_ids" in m)
                    results["summary"]["match_type_breakdown"]["combination_batch"] = batch_ct
                    results["summary"]["match_type_breakdown"]["combination_split"] = split_ct
                    
                    # Final unmatched
                    matched_ids = txn_ids
                    final_unmatched = [t for t in unmatched_after_partner 
                                      if str(t.get("transaction_id")) not in matched_ids]
                else:
                    # Combination matching failed - keep all as unmatched
                    final_unmatched = unmatched_after_partner
                
                state.completed_steps.append(6)
                results["summary"]["workflow_steps_completed"].append(6)
                logger.info(f"✓ Combination: {batch_ct} batch, {split_ct} split")
            else:
                # No transactions left for combination matching
                final_unmatched = []
                state.completed_steps.append(6)
                results["summary"]["workflow_steps_completed"].append(6)
                logger.info(f"✓ Combination: 0 batch, 0 split (all matched in previous steps)")
        else:
            # Match rate >= 80%, skip fuzzy matching entirely
            final_unmatched = unmatched_after_exact
        
        # =====================================================================
        # STEP 7: Suspense Resolution (ENHANCED)
        # =====================================================================
        logger.info("\n[STEP 7/9] Suspense Resolution")

        # Ensure final_unmatched is defined
        if 'final_unmatched' not in locals():
            final_unmatched = unmatched_after_exact if 'unmatched_after_exact' in locals() else non_dup_txns
            logger.debug("Using fallback for final_unmatched")

        # Find UNMATCHED suspense transactions
        suspense_txns = []
        for t in final_unmatched:
            txn_id = str(t.get("transaction_id"))
            
            # Check if marked as suspense
            is_suspense = t.get("is_suspense")
            
            # Also check category as fallback
            category = str(t.get("category", "")).lower()
            
            # Include if either flag is set
            if is_suspense is True or category == "suspense":
                # Make sure it's not already matched
                if not state.is_transaction_matched(txn_id):
                    suspense_txns.append(t)
                    logger.info(f"  Found suspense: TXN {txn_id}, is_suspense={is_suspense}, category={category}")

        logger.info(f"Final_unmatched: {len(final_unmatched)}, Suspense found: {len(suspense_txns)}")

        if suspense_txns:
            logger.info(f"Processing {len(suspense_txns)} unmatched suspense transactions")
            
            # Get ONLY UNMATCHED documents for suspense matching
            avail_docs = {}
            for dt, docs in all_docs.items():
                avail_docs[dt] = []
                doc_type_key = dt.rstrip('s') if dt.endswith('s') else dt
                
                for d in docs:
                    doc_id_field = f"{doc_type_key}_id"
                    doc_id = str(d.get(doc_id_field) or d.get("id") or "")
                    
                    # CRITICAL: Only include documents that haven't been matched yet
                    if doc_id and not state.is_document_matched(dt, doc_id):
                        avail_docs[dt].append(d)
                
                logger.info(f"  Available unmatched {dt}: {len(avail_docs[dt])} documents")
            
            total_avail = sum(len(v) for v in avail_docs.values())
            logger.info(f"  Total available unmatched documents: {total_avail}")
            
            if total_avail == 0:
                logger.warning("  ⚠️  NO unmatched documents available for suspense matching!")
            else:
                # Run suspense matching
                suspense_result = run_suspense_resolution(
                    executor, suspense_txns, avail_docs, config
                )
                
                if suspense_result["success"]:
                    raw_suspense = suspense_result["result"].get("matched", [])
                    logger.info(f"  LLM returned {len(raw_suspense)} suspense matches")
                    
                    # Validate matches (handle both single and combination)
                    suspense_matches = []
                    rejected_suspense = []
                    for match in raw_suspense:
                        if match.get("document_ids"):  # Combination
                            valid, rejected = validate_combination_matches(
                                [match], enriched_txns, all_docs, config
                            )
                            suspense_matches.extend(valid)
                            rejected_suspense.extend(rejected)
                        else:  # Single
                            valid, rejected = validate_exact_matches(
                                [match], enriched_txns, all_docs, config
                            )
                            suspense_matches.extend(valid)
                            rejected_suspense.extend(rejected)
                    
                    logger.info(f"  Validated {len(suspense_matches)} suspense matches, rejected {len(rejected_suspense)}")
                    
                    if suspense_matches:
                        # Update state
                        doc_ids, txn_ids = extract_matched_ids(suspense_matches)
                        for doc_type, ids in doc_ids.items():
                            for did in ids:
                                state.mark_document_matched(doc_type, did)
                        for tid in txn_ids:
                            state.mark_transaction_matched(tid)
                        
                        # Add to main matches
                        all_matches.extend(suspense_matches)
                        
                        # Remove matched from unmatched list
                        final_unmatched = [
                            t for t in final_unmatched 
                            if str(t.get("transaction_id")) not in txn_ids
                        ]
                        
                        # Count types
                        single_ct = sum(1 for m in suspense_matches if "document_id" in m and "document_ids" not in m)
                        combo_ct = sum(1 for m in suspense_matches if "document_ids" in m)
                        
                        # Update breakdown
                        results["summary"]["match_type_breakdown"]["suspense_single"] = single_ct
                        results["summary"]["match_type_breakdown"]["suspense_combination"] = combo_ct
                        
                        logger.info(f"✓ Suspense matched: {single_ct} single, {combo_ct} combination")
                    else:
                        logger.info("✓ No valid suspense matches after validation")
                else:
                    logger.warning("  Suspense resolution agent call failed")
        else:
            logger.info("✓ No unmatched suspense transactions")

        state.completed_steps.append(7)
        results["summary"]["workflow_steps_completed"].append(7)
        
        # =====================================================================
        # STEP 8: Validation
        # =====================================================================
        logger.info("\n[STEP 8/9] Final Validation")
        val_result = run_validation(executor, all_matches)
        
        if val_result["success"]:
            validated = val_result["result"].get("validated_matches", all_matches)
            rejected = val_result["result"].get("rejected_matches", [])
            
            # Rollback rejected
            for rej in rejected:
                state.rollback_match(rej)
                
                # Handle single transaction rejections
                if tid := rej.get("transaction_id"):
                    txn = next((t for t in non_dup_txns if str(t.get("transaction_id")) == str(tid)), None)
                    if txn and txn not in final_unmatched:
                        final_unmatched.append(txn)
                
                # Handle combination transaction rejections (split payments: N→1)
                for tid in rej.get("transaction_ids", []):
                    txn = next((t for t in non_dup_txns if str(t.get("transaction_id")) == str(tid)), None)
                    if txn and txn not in final_unmatched:
                        final_unmatched.append(txn)
        else:
            validated = all_matches
        
        state.completed_steps.append(8)
        results["summary"]["workflow_steps_completed"].append(8)
        logger.info(f"✓ Validated: {len(validated)}")
        
        # =====================================================================
        # STEP 9: Confidence Scoring
        # =====================================================================
        logger.info("\n[STEP 9/9] Confidence Scoring")
        score_result = run_confidence_scoring(executor, validated)
        
        if score_result["success"]:
            scored = score_result["result"].get("scored_matches", validated)
            
            # Merge scores back
            score_lookup = {m.get("transaction_id"): m for m in scored}
            for match in validated:
                tid = match.get("transaction_id")
                if tid and tid in score_lookup:
                    match.update(score_lookup[tid])
            
            # Count levels
            for m in scored:
                level = m.get("confidence_level", "LOW")
                if level in results["summary"]["confidence_breakdown"]:
                    results["summary"]["confidence_breakdown"][level] += 1
        
        state.completed_steps.append(9)
        results["summary"]["workflow_steps_completed"].append(9)
        
        # =====================================================================
        # FINAL RESULTS
        # =====================================================================
        results["matched_transactions"] = validated
        results["unmatched_transactions"] = [minify_transaction(t) for t in final_unmatched]
        results["summary"]["matched"] = len(validated)
        results["summary"]["unmatched"] = len(final_unmatched)
        results["summary"]["match_rate"] = f"{len(validated)/len(non_dup_txns)*100:.1f}%" if non_dup_txns else "0%"
        results["summary"]["api_stats"] = executor.get_stats()
        results["success"] = True
        results["workflow_completed"] = True
        
        # Summary log
        logger.info("\n" + "=" * 70)
        logger.info("WORKFLOW COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Total: {total_txns} | Duplicates: {results['summary']['duplicates_found']} | Available: {len(non_dup_txns)}")
        logger.info(f"Matched: {results['summary']['matched']} ({results['summary']['match_rate']})")
        logger.info(f"  Exact: {results['summary']['match_type_breakdown']['exact']}")
        logger.info(f"  Fuzzy: {results['summary']['match_type_breakdown']['fuzzy']}")
        logger.info(f"  Batch: {results['summary']['match_type_breakdown']['combination_batch']}")
        logger.info(f"  Split: {results['summary']['match_type_breakdown']['combination_split']}")
        logger.info(f"Unmatched: {results['summary']['unmatched']}")
        logger.info(f"Rejected (hallucinated IDs): {results['summary']['rejected_hallucinated']}")
        logger.info(f"API calls: {executor.api_calls} | Tokens: {executor.total_input_tokens + executor.total_output_tokens}")
        logger.info("=" * 70)
        
        return results
        
    except Exception as e:
        logger.error(f"CRITICAL ERROR: {e}")
        logger.error(traceback.format_exc())
        results["errors"].append({"error": str(e), "traceback": traceback.format_exc()})
        return results


def normalize_input_format(input_data: Any) -> Dict:
    """
    Normalize input to the expected format regardless of how it arrives.
    
    Handles:
    - Single object: {...}
    - Array with single object: [{...}]
    - Nested data: {data: {...}}
    - Array with nested data: [{data: {...}}]
    
    Returns: Single dict with required top-level fields
    """
    logger.info("Normalizing input format...")
    
    # Case 1: Input is a list
    if isinstance(input_data, list):
        if len(input_data) == 0:
            raise ValueError("Input array is empty")
        
        # Extract first item from array
        input_data = input_data[0]
        logger.debug("Extracted first item from array")
    
    # Case 2: Input is not a dict at this point (shouldn't happen, but defensive)
    if not isinstance(input_data, dict):
        raise ValueError(f"Expected dict after array extraction, got {type(input_data)}")
    
    # Case 3: Check if data is nested under 'data' key
    if 'data' in input_data and isinstance(input_data['data'], dict):
        # Check if 'bank_transactions' is under 'data'
        if 'bank_transactions' in input_data['data']:
            logger.debug("Found nested structure under 'data' key, extracting...")
            input_data = input_data['data']
    
    # Case 4: Verify required fields exist
    if 'bank_transactions' not in input_data:
        raise ValueError(
            f"Missing required field: bank_transactions. "
            f"Available keys: {list(input_data.keys())}"
        )
    
    # Ensure all required arrays exist (even if empty)
    required_arrays = [
        'bank_transactions',
        'bills',
        'invoices',
        'payroll_transactions',
        'share_transactions'
    ]
    
    for array_name in required_arrays:
        if array_name not in input_data:
            input_data[array_name] = []
            logger.debug(f"Added missing array: {array_name}")
    
    # Ensure company_name exists
    if 'company_name' not in input_data or not input_data['company_name']:
        input_data['company_name'] = "UNKNOWN COMPANY"
        logger.debug("Set default company_name")
    
    logger.info(f"✓ Input normalized: {input_data['company_name']}, "
                f"{len(input_data['bank_transactions'])} transactions")
    
    return input_data


# =============================================================================
# PUBLIC API
# =============================================================================

def main(data: Dict, config: Optional[MatchingConfig] = None) -> Dict:
    """Main entry point."""
    return orchestrate_matching(data, config or DEFAULT_CONFIG)


def health_check() -> Dict:
    """Health check endpoint."""
    return {
        "healthy": bool(os.getenv('ANTHROPIC_API_KEY')),
        "version": "7.0-production",
        "fixes": [
            "1. Ghost Document Rejection - REJECT hallucinated IDs",
            "2. Configurable Tolerance - bank fees, rounding",
            "3. Batched Processing - prevents context explosion",
            "4. Enhanced Validation - multi-stage with clear rejections",
        ],
        "config": {
            "batch_size": DEFAULT_CONFIG.batch_size,
            "bank_fee_tolerance": str(DEFAULT_CONFIG.bank_fee_tolerance),
            "reject_hallucinated_ids": DEFAULT_CONFIG.reject_hallucinated_ids
        }
    }


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--health":
        print(safe_json_dumps(health_check()))
    elif len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            data = json.load(f)
        result = main(data)
        print(safe_json_dumps(result))
    else:
        print("Transaction Matching Workflow V7")
        print(safe_json_dumps(health_check()))  