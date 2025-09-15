import boto3
import base64
import anthropic
import os
import json
import re

def get_bill_processing_prompt(company_name):
    """Create comprehensive bill processing prompt that combines splitting and extraction"""
    return f"""You are an advanced invoice processing AI. Your task is to analyze a multi-invoice PDF document and return structured JSON data.

**CRITICAL INSTRUCTION: Respond with ONLY the JSON object. Do not include any explanatory text, commentary, analysis, or markdown formatting before or after the JSON. Start your response immediately with the opening curly brace {{.**

**INPUT:** Multi-invoice PDF document
**COMPANY:** {company_name} (the company receiving these bills)
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
- Line Items with calculations

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

**LINE ITEMS STRUCTURE (when present):**
Each line item in the line_items array must have this exact structure:
{{
  "description": "",
  "quantity": 0,
  "price_unit": 0,
  "line_total": 0,
  "tax_rate": 0
}}

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

def process_bills_with_claude(pdf_content, company_name):
    """Process PDF document with Claude for bill splitting and extraction"""
    try:
        # Initialize Anthropic client
        anthropic_client = anthropic.Anthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY')
        )
        
        # Encode to base64
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        
        # Get comprehensive prompt
        prompt = get_bill_processing_prompt(company_name)
        
        # Send to Claude with optimized parameters for structured output
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=15000,
            temperature=0.0,  # Maximum determinism for consistent parsing
            system="You are a precise data extraction system. Respond only with valid JSON objects. Never include explanatory text, analysis, or commentary. Always include ALL required fields with their default values when data is missing.",
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

def validate_bill_data(bills):
    """Validate extracted bill data for completeness and accuracy"""
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
        
        # Check line items
        line_items = vendor_data.get("line_items", [])
        if not line_items:
            bill_validation["warnings"].append("No line items found")
        
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
            "version": "2.1",
            "capabilities": [
                "document_splitting",
                "data_extraction", 
                "monetary_calculation",
                "confidence_scoring",
                "improved_json_parsing",
                "guaranteed_structure_consistency"
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