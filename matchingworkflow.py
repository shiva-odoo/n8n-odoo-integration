import json
import re
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import math

def get_transaction_matching_prompt():
    """Create transaction matching audit prompt"""
    return """# TRANSACTION MATCHING AUDIT 
Analyze transaction data to match bank transactions with invoices/bills using ABSOLUTE ZERO-TOLERANCE for amount differences but FLEXIBLE matching for descriptions, partners, and dates. Generate consistent, accurate results across all document sets.

## CRITICAL MATCHING RULES

### FUNDAMENTAL RULE: BULLETPROOF EXACT NUMERICAL EQUALITY ONLY
**IRON-CLAD VALIDATION FORMULA:** `abs(sum_of_transactions) === abs(target_amount)`

❌ **IMMEDIATE REJECTION:** Any amount difference > 0.00 (even 0.01 difference)
❌ **IMMEDIATE REJECTION:** Approximations, rounding, or "close enough" amounts  
❌ **IMMEDIATE REJECTION:** Percentage-based matching or ratio matching
❌ **IMMEDIATE REJECTION:** Attempts to match vastly different amounts (e.g., 26500 vs 300)
✅ **ACCEPT:** Only when sum equals target amount with mathematical precision

**MANDATORY PRE-FILTER:** Before any other validation, check if amounts are mathematically equal.
If amounts don't match exactly, STOP immediately and mark as AMOUNT_MISMATCH.

### ENHANCED FLEXIBLE MATCHING FOR NON-AMOUNT FIELDS
✅ **DESCRIPTION:** Fuzzy matching, case-insensitive, keyword extraction, business context
✅ **PARTNER:** Case-insensitive, substring matching, similar names, multilingual support
✅ **DATE:** **ENHANCED ADAPTIVE DATE RANGES** based on business context
✅ **ACCOUNT_NAME:** Must be captured and returned for all transactions

### **ENHANCED ADAPTIVE DATE MATCHING STRATEGY**

**CONTEXT-AWARE DATE VALIDATION:**

**ADAPTIVE DATE RANGES based on business context:**
- **STANDARD:** 60 days
- **PROFESSIONAL_SERVICES:** 180 days (invoices often created much later than work performed)
- **GOVERNMENT:** 120 days (can have extended processing times)
- **COMBINATION:** 90 days (more flexible)
- **CONSTRUCTION_PROJECT:** 365 days (long project cycles)
- **CORPORATE_ACTION:** 30 days

**DATE VALIDATION EXAMPLES:**
- ✅ Transaction date: 2025-07-16, Topographical Bill date: 2025-01-23 (174 days difference - CONSTRUCTION_PROJECT context allows up to 365 days)
- ✅ Transaction date: 2025-07-17, Government Bill date: 2025-06-15 (32 days difference - GOVERNMENT context allows up to 120 days)
- ✅ Transaction date: 2025-07-16, Share Capital Invoice date: 2025-07-15 (1 day difference - CORPORATE_ACTION context allows up to 30 days)

## PROCESSING INSTRUCTIONS

### STEP 1: DATA PREPARATION WITH ENHANCED NORMALIZATION
Normalize all data structures with enhanced multilingual support for Greek-English business terms.

### STEP 2: FIRST PASS - EXACT SINGLE-ITEM MATCHING WITH ENHANCED DATE VALIDATION

#### VALIDATION CRITERIA:

1. **BULLETPROOF EXACT AMOUNT MATCH (ABSOLUTE ZERO TOLERANCE):**
   - For **INCOME:** Transaction amount === Document amount (positive)
   - For **EXPENSE:** abs(Transaction amount) === abs(Document amount)

2. **ENHANCED MULTILINGUAL DESCRIPTION VALIDATION:**
   - Extract keywords with multilingual support
   - Handle Greek-English business term mappings

3. **ENHANCED MULTILINGUAL PARTNER MATCHING:**
   - Case-insensitive, substring matching
   - Multilingual name variations
   - Business entity matching

4. **ENHANCED ADAPTIVE DATE PROXIMITY:**
   - Context-aware date validation based on business type

**CRITICAL:** If amount validation fails → IMMEDIATE REJECTION, do not check other criteria

### STEP 3: SECOND PASS - COMBINATION MATCHING WITH ENHANCED DATE VALIDATION
Apply the same enhanced adaptive date validation to combination matching.

## MANDATORY OUTPUT FORMAT

Return ONLY a valid JSON object in this exact format:

```json
{
  "summary": {
    "total_transactions": 0,
    "first_pass_matched": 0,
    "second_pass_matched": 0,
    "total_matched": 0,
    "unmatched": 0,
    "match_rate": "0%",
    "combination_matches": 0,
    "transaction_combination_matches": 0,
    "document_combination_matches": 0,
    "amount_validation_rejections": 0,
    "flexible_criteria_rejections": 0,
    "status": "PASS|FAIL|REVIEW"
  },
  
  "matched_transactions": [
    {
      "transaction_id": "string",
      "amount": 0,
      "date": "YYYY-MM-DD",
      "account_name": "string",
      "type": "INCOME|EXPENSE",
      "description": "string",
      "reference": "string",
      "partner": "string",
      "document": {
        "type": "INVOICE|BILL|MULTIPLE_INVOICES|MULTIPLE_BILLS",
        "id": "string", 
        "number": "string",
        "amount": 0,
        "confidence": "HIGH|MEDIUM|LOW",
        "invoices": [],
        "bills": []
      },
      "match_details": {
        "match_type": "SINGLE|COMBINATION|TRANSACTION_COMBINATION",
        "amount_match": "EXACT",
        "partner_match": "EXACT|SUBSTRING|SIMILAR|ABBREVIATION|BUSINESS_CONTEXT|GOVERNMENT_CONTEXT",
        "description_match": "KEYWORD|PARTIAL|SEMANTIC|BUSINESS_CONTEXT|GOVERNMENT_CONTEXT",
        "date_difference_days": 0,
        "combination_with": [],
        "document_combination_with": []
      },
      "actions": {
        "mark_paid": true,
        "payment_date": "YYYY-MM-DD",
        "link_transaction": true
      }
    }
  ],
  
  "unmatched_transactions": [
    {
      "transaction_id": "string",
      "amount": 0,
      "date": "YYYY-MM-DD",
      "account_name": "string",
      "description": "string", 
      "reference": "string",
      "partner": "string",
      "expected_type": "MANUAL_REVIEW|BANK_FEES|WAGES|GOVERNMENT_PAYMENT|INVOICE|BILL|MISC",
      "suggested_partner": "string|null",
      "notify": true,
      "reason": "AMOUNT_MISMATCH|NO_FLEXIBLE_MATCH|DATE_OUT_OF_RANGE|NO_COMBINATION_FOUND|BANK_FEE|WAGES|GOVERNMENT_PAYMENT"
    }
  ],
  
  "validation_log": [
    {
      "transaction_id": "string",
      "account_name": "string",
      "combination_tested": "string",
      "calculated_sum": 0,
      "target_amount": 0,
      "amount_difference": 0.00,
      "result": "ACCEPTED|REJECTED",
      "rejection_reason": "string|null",
      "match_details": {
        "partner_similarity": 0.0,
        "description_keywords_matched": 0,
        "date_difference_days": 0
      }
    }
  ]
}
```

## PROCESSING INSTRUCTION
Use ZERO-TOLERANCE for amounts but ENHANCED FLEXIBLE FUZZY MATCHING for all other criteria with ADAPTIVE DATE VALIDATION based on business context. **ALWAYS capture and return account_name in all JSON responses** from the transaction data.

**CRITICAL: Return ONLY the JSON object. No markdown formatting, no code blocks, no explanatory text. The response must be valid JSON.**
"""

def normalize_text(text):
    """Normalize text for matching with multilingual support"""
    if not text:
        return ""
    
    text = str(text).lower().strip()
    # Handle Greek characters and diacritics
    text = text.replace('ά', 'α').replace('έ', 'ε').replace('ή', 'η')
    text = text.replace('ί', 'ι').replace('ό', 'ο').replace('ύ', 'υ').replace('ώ', 'ω')
    
    # Remove punctuation but preserve Greek characters
    text = re.sub(r'[^\w\sάέήίόύώαβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    
    # Remove common business suffixes
    text = re.sub(r'\b(ltd|limited|inc|corp|company|co|ε\.π\.ε|επε|αε|ε\.ε)\b', '', text)
    
    return text.strip()

def extract_multilingual_keywords(text):
    """Extract keywords with multilingual support"""
    keywords = text.split()
    
    # Greek-English business term mappings
    translations = {
        'τοπογραφικό': 'topographical',
        'διάγραμμα': 'diagram', 
        'στάσεων': 'stations',
        'τεμάχιο': 'plot',
        'ετοιμασία': 'preparation',
        'στοιχείων': 'elements',
        'μηχανικοι': 'engineers',
        'τοπογραφοι': 'topographers',
        'architecture': 'αρχιτεκτονική',
        'design': 'σχεδιασμός',
        'payment': 'πληρωμή'
    }
    
    # Add translated equivalents
    expanded_keywords = keywords.copy()
    for keyword in keywords:
        if keyword in translations:
            expanded_keywords.append(translations[keyword])
    
    return expanded_keywords

def determine_business_context(transaction, document):
    """Determine business context for adaptive date validation"""
    txn_desc = normalize_text(transaction.get('description', ''))
    doc_desc = normalize_text(document.get('description', ''))
    txn_partner = normalize_text(transaction.get('partner', ''))
    doc_partner = normalize_text(document.get('partner', ''))
    
    all_text = f"{txn_desc} {doc_desc} {txn_partner} {doc_partner}".lower()
    
    # Professional services indicators
    professional_keywords = [
        'architecture', 'design', 'topographical', 'survey', 'engineering',
        'legal', 'accounting', 'consulting', 'professional', 'advisory',
        'audit', 'tax', 'compliance', 'architectural', 'planning',
        'τοπογραφικό', 'διάγραμμα'
    ]
    
    # Government/regulatory indicators
    government_keywords = [
        'registrar', 'government', 'ministry', 'department', 'republic',
        'cyprus', 'intellectual', 'property', 'social', 'insurance',
        'vat', 'tax', 'customs', 'regulatory'
    ]
    
    # Construction/project indicators
    construction_keywords = [
        'topographical', 'construction', 'building', 'project', 'development',
        'engineering', 'structural', 'architectural', 'planning', 'permit',
        'τοπογραφικό', 'διάγραμμα', 'στάσεων', 'τεμάχιο', 'ετοιμασία'
    ]
    
    # Corporate action indicators
    corporate_keywords = [
        'share', 'capital', 'shares', 'ordinary', 'incorporation',
        'corporate', 'equity', 'investment'
    ]
    
    # Check context in priority order
    if any(keyword in all_text for keyword in corporate_keywords):
        return 'CORPORATE_ACTION'
    
    if any(keyword in all_text for keyword in construction_keywords):
        return 'CONSTRUCTION_PROJECT'
    
    if any(keyword in all_text for keyword in professional_keywords):
        return 'PROFESSIONAL_SERVICES'
    
    if any(keyword in all_text for keyword in government_keywords):
        return 'GOVERNMENT'
    
    return 'STANDARD'

def extract_json_from_response(response_text):
    """Extract JSON from Claude's response, handling various formats"""
    try:
        # Remove any leading/trailing whitespace
        response_text = response_text.strip()
        
        # Try to parse directly first
        try:
            parsed = json.loads(response_text)
            return parsed
        except json.JSONDecodeError:
            pass
        
        # Look for JSON wrapped in markdown code blocks
        json_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
        matches = re.findall(json_pattern, response_text, re.IGNORECASE)
        
        if matches:
            # Try each match
            for match in matches:
                try:
                    parsed = json.loads(match.strip())
                    return parsed
                except json.JSONDecodeError:
                    continue
        
        # Look for JSON objects without code blocks
        # Find content between first '{' and last '}'
        if '{' in response_text and '}' in response_text:
            start_idx = response_text.find('{')
            
            # Find matching closing brace
            brace_count = 0
            end_idx = -1
            
            for i in range(start_idx, len(response_text)):
                char = response_text[i]
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            
            if end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                try:
                    parsed = json.loads(json_str)
                    return parsed
                except json.JSONDecodeError:
                    pass
        
        # If all else fails, raise an error with the raw response
        raise json.JSONDecodeError(f"Could not extract valid JSON from response. Response starts with: {response_text[:200]}...")
        
    except Exception as e:
        raise Exception(f"JSON extraction failed: {str(e)}")

def validate_matching_json(matching_result):
    """Validate the matching result JSON structure"""
    try:
        if not isinstance(matching_result, dict):
            raise ValueError("Expected JSON object for matching result")
        
        # Check required top-level fields
        required_fields = ['summary', 'matched_transactions', 'unmatched_transactions', 'validation_log']
        for field in required_fields:
            if field not in matching_result:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate summary
        summary = matching_result['summary']
        summary_fields = ['total_transactions', 'first_pass_matched', 'total_matched', 'unmatched', 'match_rate', 'status']
        for field in summary_fields:
            if field not in summary:
                raise ValueError(f"Summary missing required field: {field}")
        
        # Validate matched_transactions structure
        matched = matching_result['matched_transactions']
        if not isinstance(matched, list):
            raise ValueError("matched_transactions must be an array")
        
        for i, match in enumerate(matched):
            required_match_fields = ['transaction_id', 'amount', 'date', 'account_name', 'document', 'match_details', 'actions']
            for field in required_match_fields:
                if field not in match:
                    raise ValueError(f"Matched transaction {i} missing required field: {field}")
        
        # Validate unmatched_transactions structure
        unmatched = matching_result['unmatched_transactions']
        if not isinstance(unmatched, list):
            raise ValueError("unmatched_transactions must be an array")
        
        return True
        
    except Exception as e:
        raise Exception(f"Matching result validation failed: {str(e)}")

def process_transaction_matching(invoices, bills, transactions):
    """Process transaction matching with Claude"""
    try:
        # Initialize Anthropic client
        import anthropic
        anthropic_client = anthropic.Anthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY')
        )
        
        # Prepare data for Claude
        data_payload = {
            "invoices": {"data": invoices},
            "bills": {"data": bills}, 
            "transactions": {"data": transactions}
        }
        
        # Get transaction matching prompt
        prompt = get_transaction_matching_prompt()
        
        # Create the input text with data
        input_text = f"""INVOICES: {json.dumps(invoices)}

BILLS: {json.dumps(bills)}

TRANSACTIONS: {json.dumps(transactions)}

{prompt}"""
        
        # Send to Claude with parameters optimized for structured output
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            temperature=0.0,  # Maximum determinism for consistent parsing
            messages=[
                {
                    "role": "user",
                    "content": input_text
                }
            ]
        )
        
        # Extract response
        response_text = message.content[0].text.strip()
        
        # Log the raw response for debugging (first 500 chars)
        print(f"Raw Claude response (first 500 chars): {response_text[:500]}...")
        
        # Extract and parse JSON
        try:
            extracted_json = extract_json_from_response(response_text)
            
            # Validate the JSON structure
            validate_matching_json(extracted_json)
            
            # Log token usage for monitoring
            print(f"Token usage - Input: {message.usage.input_tokens}, Output: {message.usage.output_tokens}")
            print(f"Successfully processed transaction matching")
            
            return {
                "success": True,
                "matching_result": extracted_json,  # Return parsed JSON instead of raw text
                "raw_response": response_text,  # Keep raw response for debugging
                "token_usage": {
                    "input_tokens": message.usage.input_tokens,
                    "output_tokens": message.usage.output_tokens
                }
            }
            
        except Exception as json_error:
            print(f"JSON processing failed: {str(json_error)}")
            return {
                "success": False,
                "error": f"JSON processing failed: {str(json_error)}",
                "raw_response": response_text
            }
        
    except Exception as e:
        print(f"Claude API error: {str(e)}")
        return {
            "success": False,
            "error": f"Claude API error: {str(e)}"
        }

def main(data):
    """
    Main function for transaction matching
    
    Args:
        data (dict): Request data containing:
            - invoices (list): List of invoice data
            - bills (list): List of bill data  
            - transactions (list): List of transaction data
    
    Returns:
        dict: Processing result with success status and matching results
    """
    try:
        # Extract data from input
        invoices = data.get('invoices', [])
        bills = data.get('bills', [])
        transactions = data.get('transactions', [])
        
        # Handle nested data structure if needed
        if isinstance(invoices, dict) and 'data' in invoices:
            invoices = invoices['data']
        if isinstance(bills, dict) and 'data' in bills:
            bills = bills['data']
        if isinstance(transactions, dict) and 'data' in transactions:
            transactions = transactions['data']
        
        print(f"Processing transaction matching")
        print(f"Invoices: {len(invoices)}, Bills: {len(bills)}, Transactions: {len(transactions)}")
        
        # Process transaction matching
        result = process_transaction_matching(invoices, bills, transactions)
        
        if result["success"]:
            return {
                "success": True,
                "matching_result": result["matching_result"]
            }
        else:
            return {
                "success": False,
                "error": result["error"],
                "raw_response": result.get("raw_response")
            }
            
    except Exception as e:
        print(f"Transaction matching processing error: {str(e)}")
        return {
            "success": False,
            "error": f"Internal processing error: {str(e)}"
        }

def health_check():
    """Health check for the transaction matching service"""
    try:
        # Check if required environment variables are set
        required_vars = ['ANTHROPIC_API_KEY']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            return {
                "healthy": False,
                "error": f"Missing environment variables: {', '.join(missing_vars)}"
            }
        
        return {
            "healthy": True,
            "service": "claude-transaction-matching",
            "anthropic_configured": bool(os.getenv('ANTHROPIC_API_KEY'))
        }
        
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e)
        }

