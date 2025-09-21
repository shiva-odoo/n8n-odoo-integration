import boto3
import base64
import anthropic
import os
import json
import re

def get_share_processing_prompt(company_name):
    """Create comprehensive share transaction processing prompt that combines splitting and extraction"""
    return f"""You are an advanced share transaction processing AI. Your task is to analyze a multi-document PDF containing share capital transactions and return structured JSON data.

**CRITICAL INSTRUCTION: Respond with ONLY the JSON object. Do not include any explanatory text, commentary, analysis, or markdown formatting before or after the JSON. Start your response immediately with the opening curly brace {{.**

**INPUT:** Multi-document PDF containing share capital transactions
**COMPANY:** {company_name} (the company issuing shares to shareholders/partners)
**OUTPUT:** Raw JSON object only

**DOCUMENT SPLITTING RULES (Priority Order):**
1. **PAGE INDICATOR RULE (HIGHEST PRIORITY):**
   - "Page 1 of 1" multiple times = Multiple separate single-page transactions
   - "Page 1 of 2", "Page 2 of 2" = One two-page transaction
   - "Page 1 of 3", "Page 2 of 3", "Page 3 of 3" = One three-page transaction

2. **TRANSACTION NUMBER RULE (SECOND PRIORITY):**
   - Different transaction/document numbers = Different transactions
   - Same transaction number across pages = Same transaction

3. **HEADER COUNT RULE (THIRD PRIORITY):**
   - Multiple distinct share transaction headers = Multiple transactions

**SHARE TRANSACTION TYPES TO PROCESS:**
- Share allotment resolutions
- Capital increase documents
- Shareholder investment agreements
- Share subscription agreements
- Share issuance certificates
- Board resolutions for share capital increases
- Shareholder meeting minutes approving share issues

**DOCUMENT TYPE:** Set as "share_capital_transaction" for all share-related documents.

**COMPANY VALIDATION:**
- Identify ALL company names in the PDF
- Check if any match "{company_name}" (case-insensitive, fuzzy matching)
- Set company_match: "exact_match", "close_match", "no_match", or "unclear"

**MANDATORY FIELDS FOR SHARE TRANSACTIONS:**
- Partner/Shareholder name (Essential - the person/entity receiving shares)
- Transaction Date (Required - date of share allotment/issuance)
- Due Date or Payment Terms (when payment is expected)
- Transaction/Document Reference
- Currency and Amounts
- Description (Overall description of the share transaction)
- Share Details (number of shares, nominal value, share type)
- Credit Account: 3000 (Share Capital) - MANDATORY
- Debit Account: 1100 (Accounts receivable) - MANDATORY

**SHARE TRANSACTION EXTRACTION RULES:**
- Extract number of shares being issued/allotted
- Extract nominal value per share
- Extract total share capital amount
- Extract share type (ordinary, preference, etc.)
- Identify the shareholder/partner receiving the shares
- Calculate total amount due from shareholder
- Transaction represents cash to be received by the company

**CRITICAL ACCOUNTING ASSIGNMENT:**
- DEBIT: 1100 (Accounts receivable) - What we expect to receive from shareholder
- CREDIT: 3000 (Share Capital) - What we are issuing (shares)
- Share transactions typically do not involve VAT/tax
- Amount represents the cash investment by the shareholder

**TAX HANDLING FOR SHARE TRANSACTIONS:**
- Share capital transactions typically do not involve VAT
- If ANY tax amount is detected (rare but possible), create additional_entries
- NEVER use standard vat_treatment field when tax is present - always use additional_entries
- For ANY detected tax amount, create BOTH Input VAT AND Output VAT entries as per standard rules

**DESCRIPTION FIELD FOR SHARE TRANSACTIONS:**
- Create an overall description of the share transaction
- Include key details: number of shares, share type, nominal value
- Example: "Allotment of 15,000 ordinary shares at €1.00 nominal value each"
- Example: "Capital increase through issuance of 5,000 preference shares at €2.50 each"
- Should give clear understanding of the share transaction

**CALCULATION REQUIREMENTS:**
- line_total = number_of_shares × nominal_value_per_share
- subtotal = sum of all share allotments before any fees/tax
- total_amount = subtotal + any_fees_or_tax
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
  "total_transactions": <number>,
  "transactions": [
    {{
      "transaction_index": 1,
      "page_range": "1",
      "document_classification": {{
        "document_type": "share_capital_transaction",
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
      "partner_data": {{
        "name": "",
        "email": "",
        "phone": "",
        "website": "",
        "street": "",
        "city": "",
        "zip": "",
        "country_code": "",
        "transaction_date": null,
        "due_date": null,
        "transaction_ref": "",
        "payment_reference": "",
        "description": "",
        "subtotal": 0,
        "tax_amount": 0,
        "total_amount": 0,
        "currency_code": "",
        "share_details": []
      }},
      "accounting_assignment": {{
        "debit_account": "1100",
        "debit_account_name": "Accounts receivable",
        "credit_account": "3000",
        "credit_account_name": "Share Capital",
        "vat_treatment": "",
        "requires_reverse_charge": false,
        "additional_entries": []
      }},
      "extraction_confidence": {{
        "partner_name": "low",
        "total_amount": "low",
        "share_details": "low",
        "dates": "low",
        "company_validation": "low",
        "document_classification": "low"
      }},
      "missing_fields": []
    }}
  ]
}}

**SHARE DETAILS STRUCTURE (when present):**
Each share detail in the share_details array must have this exact structure:
{{
  "share_type": "",
  "number_of_shares": 0,
  "nominal_value_per_share": 0,
  "total_value": 0,
  "description": ""
}}

**ADDITIONAL ENTRIES STRUCTURE (for any fees or taxes):**
Each additional entry in the additional_entries array must have this exact structure:
{{
  "account_code": "",
  "account_name": "",
  "debit_amount": 0,
  "credit_amount": 0,
  "description": ""
}}

**SHARE TRANSACTION EXAMPLES:**
- Share Allotment: partner_name="John Smith", description="Allotment of 1,000 ordinary shares at €1 each"
- Capital Increase: partner_name="ABC Investment Ltd", description="Capital increase through 5,000 preference shares at €2.50 each"
- New Shareholder: partner_name="Investment Partners LLC", description="Initial share subscription of 2,500 ordinary shares at €1.20 each"

**ACCOUNTING ASSIGNMENT (MANDATORY FOR ALL SHARE TRANSACTIONS):**
- debit_account: "1100" (Accounts receivable)
- debit_account_name: "Accounts receivable"
- credit_account: "3000" (Share Capital)
- credit_account_name: "Share Capital"

**ADDITIONAL ENTRIES (only if fees or taxes detected):**
When any fees or taxes are detected:
1. For fees: Additional entry to appropriate expense account
2. For VAT (rare): Both Input VAT (2202) and Output VAT (2201) entries

**ABSOLUTE REQUIREMENTS:**
1. Every field listed above MUST be present in every transaction object
2. Use the exact default values shown when data is not found
3. Never omit fields - always include them with default values
4. String fields default to empty string ""
5. Number fields default to 0
6. Date fields default to null
7. Array fields default to empty array []
8. Confidence levels: use "high", "medium", or "low" only
9. Company match: use "exact_match", "close_match", "no_match", or "unclear" only
10. **MANDATORY ACCOUNTING: Always use debit_account="1100" and credit_account="3000" for share transactions**
11. **DOCUMENT TYPE: Always use "share_capital_transaction" for document_type**

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

def process_share_documents_with_claude(pdf_content, company_name):
    """Process PDF document with Claude for share transaction splitting and extraction"""
    try:
        # Initialize Anthropic client
        anthropic_client = anthropic.Anthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY')
        )
        
        # Encode to base64
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        
        # Get comprehensive prompt
        prompt = get_share_processing_prompt(company_name)
        
        # Send to Claude with optimized parameters for structured output
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=15000,
            temperature=0.0,  # Maximum determinism for consistent parsing
            system="""You are an expert accountant and share capital transaction specialist. Your core behavior is to think and act like a professional accountant who understands double-entry bookkeeping for EQUITY transactions, share capital regulations, and proper accounting classification for shareholder investments.

CHART OF ACCOUNTS YOU MUST USE (EXACT CODES AND NAMES):
• 1100 - Accounts receivable (Asset)
• 1204 - Bank (Asset) 
• 2100 - Accounts payable (Liability)
• 2201 - Output VAT (Sales) (Liability)
• 2202 - Input VAT (Purchases) (Asset)
• 3000 - Share Capital (Equity)
• 7602 - Consultancy fees (Expense)
• 7901 - Bank charges (Expense)
• 8200 - Other non-operating income or expenses (Expense)

**CRITICAL ACCOUNT CODE RULE: You MUST use the exact account codes and names from the chart above. Never modify or create new account codes.**

CORE ACCOUNTING BEHAVIOR FOR SHARE CAPITAL TRANSACTIONS:
• Always think: "What are we issuing?" (CREDIT 3000 Share Capital) and "What do we expect to receive?" (DEBIT 1100 Accounts receivable)
• Share capital transactions: DEBIT 1100 (Accounts receivable), CREDIT 3000 (Share Capital)
• Share allotments represent future cash inflow from shareholders
• Amount represents the cash investment by shareholders for shares received
• Share capital transactions typically do not involve VAT/tax
• Ensure debits always equal credits

**MANDATORY SHARE CAPITAL ACCOUNTING:**
• DEBIT Account: 1100 (Accounts receivable) - Cash to be received from shareholder
• CREDIT Account: 3000 (Share Capital) - Shares being issued to shareholder
• This represents the company's obligation to issue shares in exchange for cash investment

**SHARE TRANSACTION PROCESSING RULES:**
• Treat all share transactions as cash inflow transactions for accounting purposes
• Shareholder/partner becomes the "customer" receiving shares
• Extract share details: number of shares, nominal value, share type, total amount
• Description should detail the share transaction comprehensively
• Calculate total amount due from shareholder for shares

**TAX HANDLING FOR SHARE TRANSACTIONS:**
• Share capital transactions typically do not involve VAT
• Share issuance is generally not subject to VAT in most jurisdictions
• If any tax/fees are detected (rare), process through additional_entries
• When tax is detected, create BOTH Input VAT (2202) and Output VAT (2201) entries

**SHARE TRANSACTION TYPES TO RECOGNIZE:**
• Share allotment resolutions
• Capital increase documents  
• Shareholder investment agreements
• Share subscription agreements
• Share issuance certificates
• Board resolutions for share capital increases

**OUTPUT FORMAT:**
Respond only with valid JSON objects. Never include explanatory text, analysis, or commentary. Always include ALL required fields with their default values when data is missing. Apply your accounting expertise to ensure all share transactions use DEBIT 1100 and CREDIT 3000 accounts.""",
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

def ensure_transaction_structure(transaction):
    """Ensure each transaction has the complete required structure with default values"""
    
    # Define the complete structure with default values
    default_transaction = {
        "transaction_index": 1,
        "page_range": "1",
        "document_classification": {
            "document_type": "share_capital_transaction",
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
        "partner_data": {
            "name": "",
            "email": "",
            "phone": "",
            "website": "",
            "street": "",
            "city": "",
            "zip": "",
            "country_code": "",
            "transaction_date": None,
            "due_date": None,
            "transaction_ref": "",
            "payment_reference": "",
            "description": "",
            "subtotal": 0,
            "tax_amount": 0,
            "total_amount": 0,
            "currency_code": "",
            "share_details": []
        },
        "accounting_assignment": {
            "debit_account": "1100",
            "debit_account_name": "Accounts receivable",
            "credit_account": "3000",
            "credit_account_name": "Share Capital",
            "vat_treatment": "",
            "requires_reverse_charge": False,
            "additional_entries": []
        },
        "extraction_confidence": {
            "partner_name": "low",
            "total_amount": "low",
            "share_details": "low",
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
                        # Ensure arrays exist and validate structure for share_details
                        if key == "share_details" and isinstance(source[key], list):
                            result[key] = [ensure_share_detail_structure(item) for item in source[key]]
                        else:
                            result[key] = source[key] if isinstance(source[key], list) else default_value
                    else:
                        result[key] = source[key]
                else:
                    result[key] = default_value
            return result
        else:
            return source if source is not None else defaults
    
    return merge_with_defaults(transaction, default_transaction)

def ensure_share_detail_structure(share_detail):
    """Ensure each share detail has the complete required structure"""
    default_share_detail = {
        "share_type": "",
        "number_of_shares": 0,
        "nominal_value_per_share": 0,
        "total_value": 0,
        "description": ""
    }
    
    result = {}
    for key, default_value in default_share_detail.items():
        if key in share_detail and share_detail[key] is not None:
            result[key] = share_detail[key]
        else:
            result[key] = default_value
    
    return result

def parse_share_response(raw_response):
    """Parse the raw response into structured share transaction data with improved error handling"""
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
            if "total_transactions" not in result:
                result["total_transactions"] = 0
            if "transactions" not in result:
                result["transactions"] = []
            
            # Ensure each transaction has complete structure
            validated_transactions = []
            for i, transaction in enumerate(result["transactions"]):
                validated_transaction = ensure_transaction_structure(transaction)
                # Ensure transaction_index is set correctly
                validated_transaction["transaction_index"] = i + 1
                validated_transactions.append(validated_transaction)
            
            result["transactions"] = validated_transactions
            result["total_transactions"] = len(validated_transactions)
            
            print(f"Successfully parsed and validated response with {len(result['transactions'])} transactions")
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

def validate_share_data(transactions):
    """Validate extracted share transaction data for completeness and accuracy"""
    validation_results = []
    
    for transaction in transactions:
        transaction_validation = {
            "transaction_index": transaction.get("transaction_index", 0),
            "issues": [],
            "warnings": [],
            "mandatory_fields_present": True,
            "structure_complete": True
        }
        
        partner_data = transaction.get("partner_data", {})
        
        # Check mandatory fields (content validation, not structure)
        mandatory_content = {
            "partner_name": partner_data.get("name", ""),
            "total_amount": partner_data.get("total_amount", 0),
            "transaction_date": partner_data.get("transaction_date"),
            "description": partner_data.get("description", "")
        }
        
        for field_name, field_value in mandatory_content.items():
            if not field_value or field_value == "":
                transaction_validation["issues"].append(f"Missing content for mandatory field: {field_name}")
                transaction_validation["mandatory_fields_present"] = False
        
        # Check share details
        share_details = partner_data.get("share_details", [])
        if not share_details:
            transaction_validation["warnings"].append("No share details found")
        
        # Check monetary consistency
        subtotal = partner_data.get("subtotal", 0)
        tax_amount = partner_data.get("tax_amount", 0)
        total_amount = partner_data.get("total_amount", 0)
        
        if total_amount > 0:
            calculated_total = subtotal + tax_amount
            if abs(calculated_total - total_amount) > 0.01:
                transaction_validation["warnings"].append(
                    f"Amount mismatch: calculated {calculated_total}, document shows {total_amount}"
                )
        
        # Check accounting assignment for share transactions
        accounting_assignment = transaction.get("accounting_assignment", {})
        debit_account = accounting_assignment.get("debit_account", "")
        credit_account = accounting_assignment.get("credit_account", "")
        
        # Validate mandatory share capital accounting
        if debit_account != "1100":
            transaction_validation["issues"].append(f"Invalid debit account for share transaction: {debit_account}, should be 1100")
        
        if credit_account != "3000":
            transaction_validation["issues"].append(f"Invalid credit account for share transaction: {credit_account}, should be 3000")
        
        # Check document type
        document_classification = transaction.get("document_classification", {})
        document_type = document_classification.get("document_type", "")
        
        if document_type != "share_capital_transaction":
            transaction_validation["issues"].append(f"Invalid document type: {document_type}, should be share_capital_transaction")
        
        # VAT handling for share transactions (should be rare)
        additional_entries = accounting_assignment.get("additional_entries", [])
        
        if tax_amount > 0:
            if not additional_entries:
                transaction_validation["issues"].append(
                    "Tax amount detected but no additional_entries created - unusual for share transactions"
                )
            else:
                # Check for both Input VAT (2202) and Output VAT (2201) entries if tax is present
                input_vat_entries = [e for e in additional_entries if e.get("account_code") == "2202"]
                output_vat_entries = [e for e in additional_entries if e.get("account_code") == "2201"]
                
                if not input_vat_entries:
                    transaction_validation["warnings"].append(
                        "Tax amount detected but missing Input VAT (2202) entry in additional_entries"
                    )
                
                if not output_vat_entries:
                    transaction_validation["warnings"].append(
                        "Tax amount detected but missing Output VAT (2201) entry in additional_entries"
                    )
        
        # Check confidence levels
        confidence = transaction.get("extraction_confidence", {})
        low_confidence_fields = [
            field for field, conf in confidence.items() 
            if conf == "low"
        ]
        
        if low_confidence_fields:
            transaction_validation["warnings"].append(
                f"Low confidence fields: {', '.join(low_confidence_fields)}"
            )
        
        validation_results.append(transaction_validation)
    
    return validation_results

def main(data):
    """
    Main function for combined share transaction processing (splitting + extraction)
    
    Args:
        data (dict): Request data containing:
            - s3_key (str): S3 key path to the PDF document
            - company_name (str): Name of the company issuing the shares
            - bucket_name (str, optional): S3 bucket name
    
    Returns:
        dict: Processing result with structured share transaction data
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
        
        print(f"Processing share transactions for company: {company_name}, S3 key: {s3_key}")
        
        # Download PDF from S3
        pdf_content = download_from_s3(s3_key, bucket_name)
        print(f"Downloaded PDF, size: {len(pdf_content)} bytes")
        
        # Process with Claude for combined splitting and extraction
        claude_result = process_share_documents_with_claude(pdf_content, company_name)
        
        if not claude_result["success"]:
            return {
                "success": False,
                "error": f"Claude processing failed: {claude_result['error']}"
            }
        
        # Parse the structured response with validation
        parse_result = parse_share_response(claude_result["raw_response"])
        
        if not parse_result["success"]:
            return {
                "success": False,
                "error": f"Response parsing failed: {parse_result['error']}",
                "raw_response": claude_result["raw_response"],
                "parse_details": parse_result
            }
        
        result_data = parse_result["result"]
        transactions = result_data.get("transactions", [])
        
        # Validate extracted share transaction data
        validation_results = validate_share_data(transactions)
        
        # Count transactions with critical issues
        transactions_with_issues = sum(1 for v in validation_results if not v["mandatory_fields_present"])
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
                "company_name": company_name,
                "s3_key": s3_key,
                "token_usage": claude_result["token_usage"]
            }
        }
        
    except Exception as e:
        print(f"Share transaction processing error: {str(e)}")
        return {
            "success": False,
            "error": f"Internal processing error: {str(e)}"
        }

def health_check():
    """Health check for the share transaction processing service"""
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
            "service": "claude-share-transaction-processing",
            "version": "1.0",
            "capabilities": [
                "document_splitting",
                "share_data_extraction", 
                "monetary_calculation",
                "confidence_scoring",
                "share_capital_accounting",
                "share_transaction_processing",
                "equity_accounting",
                "shareholder_investment_tracking",
                "mandatory_share_capital_accounts"
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