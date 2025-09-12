import boto3
import base64
import anthropic
import os
import json
import re

def get_splitting_prompt():
    """Create concise and focused document splitting prompt"""
    return """You are an OCR specialist that splits multi-invoice PDF documents. Your task: identify separate invoices and extract complete text for each.

**CRITICAL OUTPUT RULES:**
- Output ONLY JSON objects, one per line
- No explanations, comments, or markdown
- Start response immediately with first JSON object
- Each JSON object format: {"invoice_index":1,"page_range":"1-1","raw_text":"complete text"}

**INVOICE IDENTIFICATION RULES (Priority Order):**

1. **PAGE INDICATOR RULE (HIGHEST PRIORITY):**
   - Scan EVERY page for page indicators: "Page X of Y", "Σελ X από Y", "Página X de Y"
   - "Page 1 of 1" multiple times = Multiple separate single-page invoices
   - "Page 1 of 2", "Page 2 of 2" = One two-page invoice
   - "Page 1 of 3", "Page 2 of 3", "Page 3 of 3" = One three-page invoice

2. **INVOICE NUMBER RULE (SECOND PRIORITY):**
   - Different invoice numbers = Different invoices
   - Same invoice number across pages = Same invoice (unless Rule 1 overrides)

3. **HEADER COUNT RULE (THIRD PRIORITY):**
   - Multiple "INVOICE" headers typically = Multiple invoices
   - Check invoice dates, amounts, customer details for confirmation

**COMMON SCENARIOS:**

**Single-page invoices:** Document with 4 pages, each showing "Page 1 of 1"
→ Output 4 separate JSON objects with page_range "1-1", "2-2", "3-3", "4-4"

**Multi-page invoice:** Document with 2 pages showing "Page 1 of 2", "Page 2 of 2"
→ Output 1 JSON object with page_range "1-2"

**Mixed document:** Pages showing "Page 1 of 2", "Page 2 of 2", "Page 1 of 1", "Page 1 of 1"
→ Output 3 JSON objects with page_range "1-2", "3-3", "4-4"

**OCR EXTRACTION RULES:**
- Extract complete text from top to bottom of each page in the page range
- Include ALL header information: company names, addresses, phone numbers
- Include ALL line items with descriptions, quantities, prices
- Include ALL totals: subtotal, VAT, final amount
- Include ALL dates, invoice numbers, reference numbers
- Preserve text structure with appropriate line breaks
- Do not clean or interpret text - use exact OCR output

**VALIDATION CHECKS:**
- Each invoice should have coherent line items that sum to a total amount
- Invoice numbers should be unique per invoice (except multi-page invoices)
- Dates should be consistent within each invoice
- Customer/billing information should be consistent within each invoice

**MANDATORY OUTPUT FORMAT:**
{"invoice_index":1,"page_range":"1-1","raw_text":"MFO ASSET MANAGEMENT LTD\n66, Acropolis Avenue\nINVOICE\nENAMI LIMITED\nInvoice No. : 2025/059\nDate : 07/03/25\nDescription VAT % Amount (EUR)\nPortfolio Management fee, for the month of February 2025 19 2,773.08\nAmount Excl. VAT 2,773.08\nVAT Amount 526.89\nTotal Amount 3,299.97"}

**PROCESSING ALGORITHM:**
1. Count total PDF pages
2. Scan each page for page indicators ("Page X of Y")
3. If multiple "Page 1 of 1" found → Create separate invoices for each page
4. If page sequences found (1 of 2, 2 of 2) → Group into single invoices
5. Extract complete OCR text for each determined page range
6. Output one JSON object per invoice
7. Ensure invoice_index increments sequentially (1, 2, 3, 4...)

**ERROR PREVENTION:**
- Never split pages that belong to the same invoice (same page sequence)
- Never combine pages that have different "Page 1 of 1" indicators
- Always include complete text - partial extraction is not acceptable
- Page ranges must correspond to actual pages in the document

**EXAMPLES:**
Four single-page invoices:
{"invoice_index":1,"page_range":"1-1","raw_text":"Invoice 1 complete text..."}
{"invoice_index":2,"page_range":"2-2","raw_text":"Invoice 2 complete text..."}
{"invoice_index":3,"page_range":"3-3","raw_text":"Invoice 3 complete text..."}
{"invoice_index":4,"page_range":"4-4","raw_text":"Invoice 4 complete text..."}

One two-page invoice:
{"invoice_index":1,"page_range":"1-2","raw_text":"Complete text from both pages..."}

START PROCESSING NOW. OUTPUT ONLY JSON OBJECTS."""

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

def process_document_splitting(pdf_content):
    """Process document with Claude for splitting into individual invoices"""
    try:
        # Initialize Anthropic client
        anthropic_client = anthropic.Anthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY')
        )
        
        # Encode to base64
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        
        # Get concise prompt
        prompt = get_splitting_prompt()
        
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
            "split_result": response_text,
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

def parse_split_invoices(raw_response):
    """Parse the raw response into individual invoice objects with robust handling"""
    try:
        invoices = []
        
        # Clean the response and remove excessive whitespace
        cleaned_response = raw_response.strip()
        
        # Try parsing as line-separated JSON objects first (expected format)
        lines = cleaned_response.split('\n')
        
        for line in lines:
            line = line.strip()
            if line and line.startswith('{') and line.endswith('}'):
                try:
                    invoice_data = json.loads(line)
                    # Validate required fields
                    if all(field in invoice_data for field in ['invoice_index', 'page_range', 'raw_text']):
                        # Clean up excessive newlines in raw_text
                        if 'raw_text' in invoice_data:
                            raw_text = invoice_data['raw_text']
                            # Replace excessive newlines but preserve document structure
                            cleaned_text = re.sub(r'\n{5,}', '\n\n', raw_text)
                            cleaned_text = cleaned_text.strip()
                            invoice_data['raw_text'] = cleaned_text
                        invoices.append(invoice_data)
                except json.JSONDecodeError:
                    continue
        
        # If no line-separated objects found, try parsing as single JSON object
        if not invoices:
            try:
                single_object = json.loads(cleaned_response)
                if isinstance(single_object, dict) and 'invoice_index' in single_object:
                    invoices.append(single_object)
                elif isinstance(single_object, list):
                    invoices = single_object
            except json.JSONDecodeError:
                pass
        
        # If still no invoices, try parsing concatenated JSON objects
        if not invoices and '}{' in cleaned_response:
            parts = cleaned_response.split('}{')
            for i, part in enumerate(parts):
                try:
                    if i == 0:
                        json_str = part + '}'
                    elif i == len(parts) - 1:
                        json_str = '{' + part
                    else:
                        json_str = '{' + part + '}'
                    
                    json_str = json_str.strip()
                    invoice_data = json.loads(json_str)
                    
                    # Validate required fields
                    if all(field in invoice_data for field in ['invoice_index', 'page_range', 'raw_text']):
                        invoices.append(invoice_data)
                except json.JSONDecodeError:
                    continue
        
        print(f"Successfully parsed {len(invoices)} invoices from response")
        
        # Sort invoices by invoice_index to ensure proper order
        invoices.sort(key=lambda x: x.get('invoice_index', 0))
        
        return {
            "success": True,
            "invoices": invoices,
            "total_invoices": len(invoices)
        }
        
    except Exception as e:
        print(f"Error in parse_split_invoices: {str(e)}")
        return {
            "success": False,
            "error": f"Error parsing split invoices: {str(e)}"
        }

def main(data):
    """
    Main function for document splitting
    
    Args:
        data (dict): Request data containing:
            - s3_key (str): S3 key path to the document
            - bucket_name (str, optional): S3 bucket name
    
    Returns:
        dict: Splitting result with success status and individual invoices
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
        
        print(f"Processing document for splitting, S3 key: {s3_key}")
        
        # Download PDF from S3
        pdf_content = download_from_s3(s3_key, bucket_name)
        print(f"Downloaded PDF, size: {len(pdf_content)} bytes")
        
        # Process with Claude for splitting
        result = process_document_splitting(pdf_content)
        
        if result["success"]:
            # Parse the split result into individual invoices
            parse_result = parse_split_invoices(result["split_result"])
            
            if parse_result["success"]:
                return {
                    "success": True,
                    "invoices": parse_result["invoices"],
                    "total_invoices": parse_result["total_invoices"],
                    "metadata": {
                        "token_usage": result["token_usage"],
                        "s3_key": s3_key,
                        "raw_response": result["split_result"]
                    }
                }
            else:
                return {
                    "success": False,
                    "error": parse_result["error"],
                    "raw_response": result["split_result"]
                }
        else:
            return {
                "success": False,
                "error": result["error"]
            }
            
    except Exception as e:
        print(f"Document splitting error: {str(e)}")
        return {
            "success": False,
            "error": f"Internal processing error: {str(e)}"
        }

def health_check():
    """Health check for the splitting service"""
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
            "service": "claude-document-splitting",
            "anthropic_configured": bool(os.getenv('ANTHROPIC_API_KEY')),
            "aws_configured": bool(os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY')),
            "s3_bucket": os.getenv('S3_BUCKET_NAME', 'company-documents-2025')
        }
        
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e)
        }