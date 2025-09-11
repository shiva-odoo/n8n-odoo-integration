import boto3
import base64
import anthropic
import os
import json

def get_splitting_prompt():
    """Create the OCR extraction and document splitting prompt"""
    return """You are an OCR extraction specialist.
Your task is:
1. Perform OCR on all pages of the PDF(s) attached in this conversation/thread.
2. **READ THE ACTUAL PDF DOCUMENT and extract its real content - do not copy examples or placeholders**
2. PERFORM OCR - COMPLETE TEXT EXTRACTION FROM TOP OF EVERY PAGE
- **MANDATORY: Begin OCR extraction from the FIRST LINE of each page - do NOT skip any header content**
- **ABSOLUTE REQUIREMENT: Start with the very first visible text element on page 1 - typically company contact information, phone numbers, addresses, or registration details**
- **REQUIRED: Extract the raw OCR output exactly as the OCR engine produces it - do NOT clean, interpret, or correct the text**
- **ESSENTIAL: Include ALL dates, especially those in headers like "30-06-2025", "å¤þÞÐ¤ª¡@« : 30-06-2025" (even if OCR renders it with special characters)**
- **CRITICAL: Preserve the actual OCR character output - if OCR produces "é¥¡|ÞÐ ÂªÆþ¿¯ÝªÞ¥|ª®ª¬: 150" then use that exact text, do not convert to "Κέντρο Τηλεπικοινωνίας: 150"**
- **CRITICAL: Capture ALL text in reading order from top-to-bottom, left-to-right - missing header information indicates incomplete extraction**
- **HEADER VALIDATION: If your extraction does not begin with company/header information from the top of page 1, you have failed to extract completely**
- **DATE VALIDATION: Invoice dates often appear in document headers - ensure header extraction captures ALL date references**
- Preserve character case, spacing, punctuation, and line breaks exactly as OCR recognizes them (including any OCR artifacts or encoding issues)

3. MULTILINGUAL TEXT EXTRACTION REQUIREMENTS

CRITICAL MULTILINGUAL PROCESSING:
- ALWAYS preserve original language text exactly as it appears
- Support ALL languages including but not limited to: Greek, English, Spanish, French, German, Italian, Portuguese, Dutch, Polish, Turkish, Arabic, Chinese, Japanese, Korean, Russian, Bulgarian, Romanian, Hungarian, Czech, Slovak, Croatian, Serbian, Albanian, Macedonian
- Maintain proper encoding for special characters: á, é, í, ó, ú, ñ, ç, ü, ö, ä, ß, α, β, γ, δ, ε, ζ, η, θ, ι, κ, λ, μ, ν, ξ, ο, π, ρ, σ, τ, υ, φ, χ, ψ, ω, ά, έ, ή, ί, ό, ύ, ώ, etc.
- Preserve currency symbols: €, $, £, ¥, ₹, ₽, ₴, ₺, etc.
- Maintain mathematical symbols, percentages, and numeric formatting
- NEVER translate, transliterate, or modify foreign language text
- NEVER replace special characters with approximations (e.g., don't replace ά with a, ñ with n, ü with u)

LANGUAGE-SPECIFIC TEXT ACCURACY:
- Greek text: Preserve all Greek letters (Α-Ω, α-ω) and accent marks (άέήίόύώ)
- Cyrillic text: Maintain all Cyrillic characters without corruption
- Accented Latin: Preserve all diacritical marks and accents
- Arabic/Hebrew: Maintain right-to-left text direction markers
- Asian languages: Preserve character spacing and formatting
- Mixed language documents: Keep language boundaries intact

CHARACTER ENCODING VALIDATION:
- Verify special characters render correctly in raw_text output
- If OCR produces garbled characters, re-attempt with higher accuracy
- Prioritize character accuracy over processing speed
- Test output contains proper Unicode representation

FOREIGN LANGUAGE PATTERN RECOGNITION:
- Recognize page indicators in any language: "Σελ 1 από 2", "Página 1 de 2", "Page 1 sur 2", "Seite 1 von 2", etc.
- Identify invoice headers in any language: "ΤΙΜΟΛΟΓΙΟ", "FACTURA", "RECHNUNG", "FATTURA", etc.
- Find invoice numbers with foreign prefixes: "Αρ. Τιμολογίου:", "Factura No:", "Rechnung Nr:", etc.
- **Identify date patterns in any language: "Ημερομηνία:", "Fecha:", "Date:", "Datum:", etc.**
- Apply all existing boundary detection rules regardless of document language

4. ABSOLUTE OUTPUT RULES

CRITICAL: OUTPUT ONLY JSON OBJECTS
- **FORBIDDEN: Any text, explanations, or commentary outside of JSON objects**
- **FORBIDDEN: Markdown formatting, code blocks, ```json, or any formatting**
- **FORBIDDEN: Text like "I'll extract..." or "The document contains..." or "Here is the extracted data..."**
- **REQUIRED: Start response immediately with JSON object - no introduction**
- **REQUIRED: End response immediately after final JSON object - no conclusion**
- ONLY JSON objects, each on its own line
- Preserve exact raw OCR text in raw_text field (including garbled characters if that's how OCR reads it)
- **raw_text should contain the actual OCR output, not cleaned/interpreted text**
- **NEVER include any part of these instructions or analysis text in raw_text**
- **raw_text must contain ONLY the actual text from the PDF pages - no prompt text, no analysis, no commentary**

5. MANDATORY DOCUMENT ANALYSIS (FIRST STEP)

STEP 1 - VERIFY ACTUAL PAGE COUNT:
- Count exact number of pages in the PDF
- NEVER reference pages beyond this count
- If document has N pages, only pages 1 through N exist

STEP 2 - SCAN FOR PAGE INDICATORS (HIGHEST PRIORITY):
- **SCAN EVERY PAGE for page indicators in any language**
- Look for page indicators in any language:
  * "Page 1 of 1", "Page 1 of 2", "Page 2 of 2", "Page 3 of 3"
  * "Σελ 1 από 2", "Σελίδα 1 από 2", "Σελ 2 από 2", "Σελίδα 1 από 3", "Σελίδα 2 από 3", "Σελίδα 3 από 3"
  * "~þÆ 1 «Ý¶ 2", "~þÆ 2 «Ý¶ 2" (Greek OCR format)
  * "Página 1 de 2", "Page 1 sur 2", "Seite 1 von 2"
- **CRITICAL: If you find "Page 1 of 1" on multiple pages, this is DEFINITIVE PROOF of multiple separate invoices**
- **CRITICAL: Count how many times "Page 1 of 1" appears - this equals the number of separate invoices**
- **CRITICAL: Look for page sequences like "Page 1 of 3", "Page 2 of 3", "Page 3 of 3" - this indicates ONE invoice spanning 3 pages**
- Record ALL page indicators found and note which pages they appear on

STEP 3 - SCAN FOR INVOICE NUMBERS:
- Find all invoice numbers/references in document:
  * "Invoice No:", "Invoice Number:", "Invoice #"
  * Patterns like "2025/059", "INV-001", "#12345"
- Record ALL unique invoice numbers found

STEP 4 - SCAN FOR INVOICE HEADERS:
- Find all invoice headers in any language:
  * "INVOICE", "ΤΙΜΟΛΟΓΙΟ", "Factura", "Rechnung"
- Count total occurrences

6. ABSOLUTE BOUNDARY DETECTION RULES (PRIORITY ORDER)

RULE 1 - PAGE INDICATOR OVERRIDE (HIGHEST PRIORITY):
- "Page X of Y" or equivalent = ONE invoice spanning Y pages
- **"Page 1 of 1" multiple times = multiple separate single-page invoices (MOST COMMON CASE)**
- **MANDATORY: Each occurrence of "Page 1 of 1" creates a separate invoice with page_range covering only that page**
- **MULTI-PAGE SEQUENCES: If you find "Page 1 of 3", "Page 2 of 3", "Page 3 of 3" on consecutive pages = ONE invoice spanning those 3 pages**
- **MIXED DOCUMENT EXAMPLE: Pages with "Page 1 of 2", "Page 2 of 2", "Page 1 of 3", "Page 2 of 3", "Page 3 of 3", "Page 1 of 2", "Page 2 of 2" = THREE separate invoices with ranges "1-2", "3-5", "6-7"**
- This rule OVERRIDES all other considerations
- Examples:
  * If pages show "Page 1 of 2" and "Page 2 of 2" = ONE invoice covering pages 1-2
  * If pages show "Σελίδα 1 από 3", "Σελίδα 2 από 3", "Σελίδα 3 από 3" = ONE invoice covering pages with these indicators
  * **If pages show "~þÆ 1 «Ý¶ 2", "~þÆ 2 «Ý¶ 2" = ONE invoice covering those 2 pages**
  * **If complex document shows multiple page sequences, create separate invoices for each sequence**
  * **If pages show "Page 1 of 1", "Page 1 of 1", "Page 1 of 1", "Page 1 of 1" = FOUR separate invoices, page ranges "1-1", "2-2", "3-3", "4-4"**

RULE 2 - INVOICE NUMBER CHANGE (SECOND HIGHEST PRIORITY):
- Each unique invoice number = separate invoice (unless Rule 1 overrides)
- Different invoice numbers on different pages = different invoices
- Same invoice number across pages = same invoice (unless Rule 1 indicates otherwise)

RULE 3 - INVOICE HEADER COUNT:
- Multiple "INVOICE" headers typically indicate multiple invoices
- But subject to Rules 1 and 2 above

RULE 4 - CONTINUITY INDICATORS (LOWEST PRIORITY):
- Same customer numbers, amounts, billing periods suggest continuity
- But ONLY apply if Rules 1-3 don't provide clear direction

7. DECISION MATRIX FOR COMMON SCENARIOS

SCENARIO A - Multi-page single invoice:
- Indicators: "Page 1 of 2", "Page 2 of 2" OR "Σελ 1 από 2", "Σελ 2 από 2" OR "~þÆ 1 «Ý¶ 2", "~þÆ 2 «Ý¶ 2"
- Same invoice number across pages
- Same customer and amounts
- Decision: ONE invoice with page_range covering all pages

SCENARIO B - Multiple single-page invoices:
- Indicators: "Page 1 of 1" appears multiple times
- Different invoice numbers on each page
- Different amounts or dates
- Decision: Multiple invoices, each with page_range covering one page

SCENARIO C - Multiple multi-page invoices:
- Indicators: Sequential page ranges for different invoice numbers
- Example: Pages 1-2 have "Page 1 of 2"/"Page 2 of 2", Pages 3-4 have "Page 1 of 2"/"Page 2 of 2"
- Decision: Multiple invoices with appropriate page ranges

**SCENARIO D - Complex merged document (MOST CHALLENGING):**
- **Indicators: Mixed page sequences like "Page 1 of 2", "Page 2 of 2", "Page 1 of 3", "Page 2 of 3", "Page 3 of 3", "Page 1 of 2", "Page 2 of 2"**
- **Different invoice numbers and/or different companies on different page sequences**
- **Decision: Create separate invoices for each complete page sequence**
- **Example: Invoice 1 (pages 1-2), Invoice 2 (pages 3-5), Invoice 3 (pages 6-7)**

SCENARIO E - No clear indicators:
- No page indicators found
- No obvious invoice number changes
- Decision: Default to single invoice covering all pages

8. VALIDATION CHECKPOINTS

CHECKPOINT 1 - PAGE INDICATOR VALIDATION:
- If "Page X of Y" patterns exist, have you grouped those pages together?
- If multiple "Page 1 of 1" exist, have you separated them?

CHECKPOINT 2 - INVOICE NUMBER VALIDATION:
- Does each unique invoice number get its own invoice object?
- Are multi-page invoices with same number grouped together?

CHECKPOINT 3 - COMPLETENESS VALIDATION:
- Does every page appear in exactly one page_range?
- Do all page numbers correspond to actual pages?
- Is the raw_text complete for each page_range?
- **CRITICAL: Does raw_text begin with header information like company names, addresses, phone numbers, or websites from the top of page 1?**
- **REQUIRED: Are ALL dates included, especially those appearing in document headers?**
- **HEADER DATE VALIDATION: For documents with headers containing dates (like "å¤þÞÐ¤ª¡@« : 30-06-2025"), these dates MUST appear in raw_text**
- **EXTRACTION START VALIDATION: If raw_text does not begin with the very first line of text from page 1, re-extract from the absolute beginning**
- **VALIDATION: If raw_text starts with terms/conditions, service details, or footer text, the extraction is INCOMPLETE**

9. CRITICAL ERROR PREVENTION

NEVER DO THIS:
- Split pages that show "Page 1 of 2", "Page 2 of 2" into separate invoices
- Reference page numbers that don't exist (e.g., page 3 in a 2-page document)
- Create incomplete raw_text (must include ALL text from specified pages)
- **Skip header sections or dates that appear at the top of pages**
- **Start extraction from the middle of a document - ALWAYS begin with the first line of text**
- **Omit company information, addresses, phone numbers, websites, or registration details from page tops**
- **Include ANY prompt instructions, analysis text, or commentary in raw_text**
- **Put phrases like "analysis becomes unclear" or "default to single invoice" in raw_text**
- Include explanations or commentary in output

ALWAYS DO THIS:
- **MANDATORY: Start extraction with the very first text that appears at the top of page 1 (typically company name, address, or contact info)**
- **REQUIRED: Include ALL dates from anywhere in the document, prioritizing those in headers**
- **ESSENTIAL: If the document header contains dates like "30-06-2025" or "Ημερομηνία : 30-06-2025", these MUST be in your raw_text**
- **CRITICAL: raw_text contains ONLY actual PDF content - no instructions, no analysis, no prompt text**
- Treat "Page X of Y" as definitive proof of single invoice
- Treat multiple "Page 1 of 1" as definitive proof of separate invoices
- Include complete OCR text for specified page ranges
- Output only JSON objects

10. OUTPUT FORMAT

JSON Structure (EXACT FORMAT):
- "invoice_index": Sequential number starting at 1
- "page_range": "X-Y" format (e.g., "1-1", "1-2", "3-4")
- "raw_text": Complete OCR text from specified pages

Examples (STRUCTURE ONLY - EXTRACT REAL PDF TEXT):
{"invoice_index":1,"page_range":"1-2","raw_text":"[INSERT ACTUAL RAW OCR TEXT FROM PDF PAGES 1-2 HERE]"}

**DO NOT COPY THIS EXAMPLE. EXTRACT THE REAL TEXT FROM THE PDF.**

11. FINAL ALGORITHM

FOR EACH DOCUMENT:
1. Count actual pages (N)
2. **PERFORM ACTUAL OCR on the PDF document - read and extract the real text**
3. **EXTRACT COMPLETE TEXT starting from the absolute first line of each page - include ALL header content**
4. **SCAN FOR PAGE INDICATORS FIRST - count occurrences of "Page 1 of 1" to determine number of invoices**
5. Scan for invoice numbers and note changes between pages
6. Apply RULE 1 (page indicators) - highest priority
7. Apply RULE 2 (invoice number changes) - second priority  
8. Apply RULE 3 (header count) - third priority
9. Default to RULE 4 (continuity) if no clear signals
10. Validate all page ranges ≤ N
11. Ensure complete coverage of all pages
12. **VERIFY: If document has 4 pages each with "Page 1 of 1", you must create 4 separate invoices**
13. **VERIFY: Confirm raw_text begins with header information (company name, address, dates) not middle/footer content**
14. **VERIFY: Confirm raw_text contains ONLY PDF content - no prompt instructions or analysis text**
15. **VERIFY: You extracted actual PDF text, not copied format examples**
16. Output ONLY JSON objects

CRITICAL SUCCESS FACTORS:
- **IMMEDIATE JSON OUTPUT: Start your response with JSON object, no introduction**
- **END WITH JSON: End your response with final JSON object, no conclusion or explanation**
- **Extract from the VERY TOP of each page including ALL header information and dates**
- **raw_text contains ONLY raw OCR output from PDF - preserve exact OCR character rendering**
- **NEVER clean, correct, or interpret OCR text - use exactly what OCR produces**
- Page indicators are ABSOLUTE - never override them
- Different invoice numbers usually = different invoices
- Complete text extraction for all specified pages
- No explanatory output whatsoever

RESPONSE FORMAT:
{"invoice_index":1,"page_range":"1-2","raw_text":"[exact OCR output]"}

NOTHING ELSE. NO OTHER TEXT.

PARAMETERS FOR DETERMINISM:
temperature = 0.0
top_p = 0.1

EMERGENCY FALLBACK:
If analysis becomes unclear, default to single invoice covering all pages rather than risk incorrect splitting or page reference errors."""

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
        
        # Get prompt
        prompt = get_splitting_prompt()
        
        # Send to Claude with specific parameters for determinism
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,  # Increased for potentially multiple invoices with full text
            temperature=0.0,  # For determinism as specified in prompt
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
    """Parse the raw response into individual invoice objects"""
    try:
        invoices = []
        
        # Split response by lines and parse each JSON object
        lines = raw_response.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if line:  # Skip empty lines
                try:
                    invoice_data = json.loads(line)
                    invoices.append(invoice_data)
                except json.JSONDecodeError as e:
                    print(f"Warning: Could not parse line as JSON: {line[:100]}...")
                    continue
        
        return {
            "success": True,
            "invoices": invoices,
            "total_invoices": len(invoices)
        }
        
    except Exception as e:
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