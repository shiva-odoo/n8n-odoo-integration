import boto3
import base64
import anthropic
import os
import json
import re
from odoo_accounting_logic import main as get_accounting_logic

def get_bill_processing_prompt(company_name):
    """Create comprehensive bill processing prompt that combines splitting and extraction"""
    
    # Get bill accounting logic with VAT rules
    bill_logic = get_accounting_logic("bill")
    
    return f"""You are an advanced bill processing AI. Your task is to analyze a multi-bill PDF document and return structured JSON data.

**CRITICAL INSTRUCTION: Respond with ONLY the JSON object. Do not include any explanatory text, commentary, analysis, or markdown formatting before or after the JSON. Start your response immediately with the opening curly brace {{.**

**INPUT:** Multi-bill PDF document
**COMPANY:** {company_name} (the company receiving these bills)
**OUTPUT:** Raw JSON object only

**DOCUMENT SPLITTING RULES (Priority Order):**
1. **PAGE INDICATOR RULE (HIGHEST PRIORITY):**
   - "Page 1 of 1" multiple times = Multiple separate single-page bills
   - "Page 1 of 2", "Page 2 of 2" = One two-page bill
   - "Page 1 of 3", "Page 2 of 3", "Page 3 of 3" = One three-page bill

2. **INVOICE NUMBER RULE (SECOND PRIORITY):**
   - Different invoice numbers = Different bills
   - Same invoice number across pages = Same bill

3. **HEADER COUNT RULE (THIRD PRIORITY):**
   - Multiple "INVOICE" headers typically = Multiple bills

**DATA EXTRACTION FOR EACH BILL:**

**DOCUMENT TYPE:** Always set as "vendor_bill" since {company_name} is receiving these bills.

**COMPANY VALIDATION:**
- Identify ALL company names in the PDF
- Check if any match "{company_name}" (case-insensitive, fuzzy matching)
- Set company_match: "exact_match", "close_match", "no_match", or "unclear"

**MANDATORY FIELDS:**
- Vendor name (Essential)
- Bill Date (Required)
- Due Date or Payment Terms
- Bill Reference (Invoice number)
- Currency and Amounts
- Description (Overall description of the document including details about line items)
- Line Items with calculations AND individual account assignments
- Credit Account (Account to be credited based on bill type)
- Debit Account (Account to be debited based on bill type)

**ACCOUNTING ASSIGNMENT RULES:**

{bill_logic}

**LINE-LEVEL ACCOUNT ASSIGNMENT:**
Each line item must be assigned to the most appropriate expense account based on the service/product type:

**Service Type → Account Code Mapping:**
- Legal services, law firm fees → 7600 (Legal fees)
- Accounting, bookkeeping, tax services → 7601 (Audit and accountancy fees)  
- Business consulting, advisory → 7602 (Consultancy fees)
- Other professional services → 7603 (Professional fees)
- Office/warehouse rent → 7100 (Rent)
- Mixed utility bills → 7190 (Utilities)
- Pure electricity bills → 7200 (Electricity)
- Pure gas bills → 7201 (Gas)
- Water bills → 7102 (Water rates)
- Software subscriptions, SaaS → 7508 (Computer software)
- Internet, broadband, ISP → 7503 (Internet)
- Phone, mobile, telecom → 7502 (Telephone)
- Business travel, flights, transport → 7400 (Traveling)
- Equipment repairs, maintenance → 7800 (Repairs and renewals)
- Shipping, freight, courier → 5100 (Carriage)
- Government fees, permits → 8200 (Other non-operating income or expenses)

**CRITICAL LINE ITEM ANALYSIS:**
- Analyze EACH line item individually for service type
- Same vendor can provide multiple service types
- Example: Telecom company billing for both "Internet service" (7503) AND "Mobile WiFi" (7502)
- Example: Office supplier selling "Stationery" (7504) AND "Computer equipment" (0090)
- Assign the most specific account code for each line item

**CYPRUS VAT REVERSE CHARGE DETECTION (COMPREHENSIVE):**

The reverse charge mechanism applies when the vendor/supplier falls into ANY of the following categories:

**CATEGORY 1: CONSTRUCTION & PROPERTY SERVICES**
Look for these indicators:
- Vendor name contains: "Construction", "Building", "Property Management", "Real Estate", "Contractor", "Builder"
- Services described as: "Construction services", "Building work", "Property management", "Repair services", "Maintenance services", "Demolition", "Installation services"
- Document mentions: "Reverse charge applicable", "Customer to account for VAT"

**CATEGORY 2: FOREIGN/EU SERVICE PROVIDERS**
Look for these indicators:
- Vendor located outside Cyprus (check address, VAT number format)
- EU VAT number format (non-Cyprus)
- Services provided from abroad: Legal, Accounting, Consulting, IT services, Marketing, Design, Professional services, Advisory services, Royalties, License fees
- Cross-border B2B services under general reverse charge rule

**CATEGORY 3: GAS & ELECTRICITY SUPPLIERS**
Look for these indicators:
- Pure gas supply to registered business
- Pure electricity supply to registered traders/merchants
- Utility companies selling gas/electricity (not mixed utility bills to consumers)
- Vendor name contains: "Energy", "Power", "Gas Company", "Electricity Authority"

**CATEGORY 4: SCRAP METAL & WASTE DEALERS**
Look for these indicators:
- Scrap metal supplies
- Waste materials supplies
- Vendor name contains: "Scrap", "Recycling", "Waste Management", "Metal Recycling"
- Products: Scrap iron, aluminum, copper, steel, waste materials

**CATEGORY 5: ELECTRONICS SUPPLIERS (HIGH-RISK GOODS)**
Look for these indicators:
- Mobile phones (smartphones, cell phones)
- Tablets and PC tablets
- Laptops and computers
- Microprocessors and CPUs
- Integrated circuits and chips
- Gaming consoles (PlayStation, Xbox, Nintendo)
- Other devices operating in networks
- Vendor selling electronics in bulk/wholesale

**CATEGORY 6: PRECIOUS METALS DEALERS**
Look for these indicators:
- Raw or semi-finished precious metals
- Gold, silver, platinum supplies
- Bullion dealers
- Vendor name contains: "Precious Metals", "Gold", "Silver", "Bullion"
- Products: Gold bars, silver ingots, precious metal materials

**CATEGORY 7: TELECOMMUNICATIONS SERVICES (EU)**
Look for these indicators:
- EU-based telecom service providers
- International telecommunications services
- Services from EU suppliers for Cyprus use
- Vendor name contains international telecom indicators

**CATEGORY 8: IMMOVABLE PROPERTY TRANSFERS**
Look for these indicators:
- Property transfers related to debt restructuring
- Foreclosure sales
- Debt-for-asset swaps
- Forced property transfers
- Bank repossessions

**VAT TREATMENT LOGIC:**

**NORMAL VENDORS (NO REVERSE CHARGE):**
- Standard VAT treatment for domestic Cyprus suppliers not in reverse charge categories
- Main transaction: GROSS amount (net + VAT)
- Debit: Expense accounts (per line item) - Net amounts only
- Debit: 2202 (Input VAT) - VAT amount reclaimable
- Credit: 2100 (Accounts Payable) - Full amount including VAT
- Create ONE additional entry: Input VAT (2202) debit

**REVERSE CHARGE VENDORS (ALL 8 CATEGORIES ABOVE):**
- Main transaction: NET amount only
- Debit: Expense accounts (per line item) - Net amounts
- Credit: 2100 (Accounts Payable) - Net amount only
- Create TWO VAT entries in additional_entries:
  - Input VAT (2202) - Debit VAT amount (reclaimable)
  - Output VAT (2201) - Credit VAT amount (owed to authorities)
- Set requires_reverse_charge: true
- Set vat_treatment to appropriate category (e.g., "Construction Reverse Charge", "Foreign Services Reverse Charge", "Electronics Reverse Charge")

**MIXED LINE ITEMS HANDLING:**
When line items map to different expense accounts:
- Set debit_account to "MIXED"
- Set debit_account_name to "Mixed Line Items"
- Each line item contains its own account_code and account_name
- VAT handling remains the same (vendor-level decision)

**CRITICAL VAT/TAX HANDLING RULE:**

For NORMAL vendors with VAT (domestic, not in reverse charge categories):
{{
  "account_code": "2202",
  "account_name": "Input VAT (Purchases)",
  "debit_amount": [tax_amount],
  "credit_amount": 0,
  "description": "Input VAT on purchase"
}}

For REVERSE CHARGE vendors (any of the 8 categories) with VAT:
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

**DESCRIPTION FIELD:**
- Create an overall description of the document that summarizes the goods/services provided
- Include key details from line item descriptions
- Can be a shortened combination of the description fields from each line item
- Should give a clear understanding of what the bill is for

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
  "total_bills": <number>,
  "bills": [
    {{
      "bill_index": 1,
      "page_range": "1",
      "document_classification": {{
        "document_type": "vendor_bill",
        "company_position": "recipient",
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
      "vendor_data": {{
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
        "vendor_ref": "",
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
        "vendor_name": "low",
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
- Single Service Bill: debit_account="7602", debit_account_name="Consultancy fees", credit_account="2100"
- Mixed Services Bill: debit_account="MIXED", debit_account_name="Mixed Line Items", credit_account="2100"
- Normal Domestic Vendor with VAT: Standard accounting + Input VAT (2202) in additional_entries
- Reverse Charge Vendor with VAT: Standard accounting + BOTH Input VAT (2202) AND Output VAT (2201) in additional_entries

**LINE ITEM ACCOUNT ASSIGNMENT EXAMPLES:**
- "Legal consultation services" → account_code="7600", account_name="Legal fees"
- "Internet broadband service" → account_code="7503", account_name="Internet"  
- "Mobile WiFi service" → account_code="7502", account_name="Telephone"
- "Office supplies" → account_code="7504", account_name="Office stationery"
- "Computer repair" → account_code="7800", account_name="Repairs and renewals"

**ABSOLUTE REQUIREMENTS:**
1. Every field listed above MUST be present in every bill object
2. Use the exact default values shown when data is not found
3. Never omit fields - always include them with default values
4. String fields default to empty string ""
5. Number fields default to 0
6. Date fields default to null
7. Array fields default to empty array []
8. Confidence levels: use "high", "medium", or "low" only
9. Company match: use "exact_match", "close_match", "no_match", or "unclear" only
10. **ACCOUNT CODE CONSISTENCY: Use ONLY the exact account codes and names from the bill logic above**
11. **LINE ITEM ACCOUNT ASSIGNMENT: MANDATORY for every line item - analyze each service individually**
12. **MIXED BILLS: When line items have different account codes, set debit_account="MIXED"**
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

def validate_bill_data(bills):
    """Validate extracted bill data for completeness and accuracy including comprehensive reverse charge detection"""
    validation_results = []
    
    for bill in bills:
        bill_validation = {
            "bill_index": bill.get("bill_index", 0),
            "issues": [],
            "warnings": [],
            "mandatory_fields_present": True,
            "structure_complete": True
        }
        
        vendor_data = bill.get("vendor_data", {})
        
        # Check mandatory fields (content validation, not structure)
        mandatory_content = {
            "vendor_name": vendor_data.get("name", ""),
            "total_amount": vendor_data.get("total_amount", 0),
            "invoice_date": vendor_data.get("invoice_date"),
            "description": vendor_data.get("description", "")
        }
        
        for field_name, field_value in mandatory_content.items():
            if not field_value or field_value == "":
                bill_validation["issues"].append(f"Missing content for mandatory field: {field_name}")
                bill_validation["mandatory_fields_present"] = False
        
        # Check line items and their account assignments
        line_items = vendor_data.get("line_items", [])
        if not line_items:
            bill_validation["warnings"].append("No line items found")
        else:
            # Validate line item account assignments
            valid_expense_accounts = [
                "7602", "7600", "7601", "7603", "7100", "7190", "7200", "7201", "7102",
                "7508", "7503", "7502", "7400", "7800", "5100", "8200", "7104", "7700",
                "7506", "7005", "6201", "6100", "1000", "1020", "5000", "6002", "7402",
                "7401", "7406", "7500", "7501", "7504", "7300", "7301", "7303", "1090", "1160"
            ]
            
            line_item_accounts = set()
            for i, item in enumerate(line_items):
                account_code = item.get("account_code", "")
                account_name = item.get("account_name", "")
                
                if not account_code:
                    bill_validation["issues"].append(f"Line item {i+1} missing account_code")
                elif account_code not in valid_expense_accounts:
                    bill_validation["issues"].append(f"Line item {i+1} has invalid account code: {account_code}")
                
                if not account_name:
                    bill_validation["issues"].append(f"Line item {i+1} missing account_name")
                
                if account_code:
                    line_item_accounts.add(account_code)
            
            # Check if bill is mixed (multiple account codes)
            accounting_assignment = bill.get("accounting_assignment", {})
            debit_account = accounting_assignment.get("debit_account", "")
            
            if len(line_item_accounts) > 1 and debit_account != "MIXED":
                bill_validation["warnings"].append(
                    f"Multiple account codes detected in line items ({len(line_item_accounts)}) but debit_account is not 'MIXED'"
                )
            elif len(line_item_accounts) == 1 and debit_account == "MIXED":
                bill_validation["warnings"].append(
                    "Only one account code in line items but debit_account is set to 'MIXED'"
                )
        
        # Check monetary consistency
        subtotal = vendor_data.get("subtotal", 0)
        tax_amount = vendor_data.get("tax_amount", 0)
        total_amount = vendor_data.get("total_amount", 0)
        
        if total_amount > 0:
            calculated_total = subtotal + tax_amount
            if abs(calculated_total - total_amount) > 0.01:
                bill_validation["warnings"].append(
                    f"Amount mismatch: calculated {calculated_total}, document shows {total_amount}"
                )
        
        # COMPREHENSIVE REVERSE CHARGE DETECTION - FIXED
        accounting_assignment = bill.get("accounting_assignment", {})
        additional_entries = accounting_assignment.get("additional_entries", [])
        requires_reverse_charge = accounting_assignment.get("requires_reverse_charge", False)
        vat_treatment = accounting_assignment.get("vat_treatment", "")
        
        # Detect if vendor falls into any reverse charge category
        vendor_name = vendor_data.get("name", "").lower()
        vendor_country = vendor_data.get("country_code", "")
        description = vendor_data.get("description", "").lower()
        
        # All line item descriptions combined for analysis
        all_descriptions = " ".join([item.get("description", "").lower() for item in line_items])
        
        # Check if vendor qualifies for reverse charge
        is_reverse_charge_vendor = False
        detected_category = ""
        
        # Category 1: Check construction/property
        construction_keywords = ["construction", "building", "property management", "real estate", 
                                "contractor", "builder", "repair services", "maintenance services", 
                                "demolition", "installation services"]
        if any(keyword in vendor_name or keyword in description or keyword in all_descriptions 
               for keyword in construction_keywords):
            is_reverse_charge_vendor = True
            detected_category = "Construction/Property Reverse Charge"
        
        # Category 2: Check foreign services
        elif vendor_country and vendor_country != "CY":
            is_reverse_charge_vendor = True
            detected_category = "Foreign Services Reverse Charge"
        
        # Category 3: Check gas/electricity
        elif any(keyword in vendor_name or keyword in description 
                for keyword in ["energy", "power", "gas company", "electricity authority", 
                               "natural gas", "electric power"]):
            is_reverse_charge_vendor = True
            detected_category = "Gas/Electricity Reverse Charge"
        
        # Category 4: Check scrap metal
        elif any(keyword in vendor_name or keyword in all_descriptions 
                for keyword in ["scrap", "recycling", "waste management", "metal recycling", 
                               "scrap metal", "waste materials"]):
            is_reverse_charge_vendor = True
            detected_category = "Scrap Metal Reverse Charge"
        
        # Category 5: Check electronics
        elif any(keyword in vendor_name or keyword in all_descriptions 
                for keyword in ["mobile phone", "smartphone", "tablet", "laptop", "microprocessor", 
                               "cpu", "integrated circuit", "gaming console", "playstation", "xbox"]):
            is_reverse_charge_vendor = True
            detected_category = "Electronics Reverse Charge"
        
        # Category 6: Check precious metals
        elif any(keyword in vendor_name or keyword in all_descriptions 
                for keyword in ["precious metals", "gold", "silver", "platinum", "bullion", 
                               "gold bars", "silver ingots"]):
            is_reverse_charge_vendor = True
            detected_category = "Precious Metals Reverse Charge"
        
        # Category 7: Check EU telecom - FIXED LOGIC
        elif vendor_country in ["GR", "DE", "FR", "IT", "ES"] and \
             any(keyword in vendor_name or keyword in description 
                 for keyword in ["telecommunications", "telecom services"]):
            is_reverse_charge_vendor = True
            detected_category = "Telecommunications Reverse Charge"
        
        # Category 8: Check property transfer
        elif any(keyword in description or keyword in all_descriptions 
                for keyword in ["debt restructuring", "foreclosure", "debt-for-asset", 
                               "property transfer", "bank repossession"]):
            is_reverse_charge_vendor = True
            detected_category = "Property Transfer Reverse Charge"
        
        # Validate VAT handling based on detection
        if tax_amount > 0:
            if is_reverse_charge_vendor:
                # Should have BOTH Input and Output VAT entries
                if not requires_reverse_charge:
                    bill_validation["issues"].append(
                        f"Vendor qualifies for reverse charge ({detected_category}) but requires_reverse_charge is false"
                    )
                
                if not additional_entries:
                    bill_validation["issues"].append(
                        f"Vendor qualifies for reverse charge ({detected_category}) but no additional_entries created"
                    )
                else:
                    input_vat_entries = [e for e in additional_entries if e.get("account_code") == "2202"]
                    output_vat_entries = [e for e in additional_entries if e.get("account_code") == "2201"]
                    
                    if not input_vat_entries:
                        bill_validation["issues"].append(
                            f"Reverse charge vendor ({detected_category}) missing Input VAT (2202) entry"
                        )
                    
                    if not output_vat_entries:
                        bill_validation["issues"].append(
                            f"Reverse charge vendor ({detected_category}) missing Output VAT (2201) entry"
                        )
            else:
                # Normal domestic vendor - should have only Input VAT entry
                if requires_reverse_charge:
                    bill_validation["warnings"].append(
                        "Vendor marked as reverse charge but doesn't match any reverse charge category"
                    )
                
                if not additional_entries:
                    bill_validation["issues"].append(
                        "Tax amount detected for normal vendor but no additional_entries created"
                    )
                else:
                    input_vat_entries = [e for e in additional_entries if e.get("account_code") == "2202"]
                    output_vat_entries = [e for e in additional_entries if e.get("account_code") == "2201"]
                    
                    if not input_vat_entries:
                        bill_validation["issues"].append(
                            "Tax amount detected for normal vendor but missing Input VAT (2202) entry"
                        )
                    
                    if output_vat_entries:
                        bill_validation["warnings"].append(
                            "Normal vendor has Output VAT (2201) entry - should only be for reverse charge"
                        )
        
        # Check account code consistency for main accounting assignment
        credit_account = accounting_assignment.get("credit_account", "")
        
        valid_credit_accounts = ["2100", "2201", "2202"]
        valid_expense_accounts_with_mixed = valid_expense_accounts + ["MIXED"]
        
        if debit_account and debit_account not in valid_expense_accounts_with_mixed:
            bill_validation["issues"].append(f"Invalid debit account code: {debit_account}")
        
        if credit_account and credit_account not in valid_credit_accounts:
            bill_validation["issues"].append(f"Invalid credit account code: {credit_account}")
        
        # Check confidence levels
        confidence = bill.get("extraction_confidence", {})
        low_confidence_fields = [
            field for field, conf in confidence.items() 
            if conf == "low"
        ]
        
        if low_confidence_fields:
            bill_validation["warnings"].append(
                f"Low confidence fields: {', '.join(low_confidence_fields)}"
            )
        
        validation_results.append(bill_validation)
    
    return validation_results

def process_bills_with_claude(pdf_content, company_name):
    """Process PDF document with Claude for bill splitting and extraction"""
    try:
        # Initialize Anthropic client
        anthropic_client = anthropic.Anthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY')
        )
        
        # Encode to base64
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        
        # Get comprehensive prompt with integrated accounting logic
        prompt = get_bill_processing_prompt(company_name)
        
        # Get bill accounting logic for system prompt
        bill_system_logic = get_accounting_logic("bill")
        
        # Send to Claude with optimized parameters for structured output
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=18000,
            temperature=0.0,
            system=f"""You are an expert accountant and data extraction system specialized in VENDOR BILLS and EXPENSE transactions with LINE-LEVEL account assignment and COMPREHENSIVE Cyprus VAT reverse charge detection. Your core behavior is to think and act like a professional accountant who understands double-entry bookkeeping for EXPENSE recognition, VAT regulations including ALL reverse charge categories, and granular expense categorization.

**BILL ACCOUNTING EXPERTISE:**
{bill_system_logic}

CORE ACCOUNTING BEHAVIOR FOR VENDOR BILLS WITH LINE-LEVEL PROCESSING:
• Always think: "What did we receive?" (DEBIT) and "What do we owe?" (CREDIT)
• Vendor bills: DEBIT expense account(s), CREDIT accounts payable (2100)
• ANALYZE EACH LINE ITEM INDIVIDUALLY for expense categorization:
  - Legal services → DEBIT 7600 (Legal fees)
  - Accounting services → DEBIT 7601 (Audit and accountancy fees)
  - Business consulting → DEBIT 7602 (Consultancy fees)
  - Internet services → DEBIT 7503 (Internet)
  - Mobile/phone services → DEBIT 7502 (Telephone)
  - Mixed services from same vendor → Use appropriate account per line item
• When line items use different accounts → Set main debit_account to "MIXED"
• Ensure debits always equal credits

LINE-LEVEL ACCOUNT ASSIGNMENT EXPERTISE:
• Each line item gets its own account_code and account_name
• Same vendor can provide multiple service types requiring different accounts
• Example: Telecom company billing Internet (7503) AND Mobile services (7502)
• Example: Office supplier selling Stationery (7504) AND Equipment (0090)
• Be precise - "Mobile WiFi" is telecommunications (7502), not internet (7503)

COMPREHENSIVE CYPRUS VAT REVERSE CHARGE DETECTION:
You must check ALL 8 categories for reverse charge eligibility:

1. CONSTRUCTION & PROPERTY: Construction services, building work, property management, real estate, repairs, maintenance, demolition, installation
2. FOREIGN/EU SERVICES: Any services from vendors located outside Cyprus (check country code, VAT number, address)
3. GAS & ELECTRICITY: Gas and electricity supplies to registered business traders
4. SCRAP METAL & WASTE: Scrap metal dealers, waste materials, recycling companies
5. ELECTRONICS: Mobile phones, tablets, laptops, microprocessors, CPUs, integrated circuits, gaming consoles
6. PRECIOUS METALS: Gold, silver, platinum, raw/semi-finished precious metals, bullion
7. EU TELECOMMUNICATIONS: Telecom services from EU suppliers
8. PROPERTY TRANSFERS: Foreclosures, debt restructuring, debt-for-asset swaps, bank repossessions

CRITICAL REVERSE CHARGE RULES:
• If vendor matches ANY of the 8 categories AND has VAT:
  - Set requires_reverse_charge: true
  - Set vat_treatment to specific category (e.g., "Electronics Reverse Charge")
  - Create BOTH Input VAT (2202) AND Output VAT (2201) entries
  - Main transaction amount should be NET only
  - Credit account 2100 with NET amount only

• If vendor is normal domestic (not in any category) with VAT:
  - Set requires_reverse_charge: false
  - Set vat_treatment: "Standard VAT"
  - Create ONLY Input VAT (2202) entry
  - Main transaction amount is GROSS (net + VAT)
  - Credit account 2100 with GROSS amount

OUTPUT FORMAT:
Respond only with valid JSON objects. Never include explanatory text, analysis, or commentary. Always include ALL required fields with their default values when data is missing. Apply your accounting expertise to assign correct debit/credit accounts for every expense transaction AND provide granular line-level account assignments using ONLY the exact account codes provided. Thoroughly check ALL 8 reverse charge categories before determining VAT treatment.""",
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

def ensure_bill_structure(bill):
    """Ensure each bill has the complete required structure with default values"""
    
    # Define the complete structure with default values
    default_bill = {
        "bill_index": 1,
        "page_range": "1",
        "document_classification": {
            "document_type": "vendor_bill",
            "company_position": "recipient",
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
        "vendor_data": {
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
            "vendor_ref": "",
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
            "vendor_name": "low",
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
    
    return merge_with_defaults(bill, default_bill)

def parse_bill_response(raw_response):
    """Parse the raw response into structured bill data with improved error handling"""
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
            if "total_bills" not in result:
                result["total_bills"] = 0
            if "bills" not in result:
                result["bills"] = []
            
            # Ensure each bill has complete structure
            validated_bills = []
            for i, bill in enumerate(result["bills"]):
                validated_bill = ensure_bill_structure(bill)
                # Ensure bill_index is set correctly
                validated_bill["bill_index"] = i + 1
                validated_bills.append(validated_bill)
            
            result["bills"] = validated_bills
            result["total_bills"] = len(validated_bills)
            
            print(f"Successfully parsed and validated response with {len(result['bills'])} bills")
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
    Main function for combined bill processing (splitting + extraction)
    
    Args:
        data (dict): Request data containing:
            - s3_key (str): S3 key path to the PDF document
            - company_name (str): Name of the company receiving the bills
            - bucket_name (str, optional): S3 bucket name
    
    Returns:
        dict: Processing result with structured bill data
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
        
        print(f"Processing bills for company: {company_name}, S3 key: {s3_key}")
        
        # Download PDF from S3
        pdf_content = download_from_s3(s3_key, bucket_name)
        print(f"Downloaded PDF, size: {len(pdf_content)} bytes")
        
        # Process with Claude for combined splitting and extraction
        claude_result = process_bills_with_claude(pdf_content, company_name)
        
        if not claude_result["success"]:
            return {
                "success": False,
                "error": f"Claude processing failed: {claude_result['error']}"
            }
        
        # Parse the structured response with validation
        parse_result = parse_bill_response(claude_result["raw_response"])
        
        if not parse_result["success"]:
            return {
                "success": False,
                "error": f"Response parsing failed: {parse_result['error']}",
                "raw_response": claude_result["raw_response"],
                "parse_details": parse_result
            }
        
        result_data = parse_result["result"]
        bills = result_data.get("bills", [])
        
        # Validate extracted bill data
        validation_results = validate_bill_data(bills)
        
        # Count bills with critical issues
        bills_with_issues = sum(1 for v in validation_results if not v["mandatory_fields_present"])
        total_bills = len(bills)
        
        return {
            "success": True,
            "total_bills": total_bills,
            "bills": bills,
            "processing_summary": {
                "bills_processed": total_bills,
                "bills_with_issues": bills_with_issues,
                "success_rate": f"{((total_bills - bills_with_issues) / total_bills * 100):.1f}%" if total_bills > 0 else "0%"
            },
            "validation_results": validation_results,
            "metadata": {
                "company_name": company_name,
                "s3_key": s3_key,
                "token_usage": claude_result["token_usage"]
            }
        }
        
    except Exception as e:
        print(f"Bill processing error: {str(e)}")
        return {
            "success": False,
            "error": f"Internal processing error: {str(e)}"
        }

def health_check():
    """Health check for the bill processing service"""
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
            "service": "claude-bill-processing",
            "version": "5.0",
            "capabilities": [
                "document_splitting",
                "data_extraction", 
                "monetary_calculation",
                "confidence_scoring",
                "vendor_bill_processing",
                "comprehensive_reverse_charge_detection",
                "odoo_accounting_integration",
                "8_category_reverse_charge_support",
                "line_level_account_assignment",
                "mixed_service_bill_handling",
                "granular_expense_categorization",
                "construction_property_detection",
                "foreign_services_detection",
                "gas_electricity_detection",
                "scrap_metal_detection",
                "electronics_detection",
                "precious_metals_detection",
                "eu_telecom_detection",
                "property_transfer_detection"
            ],
            "anthropic_configured": bool(os.getenv('ANTHROPIC_API_KEY')),
            "aws_configured": bool(os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY')),
            "s3_bucket": os.getenv('S3_BUCKET_NAME', 'company-documents-2025'),
            "odoo_accounting_logic": "integrated",
            "vat_compliance": "Cyprus VAT Law - All 8 Reverse Charge Categories"
        }
        
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e)
        }