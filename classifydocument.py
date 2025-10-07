import boto3
import base64
import anthropic
import os
import json

def get_classification_prompt(company_name):
    """Create classification prompt with ultra-strict company role identification"""
    return f"""You are a highly accurate document classification AI assistant. Perform strict OCR analysis on the uploaded document and extract key information in the specified JSON format. Misclassification can cause critical errors, so follow all rules strictly.

**CRITICAL OUTPUT REQUIREMENT:**
- Your response must contain ONLY valid JSON. No explanations, comments, markdown, text, or any other content before or after the JSON.
- Start your response directly with the opening brace {{{{ and end with the closing brace }}}}.
- Any additional text will cause system errors.

**COMPANY CONTEXT:**
The user's company is: "{company_name}"

**CLASSIFICATION RULES:**

1. **SHARE DOCUMENT CHECK (Do this FIRST - HIGHEST PRIORITY):**
   - Does this document contain ANY of these indicators:
     * Share certificates
     * Stock certificates
     * Equity documents
     * Shareholder agreements with share allocations
     * Share transfer documents
     * Corporate filings related to shares/equity
     * ESOP (Employee Stock Ownership Plan) documents
     * Share allotment letters
     * Dividend declarations
     * Words like "shares", "equity", "stock", "shareholder"
   - If YES → IMMEDIATELY classify as:
     * document_type = "share_document"
     * category = "money_coming_in"
     * STOP HERE - Do not apply any other rules
   - If NO → Continue to step 2

🚨 **CRITICAL RULE: ALL SHARE DOCUMENTS = money_coming_in**
- Share documents ALWAYS represent value/ownership coming to the company
- NEVER classify share documents as "money_going_out" or "bill"
- Even if company name appears in "TO:" field on a share document, it's still money_coming_in

2. **DOCUMENT RELEVANCE CHECK:**
   - Is this document a bill, invoice, bank statement, or share document with financial implications?
   - If NO (e.g., contracts, memos, letters, reports, certificates without financial data) → classify as illegible_document

3. **ILLEGIBLE DOCUMENT CHECK:**
   - Can you extract document number/ID? (YES/NO)
   - Can you extract total monetary amount? (YES/NO)
   - If BOTH answers are NO → classify as illegible_document

4. **MANDATORY COMPANY ROLE IDENTIFICATION - ULTRA STRICT VERIFICATION:**

⚠️ **CRITICAL INSTRUCTION: READ THIS CAREFULLY BEFORE PROCEEDING**

The single most important task is determining: **IS THE USER'S COMPANY PAYING OR GETTING PAID?**

**STEP 1: IDENTIFY THE DOCUMENT ISSUER (Who created this document?)**

Look for these ISSUER indicators at the TOP of the document:
- Company name in header/letterhead
- Logo at the top
- "FROM:" field
- "VENDOR:" field  
- "SELLER:" field
- "SERVICE PROVIDER:" field
- Bank account details for RECEIVING payment (usually at bottom with "Pay to:" or "Remit to:")

**Write down: Document was ISSUED BY: [Company Name]**

**STEP 2: IDENTIFY THE RECIPIENT/CUSTOMER (Who will pay this document?)**

Look for these RECIPIENT indicators:
- "TO:" field
- "CUSTOMER:" field
- "BILL TO:" field (when it refers to who is being billed)
- "CLIENT:" field
- "BUYER:" field
- "SOLD TO:" field
- "SHIP TO:" field
- The party that is being charged/invoiced

**Write down: Document will be PAID BY: [Company Name]**

**STEP 3: COMPARE WITH USER'S COMPANY**

User's company name: "{company_name}"

Now answer these questions:

**Q1: Is "{company_name}" the ISSUER of this document?**
- Check: Is "{company_name}" in the header, logo, or "FROM:" field?
- Answer: YES or NO
- If YES → User's company is REQUESTING payment → category = "money_coming_in", document_type = "invoice"
- If NO → Continue to Q2

**Q2: Is "{company_name}" the RECIPIENT/CUSTOMER of this document?**
- Check: Is "{company_name}" in "TO:", "CUSTOMER:", "BILL TO:", "CLIENT:" fields?
- Answer: YES or NO
- If YES → User's company is PAYING → category = "money_going_out", document_type = "bill"
- If NO → Continue to Q3

**Q3: Where does "{company_name}" appear on the document?**
- If it appears ONLY in the TO/CUSTOMER section → category = "money_going_out", document_type = "bill"
- If it appears ONLY in the FROM/VENDOR section → category = "money_coming_in", document_type = "invoice"
- If it appears in BOTH or NEITHER → classify as illegible_document
- If unclear or ambiguous → classify as illegible_document

**STEP 4: APPLY THE GOLDEN RULES (MANDATORY CHECKS)**

🚨 **GOLDEN RULE 1: THE "TO:" / "CUSTOMER:" RULE**
- If "{company_name}" appears in TO:, CUSTOMER:, BILL TO:, CLIENT:, BUYER:, or SOLD TO: fields
- THEN category = "money_going_out" and document_type = "bill"
- NO EXCEPTIONS - The "TO:" party ALWAYS pays!

🚨 **GOLDEN RULE 2: THE "FROM:" / "VENDOR:" RULE**
- If "{company_name}" appears in FROM:, VENDOR:, SELLER:, or the document header/logo
- AND another company appears in the TO:/CUSTOMER: field
- THEN category = "money_coming_in" and document_type = "invoice"
- NO EXCEPTIONS - The "FROM:" party ALWAYS gets paid!

🚨 **GOLDEN RULE 3: THE BANK ACCOUNT RULE**
- Find the bank account details on the document (usually at bottom)
- Read whose name is on the account: "Account holder:", "Pay to:", "Remit to:"
- If account belongs to "{company_name}" → category = "money_coming_in"
- If account belongs to ANOTHER company → category = "money_going_out"
- If no bank details or unclear → use FROM/TO fields instead

🚨 **GOLDEN RULE 4: THE POSITION RULE**
- Company in document HEADER/TOP = The issuer who will GET PAID
- Company in document BODY under TO:/CUSTOMER: = The recipient who will PAY
- "{company_name}" in header/top → money_coming_in
- "{company_name}" in TO:/CUSTOMER: section → money_going_out

🚨 **GOLDEN RULE 5: THE FINAL VERIFICATION**
Before finalizing classification, ask yourself:
- "Will {company_name} RECEIVE money from this transaction?" → If YES: money_coming_in
- "Will {company_name} SEND/PAY money from this transaction?" → If YES: money_going_out
- "Am I 100% certain of the answer?" → If NO: illegible_document

**STEP 5: HANDLE EDGE CASES**

**Case A: Document says "INVOICE" but user's company is in TO: field**
- IGNORE the document title
- Apply GOLDEN RULE 1
- Result: document_type = "bill", category = "money_going_out"

**Case B: Document says "BILL" but user's company is in FROM: field**
- IGNORE the document title  
- Apply GOLDEN RULE 2
- Result: document_type = "invoice", category = "money_coming_in"

**Case C: Multiple companies mentioned**
- Identify which company is in the ISSUER position (top/header)
- Identify which company is in the RECIPIENT position (TO:/CUSTOMER:)
- Apply the rules based on where "{company_name}" appears

**Case D: Document in foreign language**
- Look for structural cues: "FROM:", "TO:", company position on page
- Top company = issuer, TO: company = recipient
- Apply the rules accordingly

**Case E: Ambiguous or contradictory indicators**
- If you cannot determine with 100% certainty → illegible_document
- Never guess - better to flag as illegible than misclassify

**DOCUMENT TYPES:**
- "share_document": Share certificates, stock documents, equity documents (ALWAYS money_coming_in)
- "invoice": User's company ISSUED it, REQUESTING payment (money_coming_in)
- "bill": User's company RECEIVED it, MUST PAY another company (money_going_out)
- "bank_statement": Bank-issued statement with transactions
- null: Only for illegible documents

**CATEGORIES:**
- "money_coming_in": User's company RECEIVES money/value (invoices, share documents)
- "money_going_out": User's company PAYS money (bills only)
- "bank_statement": Bank statement
- "illegible_document": Cannot extract key financial data OR cannot determine company role

**REQUIRED JSON OUTPUT FORMAT:**
{{{{
  "document_type": "invoice|bill|bank_statement|share_document|null",
  "category": "money_coming_in|money_going_out|bank_statement|illegible_document",
  "company_name": "{company_name}",
  "total_amount": 1250.00
}}}}

**MANDATORY PRE-OUTPUT VERIFICATION CHECKLIST:**

Before you output the JSON, you MUST verify:

✓ [ ] I checked if this is a SHARE DOCUMENT first (Step 1)
✓ [ ] If it's a share document → I set document_type="share_document" and category="money_coming_in"
✓ [ ] I found where "{company_name}" appears on the document
✓ [ ] I identified if "{company_name}" is in the ISSUER position (header/FROM/vendor)
✓ [ ] I identified if "{company_name}" is in the RECIPIENT position (TO/CUSTOMER/bill to)
✓ [ ] I applied the GOLDEN RULES correctly
✓ [ ] If "{company_name}" is in TO:/CUSTOMER: → I set category = "money_going_out" and document_type = "bill"
✓ [ ] If "{company_name}" is in FROM:/header → I set category = "money_coming_in" and document_type = "invoice"
✓ [ ] I double-checked the bank account owner (if present)
✓ [ ] My classification passes the logic test: "Will {company_name} pay or get paid?"
✓ [ ] If any doubt exists → I classified as illegible_document

**VALIDATION RULES:**
- ALL share documents MUST be: document_type="share_document", category="money_coming_in"
- document_type and category must follow the logic above
- total_amount must be numeric or null
- If key financial data missing, use null + illegible_document
- If company role unclear after all checks, use null + illegible_document
- Response must be valid JSON only

⚠️ **FINAL WARNING: 
1. ALWAYS check for share documents FIRST before applying any other rules
2. Share documents are NEVER money_going_out, ALWAYS money_coming_in
3. The most common error is classifying a BILL as an INVOICE when the user's company appears in the TO:/CUSTOMER: field. Double-check this before outputting!**"""

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

def process_document_with_claude(pdf_content, company_name):
    """Process document with Claude and return classification"""
    try:
        # Initialize Anthropic client
        anthropic_client = anthropic.Anthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY')
        )
        
        # Encode to base64
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        
        # Get prompt
        prompt = get_classification_prompt(company_name)
        
        # Send to Claude with extended thinking for complex cases
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,  # Increased for better reasoning
            temperature=0,  # Set to 0 for maximum consistency
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
            "classification": response_text,
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
    Main function for document classification
    
    Args:
        data (dict): Request data containing:
            - company_name (str): The user's company name
            - s3_key (str): S3 key path to the document
            - bucket_name (str, optional): S3 bucket name
    
    Returns:
        dict: Classification result with success status and data
    """
    try:
        # Validate required fields
        if 'company_name' not in data:
            return {
                "success": False,
                "error": "company_name is required"
            }
            
        if 's3_key' not in data:
            return {
                "success": False,
                "error": "s3_key is required"
            }
        
        company_name = data['company_name']
        s3_key = data['s3_key']
        bucket_name = data.get('bucket_name')  # Optional
        
        print(f"Processing document for company: {company_name}, S3 key: {s3_key}")
        
        # Download PDF from S3
        pdf_content = download_from_s3(s3_key, bucket_name)
        print(f"Downloaded PDF, size: {len(pdf_content)} bytes")
        
        # Process with Claude
        result = process_document_with_claude(pdf_content, company_name)
        
        if result["success"]:
            try:
                # Parse Claude's JSON response
                classification_data = json.loads(result["classification"])
                
                # Post-processing validation to catch any remaining errors
                validation_result = validate_classification(classification_data, company_name)
                
                if not validation_result["valid"]:
                    print(f"Validation warning: {validation_result['warning']}")
                
                return {
                    "success": True,
                    "result": classification_data,
                    "metadata": {
                        "token_usage": result["token_usage"],
                        "s3_key": s3_key,
                        "company_name": company_name,
                        "validation": validation_result
                    }
                }
                
            except json.JSONDecodeError as e:
                # Handle case where Claude didn't return valid JSON
                return {
                    "success": False,
                    "error": "Claude returned invalid JSON",
                    "raw_response": result["classification"]
                }
        else:
            return {
                "success": False,
                "error": result["error"]
            }
            
    except Exception as e:
        print(f"Classification error: {str(e)}")
        return {
            "success": False,
            "error": f"Internal processing error: {str(e)}"
        }

def validate_classification(classification_data, company_name):
    """
    Post-processing validation to ensure classification logic is correct
    
    Returns dict with validation status and any warnings
    """
    doc_type = classification_data.get("document_type")
    category = classification_data.get("category")
    
    # Check for logical consistency
    validation_warnings = []
    
    # Rule 0: share_document must ALWAYS be money_coming_in
    if doc_type == "share_document" and category != "money_coming_in":
        validation_warnings.append(
            f"CRITICAL ERROR: document_type='share_document' but category='{category}'. "
            "Share documents MUST ALWAYS be money_coming_in. This is a misclassification."
        )
    
    # Rule 1: invoice must always be money_coming_in
    if doc_type == "invoice" and category != "money_coming_in":
        validation_warnings.append(
            f"Logical error: document_type='invoice' but category='{category}'. "
            "Invoices should always be money_coming_in."
        )
    
    # Rule 2: bill must always be money_going_out
    if doc_type == "bill" and category != "money_going_out":
        validation_warnings.append(
            f"Logical error: document_type='bill' but category='{category}'. "
            "Bills should always be money_going_out."
        )
    
    # Rule 3: money_coming_in must be invoice, share_document, or bank_statement
    if category == "money_coming_in" and doc_type not in ["invoice", "share_document", "bank_statement"]:
        validation_warnings.append(
            f"Logical error: category='money_coming_in' but document_type='{doc_type}'. "
            "Expected 'invoice', 'share_document', or 'bank_statement'."
        )
    
    # Rule 4: money_going_out must be bill or bank_statement (NEVER share_document)
    if category == "money_going_out" and doc_type not in ["bill", "bank_statement"]:
        validation_warnings.append(
            f"Logical error: category='money_going_out' but document_type='{doc_type}'. "
            "Expected 'bill' or 'bank_statement'. Share documents can NEVER be money_going_out."
        )
    
    # Rule 5: Explicit check - share_document can NEVER be money_going_out
    if doc_type == "share_document" and category == "money_going_out":
        validation_warnings.append(
            f"CRITICAL MISCLASSIFICATION: Share documents can NEVER be classified as money_going_out. "
            f"This must be corrected to money_coming_in."
        )
    
    return {
        "valid": len(validation_warnings) == 0,
        "warning": " | ".join(validation_warnings) if validation_warnings else None
    }

def health_check():
    """Health check for the classification service"""
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
            "service": "claude-document-classification",
            "version": "2.1-share-fixed",
            "anthropic_configured": bool(os.getenv('ANTHROPIC_API_KEY')),
            "aws_configured": bool(os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY')),
            "s3_bucket": os.getenv('S3_BUCKET_NAME', 'company-documents-2025')
        }
        
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e)
        }