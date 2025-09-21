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

## INPUT ANALYSIS
You will receive bank statement text. Extract:
1. **Bank Information**: Bank name, account holder, account number
2. **All Transactions**: Date, description, amounts, references, transaction type
3. **Currency Information**: Identify the currency used in transactions

## CRITICAL OUTPUT REQUIREMENTS
- Return ONLY a valid JSON array
- No markdown code blocks (no ```json```)
- No explanatory text before or after the JSON
- No comments or additional formatting
- Start response with [ and end with ]
- Ensure valid JSON syntax with proper escaping
- All string values must be properly escaped (quotes, backslashes, etc.)

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
      "debit_account": "1204",
      "debit_account_name": "Bank",
      "credit_account": "3000",
      "credit_account_name": "Share Capital",
      "transaction_type": "share_capital_receipt",
      "requires_vat": false,
      "additional_entries": []
    }},
    "line_items": [
      {{
        "name": "Bank",
        "debit": 15000.00,
        "credit": 0.00
      }},
      {{
        "name": "Share Capital",
        "debit": 0.00,
        "credit": 15000.00
      }}
    ]
  }}
]

## Accounting Assignment Rules

### Transaction Type Classification:
1. **share_capital_receipt**: Share capital payments, capital increases
   - DEBIT: 1204 (Bank), CREDIT: 3000 (Share Capital)

2. **customer_payment**: Payments received from customers
   - DEBIT: 1204 (Bank), CREDIT: 1100 (Accounts receivable)

3. **supplier_payment**: Payments made to suppliers/vendors
   - DEBIT: 2100 (Accounts payable), CREDIT: 1204 (Bank)

4. **consultancy_payment**: Payments for consultancy services
   - DEBIT: 6200 (Consultancy fees), CREDIT: 1204 (Bank)

5. **bank_charges**: Bank fees and charges
   - DEBIT: 7901 (Bank charges), CREDIT: 1204 (Bank)

6. **other_expense**: Government fees, registrar fees, etc.
   - DEBIT: 8200 (Other non-operating income or expenses), CREDIT: 1204 (Bank)

7. **other_income**: Reimbursements, miscellaneous income
   - DEBIT: 1204 (Bank), CREDIT: 8200 (Other non-operating income or expenses)

### Transaction Pattern Recognition:

**Share Capital Indicators:**
- "share capital", "capital increase", "new share capital"
- "shareholder investment", "equity injection"
- DEBIT: 1204 (Bank), CREDIT: 3000 (Share Capital)

**Supplier/Vendor Payment Indicators:**
- "payment to [vendor name]", "invoice payment"
- Specific vendor names (Architecture Design, Hadjioikonomou, etc.)
- DEBIT: 2100 (Accounts payable), CREDIT: 1204 (Bank)

**Consultancy Payment Indicators:**
- "consultancy", "professional services", "design services"
- "architecture", "engineering", "advisory"
- DEBIT: 6200 (Consultancy fees), CREDIT: 1204 (Bank)

**Bank Charges Indicators:**
- "bank fee", "card fee", "membership fee", "maintenance fee"
- "commission", "service charge"
- DEBIT: 7901 (Bank charges), CREDIT: 1204 (Bank)

**Government/Registrar Fee Indicators:**
- "registrar", "government fee", "license fee"
- "regulatory fee", "filing fee"
- DEBIT: 8200 (Other non-operating income or expenses), CREDIT: 1204 (Bank)

**Reimbursement Indicators:**
- "reimbursement", "refund received"
- DEBIT: 1204 (Bank), CREDIT: 8200 (Other non-operating income or expenses)

## Field Generation Rules

### Standard Fields
- **company_id**: Always set to `{company_id_value}` (as number, not string)
- **date**: Convert to YYYY-MM-DD format (string)
- **ref**: Use actual transaction reference if available, otherwise generate from description (string)
- **narration**: Clean, business-friendly description of the transaction (string)
- **partner**: Use the actual partner/counterparty name if found. If no partner name found, set to "unknown"

### Accounting Assignment Fields
- **debit_account**: Account code being debited (string)
- **debit_account_name**: Full name of debit account (string)
- **credit_account**: Account code being credited (string)
- **credit_account_name**: Full name of credit account (string)
- **transaction_type**: Classification of transaction type (string)
- **requires_vat**: Whether transaction involves VAT (boolean)
- **additional_entries**: Array for complex transactions requiring multiple entries (array)

### Reference (ref) Generation Rules

**Priority 1 - Use Actual Transaction Reference:**
- Look for transaction references, reference numbers, or unique identifiers
- Use the exact reference as provided (e.g., "255492965", "TXN123456", "REF789")

**Priority 2 - Generate from Description:**
- Create unique reference using transaction description
- Convert to lowercase, replace spaces with underscores
- Remove special characters except underscores and numbers
- Examples:
  - "FEE REGISTRAR COMPANIES" → "fee_registrar_companies"
  - "CARD PYT SUPERMARKET XYZ" → "card_pyt_supermarket_xyz"

### Narration Rules
- Remove internal bank reference numbers and codes
- Make descriptions business-friendly and readable
- Keep essential information like payee names, purpose
- Examples:
  - "FEE REGISTRAR COMPANIES REF:12345" → "Registrar of companies fee"
  - "TRF TO JOHN SMITH REF:ABC123" → "Transfer to John Smith"

## Line Items Rules

### For Money LEAVING the Bank Account (Outgoing payments):
```json
"line_items": [
  {{
    "name": "{{Expense/Asset Account Name}}",
    "debit": {{amount}},
    "credit": 0.00
  }},
  {{
    "name": "Bank",
    "debit": 0.00,
    "credit": {{amount}}
  }}
]
```

### For Money ENTERING the Bank Account (Incoming payments):
```json
"line_items": [
  {{
    "name": "Bank",
    "debit": {{amount}},
    "credit": 0.00
  }},
  {{
    "name": "{{Revenue/Liability Account Name}}",
    "debit": 0.00,
    "credit": {{amount}}
  }}
]
```

## Processing Instructions

1. **Extract ALL transactions** from the statement (both inflows and outflows)
2. **Classify each transaction** using the pattern recognition rules
3. **Assign correct debit/credit accounts** based on transaction type
4. **Generate appropriate accounting_assignment** object
5. **Create balanced line_items** ensuring debits = credits
6. **Clean descriptions** and create business-friendly narrations
7. **Set company_id** to `{company_id_value}` for every transaction
8. **Ensure all numeric values are numbers, not strings**
9. **Use ONLY the account codes and names from the chart of accounts**

## Example Transactions:

### Share Capital Receipt:
```json
{{
  "company_id": {company_id_value},
  "date": "2025-07-16",
  "ref": "255492965",
  "narration": "New Share Capital of Kyrastel Investments Ltd - Bank Credit Advice",
  "partner": "Kyrastel Investments Ltd",
  "accounting_assignment": {{
    "debit_account": "1204",
    "debit_account_name": "Bank",
    "credit_account": "3000",
    "credit_account_name": "Share Capital",
    "transaction_type": "share_capital_receipt",
    "requires_vat": false,
    "additional_entries": []
  }},
  "line_items": [
    {{
      "name": "Bank",
      "debit": 15000.00,
      "credit": 0.00
    }},
    {{
      "name": "Share Capital",
      "debit": 0.00,
      "credit": 15000.00
    }}
  ]
}}
```

### Consultancy/Professional Service Payment:
```json
{{
  "company_id": {company_id_value},
  "date": "2025-07-18",
  "ref": "255634959",
  "narration": "Payment to Architecture Design - Andreas Spanos, Invoice 621467",
  "partner": "Architecture Design Andreas Spanos",
  "accounting_assignment": {{
    "debit_account": "7602",
    "debit_account_name": "Consultancy fees",
    "credit_account": "1204",
    "credit_account_name": "Bank",
    "transaction_type": "consultancy_payment",
    "requires_vat": false,
    "additional_entries": []
  }},
  "line_items": [
    {{
      "name": "Consultancy fees",
      "debit": 400.00,
      "credit": 0.00
    }},
    {{
      "name": "Bank",
      "debit": 0.00,
      "credit": 400.00
    }}
  ]
}}
```

### Supplier Payment (for goods/equipment):
```json
{{
  "company_id": {company_id_value},
  "date": "2025-07-18",
  "ref": "supplier_payment_001",
  "narration": "Payment for office equipment purchase",
  "partner": "Office Supplies Ltd",
  "accounting_assignment": {{
    "debit_account": "2100",
    "debit_account_name": "Accounts payable",
    "credit_account": "1204",
    "credit_account_name": "Bank",
    "transaction_type": "supplier_payment",
    "requires_vat": false,
    "additional_entries": []
  }},
  "line_items": [
    {{
      "name": "Accounts payable",
      "debit": 400.00,
      "credit": 0.00
    }},
    {{
      "name": "Bank",
      "debit": 0.00,
      "credit": 400.00
    }}
  ]
}}
```

### Bank Charges:
```json
{{
  "company_id": {company_id_value},
  "date": "2025-07-15",
  "ref": "bank_card_fee",
  "narration": "Card membership fee",
  "partner": "Bank of Cyprus",
  "accounting_assignment": {{
    "debit_account": "7901",
    "debit_account_name": "Bank charges",
    "credit_account": "1204",
    "credit_account_name": "Bank",
    "transaction_type": "bank_charges",
    "requires_vat": false,
    "additional_entries": []
  }},
  "line_items": [
    {{
      "name": "Bank charges",
      "debit": 25.00,
      "credit": 0.00
    }},
    {{
      "name": "Bank",
      "debit": 0.00,
      "credit": 25.00
    }}
  ]
}}
```

**CRITICAL: Return ONLY the JSON array. No markdown formatting, no code blocks, no explanatory text. The response must start with '[' and end with ']'. Use ONLY the exact account codes and names from the chart of accounts provided.**
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
        
        # Validate account codes
        valid_accounts = ["1100", "1204", "2100", "2201", "2202", "3000", "7602", "7901", "8200"]
        
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
            max_tokens=12000,  # Increased for accounting assignment
            temperature=0.0,  # Maximum determinism for consistent parsing
            system="""You are an expert accountant and bank statement analyzer specialized in transaction classification and double-entry bookkeeping. Your core behavior is to think and act like a professional accountant who understands ALL CASH FLOW transactions, proper account classification, and double-entry accounting principles.

CHART OF ACCOUNTS (EXACT CODES AND NAMES):
• 1100 - Accounts receivable (Asset)
• 1204 - Bank (Asset) 
• 2100 - Accounts payable (Liability)
• 2201 - Output VAT (Sales) (Liability)
• 2202 - Input VAT (Purchases) (Asset)
• 3000 - Share Capital (Equity)
• 7602 - Consultancy fees (Expense)
• 7901 - Bank charges (Expense)
• 8200 - Other non-operating income or expenses (Income/Expense)

**CRITICAL ACCOUNT CODE RULE: You MUST use the exact account codes and names from the chart above. Never modify or create new account codes.**

CORE ACCOUNTING BEHAVIOR FOR BANK TRANSACTIONS:
• Always think: "What account is being debited?" and "What account is being credited?"
• Bank transactions always involve the Bank account (1204) as either debit or credit
• Money coming into bank = DEBIT Bank (1204), CREDIT appropriate source account
• Money leaving bank = DEBIT appropriate destination account, CREDIT Bank (1204)
• Apply proper double-entry principles: debits must equal credits for every transaction
• Classify transactions based on business purpose and counterparty

TRANSACTION CLASSIFICATION AND ACCOUNTING RULES:

**Share Capital Receipts:**
• Indicators: "share capital", "capital increase", "new share capital", "shareholder investment", "equity injection"
• DEBIT: 1204 (Bank), CREDIT: 1100 (Accounts receivable)
• This represents cash received for shares issued - customer/shareholder owes us money which we collect

**Customer Payments:**
• Indicators: "payment received", "customer payment", "invoice settlement"
• DEBIT: 1204 (Bank), CREDIT: 1100 (Accounts receivable)
• Money received from customers paying their outstanding invoices

**Consultancy/Professional Service Payments (DIRECT EXPENSE):**
• Indicators: "consultancy", "professional services", "design services", "architecture", "engineering", "advisory", "topographical work", "surveying", "legal services"
• Keywords: "Architecture Design", "Andreas Spanos", "Hadjioikonomou", "topografikes ergasies", invoice references for services
• DEBIT: 7602 (Consultancy fees), CREDIT: 1204 (Bank)
• Direct payment for professional services - expense recognition when payment is made
• Use this for: architectural services, engineering services, surveying, legal work, consulting

**Supplier/Vendor Payments (ACCOUNTS PAYABLE):**
• Indicators: "payment to supplier", "goods purchased", "equipment purchase", "office supplies"
• For tangible goods, equipment, or when explicitly stated as payable settlement
• DEBIT: 2100 (Accounts payable), CREDIT: 1204 (Bank)
• Payment of amounts owed to suppliers for goods already received
• Use this ONLY for physical goods/equipment, not professional services

**Bank Charges and Fees:**
• Indicators: "bank fee", "card fee", "membership fee", "maintenance fee", "commission", "service charge"
• DEBIT: 7901 (Bank charges), CREDIT: 1204 (Bank)
• All banking-related fees and charges

**Government/Regulatory Fees:**
• Indicators: "registrar", "government fee", "license fee", "regulatory fee", "filing fee", "capital increase fee"
• DEBIT: 8200 (Other non-operating income or expenses), CREDIT: 1204 (Bank)
• Fees paid to government entities and regulatory bodies

**Reimbursements and Other Income:**
• Indicators: "reimbursement", "refund received", miscellaneous income
• DEBIT: 1204 (Bank), CREDIT: 8200 (Other non-operating income or expenses)
• Money received as reimbursements or other non-operating income

**CRITICAL DISTINCTION - Services vs. Goods:**
• Professional services (architecture, engineering, consulting, legal) → 7602 (Consultancy fees)
• Physical goods, equipment, supplies → 2100 (Accounts payable)
• When in doubt about service payments, default to 7602 (Consultancy fees)

**VAT/TAX Handling:**
• Most bank transactions don't involve VAT directly
• VAT is typically handled through separate tax accounts
• Set requires_vat to false unless VAT is explicitly mentioned in transaction

TRANSACTION PATTERN RECOGNITION EXPERTISE:
• Analyze transaction descriptions to identify business purpose and payment type
• Extract counterparty names accurately from transaction descriptions
• Apply proper classification hierarchy:
  1. Check for professional service indicators first (architecture, engineering, consulting, surveying)
  2. Then check for physical goods/equipment purchases
  3. Finally classify as general supplier payment if unclear
• Recognize share capital transactions vs. regular customer payments
• Identify government and regulatory fees accurately
• Classify banking fees and charges appropriately
• Distinguish between expense recognition (7602) vs. payable settlement (2100)

**SERVICE PAYMENT IDENTIFICATION PRIORITY:**
• Architecture services, engineering, surveying, legal, consulting → 7602 (Consultancy fees)
• Professional service provider names (Andreas Spanos, Hadjioikonomou, etc.) → 7602 (Consultancy fees)
• Invoice payments for services → 7602 (Consultancy fees)
• Equipment, supplies, goods purchases → 2100 (Accounts payable)
• Default for professional services: Use 7602 unless explicitly goods/equipment

ACCOUNTING ASSIGNMENT RULES:
• Every transaction must have proper debit_account and credit_account assignments
• Use transaction_type to classify business purpose
• Generate additional_entries only for complex multi-account transactions
• Ensure line_items match the accounting_assignment entries
• Account names in line_items must match the debit_account_name and credit_account_name

OUTPUT FORMAT REQUIREMENTS:
• Respond only with valid JSON arrays containing transaction objects
• Never include explanatory text, analysis, or commentary
• Always include ALL required fields with proper default values
• Apply accounting expertise to assign correct debit/credit accounts for every transaction
• Use ONLY the exact account codes and names provided in the chart of accounts
• Ensure perfect double-entry balancing: total debits = total credits for each transaction

CRITICAL REMINDERS:
• Share capital receipts: DEBIT 1204 (Bank), CREDIT 1100 (Accounts receivable)
• Consultancy fees: Use account code 7602, not 6200
• Bank account is always 1204, never use other bank account codes
• Government fees go to 8200 (Other non-operating income or expenses)
• Supplier payments: DEBIT 2100 (Accounts payable), CREDIT 1204 (Bank)
• All bank transactions involve account 1204 (Bank) as either debit or credit""",
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
        
        # Validate account codes
        valid_accounts = ["1100", "1204", "2100", "2201", "2202", "3000", "7602", "7901", "8200"]
        
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
            "version": "1.2",
            "capabilities": [
                "transaction_extraction",
                "accounting_assignment",
                "double_entry_validation",
                "transaction_classification",
                "account_code_mapping",
                "structured_json_output"
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
    # Test the JSON extraction function with accounting assignment
    test_response = '''[
  {
    "company_id": 123,
    "date": "2025-07-16",
    "ref": "share_capital_payment",
    "narration": "New Share Capital receipt",
    "partner": "Shareholder ABC",
    "accounting_assignment": {
      "debit_account": "1204",
      "debit_account_name": "Bank",
      "credit_account": "1100", 
      "credit_account_name": "Accounts receivable",
      "transaction_type": "share_capital_receipt",
      "requires_vat": false,
      "additional_entries": []
    },
    "line_items": [
      {
        "name": "Bank",
        "debit": 15000.00,
        "credit": 0.00
      },
      {
        "name": "Accounts receivable",
        "debit": 0.00,
        "credit": 15000.00
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