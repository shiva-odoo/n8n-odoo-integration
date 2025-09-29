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
**COMPANY:** {company_name} (the company issuing these invoices)
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

**DOCUMENT TYPE:** Always set as "customer_invoice" since {company_name} is issuing these invoices.

**COMPANY VALIDATION:**
- Identify ALL company names in the PDF
- Check if any match "{company_name}" (case-insensitive, fuzzy matching)
- Set company_match: "exact_match", "close_match", "no_match", or "unclear"

**MANDATORY FIELDS:**
- Customer name (Essential)
- Invoice Date (Required)
- Due Date or Payment Terms
- Invoice Reference (Invoice number)
- Currency and Amounts
- Description (Overall description of the document including details about line items)
- Line Items with calculations AND individual account assignments
- Debit Account (Account to be debited based on invoice type)
- Credit Account (Account to be credited based on invoice type)

**ACCOUNTING ASSIGNMENT RULES:**

{invoice_logic}

**LINE-LEVEL ACCOUNT ASSIGNMENT:**
Each line item must be assigned to the most appropriate revenue account based on the service/product type:

**Service Type → Account Code Mapping:**
- Software development services → 4000 (Sales - Software Development)
- IT consulting services → 4001 (Sales - IT Consulting)
- Cloud hosting services → 4002 (Sales - Cloud Services)
- Training services → 4003 (Sales - Training)
- Support services → 4004 (Sales - Support)
- License sales → 4005 (Sales - Licenses)
- Hardware sales → 4006 (Sales - Hardware)
- Professional services → 4007 (Sales - Professional Services)
- Subscription services → 4008 (Sales - Subscriptions)
- Maintenance services → 4009 (Sales - Maintenance)

**CRITICAL LINE ITEM ANALYSIS:**
- Analyze EACH line item individually for service type
- Same customer can purchase multiple service types
- Example: IT company billing for both "Software Development" (4000) AND "Cloud Hosting" (4002)
- Example: Service provider selling "Consulting" (4001) AND "Training" (4003)
- Assign the most specific account code for each line item

**CYPRUS VAT REVERSE CHARGE DETECTION (COMPREHENSIVE):**

When {company_name} issues invoices, reverse charge applies when the CUSTOMER falls into ANY of the following categories:

**CATEGORY 1: CONSTRUCTION & PROPERTY SERVICES (to construction companies)**
Look for these indicators in CUSTOMER information:
- Customer name contains: "Construction", "Building", "Property Management", "Real Estate", "Contractor", "Builder"
- Services described as: "Construction services", "Building work", "Property management"
- Document mentions: "Reverse charge applicable", "Customer to account for VAT"

**CATEGORY 2: FOREIGN/EU CUSTOMERS (B2B services)**
Look for these indicators:
- Customer located outside Cyprus (check address, VAT number format)
- EU VAT number format (non-Cyprus)
- Customer country code is not "CY"
- Cross-border B2B sales under general reverse charge rule

**CATEGORY 3: GAS & ELECTRICITY TRADERS (if selling gas/electricity)**
Look for these indicators:
- Customer is a registered gas/electricity trader/merchant
- Customer name contains: "Energy", "Power", "Gas Company", "Electricity Authority"
- Services: Gas or electricity supply to business customers

**CATEGORY 4: SCRAP METAL & WASTE DEALERS (if selling scrap/waste)**
Look for these indicators:
- Customer is a scrap metal dealer or waste management company
- Customer name contains: "Scrap", "Recycling", "Waste Management", "Metal Recycling"

**CATEGORY 5: ELECTRONICS DEALERS (if selling electronics)**
Look for these indicators:
- Selling mobile phones, tablets, laptops, microprocessors, CPUs, gaming consoles
- Customer is an electronics dealer/wholesaler
- High-risk goods subject to reverse charge

**CATEGORY 6: PRECIOUS METALS DEALERS (if selling precious metals)**
Look for these indicators:
- Selling raw or semi-finished precious metals
- Customer is a precious metals dealer
- Customer name contains: "Precious Metals", "Gold", "Silver", "Bullion"

**CATEGORY 7: EU TELECOMMUNICATIONS (if providing telecom services to EU)**
Look for these indicators:
- Providing telecommunications services to EU business customers
- Customer in EU receiving telecom services

**CATEGORY 8: IMMOVABLE PROPERTY TRANSFERS**
Look for these indicators:
- Property sales related to debt restructuring
- Real estate transactions with reverse charge provisions
- Customer is bank or financial institution acquiring property

**VAT TREATMENT LOGIC:**

**NORMAL CUSTOMERS (NO REVERSE CHARGE):**
- Standard VAT treatment for domestic Cyprus customers not in reverse charge categories
- Main transaction: GROSS amount (net + VAT)
- Debit: 1200 (Accounts Receivable) - Full amount including VAT
- Credit: Revenue accounts (per line item) - Net amounts only
- Credit: 2201 (Output VAT) - VAT amount to pay to authorities
- Create ONE additional entry: Output VAT (2201) credit

**REVERSE CHARGE CUSTOMERS (ALL 8 CATEGORIES ABOVE):**
- Main transaction: NET amount only
- Debit: 1200 (Accounts Receivable) - Net amount only
- Credit: Revenue accounts (per line item) - Net amounts
- NO VAT entries needed (customer accounts for VAT)
- Set requires_reverse_charge: true
- Set vat_treatment to appropriate category (e.g., "Foreign Customer Reverse Charge", "Construction Customer Reverse Charge")
- Add note on invoice: "Reverse charge - Customer to account for VAT"

**MIXED LINE ITEMS HANDLING:**
When line items map to different revenue accounts:
- Set credit_account to "MIXED"
- Set credit_account_name to "Mixed Line Items"
- Each line item contains its own account_code and account_name
- VAT handling remains the same (customer-level decision)

**CRITICAL VAT/TAX HANDLING RULE:**

For NORMAL customers with VAT (domestic, not in reverse charge categories):
{{
  "account_code": "2201",
  "account_name": "Output VAT (Sales)",
  "debit_amount": 0,
  "credit_amount": [tax_amount],
  "description": "Output VAT on sales"
}}

For REVERSE CHARGE customers (any of the 8 categories):
- NO additional VAT entries
- Invoice should state "Reverse charge - Customer to account for VAT"
- requires_reverse_charge: true
- Customer is responsible for self-assessing VAT

**DESCRIPTION FIELD:**
- Create an overall description of the document that summarizes the goods/services provided
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
- Single Service Invoice: credit_account="4000", credit_account_name="Sales - Software Development", debit_account="1200"
- Mixed Services Invoice: credit_account="MIXED", credit_account_name="Mixed Line Items", debit_account="1200"
- Normal Domestic Customer with VAT: Standard accounting + Output VAT (2201) in additional_entries
- Reverse Charge Customer: Standard accounting + NO VAT entries (customer accounts for VAT)

**LINE ITEM ACCOUNT ASSIGNMENT EXAMPLES:**
- "Software development services" → account_code="4000", account_name="Sales - Software Development"
- "Cloud hosting monthly fee" → account_code="4002", account_name="Sales - Cloud Services"
- "IT consulting hours" → account_code="4001", account_name="Sales - IT Consulting"
- "Training session" → account_code="4003", account_name="Sales - Training"
- "Technical support" → account_code="4004", account_name="Sales - Support"

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
13. **REVERSE CHARGE DETECTION: Check ALL 8 categories comprehensively before determining VAT treatment**

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
    """Validate extracted invoice data for completeness and accuracy including comprehensive reverse charge detection"""
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
                "4000", "4001", "4002", "4003", "4004", "4005", "4006", "4007", "4008", "4009",
                "4010", "4100", "4200", "4300", "4400", "4500"
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
        
        # COMPREHENSIVE REVERSE CHARGE DETECTION
        accounting_assignment = invoice.get("accounting_assignment", {})
        additional_entries = accounting_assignment.get("additional_entries", [])
        requires_reverse_charge = accounting_assignment.get("requires_reverse_charge", False)
        vat_treatment = accounting_assignment.get("vat_treatment", "")
        
        # Detect if customer falls into any reverse charge category
        customer_name = customer_data.get("name", "").lower()
        customer_country = customer_data.get("country_code", "")
        description = customer_data.get("description", "").lower()
        
        # All line item descriptions combined for analysis
        all_descriptions = " ".join([item.get("description", "").lower() for item in line_items])
        
        # Category detection keywords
        reverse_charge_indicators = {
            "construction": ["construction", "building", "property management", "real estate", 
                           "contractor", "builder"],
            "foreign_customer": customer_country and customer_country != "CY",
            "gas_electricity": ["energy trader", "power trader", "gas merchant", "electricity merchant"],
            "scrap_metal": ["scrap", "recycling", "waste management", "metal recycling"],
            "electronics": ["electronics dealer", "mobile phone wholesaler", "electronics wholesaler"],
            "precious_metals": ["precious metals dealer", "gold dealer", "silver dealer", "bullion dealer"],
            "telecom_eu": ["telecommunications"] and customer_country in ["GR", "DE", "FR", "IT", "ES"],
            "property_transfer": ["debt restructuring", "foreclosure", "property acquisition"]
        }
        
        # Check if customer qualifies for reverse charge
        is_reverse_charge_customer = False
        detected_category = ""
        
        # Check construction/property customer
        if any(keyword in customer_name or keyword in description 
               for keyword in reverse_charge_indicators["construction"]):
            is_reverse_charge_customer = True
            detected_category = "Construction Customer Reverse Charge"
        
        # Check foreign customer
        elif reverse_charge_indicators["foreign_customer"]:
            is_reverse_charge_customer = True
            detected_category = "Foreign Customer Reverse Charge"
        
        # Check gas/electricity trader
        elif any(keyword in customer_name 
                for keyword in reverse_charge_indicators["gas_electricity"]):
            is_reverse_charge_customer = True
            detected_category = "Gas/Electricity Trader Reverse Charge"
        
        # Check scrap metal dealer
        elif any(keyword in customer_name 
                for keyword in reverse_charge_indicators["scrap_metal"]):
            is_reverse_charge_customer = True
            detected_category = "Scrap Metal Dealer Reverse Charge"
        
        # Check electronics dealer
        elif any(keyword in customer_name 
                for keyword in reverse_charge_indicators["electronics"]):
            is_reverse_charge_customer = True
            detected_category = "Electronics Dealer Reverse Charge"
        
        # Check precious metals dealer
        elif any(keyword in customer_name 
                for keyword in reverse_charge_indicators["precious_metals"]):
            is_reverse_charge_customer = True
            detected_category = "Precious Metals Dealer Reverse Charge"
        
        # Check EU telecom
        elif any(keyword in description 
                for keyword in reverse_charge_indicators["telecom_eu"]):
            is_reverse_charge_customer = True
            detected_category = "Telecommunications Reverse Charge"
        
        # Check property transfer
        elif any(keyword in description or keyword in all_descriptions 
                for keyword in reverse_charge_indicators["property_transfer"]):
            is_reverse_charge_customer = True
            detected_category = "Property Transfer Reverse Charge"
        
        # Validate VAT handling based on detection
        if tax_amount > 0:
            if is_reverse_charge_customer:
                # Should NOT have any VAT entries (customer accounts for VAT)
                if not requires_reverse_charge:
                    invoice_validation["issues"].append(
                        f"Customer qualifies for reverse charge ({detected_category}) but requires_reverse_charge is false"
                    )
                
                if additional_entries:
                    output_vat_entries = [e for e in additional_entries if e.get("account_code") == "2201"]
                    if output_vat_entries:
                        invoice_validation["issues"].append(
                            f"Reverse charge customer ({detected_category}) should not have Output VAT entries - customer accounts for VAT"
                        )
            else:
                # Normal domestic customer - should have Output VAT entry
                if requires_reverse_charge:
                    invoice_validation["warnings"].append(
                        "Customer marked as reverse charge but doesn't match any reverse charge category"
                    )
                
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
        elif tax_amount == 0 and is_reverse_charge_customer:
            # Reverse charge customer with no VAT shown - this is correct
            if not requires_reverse_charge:
                invoice_validation["warnings"].append(
                    f"Customer qualifies for reverse charge ({detected_category}) but requires_reverse_charge is false"
                )
        
        # Check account code consistency for main accounting assignment
        debit_account = accounting_assignment.get("debit_account", "")
        
        valid_debit_accounts = ["1200", "1000", "1100"]  # Accounts receivable and bank accounts
        valid_revenue_accounts_with_mixed = valid_revenue_accounts + ["MIXED"]
        
        if credit_account and credit_account not in valid_revenue_accounts_with_mixed:
            invoice_validation["issues"].append(f"Invalid credit account code: {credit_account}")
        
        if debit_account and debit_account not in valid_debit_accounts:
            invoice_validation["issues"].append(f"Invalid debit account code: {debit_account}")
        
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
            max_tokens=18000,
            temperature=0.0,
            system=f"""You are an expert accountant and data extraction system specialized in CUSTOMER INVOICES and REVENUE transactions with LINE-LEVEL account assignment and COMPREHENSIVE Cyprus VAT reverse charge detection. Your core behavior is to think and act like a professional accountant who understands double-entry bookkeeping for REVENUE recognition, VAT regulations including ALL reverse charge categories, and granular revenue categorization.

**INVOICE ACCOUNTING EXPERTISE:**
{invoice_system_logic}

CORE ACCOUNTING BEHAVIOR FOR CUSTOMER INVOICES WITH LINE-LEVEL PROCESSING:
• Always think: "What did we provide?" (CREDIT) and "What do we receive?" (DEBIT)
• Customer invoices: DEBIT accounts receivable (1200), CREDIT revenue account(s)
• ANALYZE EACH LINE ITEM INDIVIDUALLY for revenue categorization:
  - Software development → CREDIT 4000 (Sales - Software Development)
  - IT consulting → CREDIT 4001 (Sales - IT Consulting)
  - Cloud services → CREDIT 4002 (Sales - Cloud Services)
  - Training → CREDIT 4003 (Sales - Training)
  - Support → CREDIT 4004 (Sales - Support)
  - Mixed services from same customer → Use appropriate account per line item
• When line items use different accounts → Set main credit_account to "MIXED"
• Ensure debits always equal credits

LINE-LEVEL ACCOUNT ASSIGNMENT EXPERTISE:
• Each line item gets its own account_code and account_name
• Same customer can purchase multiple service types requiring different accounts
• Example: Customer buying "Software Development" (4000) AND "Cloud Hosting" (4002)
• Example: Client purchasing "Consulting" (4001) AND "Training" (4003)
• Be precise with revenue categorization

COMPREHENSIVE CYPRUS VAT REVERSE CHARGE DETECTION FOR INVOICES:
You must check ALL 8 categories to determine if CUSTOMER qualifies for reverse charge:

1. CONSTRUCTION & PROPERTY CUSTOMERS: Construction companies, builders, property management firms
2. FOREIGN/EU CUSTOMERS: Any customer located outside Cyprus (check country code)
3. GAS & ELECTRICITY TRADERS: If selling gas/electricity to registered traders
4. SCRAP METAL DEALERS: If selling scrap/waste to dealers
5. ELECTRONICS DEALERS: If selling electronics to dealers/wholesalers
6. PRECIOUS METALS DEALERS: If selling precious metals to dealers
7. EU TELECOM CUSTOMERS: If providing telecom services to EU businesses
8. PROPERTY TRANSFERS: Real estate transactions with reverse charge

CRITICAL REVERSE CHARGE RULES FOR INVOICES:
• If customer matches ANY of the 8 categories:
  - Set requires_reverse_charge: true
  - Set vat_treatment to specific category (e.g., "Foreign Customer Reverse Charge")
  - DO NOT create any VAT entries (customer accounts for VAT themselves)
  - Invoice amount should be NET only
  - Debit account 1200 with NET amount only
  - Add note: "Reverse charge - Customer to account for VAT"

• If customer is normal domestic (not in any category) with VAT:
  - Set requires_reverse_charge: false
  - Set vat_treatment: "Standard VAT"
  - Create Output VAT (2201) entry in additional_entries
  - Invoice amount is GROSS (net + VAT)
  - Debit account 1200 with GROSS amount

OUTPUT FORMAT:
Respond only with valid JSON objects. Never include explanatory text, analysis, or commentary. Always include ALL required fields with their default values when data is missing. Apply your accounting expertise to assign correct debit/credit accounts for every revenue transaction AND provide granular line-level account assignments using ONLY the exact account codes provided. Thoroughly check ALL 8 reverse charge categories before determining VAT treatment.""",
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
            "version": "5.0",
            "capabilities": [
                "document_splitting",
                "data_extraction", 
                "monetary_calculation",
                "confidence_scoring",
                "customer_invoice_processing",
                "comprehensive_reverse_charge_detection",
                "odoo_accounting_integration",
                "8_category_reverse_charge_support",
                "line_level_account_assignment",
                "mixed_service_invoice_handling",
                "granular_revenue_categorization",
                "construction_customer_detection",
                "foreign_customer_detection",
                "gas_electricity_trader_detection",
                "scrap_metal_dealer_detection",
                "electronics_dealer_detection",
                "precious_metals_dealer_detection",
                "eu_telecom_customer_detection",
                "property_transfer_detection"
            ],
            "anthropic_configured": bool(os.getenv('ANTHROPIC_API_KEY')),
            "aws_configured": bool(os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY')),
            "s3_bucket": os.getenv('S3_BUCKET_NAME', 'company-documents-2025'),
            "odoo_accounting_logic": "integrated",
            "vat_compliance": "Cyprus VAT Law - All 8 Reverse Charge Categories (Invoice Perspective)"
        }
        
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e)
        }