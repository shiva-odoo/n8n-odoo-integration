import boto3
import base64
import anthropic
import os
import json
import re

def get_bank_statement_extraction_prompt(matched_id=None):
    """Create bank statement transaction extraction prompt for financial data extraction"""
    # Use the matched_id if provided, otherwise use placeholder
    company_id_value = matched_id if matched_id is not None else "{{ $json.matched_id }}"
    
    return f"""# Bank Statement Transaction Extraction

## Task
Extract ALL transactions from bank statement text and convert each transaction into the exact JSON format required for double-entry accounting. Process every single transaction found in the statement.

## DOCUMENT TYPE DETECTION (CRITICAL FIRST STEP)
Before processing any transactions, you MUST determine the document type:

**CREDIT CARD STATEMENT**: Contains keywords like "VISA", "CREDIT CARD", "CREDIT LIMIT", trace numbers, merchant names
**BANK ACCOUNT STATEMENT**: Contains keywords like "SIGHT ACCOUNT", "CURRENT ACCOUNT", direct debits, transfers, account balances

## CHART OF ACCOUNTS (EXACT CODES AND NAMES):
**Assets:**
• 1201 - Bank (Current Account)
• 1240 - Credit card  
• 1100 - Accounts receivable
• 1260 - Suspense account

**Liabilities:**
• 2100 - Accounts payable
• 2200 - VAT control account
• 2210 - PAYE/NIC

**Income:**
• 4000 - Sales
• 4906 - Bank interest received

**Common Expenses:**
• 7000 - Gross wages
• 7100 - Rent
• 7190 - Utilities
• 7200 - Electricity
• 7300 - Car fuel & oil
• 7301 - Repairs and servicing
• 7302 - Licenses & mot's
• 7303 - Vehicle insurance
• 7400 - Traveling
• 7401 - Car hire
• 7402 - Hotels
• 7403 - Entertainment
• 7500 - Printing
• 7501 - Postage
• 7502 - Telephone
• 7503 - Internet
• 7600 - Legal fees
• 7601 - Audit and accountancy fees
• 7602 - Consultancy fees
• 7800 - Repairs and renewals
• 7900 - Bank interest paid
• 7901 - Bank charges
• 6900 - Miscellaneous expenses

## TRANSACTION PROCESSING RULES

### FOR CREDIT CARD STATEMENTS:

**Individual Credit Card Purchases (in transaction list):**
- DEBIT: Appropriate expense account (based on merchant/description)
- CREDIT: 1240 Credit card
- Partner: Extract from transaction description (merchant name)

**Credit Card Payments (typically in debit section):**
- DEBIT: 1240 Credit card
- CREDIT: 1201 Bank
- Partner for 1240: "Bank of Cyprus - Credit card"
- Partner for 1201: "Bank of Cyprus - Current A/c"

**Interest Received (in debit section, e.g., "Total Interest"):**
- DEBIT: 1201 Bank
- CREDIT: 4906 Bank interest received
- Partner for 1201: "Bank of Cyprus - Current A/c"
- Partner for 4906: Extract from description or "Bank interest"

### FOR BANK ACCOUNT STATEMENTS:

**Customer Payments (money coming in):**
- DEBIT: 1201 Bank
- CREDIT: 1100 Accounts receivable
- Partner for 1201: "Bank of Cyprus - Current A/c"
- Partner for 1100: Extract from description

**Supplier Payments (money going out to vendors):**
- DEBIT: 2100 Accounts payable
- CREDIT: 1201 Bank
- Partner for 2100: Extract from description
- Partner for 1201: "Bank of Cyprus - Current A/c"

**Tax Payments:**
- DEBIT: 2200 VAT control account
- CREDIT: 1201 Bank
- Partner for 2200: Extract from description (tax authority)
- Partner for 1201: "Bank of Cyprus - Current A/c"

**Bank Charges:**
- DEBIT: 7901 Bank charges
- CREDIT: 1201 Bank
- Partner for 7901: Extract from description
- Partner for 1201: "Bank of Cyprus - Current A/c"

**Ambiguous/Unclear Transactions:**
- DEBIT: 1260 Suspense account (for money out) OR DEBIT: 1201 Bank (for money in)
- CREDIT: 1201 Bank (for money out) OR CREDIT: 1260 Suspense account (for money in)
- Partner for 1260: "Suspense - " + brief description
- Partner for 1201: "Bank of Cyprus - Current A/c"

## EXPENSE ACCOUNT MAPPING GUIDE

**Fuel/Petrol Stations:** 7300 Car fuel & oil
**Restaurants/Food:** 7403 Entertainment
**Travel/Airlines:** 7400 Traveling
**Hotels:** 7402 Hotels
**Car Services:** 7301 Repairs and servicing
**Telecommunications:** 7502 Telephone or 7503 Internet
**Office Supplies:** 7500 Printing
**Professional Services:** 7602 Consultancy fees
**Utilities:** 7190 Utilities or 7200 Electricity
**DIY/Hardware Stores:** 7800 Repairs and renewals
**Unknown/Other:** 6900 Miscellaneous expenses

## PARTNER NAME RULES

**Fixed Partner Names:**
- 1201 Bank: "Bank of Cyprus - Current A/c"
- 1240 Credit card: "Bank of Cyprus - Credit card"

**Extracted Partner Names:**
- For all other accounts: Extract meaningful partner name from transaction description
- Remove reference numbers, codes, and bank-specific formatting
- Examples:
  - "RAMOIL AYIOS ATHANASIOS CYP" → "RAMOIL AYIOS ATHANASIOS"
  - "SUPERHOME CENTER (DIY)LTD CYP" → "SUPERHOME CENTER"
  - "TAX PAYMENT" → "Tax Authority"

## CRITICAL OUTPUT REQUIREMENTS
- Return ONLY a valid JSON array
- No markdown code blocks (no ```json```)
- No explanatory text before or after the JSON
- Start response with [ and end with ]
- Each transaction must have "partner" field in line_items

## Required Output Format
For EACH transaction found, create a JSON object with this EXACT structure:

[
  {{
    "company_id": {company_id_value},
    "date": "YYYY-MM-DD",
    "ref": "string",
    "narration": "string", 
    "partner": "string",
    "accounting_assignment": {{
      "debit_account": "1201",
      "debit_account_name": "Bank",
      "credit_account": "1100",
      "credit_account_name": "Accounts receivable",
      "transaction_type": "customer_payment",
      "requires_vat": false,
      "additional_entries": []
    }},
    "line_items": [
      {{
        "name": "Bank",
        "debit": 15000.00,
        "credit": 0.00,
        "partner": "Bank of Cyprus - Current A/c"
      }},
      {{
        "name": "Accounts receivable",
        "debit": 0.00,
        "credit": 15000.00,
        "partner": "Customer Name"
      }}
    ]
  }}
]

## Transaction Type Classification:

1. **customer_payment**: Payments received from customers
2. **supplier_payment**: Payments made to vendors/suppliers
3. **tax_payment**: Tax payments to authorities
4. **bank_charges**: Bank fees and charges
5. **credit_card_purchase**: Individual credit card transactions
6. **credit_card_payment**: Payment from bank to credit card
7. **interest_received**: Interest income
8. **suspense_entry**: Unclear/ambiguous transactions
9. **other_expense**: Direct expenses
10. **other_income**: Miscellaneous income

## Processing Instructions

1. **STEP 1: Determine document type** (Credit Card vs Bank Account)
2. **STEP 2: Extract ALL transactions** from the statement
3. **STEP 3: For each transaction, determine money flow direction**
4. **STEP 4: Apply appropriate accounting treatment based on document type**
5. **STEP 5: Map to specific expense accounts where possible**
6. **STEP 6: Use suspense account for unclear transactions**
7. **STEP 7: Assign correct partner names**
8. **STEP 8: Create balanced line_items** ensuring debits = credits
9. **STEP 9: Set company_id** to `{company_id_value}` for every transaction
10. **STEP 10: Ensure all numeric values are numbers, not strings**

## Example Transactions:

### Credit Card Purchase:
```json
{{
  "company_id": {company_id_value},
  "date": "2025-05-20",
  "ref": "634069",
  "narration": "Fuel purchase at RAMOIL ANALIONTAS",
  "partner": "RAMOIL ANALIONTAS",
  "accounting_assignment": {{
    "debit_account": "7300",
    "debit_account_name": "Car fuel & oil",
    "credit_account": "1240",
    "credit_account_name": "Credit card",
    "transaction_type": "credit_card_purchase",
    "requires_vat": false,
    "additional_entries": []
  }},
  "line_items": [
    {{
      "name": "Car fuel & oil",
      "debit": 60.01,
      "credit": 0.00,
      "partner": "RAMOIL ANALIONTAS"
    }},
    {{
      "name": "Credit card",
      "debit": 0.00,
      "credit": 60.01,
      "partner": "Bank of Cyprus - Credit card"
    }}
  ]
}}
```

### Credit Card Payment:
```json
{{
  "company_id": {company_id_value},
  "date": "2025-06-04",
  "ref": "394665",
  "narration": "Credit card payment",
  "partner": "Bank of Cyprus",
  "accounting_assignment": {{
    "debit_account": "1240",
    "debit_account_name": "Credit card",
    "credit_account": "1201",
    "credit_account_name": "Bank",
    "transaction_type": "credit_card_payment",
    "requires_vat": false,
    "additional_entries": []
  }},
  "line_items": [
    {{
      "name": "Credit card",
      "debit": 112.35,
      "credit": 0.00,
      "partner": "Bank of Cyprus - Credit card"
    }},
    {{
      "name": "Bank",
      "debit": 0.00,
      "credit": 112.35,
      "partner": "Bank of Cyprus - Current A/c"
    }}
  ]
}}
```

### Bank Tax Payment:
```json
{{
  "company_id": {company_id_value},
  "date": "2025-06-19",
  "ref": "tax_payment_190625",
  "narration": "Tax payment to authorities",
  "partner": "Tax Authority",
  "accounting_assignment": {{
    "debit_account": "2200",
    "debit_account_name": "VAT control account",
    "credit_account": "1201",
    "credit_account_name": "Bank",
    "transaction_type": "tax_payment",
    "requires_vat": false,
    "additional_entries": []
  }},
  "line_items": [
    {{
      "name": "VAT control account",
      "debit": 4921.79,
      "credit": 0.00,
      "partner": "Tax Authority"
    }},
    {{
      "name": "Bank",
      "debit": 0.00,
      "credit": 4921.79,
      "partner": "Bank of Cyprus - Current A/c"
    }}
  ]
}}
```

### Suspense Entry:
```json
{{
  "company_id": {company_id_value},
  "date": "2025-06-30",
  "ref": "transfer_300625",
  "narration": "Unclear transfer - needs investigation",
  "partner": "Unknown",
  "accounting_assignment": {{
    "debit_account": "1260",
    "debit_account_name": "Suspense account",
    "credit_account": "1201",
    "credit_account_name": "Bank",
    "transaction_type": "suspense_entry",
    "requires_vat": false,
    "additional_entries": []
  }},
  "line_items": [
    {{
      "name": "Suspense account",
      "debit": 1000.00,
      "credit": 0.00,
      "partner": "Suspense - Unclear transfer"
    }},
    {{
      "name": "Bank",
      "debit": 0.00,
      "credit": 1000.00,
      "partner": "Bank of Cyprus - Current A/c"
    }}
  ]
}}
```

**CRITICAL: Return ONLY the JSON array. No markdown formatting, no code blocks, no explanatory text. The response must start with '[' and end with ']'. Every line_item must include a "partner" field.**
"""

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
        
        # Look for JSON arrays/objects without code blocks
        # Find content between first '[' and last ']'
        if '[' in response_text and ']' in response_text:
            start_idx = response_text.find('[')
            
            # Find matching closing bracket
            bracket_count = 0
            end_idx = -1
            
            for i in range(start_idx, len(response_text)):
                char = response_text[i]
                if char == '[':
                    bracket_count += 1
                elif char == ']':
                    bracket_count -= 1
                    if bracket_count == 0:
                        end_idx = i + 1
                        break
            
            if end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                try:
                    parsed = json.loads(json_str)
                    return parsed
                except json.JSONDecodeError:
                    pass
        
        # Look for JSON objects if no arrays found
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
                    # If it's a single object, wrap it in an array
                    if isinstance(parsed, dict):
                        return [parsed]
                    return parsed
                except json.JSONDecodeError:
                    pass
        
        # If all else fails, raise an error with the raw response
        raise json.JSONDecodeError(f"Could not extract valid JSON from response. Response starts with: {response_text[:200]}...")
        
    except Exception as e:
        raise Exception(f"JSON extraction failed: {str(e)}")

def validate_transaction_json(transactions):
    """Validate the extracted transaction JSON structure including accounting assignment"""
    try:
        if not isinstance(transactions, list):
            raise ValueError("Expected JSON array of transactions")
        
        # Validate account codes - Updated with new accounts
        valid_accounts = [
            "1201", "1240", "1100", "1260",  # Assets
            "2100", "2200", "2210",          # Liabilities  
            "4000", "4906",                  # Income
            "7000", "7100", "7190", "7200", "7300", "7301", "7302", "7303",  # Expenses
            "7400", "7401", "7402", "7403", "7500", "7501", "7502", "7503",
            "7600", "7601", "7602", "7800", "7900", "7901", "6900"
        ]
        
        for i, transaction in enumerate(transactions):
            if not isinstance(transaction, dict):
                raise ValueError(f"Transaction {i} is not a JSON object")
            
            # Check required fields
            required_fields = ['company_id', 'date', 'ref', 'narration', 'partner', 'accounting_assignment', 'line_items']
            for field in required_fields:
                if field not in transaction:
                    raise ValueError(f"Transaction {i} missing required field: {field}")
            
            # Validate accounting_assignment structure
            accounting = transaction['accounting_assignment']
            required_accounting_fields = ['debit_account', 'debit_account_name', 'credit_account', 'credit_account_name', 'transaction_type', 'requires_vat', 'additional_entries']
            for field in required_accounting_fields:
                if field not in accounting:
                    raise ValueError(f"Transaction {i} accounting_assignment missing field: {field}")
            
            # Validate account codes
            debit_account = accounting['debit_account']
            credit_account = accounting['credit_account']
            
            if debit_account not in valid_accounts:
                raise ValueError(f"Transaction {i} invalid debit_account: {debit_account}")
            
            if credit_account not in valid_accounts:
                raise ValueError(f"Transaction {i} invalid credit_account: {credit_account}")
            
            # Validate line_items
            line_items = transaction['line_items']
            if not isinstance(line_items, list) or len(line_items) < 2:
                raise ValueError(f"Transaction {i} must have at least 2 line items")
            
            # Validate that each line item has partner field
            for j, line_item in enumerate(line_items):
                if 'partner' not in line_item:
                    raise ValueError(f"Transaction {i}, line item {j} missing 'partner' field")
            
            # Validate double-entry balancing
            total_debits = sum(item.get('debit', 0) for item in line_items)
            total_credits = sum(item.get('credit', 0) for item in line_items)
            
            if abs(total_debits - total_credits) > 0.01:  # Allow small rounding differences
                raise ValueError(f"Transaction {i} debits ({total_debits}) don't balance with credits ({total_credits})")
        
        return True
        
    except Exception as e:
        raise Exception(f"Transaction validation failed: {str(e)}")

def ensure_transaction_structure(transaction):
    """Ensure each transaction has the complete required structure with default values"""
    
    # Define the complete structure with default values
    default_transaction = {
        "company_id": 0,
        "date": "",
        "ref": "",
        "narration": "",
        "partner": "unknown",
        "accounting_assignment": {
            "debit_account": "",
            "debit_account_name": "",
            "credit_account": "",
            "credit_account_name": "",
            "transaction_type": "",
            "requires_vat": False,
            "additional_entries": []
        },
        "line_items": []
    }
    
    def merge_with_defaults(source, defaults):
        """Recursively merge source with defaults, ensuring all fields are present"""
        if isinstance(defaults, dict):
            result = {}
            for key, default_value in defaults.items():
                if key in source and source[key] is not None:
                    if isinstance(default_value, dict):
                        result[key] = merge_with_defaults(source[key], default_value)
                    elif isinstance(default_value, list):
                        result[key] = source[key] if isinstance(source[key], list) else default_value
                    else:
                        result[key] = source[key]
                else:
                    result[key] = default_value
            return result
        else:
            return source if source is not None else defaults
    
    return merge_with_defaults(transaction, default_transaction)

def download_from_s3(s3_key, bucket_name=None):
    """Download file from S3 using key"""
    try:
        if not bucket_name:
            bucket_name = os.getenv('S3_BUCKET_NAME', 'company-documents-2025')
        
        # Initialize S3 client
        aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_region = os.getenv('AWS_REGION', 'eu-north-1')
        
        if aws_access_key and aws_secret_key:
            s3_client = boto3.client(
                's3',
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                region_name=aws_region
            )
        else:
            s3_client = boto3.client('s3', region_name=aws_region)
        
        print(f"Downloading from bucket: {bucket_name}, key: {s3_key}")
        
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        return response['Body'].read()
        
    except Exception as e:
        raise Exception(f"Error downloading from S3: {str(e)}")

def process_bank_statement_extraction(pdf_content, company_id=None):
    """Process bank statement with Claude for transaction extraction with accounting assignment"""
    try:
        # Initialize Anthropic client
        anthropic_client = anthropic.Anthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY')
        )
        
        # Encode to base64
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        
        # Get bank statement extraction prompt
        prompt = get_bank_statement_extraction_prompt(company_id)
        
        # Send to Claude with parameters optimized for structured output
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=12000,
            temperature=0.0,  # Maximum determinism for consistent parsing
            system="""You are an expert accountant specializing in bank statement analysis and double-entry bookkeeping. Your core behavior is to think and act like a professional accountant who understands document types, transaction flows, and proper account classification.

CRITICAL DOCUMENT TYPE DETECTION:
Before processing any transactions, you MUST first determine whether this is:
1. **CREDIT CARD STATEMENT**: Look for "VISA", "MASTERCARD", "CREDIT CARD", "CREDIT LIMIT", merchant names, trace numbers
2. **BANK ACCOUNT STATEMENT**: Look for "SIGHT ACCOUNT", "CURRENT ACCOUNT", direct debits, transfers, IBANs

CORE ACCOUNTING PRINCIPLES:
• Always maintain double-entry bookkeeping: debits must equal credits
• Use appropriate account codes from the provided chart of accounts
• Apply correct transaction types based on document type and transaction nature
• Extract meaningful partner names from transaction descriptions
• Use suspense accounts for unclear transactions

DOCUMENT-SPECIFIC PROCESSING:

**FOR CREDIT CARD STATEMENTS:**
• Individual purchases: DEBIT expense account, CREDIT 1240 Credit card
• Card payments: DEBIT 1240 Credit card, CREDIT 1201 Bank
• Interest received: DEBIT 1201 Bank, CREDIT 4906 Bank interest received

**FOR BANK ACCOUNT STATEMENTS:**
• Customer payments: DEBIT 1201 Bank, CREDIT 1100 Accounts receivable
• Supplier payments: DEBIT 2100 Accounts payable, CREDIT 1201 Bank  
• Tax payments: DEBIT 2200 VAT control account, CREDIT 1201 Bank
• Bank charges: DEBIT 7901 Bank charges, CREDIT 1201 Bank
• Unclear transactions: Use 1260 Suspense account

EXPENSE ACCOUNT MAPPING:
• Fuel stations → 7300 Car fuel & oil
• Restaurants → 7403 Entertainment
• Travel/Airlines → 7400 Traveling
• Hotels → 7402 Hotels
• Telecommunications → 7502 Telephone or 7503 Internet
• Professional services → 7602 Consultancy fees
• Unknown merchants → 6900 Miscellaneous expenses

PARTNER NAME ASSIGNMENT:
• 1201 Bank: Always "Bank of Cyprus - Current A/c"
• 1240 Credit card: Always "Bank of Cyprus - Credit card"
• Other accounts: Extract from transaction description, clean format

OUTPUT REQUIREMENTS:
• Return ONLY valid JSON array
• Every line_item must include "partner" field
• Ensure proper double-entry balancing
• Use exact account codes and names from chart of accounts
• Apply appropriate transaction types""",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_base64
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
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
            
            # Ensure each transaction has complete structure
            validated_transactions = []
            for transaction in extracted_json:
                validated_transaction = ensure_transaction_structure(transaction)
                validated_transactions.append(validated_transaction)
            
            # Validate the JSON structure
            validate_transaction_json(validated_transactions)
            
            # Log token usage for monitoring
            print(f"Token usage - Input: {message.usage.input_tokens}, Output: {message.usage.output_tokens}")
            print(f"Successfully extracted and validated {len(validated_transactions)} transactions")
            
            return {
                "success": True,
                "extraction_result": validated_transactions,
                "raw_response": response_text,
                "token_usage": {
                    "input_tokens": message.usage.input_tokens,
                    "output_tokens": message.usage.output_tokens
                },
                "transaction_count": len(validated_transactions)
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

def validate_accounting_assignments(transactions):
    """Validate accounting assignments for extracted transactions"""
    validation_results = []
    
    for i, transaction in enumerate(transactions):
        transaction_validation = {
            "transaction_index": i + 1,
            "issues": [],
            "warnings": [],
            "accounting_valid": True
        }
        
        accounting = transaction.get("accounting_assignment", {})
        
        # Check for proper account assignment
        debit_account = accounting.get("debit_account", "")
        credit_account = accounting.get("credit_account", "")
        transaction_type = accounting.get("transaction_type", "")
        
        # Validate account codes - Updated with new accounts
        valid_accounts = [
            "1201", "1240", "1100", "1260",  # Assets
            "2100", "2200", "2210",          # Liabilities  
            "4000", "4906",                  # Income
            "7000", "7100", "7190", "7200", "7300", "7301", "7302", "7303",  # Expenses
            "7400", "7401", "7402", "7403", "7500", "7501", "7502", "7503",
            "7600", "7601", "7602", "7800", "7900", "7901", "6900"
        ]
        
        if debit_account not in valid_accounts:
            transaction_validation["issues"].append(f"Invalid debit account code: {debit_account}")
            transaction_validation["accounting_valid"] = False
        
        if credit_account not in valid_accounts:
            transaction_validation["issues"].append(f"Invalid credit account code: {credit_account}")
            transaction_validation["accounting_valid"] = False
        
        # Check transaction type consistency
        if not transaction_type:
            transaction_validation["warnings"].append("Missing transaction type classification")
        
        # Check line items consistency with accounting assignment
        line_items = transaction.get("line_items", [])
        if len(line_items) >= 2:
            # Check if line items match accounting assignment
            debit_items = [item for item in line_items if item.get('debit', 0) > 0]
            credit_items = [item for item in line_items if item.get('credit', 0) > 0]
            
            if len(debit_items) == 0 or len(credit_items) == 0:
                transaction_validation["issues"].append("Line items don't follow double-entry principles")
            
            # Check if partner field exists in all line items
            for j, line_item in enumerate(line_items):
                if 'partner' not in line_item:
                    transaction_validation["issues"].append(f"Line item {j} missing 'partner' field")
                    transaction_validation["accounting_valid"] = False
        
        validation_results.append(transaction_validation)
    
    return validation_results

def main(data):
    """
    Main function for bank statement transaction extraction with accounting assignment
    
    Args:
        data (dict): Request data containing:
            - s3_key (str): S3 key path to the document
            - bucket_name (str, optional): S3 bucket name
            - company_id (str/int, optional): Company ID for transaction extraction
    
    Returns:
        dict: Processing result with success status and extracted data
    """
    try:
        # Validate required fields
        if 's3_key' not in data:
            return {
                "success": False,
                "error": "s3_key is required"
            }
        
        s3_key = data['s3_key']
        bucket_name = data.get('bucket_name')  # Optional
        company_id = data.get('company_id')  # For bank statement extraction
        
        print(f"Processing bank statement for transaction extraction with accounting assignment")
        print(f"S3 key: {s3_key}")
        print(f"Company ID: {company_id}")
        
        # Download PDF from S3
        pdf_content = download_from_s3(s3_key, bucket_name)
        print(f"Downloaded PDF, size: {len(pdf_content)} bytes")
        
        # Process bank statement for transaction extraction
        result = process_bank_statement_extraction(pdf_content, company_id)
        
        if result["success"]:
            transactions = result["extraction_result"]
            
            # Validate accounting assignments
            validation_results = validate_accounting_assignments(transactions)
            
            # Count transactions with issues
            transactions_with_issues = sum(1 for v in validation_results if not v["accounting_valid"])
            total_transactions = len(transactions)
            
            return {
                "success": True,
                "total_transactions": total_transactions,
                "transactions": transactions,
                "processing_summary": {
                    "transactions_processed": total_transactions,
                    "transactions_with_issues": transactions_with_issues,
                    "success_rate": f"{((total_transactions - transactions_with_issues) / total_transactions * 100):.1f}%" if total_transactions > 0 else "0%"
                },
                "validation_results": validation_results,
                "metadata": {
                    "company_id": company_id,
                    "s3_key": s3_key,
                    "token_usage": result["token_usage"]
                }
            }
        else:
            return {
                "success": False,
                "error": result["error"],
                "raw_response": result.get("raw_response")
            }
            
    except Exception as e:
        print(f"Bank statement processing error: {str(e)}")
        return {
            "success": False,
            "error": f"Internal processing error: {str(e)}"
        }

def health_check():
    """Health check for the bank statement processing service"""
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
            "service": "claude-bank-statement-extraction",
            "version": "2.0",
            "capabilities": [
                "document_type_detection",
                "credit_card_transaction_processing",
                "bank_account_transaction_processing",
                "transaction_extraction",
                "accounting_assignment",
                "double_entry_validation",
                "transaction_classification",
                "partner_name_extraction",
                "suspense_account_handling",
                "structured_json_output"
            ],
            "supported_document_types": [
                "credit_card_statements",
                "bank_account_statements"
            ],
            "account_types": [
                "1201_bank_current",
                "1240_credit_card",
                "1100_accounts_receivable",
                "1260_suspense_account",
                "2100_accounts_payable",
                "2200_vat_control_account",
                "expense_accounts_7xxx",
                "income_accounts_4xxx"
            ],
            "anthropic_configured": bool(os.getenv('ANTHROPIC_API_KEY')),
            "aws_configured": bool(os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY')),
            "s3_bucket": os.getenv('S3_BUCKET_NAME', 'company-documents-2025')
        }
        
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e)
        }

# Example usage for testing
if __name__ == "__main__":
    # Test the JSON extraction function with new structure including partner fields
    test_response = '''[
  {
    "company_id": 123,
    "date": "2025-05-20",
    "ref": "634069",
    "narration": "Fuel purchase at RAMOIL ANALIONTAS",
    "partner": "RAMOIL ANALIONTAS",
    "accounting_assignment": {
      "debit_account": "7300",
      "debit_account_name": "Car fuel & oil",
      "credit_account": "1240",
      "credit_account_name": "Credit card",
      "transaction_type": "credit_card_purchase",
      "requires_vat": false,
      "additional_entries": []
    },
    "line_items": [
      {
        "name": "Car fuel & oil",
        "debit": 60.01,
        "credit": 0.00,
        "partner": "RAMOIL ANALIONTAS"
      },
      {
        "name": "Credit card",
        "debit": 0.00,
        "credit": 60.01,
        "partner": "Bank of Cyprus - Credit card"
      }
    ]
  }
]'''
    
    try:
        result = extract_json_from_response(test_response)
        print("JSON extraction test successful:")
        print(json.dumps(result, indent=2))
        
        validate_transaction_json(result)
        print("Validation test successful!")
        
        # Test accounting validation
        validation_results = validate_accounting_assignments(result)
        print("Accounting validation results:")
        for validation in validation_results:
            print(f"Transaction {validation['transaction_index']}: {'Valid' if validation['accounting_valid'] else 'Invalid'}")
            if validation['issues']:
                print(f"  Issues: {validation['issues']}")
            if validation['warnings']:
                print(f"  Warnings: {validation['warnings']}")
        
    except Exception as e:
        print(f"Test failed: {str(e)}")