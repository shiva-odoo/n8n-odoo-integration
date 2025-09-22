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
4. **CRITICAL: Money Flow Direction**: Determine if each transaction is money entering or leaving the bank based on debit/credit columns, NOT description keywords

## MONEY FLOW ANALYSIS RULES (CRITICAL):
- **Bank Statement DEBIT column**: Money leaving the bank account → DEBIT expense/asset account, CREDIT Bank (1204)
- **Bank Statement CREDIT column**: Money entering the bank account → DEBIT Bank (1204), CREDIT revenue/liability account
- **IGNORE misleading keywords**: Words like "reimbursement", "refund", "payment" can be misleading
- **TRUST the numbers**: The debit/credit columns show actual money movement
- **Example**: "Reimbursement" in DEBIT column = money going OUT (expense), not coming in (income)

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
      "credit_account": "1100",
      "credit_account_name": "Accounts receivable",
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
        "name": "Accounts receivable",
        "debit": 0.00,
        "credit": 15000.00
      }}
    ]
  }}
]

## Accounting Assignment Rules

### Transaction Type Classification:
1. **share_capital_receipt**: Share capital payments, capital increases
   - DEBIT: 1204 (Bank), CREDIT: 1100 (Accounts receivable)

2. **customer_payment**: Payments received from customers
   - DEBIT: 1204 (Bank), CREDIT: 1100 (Accounts receivable)

3. **supplier_payment**: Payments made to ALL vendors/suppliers (DEFAULT for ALL vendor payments)
   - DEBIT: 2100 (Accounts payable), CREDIT: 1204 (Bank)

4. **consultancy_payment**: Direct payments for consultancy services (RARE - only when no prior bill)
   - DEBIT: 7602 (Consultancy fees), CREDIT: 1204 (Bank)

5. **bank_charges**: Bank fees and charges
   - DEBIT: 7901 (Bank charges), CREDIT: 1204 (Bank)

6. **other_expense**: Direct expenses with no prior bill (VERY RARE)
   - DEBIT: 8200 (Other non-operating income or expenses), CREDIT: 1204 (Bank)

7. **other_income**: Reimbursements, miscellaneous income
   - DEBIT: 1204 (Bank), CREDIT: 8200 (Other non-operating income or expenses)

### Transaction Pattern Recognition:

**Share Capital Indicators:**
- "share capital", "capital increase", "new share capital"
- "shareholder investment", "equity injection"
- DEBIT: 1204 (Bank), CREDIT: 1100 (Accounts receivable)

**Supplier/Vendor Payment Indicators (DEFAULT for ALL vendor payments):**
- "payment to [vendor name]", "invoice payment"
- Specific vendor names (Architecture Design, Andreas Spanos, Hadjioikonomou, etc.)
- Professional service providers (architects, engineers, surveyors, consultants)
- Equipment suppliers, office suppliers
- **Government entities, registrar offices, regulatory bodies (ALL are vendors)**
- **ANY payment where a bill could have been recorded previously**
- DEBIT: 2100 (Accounts payable), CREDIT: 1204 (Bank)
- **Use this for ALL payments to ANY vendor/supplier - assumes bills were recorded previously**
- **INCLUDES: Government fees, registrar fees, regulatory fees, professional services**

**Direct Consultancy Payment Indicators (RARE - only when certain no prior bill exists):**
- "consultancy", "professional services" where no vendor relationship evident
- One-off professional services with no established vendor relationship
- DEBIT: 7602 (Consultancy fees), CREDIT: 1204 (Bank)
- **WARNING: Use sparingly - most vendor payments should be supplier_payment type**

**Bank Charges Indicators:**
- "bank fee", "card fee", "membership fee", "maintenance fee"
- "commission", "service charge"
- DEBIT: 7901 (Bank charges), CREDIT: 1204 (Bank)

**Government/Registrar Fee Indicators:**
- "registrar", "government fee", "license fee"
- "regulatory fee", "filing fee", "capital increase fee"
- **CRITICAL: These are also vendor payments - classify as supplier_payment if bills were recorded**
- DEBIT: 2100 (Accounts payable), CREDIT: 1204 (Bank)
- Only use direct expense (8200) if certain no prior bill exists

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

1. **STEP 1: Analyze money flow direction** - Check debit/credit columns in bank statement to determine actual money movement
2. **STEP 2: Extract ALL transactions** from the statement (both inflows and outflows)
3. **STEP 3: Classify each transaction** using the pattern recognition rules AFTER confirming money flow direction
4. **STEP 4: PRIORITY: Default to supplier_payment for all vendor payments** (assumes proper bill recording)
5. **STEP 5: Assign correct debit/credit accounts** based on transaction type AND money flow direction
6. **STEP 6: Generate appropriate accounting_assignment** object
7. **STEP 7: Create balanced line_items** ensuring debits = credits
8. **STEP 8: Clean descriptions** and create business-friendly narrations
9. **STEP 9: Set company_id** to `{company_id_value}` for every transaction
10. **STEP 10: Ensure all numeric values are numbers, not strings**
11. **STEP 11: Use ONLY the account codes and names from the chart of accounts**

**CRITICAL MONEY FLOW VALIDATION:**
- If bank statement shows DEBIT: Transaction reduces bank balance (money out) → CREDIT Bank (1204)
- If bank statement shows CREDIT: Transaction increases bank balance (money in) → DEBIT Bank (1204)
- Double-check money flow direction against description keywords to catch contradictions

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
    "credit_account": "1100",
    "credit_account_name": "Accounts receivable",
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
      "name": "Accounts receivable",
      "debit": 0.00,
      "credit": 15000.00
    }}
  ]
}}
```

### Supplier Payment (DEFAULT for vendor payments):
```json
{{
  "company_id": {company_id_value},
  "date": "2025-07-18",
  "ref": "255634959",
  "narration": "Payment to Architecture Design - Andreas Spanos, Invoice 621467",
  "partner": "Architecture Design Andreas Spanos",
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
• **FIRST PRIORITY: Analyze actual money flow direction from bank statement**
• Check bank statement debit/credit columns to determine if money is entering or leaving bank
• Money flow takes precedence over description keywords
• Always think: "What account is being debited?" and "What account is being credited?"
• Bank transactions always involve the Bank account (1204) as either debit or credit
• Money coming into bank (CREDIT on bank statement) = DEBIT Bank (1204), CREDIT appropriate source account
• Money leaving bank (DEBIT on bank statement) = DEBIT appropriate destination account, CREDIT Bank (1204)
• Apply proper double-entry principles: debits must equal credits for every transaction
• Classify transactions based on actual money flow direction FIRST, then business purpose and counterparty

TRANSACTION CLASSIFICATION AND ACCOUNTING RULES:

**Share Capital Receipts:**
• Indicators: "share capital", "capital increase", "new share capital", "shareholder investment", "equity injection"
• DEBIT: 1204 (Bank), CREDIT: 1100 (Accounts receivable)
• This represents cash received from shareholders who were previously issued shares
• Assumes share issuance was already recorded: Dr. Accounts receivable, Cr. Share Capital

**Customer Payments:**
• Indicators: "payment received", "customer payment", "invoice settlement"
• DEBIT: 1204 (Bank), CREDIT: 1100 (Accounts receivable)
• Money received from customers paying their outstanding invoices

**Supplier/Vendor Payments (DEFAULT for all vendor payments):**
• Indicators: Payment to known suppliers/vendors for whom bills were previously recorded
• Keywords: "Architecture Design", "Andreas Spanos", "Hadjioikonomou", "payment to [vendor name]", invoice references
• For professional services: architecture, engineering, surveying, legal work, consulting
• For goods: office supplies, equipment, materials
• DEBIT: 2100 (Accounts payable), CREDIT: 1204 (Bank)
• This clears previously recorded liabilities when bills were entered into the system
• **USE THIS FOR ALL PAYMENTS TO VENDORS/SUPPLIERS - assumes bills were recorded previously**

**Direct Consultancy Payments (RARE - only when certain no prior bill exists):**
• Indicators: Direct payments for services where no prior bill recording is evident
• Only use when certain no accounts payable entry was made previously
• DEBIT: 7602 (Consultancy fees), CREDIT: 1204 (Bank)
• For immediate expense recognition when payment represents the first accounting entry
• **WARNING: This should be rare in established businesses with proper bill recording procedures**

**Bank Charges and Fees:**
• Indicators: "bank fee", "card fee", "membership fee", "maintenance fee", "commission", "service charge"
• DEBIT: 7901 (Bank charges), CREDIT: 1204 (Bank)
• All banking-related fees and charges

**Government/Regulatory Fees:**
• Indicators: "registrar", "government fee", "license fee", "regulatory fee", "filing fee", "capital increase fee"
• **CRITICAL: Government entities are also vendors - follow same rule**
• DEBIT: 2100 (Accounts payable), CREDIT: 1204 (Bank)
• **Government fees are vendor payments that clear previously recorded liabilities**

**Other Non-Operating Expenses (EXTREMELY RARE for outgoing payments):**
• **WARNING: Only use for very specific cases where absolutely certain no vendor relationship exists**
• **DO NOT USE for**: Bank transfers, internet transfers, generic payments, unknown transfers
• **EXCEPTIONS ONLY**: Regulatory penalties, interest payments, very specific non-vendor expenses
• **DEFAULT RULE**: When uncertain about outgoing payment → Use supplier_payment, NOT other_expense
• **CONSERVATIVE APPROACH**: Better to incorrectly classify as vendor payment than miss vendor settlement

**CRITICAL PAYMENT CLASSIFICATION HIERARCHY:**
1. **ABSOLUTE PRIORITY - Supplier Payment**: ALL outgoing payments default to supplier_payment unless explicitly identified otherwise
2. **UNIVERSAL DEFAULT**: When in doubt about ANY outgoing payment → Use supplier_payment (2100 Accounts payable)
3. **RULE**: "The payment to the Vendor always goes to accounts payable. When the supporting invoice is provided that is when we create the expense and allocate VAT"
4. **ASSUMPTION**: All businesses have proper bill recording procedures - payments clear previously recorded liabilities
5. **RARE EXCEPTIONS ONLY**: Bank charges (to banks), share capital, or explicit income receipts
6. **NEVER use direct expenses for ambiguous payments** - always default to supplier_payment

**VENDOR PAYMENT IDENTIFICATION:**
• **UNIVERSAL DEFAULT**: ALL outgoing payments → supplier_payment (2100 Accounts payable) unless explicitly identified as:
  - Bank charges to financial institutions
  - Share capital transactions  
  - Clearly identified customer receipts
• **AMBIGUOUS PAYMENTS**: Bank transfers, internet transfers, generic payments → supplier_payment (2100 Accounts payable)
• **ASSUMPTION**: Every business payment could have had a bill recorded previously
• **INCLUDES**: Professional services, government fees, utilities, supplies, equipment, regulatory fees, unknown transfers
• **When partner unknown or description unclear → ALWAYS use supplier_payment (2100 Accounts payable)**
• **NEVER guess direct expenses** - default to liability settlement

**VAT/TAX Handling:**
• Most bank transactions don't involve VAT directly
• VAT is typically handled through separate tax accounts
• Set requires_vat to false unless VAT is explicitly mentioned in transaction

TRANSACTION PATTERN RECOGNITION EXPERTISE:
• **STEP 1: Determine money flow direction from bank statement debit/credit columns**
• **STEP 2: Apply UNIVERSAL DEFAULT - ALL outgoing payments = supplier_payment unless explicitly identified otherwise**
• **STEP 3: Only classify as non-supplier if clearly identifiable as bank charges, share capital, or customer receipts**
• **CRITICAL: Reconcile description keywords with actual money flow direction**
• Apply proper classification hierarchy AFTER confirming money direction:
  1. Check actual money flow (in/out) from bank statement columns
  2. **If money leaving bank → DEFAULT to supplier_payment (2100 Accounts payable)**
  3. **EXCEPTIONS ONLY**: Bank charges to banks → bank_charges (7901), Share capital → share_capital_receipt (1100)
  4. **NEVER use other_expense (8200) for ambiguous outgoing payments**
  5. **AMBIGUOUS = SUPPLIER PAYMENT**: Unknown transfers, internet transfers, generic payments → supplier_payment
• **UNIVERSAL RULE**: "The payment to the Vendor always goes to accounts payable"
• **AGGRESSIVE APPLICATION**: Treat ALL unclear outgoing payments as vendor payments
• **CONSERVATIVE APPROACH**: Better to clear non-existent payables than miss real vendor payments**
• **WARNING: Do not be misled by keywords like "reimbursement" if money flow shows opposite direction**

**ACCOUNTING ASSIGNMENT RULES:**
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
• **MONEY FLOW DIRECTION IS PARAMOUNT: Always check bank statement debit/credit columns first**
• **UNIVERSAL VENDOR RULE: "The payment to the Vendor always goes to accounts payable. When the supporting invoice is provided that is when we create the expense and allocate VAT"**
• **AGGRESSIVE DEFAULT**: ALL outgoing payments → supplier_payment (2100 Accounts payable) unless explicitly identified otherwise
• Share capital receipts: DEBIT 1204 (Bank), CREDIT 1100 (Accounts receivable)
• **ALL outgoing payments (DEFAULT): DEBIT 2100 (Accounts payable), CREDIT 1204 (Bank)**
• **INCLUDES: All transfers, internet payments, unknown payments, professional services, government fees, utilities, supplies**
• **EXCEPTIONS ONLY**: Bank charges to banks → 7901 (Bank charges), Share capital → 1100 (Accounts receivable)
• Bank account is always 1204, never use other bank account codes
• **NEVER use other_expense (8200) for ambiguous outgoing payments**
• All bank transactions involve account 1204 (Bank) as either debit or credit
• **When payment purpose unclear, ALWAYS use supplier_payment (2100 Accounts payable settlement)**
• **CONSERVATIVE APPROACH**: Better to clear non-existent payables than create incorrect direct expenses
• Assume proper bill recording procedures exist in established businesses
• **CRITICAL: Keywords like "reimbursement" can be misleading - trust the money flow direction from bank statement columns**
• **If bank statement shows DEBIT amount: Money is leaving = CREDIT Bank (1204) = DEFAULT to supplier_payment**
• **If bank statement shows CREDIT amount: Money is entering = DEBIT Bank (1204)**""",
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