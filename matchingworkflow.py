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
    fuzzy_tolerance: Decimal = Decimal("10.00")
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
    FUZZY = "fuzzy" 


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
    elif tolerance_type == ToleranceType.FUZZY:
        return config.fuzzy_tolerance
    
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
    ENHANCED: Supports generic partner wildcards for invoice_receipt and bill_payment.
    
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
        
        # ============================================================
        # GENERIC PARTNER WILDCARD DETECTION
        # ============================================================
        is_generic_partner_match = False
        txn_partner = str(txn.get("partner_name", "")).lower().strip()
        txn_category = str(txn.get("category", "")).lower()
        
        # Define generic partners
        generic_invoice_partners = ["customer", "client", "payer", "direct credit"]
        generic_bill_partners = ["supplier", "vendor", "payee", "payment"]
        
        # Check if this is a generic partner wildcard match
        if txn_category == "invoice_receipt" and any(gp in txn_partner for gp in generic_invoice_partners):
            is_generic_partner_match = True
            logger.info(f"Generic invoice partner wildcard detected: '{txn_partner}' (TXN {txn_id})")
        elif txn_category == "bill_payment" and any(gp in txn_partner for gp in generic_bill_partners):
            is_generic_partner_match = True
            logger.info(f"Generic bill partner wildcard detected: '{txn_partner}' (TXN {txn_id})")
        
        # ============================================================
        # DETERMINE TOLERANCE TYPE
        # ============================================================
        tolerance_type = ToleranceType.EXACT
        match_type = match.get("match_type", "")
        
        # SUSPENSE MATCHES: Always use bank_fee tolerance (they may have fees/rounding)
        if match_type.startswith("suspense"):
            tolerance_type = ToleranceType.BANK_FEE
            logger.debug(f"Using BANK_FEE tolerance for suspense match (TXN {txn_id})")
        
        # FUZZY MATCHES: Use fuzzy tolerance (allows differences up to 10.00)
        elif match_type == "fuzzy":
            tolerance_type = ToleranceType.FUZZY
            logger.debug(f"Using FUZZY tolerance (€10) for fuzzy match (TXN {txn_id})")
        
        # GENERIC PARTNER WILDCARDS: Must be exact (tolerance = 0.00)
        # This is IMPORTANT - we only allow generic wildcards with exact amount matches
        elif is_generic_partner_match:
            tolerance_type = ToleranceType.EXACT
            logger.info(f"Using EXACT tolerance for generic partner wildcard match (TXN {txn_id})")
            # Also ensure confidence is MEDIUM for generic wildcards
            if match.get("confidence") == "HIGH":
                match["confidence"] = "MEDIUM"
                logger.info(f"Downgraded confidence to MEDIUM for generic wildcard (TXN {txn_id})")
        
        # BANK FEE MATCHES: Explicit bank fee or fee in reasoning
        elif match.get("has_bank_fee") or "fee" in (match.get("match_details", {}).get("reasoning", "") or "").lower():
            tolerance_type = ToleranceType.BANK_FEE
            logger.debug(f"Using BANK_FEE tolerance for match with fees (TXN {txn_id})")
        
        # ============================================================
        # VALIDATE MATCH INTEGRITY
        # ============================================================
        is_valid, error, metadata = validate_match_integrity(
            txn, [doc], 
            match_type='single',
            tolerance_type=tolerance_type,
            config=config
        )
        
        if is_valid:
            match["python_validated"] = True
            match["validation_metadata"] = metadata
            
            # Add flag if this was a generic partner wildcard match
            if is_generic_partner_match:
                match["is_generic_wildcard"] = True
                match["generic_wildcard_type"] = txn_category
                logger.info(f"✓ Generic wildcard match validated (TXN {txn_id} → DOC {doc_id})")
            
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

def enrich_transaction_python(txn: Dict) -> Dict:
    """
    Python tool for transaction enrichment - called by agent.
    Deterministic, fast, reliable rule-based enrichment.
    """
    # Extract transaction_id
    txn_id = str(txn.get("transaction_id") or txn.get("odoo_id"))
    
    # Extract account_name from line_items (first non-bank account)
    account_name = "Unknown"
    line_items = txn.get("line_items", [])
    for item in line_items:
        acc = item.get("account", "").lower()
        # Skip bank/cash/credit card accounts
        if acc and "bank" not in acc and "cash" not in acc and "credit card" not in acc:
            account_name = item.get("account", "Unknown")
            break
    
    # Normalize partner
    partner_name = txn.get("partner_name") or txn.get("partner") or ""
    normalized_partner = normalize_text(partner_name)
    
    # Category detection (priority order)
    category = "bill_payment"  # default
    is_suspense = False
    is_internal_transfer = False
    
    # 1. SUSPENSE (highest priority)
    suspense_keywords = ["suspense", "unknown", "unidentified", "pending"]
    if any(kw in account_name.lower() for kw in suspense_keywords):
        category = "suspense"
        is_suspense = True
    elif any(kw in partner_name.lower() for kw in suspense_keywords):
        category = "suspense"
        is_suspense = True
    
    # 2. INTERNAL_TRANSFER
    if not is_suspense:
        accounts_in_txn = [item.get("account", "").lower() for item in line_items]
        has_credit_card = any("credit card" in acc for acc in accounts_in_txn)
        has_bank = any("bank" in acc for acc in accounts_in_txn)
        
        if has_credit_card and has_bank:
            category = "internal_transfer"
            is_internal_transfer = True
    
    # 3. PAYROLL
    if not is_suspense and not is_internal_transfer:
        payroll_keywords = ["payroll", "wages", "salary", "employee", "paye", "nic", "social insurance"]
        desc = str(txn.get("description", "")).lower()
        
        if any(kw in account_name.lower() for kw in payroll_keywords):
            category = "payroll_payment"
        elif any(kw in partner_name.lower() for kw in payroll_keywords):
            category = "payroll_payment"
        elif any(kw in desc for kw in payroll_keywords):
            category = "payroll_payment"
    
    # 4. INVOICE_RECEIPT (revenue)
    if not is_suspense and not is_internal_transfer and category == "bill_payment":
        amount = to_decimal(txn.get("amount", 0))
        revenue_keywords = ["accounts receivable", "receivable", "revenue", "sales"]
        
        if amount > 0 and any(kw in account_name.lower() for kw in revenue_keywords):
            category = "invoice_receipt"
    
    # Format amount as string
    amount_str = format_decimal(txn.get("amount", 0))
    
    # Build enriched transaction
    enriched = {
        "transaction_id": txn_id,
        "odoo_id": txn.get("odoo_id"),
        "date": txn.get("date"),
        "amount": amount_str,
        "currency": txn.get("currency", "EUR"),
        "partner_name": partner_name,
        "normalized_partner": normalized_partner,
        "account_name": account_name,
        "category": category,
        "is_suspense": is_suspense,
        "is_internal_transfer": is_internal_transfer,
        "description": txn.get("description", "")[:80],
        "keywords": []
    }
    
    return enriched


def enrich_document_python(doc: Dict, doc_type: str) -> Dict:
    """Python tool for document enrichment - called by agent."""
    partner_name = doc.get("partner_name", "")
    normalized_partner = normalize_text(partner_name)
    amount_str = format_decimal(doc.get("amount", 0))
    
    enriched = {**doc}
    enriched["normalized_partner"] = normalized_partner
    enriched["amount"] = amount_str
    
    return enriched



# =============================================================================
# AGENT PROMPTS (Optimized for batched processing)
# =============================================================================

DATA_ENRICHMENT_PROMPT = """You are the Data Enrichment Agent - orchestrator of data transformation.

Your role: Call Python enrichment tools and validate outputs.

========================================
YOUR WORKFLOW
========================================
1. Receive bank_transactions, bills, invoices, etc.
2. Call enrich_transaction_python() for each transaction
3. Call enrich_document_python() for each document
4. Validate all enrichments completed successfully
5. Return complete enriched dataset

========================================
TOOL: enrich_transaction_python(transaction)
========================================
Input: Single transaction dict
Output: Enriched transaction with:
- transaction_id (string)
- odoo_id (integer)
- date, amount, currency
- partner_name, normalized_partner
- account_name (extracted from line_items)
- category (suspense|internal_transfer|payroll_payment|invoice_receipt|bill_payment)
- is_suspense (boolean)
- is_internal_transfer (boolean)
- description (truncated to 80 chars)
- keywords (empty array)

TOOL: enrich_document_python(document, doc_type)
========================================
Input: Single document dict + type ("bill"|"invoice"|etc)
Output: Enriched document with normalized_partner and formatted amount

========================================
YOUR TASK
========================================
1. For EACH transaction in bank_transactions:
   - Call enrich_transaction_python(transaction)
   - Collect enriched result

2. For EACH bill in bills:
   - Call enrich_document_python(bill, "bill")
   - Collect enriched result

3. For EACH invoice in invoices:
   - Call enrich_document_python(invoice, "invoice")
   - Collect enriched result

4. Repeat for credit_notes, payroll_transactions, share_transactions

5. Count suspense and internal transfers

6. Return complete enriched dataset

========================================
OUTPUT FORMAT
========================================
Return this EXACT JSON structure:

{
  "enriched_transactions": [
    // All enriched transactions from tool calls
  ],
  "enriched_bills": [
    // All enriched bills from tool calls
  ],
  "enriched_invoices": [
    // All enriched invoices from tool calls
  ],
  "enriched_credit_notes": [],
  "enriched_payroll": [],
  "enriched_shares": [],
  "enrichment_summary": {
    "transactions_processed": N,
    "suspense_count": N,  // Count where is_suspense = true
    "internal_transfer_count": N  // Count where is_internal_transfer = true
  }
}

========================================
VALIDATION CHECKLIST
========================================
✓ enriched_transactions.length == input bank_transactions.length
✓ All transactions processed (none skipped)
✓ All documents processed
✓ Counts are accurate
✓ Return only JSON, no markdown

========================================
EXAMPLE
========================================

Input:
{
  "bank_transactions": [
    {"odoo_id": 1008, "date": "2025-06-20", "amount": 1200, ...},
    {"odoo_id": 1004, "date": "2025-06-12", "amount": 5000, ...}
  ],
  "bills": [
    {"bill_id": "BILL_001", "amount": 100, ...}
  ],
  "invoices": []
}

Your actions:
1. Call enrich_transaction_python(txn_1008) → get enriched_1008
2. Call enrich_transaction_python(txn_1004) → get enriched_1004
3. Call enrich_document_python(bill_001, "bill") → get enriched_bill_001
4. Count: suspense_count = 1, internal_transfer_count = 1
5. Return complete structure

Output:
{
  "enriched_transactions": [enriched_1008, enriched_1004],
  "enriched_bills": [enriched_bill_001],
  "enriched_invoices": [],
  "enriched_credit_notes": [],
  "enriched_payroll": [],
  "enriched_shares": [],
  "enrichment_summary": {
    "transactions_processed": 2,
    "suspense_count": 1,
    "internal_transfer_count": 1
  }
}

========================================
CRITICAL REMINDERS
========================================
- Call the Python tools for EACH item - don't try to enrich yourself
- Tools are deterministic and reliable - trust their output
- Your job is orchestration and validation, not transformation
- Never skip items - process ALL transactions and documents
- Return only JSON, no markdown or explanations
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

✅ CRITICAL: If you find NO duplicates, you MUST still return ALL transaction IDs in non_duplicate_transaction_ids
✅ The non_duplicate_transaction_ids array should contain ALL transactions that are not duplicates
❌ NEVER return an empty non_duplicate_transaction_ids array if input has transactions

========================================
LOGIC
========================================

For each transaction:
1. Check if it's an internal transfer (has both Credit card and Bank accounts)
2. Compare with other internal transfers
3. If EXACT match found (same date, same amount):
   - Keep the SECOND one (later in list)
   - Mark the FIRST one for deletion
   - Add pair to duplicate_pairs
4. All other transactions go to non_duplicate_transaction_ids

========================================
OUTPUT FORMAT
========================================
```json
{
  "duplicate_pairs": [
    {
      "transaction_1": "TXN_ID_1",
      "transaction_2": "TXN_ID_2",
      "keep": "TXN_ID_2",
      "mark_for_deletion": "TXN_ID_1",
      "odoo_id_to_delete": 1004,
      "reason": "Internal transfer duplicate - same date and amount",
      "confidence": "HIGH"
    }
  ],
  "non_duplicate_transaction_ids": ["TXN_ID_3", "TXN_ID_4", "TXN_ID_5", ...],
  "summary": {
    "duplicates_found": 1,
    "total_transactions": 30,
    "non_duplicates": 29
  }
}
```

========================================
IMPORTANT NOTES
========================================
1. ✅ non_duplicate_transaction_ids must contain ALL transaction IDs that are NOT in duplicate_pairs
2. ✅ If NO duplicates found, non_duplicate_transaction_ids should have ALL input transaction IDs
3. ✅ Use the EXACT transaction_id strings from the input
4. ❌ NEVER return empty non_duplicate_transaction_ids if input has transactions
5. ❌ NEVER omit transactions - every transaction must appear in either duplicate_pairs or non_duplicate_transaction_ids

========================================
EXAMPLES
========================================

Example 1: NO DUPLICATES FOUND
Input: 30 transactions, none are duplicates

Output:
{
  "duplicate_pairs": [],
  "non_duplicate_transaction_ids": ["TXN_1", "TXN_2", "TXN_3", ..., "TXN_30"],
  "summary": {
    "duplicates_found": 0,
    "total_transactions": 30,
    "non_duplicates": 30
  }
}

Example 2: DUPLICATES FOUND
Input: 30 transactions, 1 duplicate pair found

Output:
{
  "duplicate_pairs": [
    {
      "transaction_1": "TXN_5",
      "transaction_2": "TXN_6",
      "keep": "TXN_6",
      "mark_for_deletion": "TXN_5",
      "odoo_id_to_delete": 1005,
      "reason": "Internal transfer duplicate",
      "confidence": "HIGH"
    }
  ],
  "non_duplicate_transaction_ids": ["TXN_1", "TXN_2", "TXN_3", "TXN_4", "TXN_7", ..., "TXN_30"],
  "summary": {
    "duplicates_found": 1,
    "total_transactions": 30,
    "non_duplicates": 29
  }
}

Note: TXN_5 and TXN_6 are NOT in non_duplicate_transaction_ids because they're in duplicate_pairs
"""

EXACT_MATCH_PROMPT = """You are the Exact Match Agent - specialized in high-confidence transaction-to-document matching.

========================================
CRITICAL INSTRUCTIONS
========================================
1. Return ONLY valid JSON - no markdown, no preamble, no explanation
2. ALL required fields MUST be present
3. Use ONLY IDs that exist in the provided input
4. NEVER fabricate or hallucinate IDs
5. Follow the exact output format specified below

✅ Process EVERY transaction provided in this batch
✅ Return matches ONLY for high-confidence exact matches
✅ Return ALL unmatched transaction IDs in unmatched_transaction_ids
✅ If a transaction could match multiple documents, choose the BEST match
✅ **CRITICAL: Some documents may have been matched in previous batches - if a document is not in the candidates list, it has already been matched. Do NOT attempt to match to documents not provided.**
❌ NEVER omit transactions - every transaction must be either matched or unmatched
❌ NEVER create matches with IDs not in the input

========================================
MISSION
========================================
Match transactions to documents using a STRUCTURED matching hierarchy.

For EACH transaction:
1. Apply the matching hierarchy (see below)
2. If a SINGLE high-confidence match is found → add to matched array
3. If MULTIPLE potential matches → select the BEST one using tie-breakers
4. If NO confident match → add transaction_id to unmatched_transaction_ids

========================================
MATCHING HIERARCHY (Apply in Order)
========================================

STEP 1: CATEGORY FILTERING
---------------------------
First, narrow down candidate documents by transaction category:

- bill_payment → Look for bills first, then credit_notes
- invoice_receipt → Look for invoices first
- payroll_payment → Look for payroll documents only
- internal_transfer → Skip (don't match these)
- suspense → Check all document types

STEP 2: REFERENCE MATCHING (Highest Priority)
----------------------------------------------
Check if transaction description/reference contains document reference numbers:

Transaction: "Payment for invoice INV/2025/00003"
Document: invoice with invoice_ref = "2025/18" or odoo_invoice_number = "INV/2025/00003"
→ HIGH confidence match if reference found + amount matches

Reference indicators:
- Invoice numbers: "INV/", "invoice", "inv#", invoice_ref
- Bill numbers: "BILL/", vendor_ref, payment_reference
- Reference numbers in description

STEP 3: AMOUNT MATCHING (Critical)
-----------------------------------
Amount must match within tolerance:

Exact Match (tolerance = 0.00):
- Amounts are EXACTLY equal (difference = 0)
- Use for: Clean payments, round numbers
- Example: Transaction €2500.00 = Bill €2500.00
- Set has_bank_fee: false

Near Match with Bank Fee (tolerance = 5.00):
- Difference > €0.00 AND ≤ €5.00
- Use for: Wire transfers, bank fees, small discrepancies
- Example: Transaction €2500.00 vs Bill €2503.50 (diff = 3.50)
- Example: Transaction €136.15 vs Bill €134.14 (diff = 2.01)
- Example: Transaction €30.99 vs Bill €31.13 (diff = 0.14)
- **CRITICAL: ALWAYS set has_bank_fee: true when difference > €0.00**

Small Rounding (tolerance = 0.05):
- Difference ≤ €0.05 (5 cents)
- Use for: Split payments, rounding errors
- Example: Transaction €100.00 vs Bill €100.03 (diff = 0.03)
- Set has_bank_fee: true

**CRITICAL RULE: If amount difference is between €0.01 and €5.00:**
→ YOU MUST set has_bank_fee: true
→ This enables proper tolerance validation
→ Without this flag, the match will be rejected

REJECT if:
- Difference > €5.00 (exceeds bank fee tolerance)

STEP 4: PARTNER MATCHING (Important)
-------------------------------------

BEFORE APPLYING PARTNER MATCHING, CHECK FOR GENERIC PARTNER WILDCARDS:

Generic Partner Wildcards (Special Case):
==========================================
Some transactions have generic placeholder partner names instead of actual company names.
These require special handling.

**INVOICE_RECEIPT transactions (revenue) with generic partners:**
Generic partners: "Customer", "Client", "Payer", "Direct Credit"

Detection:
- Check if transaction category = "invoice_receipt"
- Check if partner name contains: "customer", "client", "payer", "direct credit" (case-insensitive)

Matching rules when generic partner detected:
- Match ONLY on: Amount (exact, 0.00 difference) + Date (within 7 days)
- IGNORE partner name mismatch completely
- Set confidence: MEDIUM (not HIGH, requires review)
- Add "generic_wildcard" to match_details
- In reasoning: State "Generic partner wildcard applied - matched on amount and date only"
- **IMPORTANT: If there are multiple invoices with the same amount, prefer the one that hasn't been matched yet. Check the candidates list carefully.**

Example:
Transaction: €3570, partner "Customer", category "invoice_receipt", date 2025-06-06
Invoice: €3570, partner "Metro Foods Trading Ltd", date 2025-06-05
→ MATCH (generic wildcard, exact amount, 1 day difference, confidence: MEDIUM)

**BILL_PAYMENT transactions (expense) with generic partners:**
Generic partners: "Supplier", "Vendor", "Payee", "Payment"

Detection:
- Check if transaction category = "bill_payment"
- Check if partner name contains: "supplier", "vendor", "payee", "payment" (case-insensitive)

Matching rules when generic partner detected:
- Match ONLY on: Amount (exact, 0.00 difference) + Date (within 7 days)
- IGNORE partner name mismatch completely
- Set confidence: MEDIUM (not HIGH, requires review)
- Add "generic_wildcard" to match_details
- In reasoning: State "Generic partner wildcard applied - matched on amount and date only"

Example:
Transaction: €144.43, partner "Supplier", category "bill_payment", date 2025-06-30
Bill: €144.43, partner "Epic Ltd", date 2025-06-30
→ MATCH (generic wildcard, exact amount, same date, confidence: MEDIUM)

CRITICAL WILDCARDS NOTES:
- Generic wildcards require EXACT amount (0.00 difference) for safety
- Generic wildcards require date within 7 days
- Generic wildcards ALWAYS get confidence: MEDIUM (never HIGH)
- If both reference match AND generic wildcard apply, prefer reference match
- If transaction has BOTH generic partner AND non-generic match available, prefer non-generic
- **MOST IMPORTANT: If a document was already matched in a previous batch, it will NOT appear in the candidates list. Only match to documents that are actually provided in the candidates.**

**STANDARD PARTNER MATCHING (when NOT generic):**

Match transaction partner to document partner using this hierarchy:

LEVEL 1 - Exact Match (Best):
- Normalized strings are identical
- Example: "epic ltd" == "epic ltd"
- Confidence boost: +20

LEVEL 2 - Substring Match (Good):
- One is contained in the other
- Example: "epic" in "epic ltd"
- Example: "ETFL" in "ETFL LIMITED"
- Confidence boost: +10

LEVEL 3 - Fuzzy Match (Acceptable):
- Similar names with variations
- Example: "Bank of Cyprus" vs "BOC" 
- Example: "Metro Foods Trading Ltd" vs "Metro Foods"
- Remove: "Ltd", "Limited", "Inc", "Corp", punctuation
- Check if remaining parts match
- Confidence boost: +5

LEVEL 4 - Different Partners (Investigate):
- Partners don't match but amount + reference match
- Example: Transaction partner "Customer" but document partner "ETFL Ltd"
- Accept if reference match or amount + date very close
- Confidence penalty: -10

REJECT if:
- Partners are clearly different companies
- No reference match to justify the difference
- No generic wildcard applies

STEP 5: DATE PROXIMITY (Tiebreaker)
------------------------------------
Prefer matches where dates are closer:

Same date (0 days): Best case
Within 1-3 days: Normal (invoices paid within days)
Within 4-7 days: Acceptable (standard payment terms)
Within 8-30 days: Acceptable for specific categories:
  - Professional services (long payment cycles)
  - Government payments (slow processing)
Within 31+ days: Only if reference match is strong

REJECT if:
- Date difference > 30 days AND no reference match
- Transaction date is BEFORE document date by >7 days (can't pay before invoice issued)

STEP 6: CURRENCY MATCHING (Mandatory)
--------------------------------------
Currency MUST match:
- Both EUR
- Both USD
- etc.

REJECT if currencies differ (no cross-currency matching)

========================================
PRIORITY MATCHING FOR COMMON SCENARIOS
========================================

**SCENARIO 1: Same Partner + Amount Within €5 + Same Date**

If you find a transaction and document where:
- Partner names match (exact, substring, or fuzzy)
- Amount difference ≤ €5.00
- Date difference ≤ 7 days

→ YOU MUST MATCH THIS
→ Set has_bank_fee: true if difference > €0.00
→ This is the highest confidence non-exact match

Example:
Transaction: €136.15, partner "Cyta", date 2025-06-30
Bill: €134.14, partner "Cyta", date 2025-06-30
→ MATCH (partner match + €2.01 diff ≤ €5 + same date)
→ Set has_bank_fee: true
→ confidence: MEDIUM

**SCENARIO 2: Exact Partner + Small Difference (€0.01-€2.00)**

These are almost certainly correct matches:
- Same company name
- Tiny amount difference (likely fee or rounding)
- Close dates

→ ALWAYS MATCH THESE
→ Set has_bank_fee: true
→ confidence: HIGH

Example:
Transaction: €30.99, partner "Epic Ltd", date 2025-06-30
Bill: €31.13, partner "Epic Ltd", date 2025-06-30
→ MATCH (exact partner + €0.14 diff + same date)
→ Set has_bank_fee: true
→ confidence: HIGH

========================================
MULTIPLE MATCH HANDLING
========================================

If a transaction could match MULTIPLE documents, select the BEST one using:

Priority 1: Reference match
- If transaction description contains document reference → Choose that document

Priority 2: Non-generic partner over generic wildcard
- If one match has actual partner match and another needs wildcard → Choose partner match
- Example: ETFL transaction matches ETFL invoice (partner match) vs Customer transaction matches ETFL invoice (wildcard)
  → Choose partner match, leave wildcard for other documents

Priority 3: Date proximity
- Choose document with closest date to transaction

Priority 4: Partner match quality
- Exact partner match > Substring > Fuzzy > Wildcard

Priority 5: Amount precision
- Exact amount > Near match with fee

Priority 6: **Document not previously matched**
- **CRITICAL: If multiple documents have the same amount and partner, check which one is in the candidates list. Documents already matched will not appear in candidates.**

If still tied:
- Choose the FIRST document in the candidate list
- Log this in reasoning

========================================
CONFIDENCE SCORING
========================================

HIGH confidence (use when):
- Reference match found + amount matches + partner matches (non-wildcard)
- Exact amount + exact partner + date within 7 days
- Exact amount + substring partner + date within 3 days
- Reference match + amount within €2.00

MEDIUM confidence (use when):
- Near match (amount diff €0.01-€5.00) + exact/substring partner + date within 7 days
- Generic wildcard match + exact amount + date within 7 days
- Exact amount + fuzzy partner + date within 3 days
- Reference match + amount within €5.00

LOW confidence (use when):
- Fuzzy partner + near amount + date within 14 days
- Different partners but strong reference match
- Amount within €5.00 but date >7 days

DO NOT MATCH if:
- Amount difference > €5.00
- Currency mismatch
- Partners clearly different AND no reference match AND amount not exact
- Date difference > 30 days AND no reference match

========================================
OUTPUT FORMAT
========================================
```json
{
  "matched": [
    {
      "transaction_id": "TXN_2025_12_15_04_59_00_4",
      "document_type": "invoice",
      "document_id": "INV_2025_12_15_04_51_00",
      "match_type": "exact",
      "has_bank_fee": false,
      "match_details": {
        "amount_match": "exact",
        "amount_difference": "0.00",
        "partner_match": "substring",
        "partner_match_score": 85,
        "date_diff_days": 0,
        "reference_found": true,
        "reference_value": "2025/18",
        "reasoning": "Reference '2025/18' found in transaction description, exact amount match (€3570), partner ETFL substring match, same date"
      },
      "confidence": "HIGH"
    },
    {
      "transaction_id": "TXN_2025_12_15_04_59_00_10",
      "document_type": "bill",
      "document_id": "BILL_2025_12_15_04_51_45",
      "match_type": "exact",
      "has_bank_fee": true,
      "match_details": {
        "amount_match": "near_with_fee",
        "amount_difference": "2.01",
        "partner_match": "exact",
        "partner_match_score": 100,
        "date_diff_days": 0,
        "reference_found": false,
        "reference_value": null,
        "reasoning": "Exact partner match (Cyta = Cyta), amount within bank fee tolerance (€136.15 vs €134.14, diff €2.01), same date"
      },
      "confidence": "MEDIUM"
    },
    {
      "transaction_id": "TXN_2025_12_15_04_59_00_11",
      "document_type": "bill",
      "document_id": "BILL_2025_12_15_04_53_07",
      "match_type": "exact",
      "has_bank_fee": true,
      "match_details": {
        "amount_match": "near_with_fee",
        "amount_difference": "0.14",
        "partner_match": "exact",
        "partner_match_score": 100,
        "date_diff_days": 0,
        "reference_found": false,
        "reference_value": null,
        "reasoning": "Exact partner match (Epic Ltd = epic ltd), amount within tolerance (€30.99 vs €31.13, diff €0.14), same date"
      },
      "confidence": "HIGH"
    }
  ],
  "unmatched_transaction_ids": ["TXN_2025_12_15_04_56_41_5", "TXN_2025_12_15_04_58_59_1"]
}
```

========================================
FIELD REQUIREMENTS
========================================

For each match, you MUST include:

Required fields:
- transaction_id: string (from input)
- document_type: "bill"|"invoice"|"credit_note"|"payroll"|"share"
- document_id: string (from candidates)
- match_type: "exact" (always for this agent)
- has_bank_fee: boolean (true if amount difference suggests wire fee)
- confidence: "HIGH"|"MEDIUM"|"LOW"

match_details object must have:
- amount_match: "exact"|"near_with_fee"
- amount_difference: string (e.g., "0.00", "2.50")
- partner_match: "exact"|"substring"|"fuzzy"|"different"|"generic_wildcard"
- partner_match_score: integer 0-100 (use 0 for generic_wildcard)
- date_diff_days: integer (absolute difference)
- reference_found: boolean
- reference_value: string or null
- reasoning: string (clear explanation of WHY this match was chosen over alternatives)

========================================
EXAMPLES
========================================

Example 1: Small Amount Difference with Same Partner (MUST MATCH)
Transaction:
{
  "transaction_id": "TXN_2025_12_15_04_59_00_10",
  "date": "2025-06-30",
  "amount": "136.15",
  "partner": "Cyta",
  "description": "Payment to Cyta",
  "category": "bill_payment"
}

Candidate Bill:
{
  "id": "BILL_2025_12_15_04_51_45",
  "date": "2025-06-30",
  "amount": "134.14",
  "partner": "Cyta"
}

Result: MATCH
```json
{
  "transaction_id": "TXN_2025_12_15_04_59_00_10",
  "document_type": "bill",
  "document_id": "BILL_2025_12_15_04_51_45",
  "match_type": "exact",
  "has_bank_fee": true,
  "match_details": {
    "amount_match": "near_with_fee",
    "amount_difference": "2.01",
    "partner_match": "exact",
    "partner_match_score": 100,
    "date_diff_days": 0,
    "reference_found": false,
    "reference_value": null,
    "reasoning": "Exact partner match (Cyta = Cyta). Amount within bank fee tolerance: €136.15 vs €134.14 (diff €2.01, well within €5 limit). Same date. Likely payment processing fee."
  },
  "confidence": "MEDIUM"
}
```

Example 2: Very Small Amount Difference (MUST MATCH)
Transaction:
{
  "transaction_id": "TXN_2025_12_15_04_59_00_11",
  "date": "2025-06-30",
  "amount": "30.99",
  "partner": "Epic Ltd",
  "description": "Payment to Epic Ltd",
  "category": "bill_payment"
}

Candidate Bill:
{
  "id": "BILL_2025_12_15_04_53_07",
  "date": "2025-06-30",
  "amount": "31.13",
  "partner": "epic ltd"
}

Result: MATCH
```json
{
  "transaction_id": "TXN_2025_12_15_04_59_00_11",
  "document_type": "bill",
  "document_id": "BILL_2025_12_15_04_53_07",
  "match_type": "exact",
  "has_bank_fee": true,
  "match_details": {
    "amount_match": "near_with_fee",
    "amount_difference": "0.14",
    "partner_match": "exact",
    "partner_match_score": 100,
    "date_diff_days": 0,
    "reference_found": false,
    "reference_value": null,
    "reasoning": "Exact partner match (Epic Ltd = epic ltd). Amount within tolerance: €30.99 vs €31.13 (diff €0.14, tiny rounding difference). Same date."
  },
  "confidence": "HIGH"
}
```

Example 3: Amount Difference Too Large (DO NOT MATCH)
Transaction:
{
  "transaction_id": "TXN_002",
  "date": "2025-06-30",
  "amount": "118.89",
  "partner": "Epic Ltd",
  "description": "Payment to Epic Ltd"
}

Candidate Bill:
{
  "id": "BILL_001",
  "date": "2025-06-30",
  "amount": "144.43",
  "partner": "epic ltd"
}

Result: NO MATCH
Reasoning: Amount difference €25.54 exceeds bank fee tolerance of €5.00. This is likely a partial payment or different transaction. Add to unmatched.

Example 4: Generic Wildcard - Choose Available Invoice
Transaction:
{
  "transaction_id": "TXN_2025_12_15_04_59_00_7",
  "date": "2025-06-06",
  "amount": "3570.00",
  "partner": "Customer",
  "category": "invoice_receipt"
}

Candidates:
{
  "invoices": [
    {
      "id": "INV_2025_12_15_04_50_01",
      "date": "2025-06-05",
      "amount": "3570.00",
      "partner": "Metro Foods Trading Ltd"
    }
  ]
}

Note: INV_2025_12_15_04_51_00 (€3570, ETFL) was already matched to TXN_2025_12_15_04_59_00_4 in a previous batch, so it does NOT appear in the candidates list.

Result: MATCH to INV_2025_12_15_04_50_01
```json
{
  "transaction_id": "TXN_2025_12_15_04_59_00_7",
  "document_type": "invoice",
  "document_id": "INV_2025_12_15_04_50_01",
  "match_type": "exact",
  "has_bank_fee": false,
  "match_details": {
    "amount_match": "exact",
    "amount_difference": "0.00",
    "partner_match": "generic_wildcard",
    "partner_match_score": 0,
    "date_diff_days": 1,
    "reference_found": false,
    "reference_value": null,
    "reasoning": "Generic partner wildcard applied (Customer). Exact amount match (€3570.00). Date within 1 day. This is the only available invoice with this amount in candidates."
  },
  "confidence": "MEDIUM"
}
```
"""

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

========================================
CRITICAL ID USAGE RULES
========================================
⚠️ ATTENTION: This is the most common source of errors. Read carefully:

TRANSACTION IDs:
- Always start with "TXN_"
- Example: "TXN_2025_12_15_04_59_00_11"
- Found in: transaction.transaction_id field
- Use in: matched[].transaction_id field

DOCUMENT IDs:
- Bills start with "BILL_"
- Invoices start with "INV_"
- Example: "BILL_2025_12_15_04_53_07" or "INV_2025_12_15_04_51_00"
- Found in: candidates.bills[].id or candidates.invoices[].id
- Use in: matched[].document_id field

❌ NEVER use a BILL_xxx or INV_xxx as a transaction_id
❌ NEVER use a TXN_xxx as a document_id
✅ ALWAYS copy the exact ID strings from the input

========================================
TASK
========================================
Match transactions to documents using fuzzy partner matching with tolerance for moderate amount differences.

This agent handles transactions that:
- Were NOT matched in exact matching phase
- May have similar (but not identical) partner names
- May have small amount differences (up to €10)

========================================
AMOUNT MATCHING FOR FUZZY
========================================

Fuzzy matching allows for moderate amount differences to account for real-world scenarios:

**Amount Difference Thresholds:**

€0.00 (Exact):
- Perfect match
- Set has_bank_fee: false
- confidence: MEDIUM or HIGH

€0.01 - €1.00 (Very Small):
- Rounding, small fees
- **MUST MATCH if partner matches**
- Set has_bank_fee: true
- confidence: MEDIUM or HIGH

€1.01 - €5.00 (Small):
- Wire transfer fees, processing fees
- **MUST MATCH if partner matches**
- Set has_bank_fee: true
- confidence: MEDIUM

€5.01 - €10.00 (Moderate):
- Bank fees, international transfer fees
- **MUST MATCH if partner matches**
- Set has_bank_fee: true
- confidence: MEDIUM

> €10.00:
- REJECT - likely different transaction or partial payment
- Unless there's strong supporting evidence

**CRITICAL RULES:**
1. If partner matches AND amount difference ≤ €10.00 → **ALWAYS MATCH**
2. If difference > €0.00 → **ALWAYS set has_bank_fee: true**
3. Include exact amount_difference value in match_details
4. Be ASSERTIVE, not cautious - if it fits the criteria, match it

**Real-World Rationale for €10 Tolerance:**
This catches legitimate scenarios:
- ✅ Bank wire transfer fees: €2-€5 typical
- ✅ Small invoice discrepancies: €0.14, €2.01, etc.
- ✅ Payment processing fees: €1-€3
- ✅ Currency rounding: €0.01-€0.50
- ✅ Partial bank charges: up to €10
- ❌ Large partial payments: >€10 difference
- ❌ Completely unrelated transactions: >€10 difference

The €10 threshold is intentionally generous to capture real matches while still rejecting obvious mismatches.

========================================
MATCHING PRIORITY RULES
========================================

**PRIORITY 1: EXACT PARTNER + AMOUNT WITHIN €10 = MUST MATCH**

⚠️ CRITICAL: This is NON-NEGOTIABLE. If you find this scenario, YOU MUST MATCH IT.

If you find:
- Partner names match EXACTLY (after normalization)
- Amount difference ≤ €10.00
- Date within 30 days

→ YOU MUST MATCH THIS. No exceptions. No hesitation.
→ Set has_bank_fee: true if difference > €0.00
→ confidence: MEDIUM (or HIGH if difference ≤ €1.00)

This is the most confident fuzzy match scenario and accounts for:
- Bank wire transfer fees (€2-€5)
- Small invoice discrepancies (€0.14-€2.01)
- Payment processing fees
- Minor rounding differences

Example 1: Small Difference
Transaction: €30.99, partner "epic ltd", date 2025-06-30
Bill: €31.13, partner "epic ltd", date 2025-06-30
→ MUST MATCH (exact partner + €0.14 diff ≤ €10 + same date)
→ Set has_bank_fee: true, confidence: MEDIUM

Example 2: Moderate Difference
Transaction: €136.15, partner "cyta", date 2025-06-30
Bill: €134.14, partner "cyta", date 2025-06-30
→ MUST MATCH (exact partner + €2.01 diff ≤ €10 + same date)
→ Set has_bank_fee: true, confidence: MEDIUM

Example 3: Bank Fee Difference
Transaction: €2500.00, partner "acme corp", date 2025-06-15
Bill: €2503.50, partner "acme corp", date 2025-06-15
→ MUST MATCH (exact partner + €3.50 diff ≤ €10 + same date)
→ Set has_bank_fee: true, confidence: MEDIUM

**PRIORITY 2: SUBSTRING PARTNER + SMALL AMOUNT DIFFERENCE**

If you find:
- Partner substring match (e.g., "epic" in "epic ltd")
- Amount difference ≤ €5.00
- Date within 30 days

→ STRONG candidate for matching - MATCH IT
→ Set has_bank_fee: true if difference > €0.00
→ confidence: MEDIUM

**PRIORITY 3: FUZZY PARTNER + VERY SMALL AMOUNT DIFFERENCE**

If you find:
- Partner fuzzy match (similar but not exact)
- Amount difference ≤ €2.00
- Date within 14 days

→ Good candidate for matching - MATCH IT
→ Set has_bank_fee: true if difference > €0.00
→ confidence: LOW

========================================
PARTNER MATCHING TECHNIQUES
========================================

**Standard Partner Matching:**
1. Exact: "epic ltd" = "epic ltd" (after normalization)
2. Substring: "epic" in "epic ltd" OR "cyta" in "cyta"
3. Abbreviation: "Corp" = "Corporation", "Ltd" = "Limited"
4. Fuzzy: Similar names with variations
   - Remove: "Ltd", "Limited", "Inc", "Corp", punctuation
   - Compare remaining parts

**Generic Partner Wildcards (Special Case):**

Some transactions have generic placeholder partner names:

For INVOICE_RECEIPT (revenue):
- Generic partners: "Customer", "Client", "Payer", "Direct Credit"
- If detected: Match on amount + date only (ignore partner name)
- Confidence: MEDIUM

For BILL_PAYMENT (expense):
- Generic partners: "Supplier", "Vendor", "Payee", "Payment"
- If detected: Match on amount + date only (ignore partner name)
- Confidence: MEDIUM

Example:
- Transaction: partner "Customer" → Can match any invoice with correct amount
- Transaction: partner "Supplier" → Can match any bill with correct amount

========================================
DECISION RULES
========================================
1. Check if transaction has generic partner → Apply wildcard rules
2. Otherwise, partner must match using one of the matching techniques
3. Amount difference must be ≤ 10.00
4. If amount difference is 0.01-10.00, set has_bank_fee: true
5. If amount difference is 0.00, set has_bank_fee: false
6. Include amount_difference in match_details
7. Provide clear reasoning mentioning amount difference and partner match type

========================================
STEP-BY-STEP MATCHING PROCESS
========================================

For EACH transaction in the input:

STEP 1: Extract transaction details
- transaction_id: Get from transaction.transaction_id (starts with TXN_)
- amount: transaction.amount
- partner: transaction.partner (lowercase, normalized)
- category: transaction.category
- date: transaction.date

STEP 2: Filter candidate documents by category
- If category = "bill_payment" → Look at bills first
- If category = "invoice_receipt" → Look at invoices first

STEP 3: For each candidate document, calculate match score
- Partner similarity (0-100)
- Amount difference (absolute value)
- Date difference (days)

STEP 4: Apply matching rules (PRIORITY 1, 2, 3 above)
- If EXACT partner + amount ≤ €10 → MUST MATCH
- If SUBSTRING partner + amount ≤ €5 → MATCH
- If FUZZY partner + amount ≤ €2 → MATCH

STEP 5: If match found, construct match object
- transaction_id: Use exact ID from input
- document_id: Use exact ID from candidates
- match_type: "fuzzy"
- has_bank_fee: true if amount difference > 0.00
- match_details: Fill all required fields
- confidence: Based on match quality

STEP 6: If no match found, add to unmatched_transaction_ids

========================================
OUTPUT FORMAT
========================================
```json
{
  "matched": [
    {
      "transaction_id": "TXN_2025_12_15_04_59_00_10",
      "document_type": "bill",
      "document_id": "BILL_2025_12_15_04_51_45",
      "match_type": "fuzzy",
      "has_bank_fee": true,
      "match_details": {
        "amount_difference": "2.01",
        "partner_match": "exact",
        "partner_similarity": 100,
        "date_diff_days": 0,
        "reasoning": "Partner match: Cyta exact match. Amount within tolerance: €136.15 vs €134.14 (diff: €2.01, well within €10 fuzzy limit). Same date."
      },
      "confidence": "MEDIUM"
    },
    {
      "transaction_id": "TXN_2025_12_15_04_59_00_11",
      "document_type": "bill",
      "document_id": "BILL_2025_12_15_04_53_07",
      "match_type": "fuzzy",
      "has_bank_fee": true,
      "match_details": {
        "amount_difference": "0.14",
        "partner_match": "exact",
        "partner_similarity": 100,
        "date_diff_days": 0,
        "reasoning": "Exact partner match: Epic Ltd. Amount within tolerance: €30.99 vs €31.13 (diff: €0.14, tiny difference). Same date."
      },
      "confidence": "MEDIUM"
    }
  ],
  "unmatched_transaction_ids": ["TXN_2025_12_15_04_56_41_5", "TXN_2025_12_15_04_58_59_1"]
}
```

========================================
CRITICAL VALIDATION BEFORE RETURNING
========================================

Before you return your response, CHECK EVERY MATCH:

1. Does transaction_id start with "TXN_"? ✓ or ✗
2. Does document_id start with "BILL_" or "INV_"? ✓ or ✗
3. Does transaction_id exist in the input transactions? ✓ or ✗
4. Does document_id exist in the input candidates? ✓ or ✗
5. Is has_bank_fee set correctly (true if diff > 0.00, false if diff = 0.00)? ✓ or ✗

If ANY check fails, DO NOT include that match. Add the transaction_id to unmatched_transaction_ids instead.

========================================
EXAMPLES
========================================

Example 1: Small Difference with Exact Partner (€0.14) - MUST MATCH
Input:
```json
{
  "transaction": {
    "transaction_id": "TXN_2025_12_15_04_59_00_11",
    "amount": "30.99",
    "partner": "Epic Ltd",
    "date": "2025-06-30",
    "category": "bill_payment"
  },
  "candidates": {
    "bills": [
      {
        "id": "BILL_2025_12_15_04_53_07",
        "amount": "31.13",
        "partner": "epic ltd",
        "date": "2025-06-30"
      }
    ]
  }
}
```

Output:
```json
{
  "matched": [
    {
      "transaction_id": "TXN_2025_12_15_04_59_00_11",
      "document_type": "bill",
      "document_id": "BILL_2025_12_15_04_53_07",
      "match_type": "fuzzy",
      "has_bank_fee": true,
      "match_details": {
        "amount_difference": "0.14",
        "partner_match": "exact",
        "partner_similarity": 100,
        "date_diff_days": 0,
        "reasoning": "EXACT partner match (Epic Ltd = epic ltd). Amount within tolerance: €30.99 vs €31.13 (diff: €0.14, tiny rounding difference). Same date. Clear match."
      },
      "confidence": "MEDIUM"
    }
  ],
  "unmatched_transaction_ids": []
}
```

**Why this MUST match:**
- ✅ Partner names MATCH (after normalization): "Epic Ltd" = "epic ltd"
- ✅ Amount difference €0.14 is TINY (well within both €5 bank fee and €10 fuzzy tolerances)
- ✅ Same date
- ✅ Likely a rounding adjustment or small processing fee
- ❌ No reason to reject

Example 2: CRITICAL - Exact Partner with €2.01 Difference - MUST MATCH!
Input:
```json
{
  "transaction": {
    "transaction_id": "TXN_2025_12_15_04_59_00_10",
    "amount": "136.15",
    "partner": "Cyta",
    "date": "2025-06-30",
    "category": "bill_payment"
  },
  "candidates": {
    "bills": [
      {
        "id": "BILL_2025_12_15_04_51_45",
        "amount": "134.14",
        "partner": "Cyta",
        "date": "2025-06-30"
      }
    ]
  }
}
```

Output:
```json
{
  "matched": [
    {
      "transaction_id": "TXN_2025_12_15_04_59_00_10",
      "document_type": "bill",
      "document_id": "BILL_2025_12_15_04_51_45",
      "match_type": "fuzzy",
      "has_bank_fee": true,
      "match_details": {
        "amount_difference": "2.01",
        "partner_match": "exact",
        "partner_similarity": 100,
        "date_diff_days": 0,
        "reasoning": "EXACT partner match (Cyta = Cyta). Amount within tolerance: €136.15 vs €134.14 (diff: €2.01, well within €10 fuzzy limit). Same date. This is a clear match with a small bank fee or payment processing charge."
      },
      "confidence": "MEDIUM"
    }
  ],
  "unmatched_transaction_ids": []
}
```

**Why this MUST match:**
- ✅ Partner names are IDENTICAL: "Cyta" = "Cyta"
- ✅ Amount difference €2.01 is WELL WITHIN €10 fuzzy tolerance
- ✅ Same date (2025-06-30)
- ✅ This is a textbook case of a small payment processing fee or bank charge
- ❌ There is NO reason to reject this match

**Remember:** €2.01 is only 1.5% of the bill amount. This is a clear match with a minor fee.

Example 3: Large Difference - DO NOT MATCH
Input:
```json
{
  "transaction": {
    "transaction_id": "TXN_2025_12_15_04_59_00_12",
    "amount": "118.89",
    "partner": "Epic Ltd",
    "date": "2025-06-30",
    "category": "bill_payment"
  },
  "candidates": {
    "bills": [
      {
        "id": "BILL_2025_12_15_04_52_29",
        "amount": "144.43",
        "partner": "epic ltd",
        "date": "2025-06-30"
      }
    ]
  }
}
```

Output:
```json
{
  "matched": [],
  "unmatched_transaction_ids": ["TXN_2025_12_15_04_59_00_12"]
}
```

**Why NOT match:**
- ✅ Partner names match (Epic Ltd = epic ltd)
- ❌ Amount difference €25.54 EXCEEDS €10 fuzzy tolerance
- ✅ Same date
- **Conclusion:** While partner matches, the amount difference is too large. This is likely a partial payment or payment for a different bill entirely. Do not match.
"""

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
    """Executes LLM agents with retry logic, batching support, and validation."""
    
    def __init__(self, config=None):
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
        """Execute an agent with retry, temperature jitter, and validation."""
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
                
                # ✅ NEW: Log raw response for debugging
                logger.debug(f"[{agent_name}] Raw response length: {len(result_text)} chars")
                if len(result_text) < 500:
                    logger.debug(f"[{agent_name}] Raw response: {result_text}")
                elif len(result_text) < 2000:
                    logger.debug(f"[{agent_name}] Raw response preview: {result_text[:500]}...")
                
                # Extract JSON
                if result_json := self._extract_json(result_text):
                    # ✅ NEW: Validate response structure
                    if self._validate_agent_response(agent_name, result_json):
                        logger.info(f"[{agent_name}] ✓ Success")
                        return {"success": True, "result": result_json}
                    else:
                        logger.warning(f"[{agent_name}] Response validation failed, retrying...")
                        # ✅ NEW: Log what was wrong
                        logger.debug(f"[{agent_name}] Invalid response structure: {list(result_json.keys())}")
                else:
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
    
    # ✅ NEW: Validate agent responses
    def _validate_agent_response(self, agent_name: str, response: Dict) -> bool:
        """
        Validate that the agent response has the expected structure.
        This prevents accepting incomplete or malformed responses.
        """
        if agent_name == "DataEnrichment":
            # Must have enriched_transactions array
            if "enriched_transactions" not in response:
                logger.error("DataEnrichment response missing 'enriched_transactions' field")
                return False
            if not isinstance(response["enriched_transactions"], list):
                logger.error("'enriched_transactions' must be a list")
                return False
            # Must have other enrichment arrays
            required_fields = ["enriched_bills", "enriched_invoices", "enrichment_summary"]
            for field in required_fields:
                if field not in response:
                    logger.warning(f"DataEnrichment response missing '{field}' field (will use default)")
            return True
        
        elif agent_name == "DuplicateDetection":
            # Must have duplicate_pairs and non_duplicate_transaction_ids
            if "duplicate_pairs" not in response:
                logger.error("DuplicateDetection response missing 'duplicate_pairs' field")
                return False
            if "non_duplicate_transaction_ids" not in response:
                logger.error("DuplicateDetection response missing 'non_duplicate_transaction_ids' field")
                return False
            if not isinstance(response["duplicate_pairs"], list):
                logger.error("'duplicate_pairs' must be a list")
                return False
            if not isinstance(response["non_duplicate_transaction_ids"], list):
                logger.error("'non_duplicate_transaction_ids' must be a list")
                return False
            return True
        
        elif agent_name in ["ExactMatch", "PartnerResolution", "SuspenseResolution", "CombinationMatch"]:
            # Must have matched and unmatched_transaction_ids
            if "matched" not in response:
                logger.error(f"{agent_name} response missing 'matched' field")
                return False
            if "unmatched_transaction_ids" not in response:
                logger.error(f"{agent_name} response missing 'unmatched_transaction_ids' field")
                return False
            if not isinstance(response["matched"], list):
                logger.error("'matched' must be a list")
                return False
            if not isinstance(response["unmatched_transaction_ids"], list):
                logger.error("'unmatched_transaction_ids' must be a list")
                return False
            return True
        
        elif agent_name == "ContextAnalysis":
            if "context_analysis" not in response:
                logger.error("ContextAnalysis response missing 'context_analysis' field")
                return False
            return True
        
        elif agent_name == "Validation":
            if "validated_matches" not in response:
                logger.error("Validation response missing 'validated_matches' field")
                return False
            return True
        
        elif agent_name == "ConfidenceScoring":
            if "scored_matches" not in response:
                logger.error("ConfidenceScoring response missing 'scored_matches' field")
                return False
            return True
        
        # For other agents, accept any dict
        return True
    
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
    """
    Run Data Enrichment Agent with Python tool support.
    
    Agent orchestrates the enrichment by "calling" Python tools.
    Since we don't have real tool-calling yet, we simulate by:
    1. Calling Python enrichment directly
    2. Wrapping in agent-style response format
    
    Future: When tool calling is available, agent will actually call these tools.
    """
    try:
        logger.info("Running enrichment agent with Python tools...")
        
        # SIMULATE TOOL CALLING:
        # In real tool-calling, the agent would request tool calls
        # For now, we call Python directly and format as if agent did it
        
        enriched_txns = []
        suspense_count = 0
        internal_transfer_count = 0
        
        # "Agent calls enrich_transaction_python for each transaction"
        for txn in input_data.get("bank_transactions", []):
            enriched = enrich_transaction_python(txn)
            enriched_txns.append(enriched)
            
            if enriched["is_suspense"]:
                suspense_count += 1
            if enriched["is_internal_transfer"]:
                internal_transfer_count += 1
        
        # "Agent calls enrich_document_python for each document"
        enriched_bills = [
            enrich_document_python(doc, "bill") 
            for doc in input_data.get("bills", [])
        ]
        
        enriched_invoices = [
            enrich_document_python(doc, "invoice")
            for doc in input_data.get("invoices", [])
        ]
        
        enriched_credit_notes = [
            enrich_document_python(doc, "credit_note")
            for doc in input_data.get("credit_notes", [])
        ]
        
        enriched_payroll = [
            enrich_document_python(doc, "payroll")
            for doc in input_data.get("payroll_transactions", [])
        ]
        
        enriched_shares = [
            enrich_document_python(doc, "share")
            for doc in input_data.get("share_transactions", [])
        ]
        
        # Format as agent response
        result = {
            "enriched_transactions": enriched_txns,
            "enriched_bills": enriched_bills,
            "enriched_invoices": enriched_invoices,
            "enriched_credit_notes": enriched_credit_notes,
            "enriched_payroll": enriched_payroll,
            "enriched_shares": enriched_shares,
            "enrichment_summary": {
                "transactions_processed": len(enriched_txns),
                "suspense_count": suspense_count,
                "internal_transfer_count": internal_transfer_count
            }
        }
        
        # Validate
        input_txn_count = len(input_data.get("bank_transactions", []))
        if input_txn_count > 0 and len(enriched_txns) == 0:
            return {"success": False, "error": "Enrichment failed - 0 transactions processed"}
        
        # Log summary
        logger.info("=" * 70)
        logger.info("DATA ENRICHMENT - SUMMARY:")
        logger.info(f"  Input transactions: {input_txn_count}")
        logger.info(f"  Enriched transactions: {len(enriched_txns)}")
        logger.info(f"  Suspense: {suspense_count}, Internal transfers: {internal_transfer_count}")
        logger.info("=" * 70)
        
        if suspense_count > 0:
            logger.info("SUSPENSE TRANSACTIONS:")
            for txn in enriched_txns:
                if txn.get("is_suspense"):
                    logger.info(f"  ✓ {txn['transaction_id']}: {txn['partner_name']}")
            logger.info("=" * 70)
        
        return {"success": True, "result": result}
        
    except Exception as e:
        logger.error(f"Enrichment error: {e}")
        return {"success": False, "error": str(e)}

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
    config: MatchingConfig = DEFAULT_CONFIG,
    state: MatchingState = None  # ADDED: state parameter for tracking
) -> Dict:
    """
    Run Exact Match Agent with BATCHED processing.
    Processes transactions in small batches to prevent context explosion.
    FIXED: Now tracks matched documents across batches to prevent duplicate matching.
    """
    all_matched = []
    all_unmatched_ids = []
    batch_size = config.batch_size
    
    # ADDED: Track matched documents across batches
    matched_doc_ids = {k: set() for k in ['bill', 'invoice', 'credit_note', 'payroll', 'share']}
    
    logger.info(f"Processing {len(transactions)} transactions in batches of {batch_size}")
    
    for i in range(0, len(transactions), batch_size):
        batch = transactions[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(transactions) + batch_size - 1) // batch_size
        
        logger.info(f"  Batch {batch_num}/{total_batches}: {len(batch)} transactions")
        
        # Prepare batch data - FILTER OUT ALREADY MATCHED DOCUMENTS
        batch_data = []
        for txn in batch:
            filtered = filter_candidate_documents(txn, documents, config)
            
            # ADDED: REMOVE ALREADY MATCHED DOCUMENTS FROM CANDIDATES
            filtered_available = {}
            for doc_type, docs_list in filtered.items():
                doc_type_key = doc_type.rstrip('s') if doc_type.endswith('s') else doc_type
                filtered_available[doc_type] = [
                    doc for doc in docs_list
                    if str(doc.get(f"{doc_type_key}_id") or doc.get("id")) not in matched_doc_ids.get(doc_type_key, set())
                ]
            
            minified_docs = minify_documents_dict(filtered_available, config.max_candidates_per_txn)
            
            batch_data.append({
                "transaction": minify_transaction(txn),
                "candidates": minified_docs
            })
        
        user_message = f"""Match these {len(batch)} transactions:

{safe_json_dumps(batch_data)}

Return matches and unmatched IDs."""

        result = executor.execute("ExactMatch", EXACT_MATCH_PROMPT, user_message)
        
        if result["success"]:
            batch_matches = result["result"].get("matched", [])
            all_matched.extend(batch_matches)
            all_unmatched_ids.extend(result["result"].get("unmatched_transaction_ids", []))
            
            # ADDED: UPDATE MATCHED DOCUMENT IDS FOR NEXT BATCH
            for match in batch_matches:
                doc_type = (match.get("document_type") or "bill").lower()
                doc_type_key = doc_type.rstrip('s') if doc_type.endswith('s') else doc_type
                if doc_type_key not in matched_doc_ids:
                    doc_type_key = 'bill'
                
                if doc_id := match.get("document_id"):
                    matched_doc_ids[doc_type_key].add(str(doc_id))
                    logger.debug(f"  Marked {doc_type}:{doc_id} as matched in batch {batch_num}")
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
        exact_result = run_exact_match_batched(executor, non_dup_txns, all_docs, config, state)
        
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
            
            # DEBUG: Log what the LLM returned
            logger.info(f"Confidence scoring returned {len(scored)} scored matches")
            for s in scored:
                if s.get("transaction_ids"):
                    logger.info(f"  Scored combination: {s.get('transaction_ids')} → confidence={s.get('confidence_level')}")
            
            # Merge scores back - handle BOTH single and combination matches
            merge_failures = []
            for match in validated:
                # Find the corresponding scored match
                scored_match = None
                match_key = None
                
                # Try matching by transaction_id (single matches, batch payments)
                if tid := match.get("transaction_id"):
                    match_key = f"transaction_id={tid}"
                    scored_match = next(
                        (s for s in scored if s.get("transaction_id") == tid),
                        None
                    )
                
                # Try matching by transaction_ids (split payments)
                if not scored_match and (tids := match.get("transaction_ids")):
                    match_key = f"transaction_ids={tids}"
                    # Convert to sets of strings for comparison
                    tids_set = set(str(t) for t in tids)
                    scored_match = next(
                        (s for s in scored 
                        if set(str(t) for t in s.get("transaction_ids", [])) == tids_set),
                        None
                    )
                
                # Merge the confidence fields if found
                if scored_match:
                    match["confidence_level"] = scored_match.get("confidence_level", "LOW")
                    match["confidence_score"] = scored_match.get("confidence_score", 50.0)
                    match["recommendation"] = scored_match.get("recommendation", "MANUAL")
                    logger.debug(f"  Merged confidence for {match_key}")
                else:
                    # Track failures
                    merge_failures.append({
                        "match_type": match.get("match_type"),
                        "key": match_key,
                        "has_tid": bool(match.get("transaction_id")),
                        "has_tids": bool(match.get("transaction_ids"))
                    })
                    # Set defaults for unscored matches
                    match["confidence_level"] = "LOW"
                    match["confidence_score"] = 50.0
                    match["recommendation"] = "MANUAL"
            
            # Log merge failures
            if merge_failures:
                logger.warning(f"Failed to merge confidence for {len(merge_failures)} matches:")
                for f in merge_failures:
                    logger.warning(f"  {f}")
            
            # Count levels
            for m in validated:
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