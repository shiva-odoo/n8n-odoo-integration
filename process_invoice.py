import boto3
import base64
import anthropic
import os
import json
import re
from odoo_accounting_logic import main as get_accounting_logic

def get_invoice_processing_prompt(company_name):
    """Create comprehensive invoice processing prompt that combines splitting and extraction"""
    
    # Get invoice accounting logic with VAT rules
    invoice_logic = get_accounting_logic("invoice")
    
    return f"""You are an advanced invoice processing AI. Your task is to analyze a multi-invoice PDF document and return structured JSON data.

**CRITICAL INSTRUCTION: Respond with ONLY the JSON object. Do not include any explanatory text, commentary, analysis, or markdown formatting before or after the JSON. Start your response immediately with the opening curly brace {{.**

**INPUT:** Multi-invoice PDF document
**COMPANY:** {company_name} (the company issuing these invoices to customers)
**OUTPUT:** Raw JSON object only

**DOCUMENT SPLITTING RULES (Priority Order):**
1. **PAGE INDICATOR RULE (HIGHEST PRIORITY):**
   - "Page 1 of 1" multiple times = Multiple separate single-page invoices
   - "Page 1 of 2", "Page 2 of 2" = One two-page invoice
   - "Page 1 of 3", "Page 2 of 3", "Page 3 of 3" = One three-page invoice

2. **INVOICE NUMBER RULE (SECOND PRIORITY):**
   - Different invoice numbers = Different invoices
   - Same invoice number across pages = Same invoice

3. **HEADER COUNT RULE (THIRD PRIORITY):**
   - Multiple "INVOICE" headers typically = Multiple invoices

**DATA EXTRACTION FOR EACH INVOICE:**

**DOCUMENT TYPE:** Set as "customer_invoice" for traditional invoices or "share_capital_invoice" for share allotments and capital increases.

**DOCUMENT IDENTIFICATION:**
- Traditional customer invoices: Services/goods provided to customers
- Share capital documents: Share allotments, capital increases, shareholder investments
- Both types represent cash inflow to the company and should be processed

**COMPANY VALIDATION:**
- Identify ALL company names in the PDF
- Check if any match "{company_name}" (case-insensitive, fuzzy matching)
- Set company_match: "exact_match", "close_match", "no_match", or "unclear"

**MANDATORY FIELDS:**
- Customer/Shareholder name (Essential)
- Invoice/Transaction Date (Required)
- Due Date or Payment Terms
- Invoice/Document Reference
- Currency and Amounts
- Description (Overall description of the services/goods/shares provided)
- Line Items with calculations AND individual account assignments
- Credit Account (Account to be credited based on transaction type)
- Debit Account (Account to be debited based on transaction type)

**ACCOUNTING ASSIGNMENT RULES:**

{invoice_logic}

**LINE-LEVEL ACCOUNT ASSIGNMENT FOR INVOICES:**
Each line item must be assigned to the most appropriate revenue account based on the service/product type:

**Service/Product Type → Account Code Mapping:**
- Primary business services, consulting, professional work → 4000 (Sales)
- Software development, technical services → 4000 (Sales)
- Core product sales, manufacturing sales → 4000 (Sales)
- Main business activities, project work → 4000 (Sales)
- Secondary/ancillary services not core to business → 4900 (Other sales)
- Training services (if not main business) → 4900 (Other sales)
- Support/maintenance services (if not main business) → 4900 (Other sales)
- Licensing income, IP royalties → 4901 (Royalties received)
- Commission income from partnerships → 4902 (Commissions received)
- Property rental income, space subletting → 4904 (Rent income)
- Equipment sales, asset disposals → 4200 (Sales of assets)
- Insurance claim settlements → 4903 (Insurance claims)
- Interest earned, financial income → 4906 (Bank interest received)
- Shipping charges to customers → 4905 (Distribution and carriage)
- Miscellaneous income → 8200 (Other non-operating income or expenses)
- Share capital transactions → 3000 (Share Capital)

**CRITICAL LINE ITEM ANALYSIS:**
- Analyze EACH line item individually for revenue type
- Same customer can receive multiple service types
- Example: Consulting firm billing for both "Strategic consulting" (4000) AND "Training services" (4900)
- Example: Software company selling "Core software" (4000) AND "Optional support" (4900)
- Assign the most specific account code for each line item
- DEFAULT: Use 4000 (Sales) for 80% of business invoices unless clearly secondary

**CONSTRUCTION/PROPERTY COMPANY DETECTION:**
Look for these indicators in customer information to determine VAT treatment:
- Customer name contains: "Construction", "Building", "Property Management", "Real Estate"
- Services described as: "Construction services", "Building work", "Property management"
- Document mentions: "Reverse charge applicable", "Customer to account for VAT"

**VAT TREATMENT LOGIC:**
- **NORMAL CUSTOMERS:** Standard VAT treatment
  - Main transaction: GROSS amount (net + VAT)
  - Debit: 1100 (Accounts Receivable) - Full amount including VAT
  - Credit: Revenue accounts (per line item) - Net amounts only
  - Credit: 2201 (Output VAT) - VAT amount owed to authorities

- **CONSTRUCTION/PROPERTY CUSTOMERS:** Reverse charge mechanism
  - Main transaction: NET amount only
  - Debit: 1100 (Accounts Receivable) - Net amount only
  - Credit: Revenue accounts (per line item) - Net amounts
  - Create BOTH VAT entries in additional_entries:
    - Input VAT (2202) - Debit VAT amount
    - Output VAT (2201) - Credit VAT amount

**MIXED LINE ITEMS HANDLING:**
When line items map to different revenue accounts:
- Set credit_account to "MIXED"
- Set credit_account_name to "Mixed Line Items"
- Each line item contains its own account_code and account_name
- VAT handling remains the same (customer-level decision)

**CRITICAL VAT/TAX HANDLING RULE:**
- If customer is NORMAL company with VAT: Create Output VAT entry in additional_entries
- If customer is CONSTRUCTION/PROPERTY company with VAT: Create BOTH Input VAT AND Output VAT entries in additional_entries
- For NORMAL customers with VAT: Create Output VAT entry:
  {{
    "account_code": "2201",
    "account_name": "Output VAT (Sales)",
    "debit_amount": 0,
    "credit_amount": [tax_amount],
    "description": "Output VAT on customer invoice"
  }}
- For CONSTRUCTION/PROPERTY customers with VAT: Create BOTH entries:
  {{
    "account_code": "2202",
    "account_name": "Input VAT (Purchases)",
    "debit_amount": [tax_amount],
    "credit_amount": 0,
    "description": "Reverse charge Input VAT"
  }},
  {{
    "account_code": "2201",
    "account_name": "Output VAT (Sales)",
    "debit_amount": 0,
    "credit_amount": [tax_amount],
    "description": "Reverse charge Output VAT"
  }}

**SHARE CAPITAL TRANSACTION HANDLING:**
- Treat share allotments as invoices for accounting purposes
- Shareholder becomes the "customer" receiving shares
- Amount represents cash to be received from shareholder
- Description should detail share allotment (e.g., "15,000 ordinary shares at €1 each")
- Use appropriate accounting codes: DEBIT 1100 (Accounts receivable), CREDIT 3000 (Share Capital)
- Share transactions are VAT-EXEMPT (no VAT entries)
- All share line items should use account_code="3000", account_name="Share Capital"

**DESCRIPTION FIELD:**
- Create an overall description of the services/goods provided to the customer
- Include key details from line item descriptions
- Can be a shortened combination of the description fields from each line item
- Should give a clear understanding of what the invoice is for

**CALCULATION REQUIREMENTS:**
- line_total = quantity × price_unit
- subtotal = sum of all line_totals before tax
- total_amount = subtotal + tax_amount
- If only total visible: subtotal = total_amount, tax_amount = 0

**STRICT FORMATTING RULES:**
- Text fields: Use empty string "" if not found (never use "none", "null", or "N/A")
- Date fields: Use null if not found (never use empty string)
- Number fields: Use 0 if not found (never use null or empty string)
- Array fields: Use empty array [] if no items found
- Country codes: Use standard 2-letter codes: Cyprus="CY", Greece="GR", USA="US", UK="GB", or "" if unknown

**REQUIRED JSON STRUCTURE - ALL FIELDS MUST BE PRESENT IN EVERY RESPONSE:**

{{
  "success": true,
  "total_invoices": <number>,
  "invoices": [
    {{
      "invoice_index": 1,
      "page_range": "1",
      "document_classification": {{
        "document_type": "customer_invoice",
        "company_position": "issuer",
        "direction_confidence": "high",
        "detection_details": ""
      }},
      "company_validation": {{
        "expected_company": "{company_name}",
        "found_companies": [],
        "company_match": "no_match",
        "match_details": ""
      }},
      "company_data": {{
        "name": "",
        "email": "",
        "phone": "",
        "website": "",
        "street": "",
        "city": "",
        "zip": "",
        "country_code": ""
      }},
      "customer_data": {{
        "name": "",
        "email": "",
        "phone": "",
        "website": "",
        "street": "",
        "city": "",
        "zip": "",
        "country_code": "",
        "invoice_date": null,
        "due_date": null,
        "invoice_ref": "",
        "payment_reference": "",
        "description": "",
        "subtotal": 0,
        "tax_amount": 0,
        "total_amount": 0,
        "currency_code": "",
        "line_items": []
      }},
      "accounting_assignment": {{
        "debit_account": "",
        "debit_account_name": "",
        "credit_account": "",
        "credit_account_name": "",
        "vat_treatment": "",
        "requires_reverse_charge": false,
        "additional_entries": []
      }},
      "extraction_confidence": {{
        "customer_name": "low",
        "total_amount": "low",
        "line_items": "low",
        "dates": "low",
        "company_validation": "low",
        "document_classification": "low"
      }},
      "missing_fields": []
    }}
  ]
}}

**LINE ITEMS STRUCTURE (ENHANCED - when present):**
Each line item in the line_items array must have this exact structure:
{{
  "description": "",
  "quantity": 0,
  "price_unit": 0,
  "line_total": 0,
  "tax_rate": 0,
  "account_code": "",
  "account_name": ""
}}

**ADDITIONAL ENTRIES STRUCTURE (for VAT and complex transactions):**
Each additional entry in the additional_entries array must have this exact structure:
{{
  "account_code": "",
  "account_name": "",
  "debit_amount": 0,
  "credit_amount": 0,
  "description": ""
}}

**ACCOUNTING ASSIGNMENT EXAMPLES:**
- Single Service Invoice: debit_account="1100", credit_account="4000", credit_account_name="Sales"
- Mixed Services Invoice: debit_account="1100", credit_account="MIXED", credit_account_name="Mixed Line Items"
- Share Capital Transaction: debit_account="1100", credit_account="3000", credit_account_name="Share Capital"
- Normal Customer with VAT: Standard accounting + Output VAT (2201) in additional_entries
- Construction/Property Customer with VAT: Standard accounting + BOTH Input VAT (2202) AND Output VAT (2201) in additional_entries

**LINE ITEM ACCOUNT ASSIGNMENT EXAMPLES:**
- "Strategic consulting services" → account_code="4000", account_name="Sales"
- "Training workshop" → account_code="4900", account_name="Other sales"  
- "Software license royalty" → account_code="4901", account_name="Royalties received"
- "Commission from partner sales" → account_code="4902", account_name="Commissions received"
- "Office space rental" → account_code="4904", account_name="Rent income"
- "15,000 ordinary shares" → account_code="3000", account_name="Share Capital"

**ABSOLUTE REQUIREMENTS:**
1. Every field listed above MUST be present in every invoice object
2. Use the exact default values shown when data is not found
3. Never omit fields - always include them with default values
4. String fields default to empty string ""
5. Number fields default to 0
6. Date fields default to null
7. Array fields default to empty array []
8. Confidence levels: use "high", "medium", or "low" only
9. Company match: use "exact_match", "close_match", "no_match", or "unclear" only
10. **ACCOUNT CODE CONSISTENCY: Use ONLY the exact account codes and names from the invoice logic above**
11. **LINE ITEM ACCOUNT ASSIGNMENT: MANDATORY for every line item - analyze each service individually**
12. **MIXED INVOICES: When line items have different account codes, set credit_account="MIXED"**
13. **DEFAULT TO 4000 (Sales): Use for 80% of business invoices unless clearly secondary services**

**FINAL REMINDER: Return ONLY the JSON object with ALL fields present. No explanatory text. Start with {{ and end with }}.**"""

def ensure_line_item_structure(line_item):
    """Ensure each line item has the complete required structure including account assignment"""
    default_line_item = {
        "description": "",
        "quantity": 0,
        "price_unit": 0,
        "line_total": 0,
        "tax_rate": 0,
        "account_code": "",
        "account_name": ""
    }
    
    result = {}
    for key, default_value in default_line_item.items():
        if key in line_item and line_item[key] is not None:
            result[key] = line_item[key]
        else:
            result[key] = default_value
    
    return result

def validate_invoice_data(invoices):
    """Validate extracted invoice data for completeness and accuracy including line-level accounts"""
    validation_results = []
    
    for invoice in invoices:
        invoice_validation = {
            "invoice_index": invoice.get("invoice_index", 0),
            "issues": [],
            "warnings": [],
            "mandatory_fields_present": True,
            "structure_complete": True
        }
        
        customer_data = invoice.get("customer_data", {})
        
        # Check mandatory fields (content validation, not structure)
        mandatory_content = {
            "customer_name": customer_data.get("name", ""),
            "total_amount": customer_data.get("total_amount", 0),
            "invoice_date": customer_data.get("invoice_date"),
            "description": customer_data.get("description", "")
        }
        
        for field_name, field_value in mandatory_content.items():
            if not field_value or field_value == "":
                invoice_validation["issues"].append(f"Missing content for mandatory field: {field_name}")
                invoice_validation["mandatory_fields_present"] = False
        
        # Check line items and their account assignments
        line_items = customer_data.get("line_items", [])
        if not line_items:
            invoice_validation["warnings"].append("No line items found")
        else:
            # Validate line item account assignments
            valid_revenue_accounts = [
                "4000", "4900", "4901", "4902", "4904", "4906", "4200", "4903", "4905", "3000", "8200"
            ]
            
            line_item_accounts = set()
            for i, item in enumerate(line_items):
                account_code = item.get("account_code", "")
                account_name = item.get("account_name", "")
                
                if not account_code:
                    invoice_validation["issues"].append(f"Line item {i+1} missing account_code")
                elif account_code not in valid_revenue_accounts:
                    invoice_validation["issues"].append(f"Line item {i+1} has invalid account code: {account_code}")
                
                if not account_name:
                    invoice_validation["issues"].append(f"Line item {i+1} missing account_name")
                
                if account_code:
                    line_item_accounts.add(account_code)
            
            # Check if invoice is mixed (multiple account codes)
            accounting_assignment = invoice.get("accounting_assignment", {})
            credit_account = accounting_assignment.get("credit_account", "")
            
            if len(line_item_accounts) > 1 and credit_account != "MIXED":
                invoice_validation["warnings"].append(
                    f"Multiple account codes detected in line items ({len(line_item_accounts)}) but credit_account is not 'MIXED'"
                )
            elif len(line_item_accounts) == 1 and credit_account == "MIXED":
                invoice_validation["warnings"].append(
                    "Only one account code in line items but credit_account is set to 'MIXED'"
                )
        
        # Check monetary consistency
        subtotal = customer_data.get("subtotal", 0)
        tax_amount = customer_data.get("tax_amount", 0)
        total_amount = customer_data.get("total_amount", 0)
        
        if total_amount > 0:
            calculated_total = subtotal + tax_amount
            if abs(calculated_total - total_amount) > 0.01:
                invoice_validation["warnings"].append(
                    f"Amount mismatch: calculated {calculated_total}, document shows {total_amount}"
                )
        
        # Check VAT handling compliance for invoices
        accounting_assignment = invoice.get("accounting_assignment", {})
        additional_entries = accounting_assignment.get("additional_entries", [])
        
        # Detect if customer is construction/property company
        customer_name = customer_data.get("name", "").lower()
        is_construction_property = any(keyword in customer_name for keyword in [
            "construction", "building", "property", "real estate"
        ])
        
        if tax_amount > 0 and not is_construction_property:
            # Normal customer with VAT should have Output VAT entry only
            if not additional_entries:
                invoice_validation["issues"].append(
                    "Tax amount detected for normal customer but no additional_entries created"
                )
            else:
                output_vat_entries = [e for e in additional_entries if e.get("account_code") == "2201"]
                if not output_vat_entries:
                    invoice_validation["issues"].append(
                        "Tax amount detected for normal customer but missing Output VAT (2201) entry"
                    )
        elif tax_amount > 0 and is_construction_property:
            # Construction/property customer should have BOTH Input and Output VAT entries (reverse charge)
            if not additional_entries:
                invoice_validation["issues"].append(
                    "Tax amount detected for construction/property customer but no additional_entries created - reverse charge requires both VAT entries"
                )
            else:
                input_vat_entries = [e for e in additional_entries if e.get("account_code") == "2202"]
                output_vat_entries = [e for e in additional_entries if e.get("account_code") == "2201"]
                
                if not input_vat_entries:
                    invoice_validation["issues"].append(
                        "Construction/property customer with tax but missing Input VAT (2202) entry for reverse charge"
                    )
                
                if not output_vat_entries:
                    invoice_validation["issues"].append(
                        "Construction/property customer with tax but missing Output VAT (2201) entry for reverse charge"
                    )
        
        # Check account code consistency for main accounting assignment
        debit_account = accounting_assignment.get("debit_account", "")
        
        valid_debit_accounts = ["1100"]
        valid_credit_accounts = ["4000", "4900", "4901", "4902", "4904", "4906", "4200", "4903", "4905", "3000", "8200", "MIXED"]
        
        if debit_account and debit_account not in valid_debit_accounts:
            invoice_validation["issues"].append(f"Invalid debit account code: {debit_account}")
        
        if credit_account and credit_account not in valid_credit_accounts:
            invoice_validation["issues"].append(f"Invalid credit account code: {credit_account}")
        
        # Check confidence levels
        confidence = invoice.get("extraction_confidence", {})
        low_confidence_fields = [
            field for field, conf in confidence.items() 
            if conf == "low"
        ]
        
        if low_confidence_fields:
            invoice_validation["warnings"].append(
                f"Low confidence fields: {', '.join(low_confidence_fields)}"
            )
        
        validation_results.append(invoice_validation)
    
    return validation_results

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

def process_invoices_with_claude(pdf_content, company_name):
    """Process PDF document with Claude for invoice splitting and extraction"""
    try:
        # Initialize Anthropic client
        anthropic_client = anthropic.Anthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY')
        )
        
        # Encode to base64
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        
        # Get comprehensive prompt with integrated accounting logic
        prompt = get_invoice_processing_prompt(company_name)
        
        # Get invoice accounting logic for system prompt
        invoice_system_logic = get_accounting_logic("invoice")
        
        # Send to Claude with optimized parameters for structured output
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=18000,  # Increased for line-level account processing
            temperature=0.0,  # Maximum determinism for consistent parsing
            system=f"""You are an expert accountant and data extraction system specialized in CUSTOMER INVOICES and REVENUE transactions with LINE-LEVEL account assignment. Your core behavior is to think and act like a professional accountant who understands double-entry bookkeeping for REVENUE recognition, EQUITY transactions, VAT regulations, and granular revenue categorization.

**INVOICE ACCOUNTING EXPERTISE:**
{invoice_system_logic}

CORE ACCOUNTING BEHAVIOR FOR CUSTOMER INVOICES WITH LINE-LEVEL PROCESSING:
• Always think: "What did we provide?" (CREDIT) and "What do we expect to receive?" (DEBIT)
• Customer invoices: DEBIT accounts receivable (1100), CREDIT revenue account(s)
• ANALYZE EACH LINE ITEM INDIVIDUALLY for revenue categorization:
  - Core business services → CREDIT 4000 (Sales) [DEFAULT for 80% of invoices]
  - Professional consulting → CREDIT 4000 (Sales)
  - Software development → CREDIT 4000 (Sales)
  - Secondary services → CREDIT 4900 (Other sales)
  - Training (if not core business) → CREDIT 4900 (Other sales)
  - Licensing income → CREDIT 4901 (Royalties received)
  - Commission income → CREDIT 4902 (Commissions received)
  - Share allotments → CREDIT 3000 (Share Capital)
• When line items use different accounts → Set main credit_account to "MIXED"
• Ensure debits always equal credits

LINE-LEVEL ACCOUNT ASSIGNMENT EXPERTISE:
• Each line item gets its own account_code and account_name
• Same customer can receive multiple service types requiring different accounts
• Example: Consulting firm billing "Strategic consulting" (4000) AND "Training workshop" (4900)
• Example: Software company selling "Core software" (4000) AND "Optional support" (4900)
• Be precise - "Core business services" use 4000, "Secondary services" use 4900
• DEFAULT: Use 4000 (Sales) for 80% of business invoices unless clearly secondary

CUSTOMER TYPE DETECTION FOR VAT:
• Normal customers = Standard VAT (Output VAT in additional_entries)
• Construction/Property customers = Reverse charge (BOTH Input and Output VAT in additional_entries)
• Share transactions = VAT exempt (no VAT entries)

VAT EXPERTISE FOR CUSTOMER INVOICES:
• Normal customers with VAT = Create Output VAT additional entry (2201)
• Construction/Property customers = Create BOTH Input VAT (2202) AND Output VAT (2201) additional entries
• Share capital transactions = NO VAT entries (exempt)
• When VAT detected for normal customers = MANDATORY additional_entries with Output VAT

OUTPUT FORMAT:
Respond only with valid JSON objects. Never include explanatory text, analysis, or commentary. Always include ALL required fields with their default values when data is missing. Apply your accounting expertise to assign correct debit/credit accounts for every cash inflow transaction AND provide granular line-level account assignments using ONLY the exact account codes provided.""",
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
        
        # Debug: Log first 200 characters of response to identify issues
        print(f"Response preview: {response_text[:200]}...")
        
        return {
            "success": True,
            "raw_response": response_text,
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

def ensure_invoice_structure(invoice):
    """Ensure each invoice has the complete required structure with default values"""
    
    # Define the complete structure with default values
    default_invoice = {
        "invoice_index": 1,
        "page_range": "1",
        "document_classification": {
            "document_type": "customer_invoice",
            "company_position": "issuer",
            "direction_confidence": "low",
            "detection_details": ""
        },
        "company_validation": {
            "expected_company": "",
            "found_companies": [],
            "company_match": "no_match",
            "match_details": ""
        },
        "company_data": {
            "name": "",
            "email": "",
            "phone": "",
            "website": "",
            "street": "",
            "city": "",
            "zip": "",
            "country_code": ""
        },
        "customer_data": {
            "name": "",
            "email": "",
            "phone": "",
            "website": "",
            "street": "",
            "city": "",
            "zip": "",
            "country_code": "",
            "invoice_date": None,
            "due_date": None,
            "invoice_ref": "",
            "payment_reference": "",
            "description": "",
            "subtotal": 0,
            "tax_amount": 0,
            "total_amount": 0,
            "currency_code": "",
            "line_items": []
        },
        "accounting_assignment": {
            "debit_account": "",
            "debit_account_name": "",
            "credit_account": "",
            "credit_account_name": "",
            "vat_treatment": "",
            "requires_reverse_charge": False,
            "additional_entries": []
        },
        "extraction_confidence": {
            "customer_name": "low",
            "total_amount": "low",
            "line_items": "low",
            "dates": "low",
            "company_validation": "low",
            "document_classification": "low"
        },
        "missing_fields": []
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
                        # Ensure arrays exist and validate structure for line_items
                        if key == "line_items" and isinstance(source[key], list):
                            result[key] = [ensure_line_item_structure(item) for item in source[key]]
                        else:
                            result[key] = source[key] if isinstance(source[key], list) else default_value
                    else:
                        result[key] = source[key]
                else:
                    result[key] = default_value
            return result
        else:
            return source if source is not None else defaults
    
    return merge_with_defaults(invoice, default_invoice)

def parse_invoice_response(raw_response):
    """Parse the raw response into structured invoice data with improved error handling"""
    try:
        # Clean the response
        cleaned_response = raw_response.strip()
        
        # Remove any markdown formatting if present
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:]
        elif cleaned_response.startswith('```'):
            cleaned_response = cleaned_response[3:]
            
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3]
            
        cleaned_response = cleaned_response.strip()
        
        # Handle cases where Claude adds explanatory text before JSON
        # Look for the first opening brace
        json_start = cleaned_response.find('{')
        if json_start > 0:
            print(f"Warning: Found text before JSON, removing: {cleaned_response[:json_start][:100]}...")
            cleaned_response = cleaned_response[json_start:]
        
        # Look for the last closing brace (in case there's text after)
        json_end = cleaned_response.rfind('}')
        if json_end > 0 and json_end < len(cleaned_response) - 1:
            print(f"Warning: Found text after JSON, removing: {cleaned_response[json_end+1:][:100]}...")
            cleaned_response = cleaned_response[:json_end + 1]
        
        # Additional cleaning for common issues
        cleaned_response = cleaned_response.strip()
        
        # Parse JSON response
        try:
            result = json.loads(cleaned_response)
            
            # Validate basic structure
            if not isinstance(result, dict):
                raise ValueError("Response is not a JSON object")
            
            # Ensure top-level structure
            if "success" not in result:
                result["success"] = True
            if "total_invoices" not in result:
                result["total_invoices"] = 0
            if "invoices" not in result:
                result["invoices"] = []
            
            # Ensure each invoice has complete structure
            validated_invoices = []
            for i, invoice in enumerate(result["invoices"]):
                validated_invoice = ensure_invoice_structure(invoice)
                # Ensure invoice_index is set correctly
                validated_invoice["invoice_index"] = i + 1
                validated_invoices.append(validated_invoice)
            
            result["invoices"] = validated_invoices
            result["total_invoices"] = len(validated_invoices)
            
            print(f"Successfully parsed and validated response with {len(result['invoices'])} invoices")
            return {
                "success": True,
                "result": result
            }
            
        except json.JSONDecodeError as e:
            # Provide more detailed error information
            error_position = getattr(e, 'pos', 0)
            context_start = max(0, error_position - 50)
            context_end = min(len(cleaned_response), error_position + 50)
            context = cleaned_response[context_start:context_end]
            
            return {
                "success": False,
                "error": f"Invalid JSON response at position {error_position}: {str(e)}",
                "context": context,
                "raw_response": cleaned_response[:1000],
                "cleaned_length": len(cleaned_response)
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Error parsing response: {str(e)}",
            "raw_response": raw_response[:500] if raw_response else "No response"
        }

def main(data):
    """
    Main function for combined invoice processing (splitting + extraction)
    
    Args:
        data (dict): Request data containing:
            - s3_key (str): S3 key path to the PDF document
            - company_name (str): Name of the company issuing the invoices
            - bucket_name (str, optional): S3 bucket name
    
    Returns:
        dict: Processing result with structured invoice data
    """
    try:
        # Validate required fields
        required_fields = ['s3_key', 'company_name']
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            return {
                "success": False,
                "error": f"Missing required fields: {', '.join(missing_fields)}"
            }
        
        s3_key = data['s3_key']
        company_name = data['company_name']
        bucket_name = data.get('bucket_name')
        
        print(f"Processing invoices for company: {company_name}, S3 key: {s3_key}")
        
        # Download PDF from S3
        pdf_content = download_from_s3(s3_key, bucket_name)
        print(f"Downloaded PDF, size: {len(pdf_content)} bytes")
        
        # Process with Claude for combined splitting and extraction
        claude_result = process_invoices_with_claude(pdf_content, company_name)
        
        if not claude_result["success"]:
            return {
                "success": False,
                "error": f"Claude processing failed: {claude_result['error']}"
            }
        
        # Parse the structured response with validation
        parse_result = parse_invoice_response(claude_result["raw_response"])
        
        if not parse_result["success"]:
            return {
                "success": False,
                "error": f"Response parsing failed: {parse_result['error']}",
                "raw_response": claude_result["raw_response"],
                "parse_details": parse_result
            }
        
        result_data = parse_result["result"]
        invoices = result_data.get("invoices", [])
        
        # Validate extracted invoice data
        validation_results = validate_invoice_data(invoices)
        
        # Count invoices with critical issues
        invoices_with_issues = sum(1 for v in validation_results if not v["mandatory_fields_present"])
        total_invoices = len(invoices)
        
        return {
            "success": True,
            "total_invoices": total_invoices,
            "invoices": invoices,
            "processing_summary": {
                "invoices_processed": total_invoices,
                "invoices_with_issues": invoices_with_issues,
                "success_rate": f"{((total_invoices - invoices_with_issues) / total_invoices * 100):.1f}%" if total_invoices > 0 else "0%"
            },
            "validation_results": validation_results,
            "metadata": {
                "company_name": company_name,
                "s3_key": s3_key,
                "token_usage": claude_result["token_usage"]
            }
        }
        
    except Exception as e:
        print(f"Invoice processing error: {str(e)}")
        return {
            "success": False,
            "error": f"Internal processing error: {str(e)}"
        }

def health_check():
    """Health check for the invoice processing service"""
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
            "service": "claude-invoice-processing",
            "version": "3.0",
            "capabilities": [
                "document_splitting",
                "data_extraction", 
                "monetary_calculation",
                "confidence_scoring",
                "revenue_accounting",
                "customer_invoice_processing",
                "construction_property_vat_detection",
                "share_capital_processing",
                "odoo_accounting_integration",
                "normal_vs_reverse_charge_vat",
                "line_level_account_assignment",
                "mixed_service_invoice_handling",
                "granular_revenue_categorization"
            ],
            "anthropic_configured": bool(os.getenv('ANTHROPIC_API_KEY')),
            "aws_configured": bool(os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY')),
            "s3_bucket": os.getenv('S3_BUCKET_NAME', 'company-documents-2025'),
            "odoo_accounting_logic": "integrated"
        }
        
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e)
        }