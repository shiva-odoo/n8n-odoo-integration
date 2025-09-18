import boto3
import base64
import anthropic
import os
import json
import re

def get_invoice_processing_prompt(company_name):
    """Create comprehensive invoice processing prompt that combines splitting and extraction"""
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
- Line Items with calculations
- Credit Account (Account to be credited based on transaction type)
- Debit Account (Account to be debited based on transaction type)

**CRITICAL VAT/TAX HANDLING RULE:**
- If ANY tax amount is detected in the document (VAT, sales tax, etc.), you MUST create additional_entries for the tax handling
- NEVER use standard vat_treatment field when tax is present - always use additional_entries
- For Output VAT: Create entry with debit amount equal to tax amount and credit to account 2201 (Output VAT Sales)
- The main entry should be for the net amount only, with tax handled separately in additional_entries

**SHARE CAPITAL TRANSACTION HANDLING:**
- Treat share allotments as invoices for accounting purposes
- Shareholder becomes the "customer" receiving shares
- Amount represents cash to be received from shareholder
- Description should detail share allotment (e.g., "15,000 ordinary shares at €1 each")
- Use appropriate accounting codes: DEBIT 1204 (Bank), CREDIT 3000 (Share Capital)

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

**LINE ITEMS STRUCTURE (when present):**
Each line item in the line_items array must have this exact structure:
{{
  "description": "",
  "quantity": 0,
  "price_unit": 0,
  "line_total": 0,
  "tax_rate": 0
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
- Consultancy Invoice (no tax): debit_account="1100", credit_account="6200"
- Service Invoice (with VAT): debit_account="1100", credit_account="4000" + additional_entries for VAT
- Product Sale: debit_account="1100", credit_account="4100"
- Share Capital Transaction: debit_account="1204", credit_account="3000"
- EU Customer with Reverse Charge: Main entry + additional VAT entries in additional_entries array

**VAT ADDITIONAL ENTRIES EXAMPLES:**
When tax_amount > 0, always add:
{{
  "account_code": "2201",
  "account_name": "Output VAT (Sales)",
  "debit_amount": <tax_amount>,
  "credit_amount": 0,
  "description": "Output VAT on sale"
}}

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
10. **ACCOUNT CODE CONSISTENCY: The account codes and names you assign must exactly match the ones provided in the chart of accounts**
11. **MANDATORY TAX HANDLING: Any detected tax amount MUST be processed through additional_entries, never through standard vat_treatment**

**FINAL REMINDER: Return ONLY the JSON object with ALL fields present. No explanatory text. Start with {{ and end with }}.**"""

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
        
        # Get comprehensive prompt
        prompt = get_invoice_processing_prompt(company_name)
        
        # Send to Claude with optimized parameters for structured output
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=15000,
            temperature=0.0,  # Maximum determinism for consistent parsing
            system="""You are an expert accountant and data extraction system specialized in ALL CASH INFLOW transactions. Your core behavior is to think and act like a professional accountant who understands double-entry bookkeeping for REVENUE recognition, EQUITY transactions, VAT regulations, and proper account classification.

CHART OF ACCOUNTS YOU MUST USE (EXACT CODES AND NAMES):
• 1100 - Accounts receivable (Asset)
• 1204 - Bank (Asset)
• 2201 - Output VAT (Sales) (Liability)
• 2202 - Input VAT (Purchases) (Asset)
• 3000 - Share Capital (Equity)
• 4000 - Service revenue (Revenue)
• 4100 - Sales revenue (Revenue)
• 7602 - Consultancy fees (Revenue)
• 7900 - Other income (Revenue)

**CRITICAL ACCOUNT CODE RULE: You MUST use the exact account codes and names from the chart above. Never modify or create new account codes.**

CORE ACCOUNTING BEHAVIOR FOR ALL CASH INFLOW DOCUMENTS:
• Always think: "What did we provide?" (CREDIT) and "What do we expect to receive?" (DEBIT)
• Customer invoices: DEBIT accounts receivable (1100), CREDIT appropriate revenue account
• Share capital transactions: DEBIT bank (1204), CREDIT share capital (3000)
• Consultancy services → CREDIT 6200 (Consultancy fees)
• Professional services → CREDIT 4000 (Service revenue)
• Product sales → CREDIT 4100 (Sales revenue)
• Share allotments/capital increases → CREDIT 3000 (Share Capital)
• Other services → CREDIT 7900 (Other income)
• Apply output VAT when applicable: Additional DEBIT amount, CREDIT 2201 (VAT portion)
• EU customers may require reverse charge treatment
• Ensure debits always equal credits

**MANDATORY VAT PROCESSING RULE:**
• When ANY tax/VAT amount is detected in a document, you MUST process it through additional_entries
• NEVER use vat_treatment field when tax is present - always create additional_entries
• For any detected tax: Create additional entry with debit_amount to "2201" (Output VAT Sales) and corresponding entry
• Main accounting entry should be for net amount only
• Tax handling is ALWAYS through additional_entries when tax is detected

DOCUMENT TYPES TO PROCESS AS INVOICES:
• Traditional customer invoices for services/products
• Share allotment documents and capital increase resolutions
• Shareholder investment agreements
• Any document representing cash inflow to the company

VAT EXPERTISE FOR SALES:
• Domestic customers = Standard VAT on invoice (CREDIT 2201)
• EU business customers = May qualify for reverse charge (no VAT on invoice)
• Non-EU customers = Usually no VAT
• Share capital transactions = Usually no VAT
• Any VAT detected = Mandatory additional_entries processing

SHARE CAPITAL TRANSACTION HANDLING:
• Treat share allotments as invoices for Odoo integration
• Shareholder becomes the "customer" receiving shares
• Extract share details: number of shares, nominal value, total amount
• Use DEBIT 1204 (Bank), CREDIT 3000 (Share Capital)
• Description should detail the share transaction

OUTPUT FORMAT:
Respond only with valid JSON objects. Never include explanatory text, analysis, or commentary. Always include ALL required fields with their default values when data is missing. Apply your accounting expertise to assign correct debit/credit accounts for every cash inflow transaction using ONLY the exact account codes provided.""",
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

def ensure_line_item_structure(line_item):
    """Ensure each line item has the complete required structure"""
    default_line_item = {
        "description": "",
        "quantity": 0,
        "price_unit": 0,
        "line_total": 0,
        "tax_rate": 0
    }
    
    result = {}
    for key, default_value in default_line_item.items():
        if key in line_item and line_item[key] is not None:
            result[key] = line_item[key]
        else:
            result[key] = default_value
    
    return result

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

def validate_invoice_data(invoices):
    """Validate extracted invoice data for completeness and accuracy"""
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
        
        # Check line items
        line_items = customer_data.get("line_items", [])
        if not line_items:
            invoice_validation["warnings"].append("No line items found")
        
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
        
        # Check VAT handling compliance
        accounting_assignment = invoice.get("accounting_assignment", {})
        additional_entries = accounting_assignment.get("additional_entries", [])
        
        if tax_amount > 0 and not additional_entries:
            invoice_validation["issues"].append(
                "Tax amount detected but no additional_entries created - VAT must be handled through additional_entries"
            )
        
        # Check account code consistency
        debit_account = accounting_assignment.get("debit_account", "")
        credit_account = accounting_assignment.get("credit_account", "")
        
        valid_accounts = ["1100", "1204", "2201", "2202", "3000", "4000", "4100", "6200", "7900"]
        
        if debit_account and debit_account not in valid_accounts:
            invoice_validation["issues"].append(f"Invalid debit account code: {debit_account}")
        
        if credit_account and credit_account not in valid_accounts:
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
            "version": "1.1",
            "capabilities": [
                "document_splitting",
                "data_extraction", 
                "monetary_calculation",
                "confidence_scoring",
                "revenue_accounting",
                "customer_invoice_processing",
                "mandatory_vat_additional_entries",
                "strict_account_code_validation"
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