import boto3
import base64
import anthropic
import os
import json
import re

def get_bank_statement_extraction_prompt(matched_id=None):
    """Create bank statement transaction extraction prompt"""
    # Use the matched_id if provided, otherwise use placeholder
    company_id_value = matched_id if matched_id is not None else "{{ $json.matched_id }}"
    
    return f"""# Bank Statement Transaction Extraction

## Task
Extract ALL transactions from bank statement text and convert each transaction into the exact JSON format required for double-entry accounting. Process every single transaction found in the statement.

## Input Analysis
You will receive bank statement text. Extract:
1. **Bank Information**: Bank name, account holder, account number
2. **All Transactions**: Date, description, amounts, references, transaction type
3. **Currency Information**: Identify the currency used in transactions

## Required Output Format
For EACH transaction found, create a JSON object with this EXACT structure and return as a JSON array:

```json
[
  {{
    "company_id": {company_id_value},
    "date": "YYYY-MM-DD",
    "ref": "string",
    "narration": "string", 
    "partner": "string",
    "line_items": [
      {{
        "name": "string",
        "debit": number,
        "credit": number
      }},
      {{
        "name": "string", 
        "debit": number,
        "credit": number
      }}
    ]
  }}
]
```

## Field Generation Rules

### Standard Fields
- **company_id**: Always set to `{company_id_value}` 
- **date**: Convert to YYYY-MM-DD format
- **ref**: Use actual transaction reference if available, otherwise generate from description
- **narration**: Clean, business-friendly description of the transaction
- **partner**: Use the actual partner/counterparty name if found in the transaction. **If no partner name is found, set the value to `"unknown"` (do not leave empty or null).**
- **line_items**: Array of 2+ accounting entries that balance (total debits = total credits)

### Reference (ref) Generation Rules

**Priority 1 - Use Actual Transaction Reference (if present in statement):**
- Look for transaction references, reference numbers, or unique identifiers in the bank statement
- Use the exact reference as provided (e.g., "255492965", "TXN123456", "REF789")
- Do not modify or add prefixes to actual bank references

**Priority 2 - Generate from Description (if no reference available):**
- Create a unique reference using the transaction description
- Convert to lowercase
- Replace spaces with underscores
- Remove special characters except underscores and numbers
- Truncate to reasonable length (max 25 characters)
- For uniqueness, use one of these approaches:
  - **Method 1**: Include specific identifiers from description (vendor names, account numbers, etc.)
  - **Method 2**: Add date if descriptions are similar: `description_dd_mm_yyyy`

**Examples:**
- If reference "252333114" exists → use "252333114"
- If reference "TXN789123" exists → use "TXN789123"
- If no reference, description "FEE REGISTRAR COMPANIES" → use "fee_registrar_companies"
- If no reference, description "CARD PYT SUPERMARKET XYZ" → use "card_pyt_supermarket_xyz"
- If no reference, description "IBU MAINTENANCE FEE ABC ACCOUNT" → use "ibu_maintenance_fee_abc"
- If no reference, description "IBU MAINTENANCE FEE DEF ACCOUNT" → use "ibu_maintenance_fee_def"
- If similar descriptions on same date "IBU MAINTENANCE FEE" → use "ibu_maintenance_fee_30_05_2025"
- If multiple similar transactions → use "abc_commission_fee", "def_commission_fee" (extract different parts)

### Narration Rules
- Remove internal bank reference numbers and codes
- Make descriptions business-friendly and readable
- Keep essential information like payee names, purpose
- Examples:
  - "FEE REGISTRAR COMPANIES REF:12345" → "Registrar of companies fee"
  - "TRF TO JOHN SMITH REF:ABC123" → "Transfer to John Smith"
  - "CARD PYT SUPERMARKET XYZ" → "Card payment - Supermarket XYZ"

## Double-Entry Accounting Logic

### For Money LEAVING the Bank Account (Debits on bank statement):
```json
"line_items": [
  {{
    "name": "{{Bank Name}}",
    "debit": 0.00,
    "credit": {{amount}}
  }},
  {{
    "name": "{{Appropriate Expense/Asset Account}}",
    "debit": {{amount}},
    "credit": 0.00
  }}
]
```

### For Money ENTERING the Bank Account (Credits on bank statement):
```json
"line_items": [
  {{
    "name": "{{Bank Name}}",
    "debit": {{amount}},
    "credit": 0.00
  }},
  {{
    "name": "{{Appropriate Revenue/Liability Account}}",
    "debit": 0.00,
    "credit": {{amount}}
  }}
]
```

## Account Name Mapping

### Bank Accounts
- Use the actual bank name: "Bank of Cyprus", "HSBC", "1Bank"

### Counterpart Accounts (determine based on transaction type):

**Common Expense Accounts:**
- "Office Expenses" - for office supplies, utilities
- "Professional Fees" - for legal, accounting, consulting fees
- "Bank Charges" - for bank fees and charges
- "Travel Expenses" - for travel related costs
- "Equipment" - for equipment purchases
- "Supplies" - for general supplies

**Common Revenue Accounts:**
- "Service Revenue" - for service income
- "Sales Revenue" - for product sales
- "Interest Income" - for interest received
- "Other Income" - for miscellaneous income

**Common Asset/Liability Accounts:**
- "Share Capital" - for share capital transactions
- "Loans Payable" - for loan transactions
- "Accounts Receivable" - for customer payments
- "Accounts Payable" - for supplier payments
- "Petty Cash" - for cash transactions

## Processing Instructions

1. **Extract ALL transactions** from the statement (both inflows and outflows)
2. **Process chronologically** and generate sequential references for same-date transactions
3. **Determine transaction type** and map to appropriate accounts
4. **Apply double-entry logic** ensuring debits = credits for each transaction
5. **Clean descriptions** and create business-friendly narrations
6. **Verify currency consistency** throughout the statement
7. **Set company_id** to `{company_id_value}` for every transaction

## Example Output Structure
Return a JSON array containing one object for each transaction:

```json
[
  {{
    "company_id": {company_id_value},
    "date": "2025-07-16",
    "ref": "255492965", 
    "narration": "New Share Capital of Kyrastel Investments Ltd - Bank Credit Advice",
    "partner": "Kyrastel Investments Ltd",
    "line_items": [
      {{
        "name": "Bank of Cyprus",
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
```

**IMPORTANT: Return ONLY the JSON array with no additional text, explanations, or markdown formatting.**
"""

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
    """Process bank statement with Claude for transaction extraction"""
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
            max_tokens=8000,
            temperature=0.0,  # Maximum determinism for consistent parsing
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
        
        # Log token usage for monitoring
        print(f"Token usage - Input: {message.usage.input_tokens}, Output: {message.usage.output_tokens}")
        
        return {
            "success": True,
            "extraction_result": response_text,
            "token_usage": {
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def main(data):
    """
    Main function for bank statement transaction extraction
    
    Args:
        data (dict): Request data containing:
            - s3_key (str): S3 key path to the document
            - bucket_name (str, optional): S3 bucket name
            - company_id (str, optional): Company ID for transaction extraction
    
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
        
        print(f"Processing bank statement for transaction extraction, S3 key: {s3_key}")
        
        # Download PDF from S3
        pdf_content = download_from_s3(s3_key, bucket_name)
        print(f"Downloaded PDF, size: {len(pdf_content)} bytes")
        
        # Process bank statement for transaction extraction
        result = process_bank_statement_extraction(pdf_content, company_id)
        
        if result["success"]:
            return {
                "success": True,
                "raw_response": result["extraction_result"],
                "metadata": {
                    "token_usage": result["token_usage"],
                    "s3_key": s3_key,
                    "company_id": company_id
                }
            }
        else:
            return {
                "success": False,
                "error": result["error"]
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
            "anthropic_configured": bool(os.getenv('ANTHROPIC_API_KEY')),
            "aws_configured": bool(os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY')),
            "s3_bucket": os.getenv('S3_BUCKET_NAME', 'company-documents-2025')
        }
        
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e)
        }