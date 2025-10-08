import boto3
import base64
import anthropic
import os
import json

def get_classification_prompt(company_name):
    """Create classification prompt with ultra-strict company role identification"""
    
    # Generate company name variations for better matching
    company_variations = generate_company_variations(company_name)
    
    return f"""You are a highly accurate document classification AI assistant. Perform strict OCR analysis on the uploaded document and extract key information in the specified JSON format. Misclassification can cause critical errors, so follow all rules strictly.

**CRITICAL OUTPUT REQUIREMENT:**
- Your response must contain ONLY valid JSON. No explanations, comments, markdown, text, or any other content before or after the JSON.
- Start your response directly with the opening brace {{{{ and end with the closing brace }}}}.
- Any additional text will cause system errors.

**COMPANY CONTEXT:**
The user's company is: "{company_name}"

**COMPANY NAME MATCHING - IMPORTANT:**
The company name may appear with variations. Match ANY of these forms:
{company_variations}

When you see any of these variations, treat it as "{company_name}".

**CLASSIFICATION RULES:**

═══════════════════════════════════════════════════════════════════════════════
STEP 1: SHARE DOCUMENT CHECK (HIGHEST PRIORITY - DO THIS FIRST)
═══════════════════════════════════════════════════════════════════════════════

Does this document contain ANY of these indicators:
- Share certificates, stock certificates, equity documents
- Shareholder agreements with share allocations
- Share transfer documents, share allotment letters
- ESOP (Employee Stock Ownership Plan) documents
- Corporate filings related to shares/equity
- Dividend declarations, stock option grants
- Keywords: "shares", "equity", "stock", "shareholder", "securities", "shareholding"

✓ If YES → IMMEDIATELY classify as:
  * document_type = "share_document"
  * category = "money_coming_in"
  * STOP HERE - Do not apply any other rules

✗ If NO → Continue to Step 2

🚨 CRITICAL: ALL share documents = money_coming_in (represents ownership/value coming to company)

═══════════════════════════════════════════════════════════════════════════════
STEP 2: DOCUMENT TYPE IDENTIFICATION
═══════════════════════════════════════════════════════════════════════════════

Identify the document type by looking for these keywords and structural patterns:

**INVOICE Indicators:**
- Words: "INVOICE", "TAX INVOICE", "SALES INVOICE", "PROFORMA INVOICE"
- Phrases: "Please pay", "Payment due", "Amount payable to us", "Remit payment to"
- Structure: Company logo/header at TOP, customer details in middle/body
- Payment flow: Money should flow TO the issuing company

**BILL/PURCHASE ORDER Indicators:**
- Words: "BILL", "PURCHASE ORDER", "PO", "RECEIPT", "PAYMENT REQUEST"
- Phrases: "Amount due", "Please remit payment", "Pay to the order of [another company]"
- Structure: Vendor/seller details at TOP, buyer/customer details below
- Payment flow: Money should flow FROM the recipient TO the vendor

**Bank Statement Indicators:**
- Bank name in header (e.g., "State Bank of India", "HDFC Bank", "ICICI Bank")
- Account number, transaction list, opening/closing balance
- Words: "Statement", "Account Statement", "Transaction History"

═══════════════════════════════════════════════════════════════════════════════
STEP 3: DOCUMENT STRUCTURE ANALYSIS (CRITICAL FOR CLASSIFICATION)
═══════════════════════════════════════════════════════════════════════════════

**3A. IDENTIFY THE DOCUMENT ISSUER (Who created and sent this document?)**

Look for these ISSUER indicators at the TOP/HEADER of the document:
✓ Company name in letterhead/header (usually largest text at top)
✓ Company logo at the top
✓ "FROM:", "SELLER:", "VENDOR:", "SERVICE PROVIDER:" fields
✓ GST number/Tax ID belonging to which company (at top)
✓ Contact details in header (phone, email, address at top)
✓ Bank account with "Please pay to:", "Remit to:", "Our bank details:"

**Document ISSUER = [Write the company name here]**

**3B. IDENTIFY THE RECIPIENT/CUSTOMER (Who must pay this document?)**

Look for these RECIPIENT indicators in the BODY/MIDDLE section:
✓ "TO:", "BILL TO:", "SOLD TO:", "CUSTOMER:" fields
✓ "BUYER:", "CLIENT:", "SHIP TO:" fields
✓ Address block that starts with "To:" or is clearly labeled as recipient
✓ Company name that appears AFTER the header section

**Document RECIPIENT = [Write the company name here]**

**3C. CROSS-REFERENCE WITH USER'S COMPANY**

Now perform these checks in order:

CHECK 1: Is "{company_name}" (or any variation) the ISSUER?
- Is the company name in the TOP/HEADER section?
- Is the company name next to the logo?
- Is it in "FROM:", "VENDOR:", "SELLER:" fields?
- Does the bank account belong to "{company_name}"?

→ If YES to any: The user's company ISSUED this document
   RESULT: document_type = "invoice", category = "money_coming_in"
   LOGIC: User's company is requesting payment from customer
   
→ If NO: Continue to CHECK 2

CHECK 2: Is "{company_name}" (or any variation) the RECIPIENT?
- Is the company name in "TO:", "BILL TO:", "CUSTOMER:", "CLIENT:" fields?
- Is it in the middle/body section (not header)?
- Is it labeled as the buyer/purchaser/client?
- Does another company's bank account appear at the bottom?

→ If YES to any: The user's company RECEIVED this document
   RESULT: document_type = "bill", category = "money_going_out"
   LOGIC: User's company must pay another company
   
→ If NO: Continue to CHECK 3

CHECK 3: Where does "{company_name}" appear (if at all)?
- Appears ONLY at top/header → User is ISSUER → invoice + money_coming_in
- Appears ONLY in body/TO section → User is RECIPIENT → bill + money_going_out
- Appears in BOTH sections → AMBIGUOUS → Continue to Step 4 for tie-breaker
- Does NOT appear → Cannot determine → illegible_document
- Appears but unclear which section → Continue to Step 4 for tie-breaker

═══════════════════════════════════════════════════════════════════════════════
STEP 4: TIE-BREAKER RULES (Use when Step 3 is ambiguous)
═══════════════════════════════════════════════════════════════════════════════

**4A. BANK ACCOUNT OWNERSHIP TEST**
- Find bank account details (usually at bottom of document)
- Read the account holder name carefully
- If account belongs to "{company_name}" → money_coming_in (they receive payment)
- If account belongs to ANOTHER company → money_going_out (they must pay)

**4B. PAYMENT DIRECTION TEST**
Look for phrases that indicate payment direction:
- "Please pay us", "Remit payment to us", "Amount payable to [company_name]" → money_coming_in
- "Please pay to [other company]", "Amount due to [vendor]" → money_going_out

**4C. DOCUMENT TITLE vs STRUCTURE TEST**
⚠️ IMPORTANT: Document title can be misleading!
- If document says "INVOICE" but "{company_name}" is in TO:/CUSTOMER: field
  → IGNORE title → Apply structure analysis → bill + money_going_out
  
- If document says "BILL" but "{company_name}" is in FROM:/header
  → IGNORE title → Apply structure analysis → invoice + money_coming_in

**4D. GST/TAX NUMBER LOCATION TEST**
- GST/Tax number at TOP usually belongs to the ISSUER
- If it matches "{company_name}" → invoice + money_coming_in
- If it belongs to another company → bill + money_going_out

**4E. MULTIPLE MENTIONS TEST**
If "{company_name}" appears multiple times:
- Count how many times it appears in ISSUER positions (header, FROM, logo area)
- Count how many times it appears in RECIPIENT positions (TO, CUSTOMER, body)
- Whichever count is higher determines the classification
- If tied or unclear → illegible_document

═══════════════════════════════════════════════════════════════════════════════
STEP 5: MANDATORY GOLDEN RULES (OVERRIDE ALL OTHER ANALYSIS)
═══════════════════════════════════════════════════════════════════════════════

🚨 **GOLDEN RULE 1: THE HEADER POSITION RULE**
Company in the TOP/HEADER section with logo = ISSUER = GETS PAID
- If "{company_name}" is in header → invoice + money_coming_in
- NO EXCEPTIONS

🚨 **GOLDEN RULE 2: THE "TO:" FIELD RULE**
Company in "TO:", "BILL TO:", "CUSTOMER:", "CLIENT:" fields = RECIPIENT = PAYS
- If "{company_name}" is in these fields → bill + money_going_out
- NO EXCEPTIONS
- Even if document is titled "INVOICE", if user's company is in TO: → it's a BILL

🚨 **GOLDEN RULE 3: THE BANK ACCOUNT RULE**
Whose bank account is listed for payment?
- "{company_name}" bank account → invoice + money_coming_in (they receive money)
- Another company's bank account → bill + money_going_out (they send money)

🚨 **GOLDEN RULE 4: THE PAYMENT FLOW RULE**
Ask yourself: "Based on this document, will {company_name} RECEIVE or SEND money?"
- RECEIVE money → invoice + money_coming_in
- SEND money → bill + money_going_out
- Cannot determine → illegible_document

🚨 **GOLDEN RULE 5: SHARE DOCUMENTS OVERRIDE EVERYTHING**
If Step 1 identified this as a share document:
- document_type = "share_document"
- category = "money_coming_in"
- IGNORE all other rules
- NEVER classify as bill or money_going_out

═══════════════════════════════════════════════════════════════════════════════
STEP 6: FINAL VERIFICATION BEFORE OUTPUT
═══════════════════════════════════════════════════════════════════════════════

Before generating JSON, verify EVERY item on this checklist:

✓ [ ] I checked for share document indicators FIRST
✓ [ ] If share document → Set document_type="share_document", category="money_coming_in" and STOPPED
✓ [ ] I identified the document ISSUER (who created it)
✓ [ ] I identified the document RECIPIENT (who must pay it)
✓ [ ] I found "{company_name}" or its variations in the document
✓ [ ] I determined if "{company_name}" is ISSUER or RECIPIENT
✓ [ ] I applied the GOLDEN RULES correctly
✓ [ ] If "{company_name}" in header/FROM → invoice + money_coming_in
✓ [ ] If "{company_name}" in TO:/CUSTOMER → bill + money_going_out
✓ [ ] I verified bank account ownership matches my classification
✓ [ ] My classification makes logical sense: "Will {company_name} receive or send money?"
✓ [ ] If ANY ambiguity remains → I will classify as illegible_document

**DECISION TREE SUMMARY:**
1. Share document? → YES: share_document + money_coming_in | NO: Continue
2. "{company_name}" in header/FROM? → YES: invoice + money_coming_in | NO: Continue
3. "{company_name}" in TO:/CUSTOMER? → YES: bill + money_going_out | NO: Continue
4. Can determine from bank account? → YES: Use bank account owner | NO: Continue
5. Still unclear? → illegible_document

═══════════════════════════════════════════════════════════════════════════════
STEP 7: ILLEGIBLE DOCUMENT CRITERIA
═══════════════════════════════════════════════════════════════════════════════

Classify as illegible_document ONLY if:
- Cannot extract document number/ID AND cannot extract total amount
- Cannot find "{company_name}" anywhere in document
- "{company_name}" appears in ambiguous/contradictory positions
- Document is not a financial document (contracts, letters, memos without financial data)
- Image quality too poor to read company names or amounts
- Cannot determine with 80%+ confidence whether user is paying or receiving

DO NOT classify as illegible if:
- Document structure is clear (header vs body sections are distinguishable)
- Company name is found and position is determinable
- Document title exists (invoice/bill/statement)
- Amount is visible even if other fields are unclear

═══════════════════════════════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════════════════════════════

**DOCUMENT TYPES:**
- "share_document": Share/stock/equity documents (ALWAYS money_coming_in)
- "invoice": User's company issued it, requesting payment (money_coming_in)
- "bill": User's company received it, must pay vendor (money_going_out)
- "bank_statement": Bank-issued transaction statement
- null: Only for illegible documents

**CATEGORIES:**
- "money_coming_in": User's company RECEIVES money (invoices, share docs, some bank statements)
- "money_going_out": User's company PAYS money (bills, some bank statements)
- "bank_statement": Bank statement (can be either direction)
- "illegible_document": Cannot extract data or determine company role

**REQUIRED JSON OUTPUT:**
{{{{
  "document_type": "invoice|bill|bank_statement|share_document|null",
  "category": "money_coming_in|money_going_out|bank_statement|illegible_document",
  "company_name": "{company_name}",
  "total_amount": 1250.00,
  "confidence_score": 0.95,
  "reasoning": "Brief explanation of why this classification was chosen"
}}}}

**VALIDATION LOGIC:**
- share_document → MUST be money_coming_in
- invoice → MUST be money_coming_in
- bill → MUST be money_going_out
- bank_statement → category can be "bank_statement" or money_coming_in/money_going_out based on net flow
- null document_type → MUST be illegible_document category

⚠️ **FINAL REMINDERS:**
1. Share documents are NEVER money_going_out, ALWAYS money_coming_in
2. Company in TO:/CUSTOMER: field = PAYS = bill = money_going_out
3. Company in header/FROM: field = RECEIVES = invoice = money_coming_in
4. When in doubt, use illegible_document rather than guessing
5. Document title can be misleading - trust the structure and company positions over the title
6. Match company name variations (abbreviations, with/without legal suffixes)"""

def generate_company_variations(company_name):
    """Generate common variations of company name for better matching"""
    variations = [company_name]
    
    # Remove common suffixes for matching
    suffixes = [
        ' Pvt Ltd', ' Private Limited', ' Pvt. Ltd.', ' Private Ltd',
        ' Ltd', ' Limited', ' LLC', ' Inc', ' Corp', ' Corporation',
        ' LLP', ' LP', ' PLC', ' Co.', ' Company'
    ]
    
    name_without_suffix = company_name
    for suffix in suffixes:
        if company_name.endswith(suffix):
            name_without_suffix = company_name[:-len(suffix)].strip()
            variations.append(name_without_suffix)
            break
    
    # Add common abbreviations
    if len(name_without_suffix.split()) > 1:
        # Create acronym
        words = name_without_suffix.split()
        acronym = ''.join([w[0].upper() for w in words if w])
        if len(acronym) > 1:
            variations.append(acronym)
    
    # Format variations as bullet list
    return '\n'.join([f"  - {var}" for var in variations])

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
            max_tokens=2500,  # Increased for detailed reasoning
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
                    
                    # If critical error, try to auto-correct
                    if "CRITICAL" in validation_result["warning"]:
                        classification_data = auto_correct_classification(classification_data)
                        print(f"Auto-corrected to: {classification_data}")
                
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
            f"CRITICAL ERROR: document_type='invoice' but category='{category}'. "
            "Invoices should always be money_coming_in. Possible misclassification."
        )
    
    # Rule 2: bill must always be money_going_out
    if doc_type == "bill" and category != "money_going_out":
        validation_warnings.append(
            f"CRITICAL ERROR: document_type='bill' but category='{category}'. "
            "Bills should always be money_going_out. Possible misclassification."
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
            f"CRITICAL ERROR: category='money_going_out' but document_type='{doc_type}'. "
            "Expected 'bill' or 'bank_statement'. Share documents can NEVER be money_going_out."
        )
    
    # Rule 5: Explicit check - share_document can NEVER be money_going_out
    if doc_type == "share_document" and category == "money_going_out":
        validation_warnings.append(
            f"CRITICAL MISCLASSIFICATION: Share documents can NEVER be classified as money_going_out. "
            f"This must be corrected to money_coming_in."
        )
    
    # Rule 6: Check confidence score if provided
    confidence = classification_data.get("confidence_score", 1.0)
    if confidence < 0.6:
        validation_warnings.append(
            f"Low confidence score ({confidence}). Consider reviewing this classification manually."
        )
    
    return {
        "valid": len(validation_warnings) == 0,
        "warning": " | ".join(validation_warnings) if validation_warnings else None
    }

def auto_correct_classification(classification_data):
    """
    Automatically correct obvious misclassifications
    """
    doc_type = classification_data.get("document_type")
    category = classification_data.get("category")
    
    # Fix share_document misclassifications
    if doc_type == "share_document" and category != "money_coming_in":
        classification_data["category"] = "money_coming_in"
        classification_data["reasoning"] = "Auto-corrected: Share documents always represent money_coming_in"
    
    # Fix invoice/bill mismatches
    if doc_type == "invoice" and category != "money_coming_in":
        classification_data["category"] = "money_coming_in"
        classification_data["reasoning"] = "Auto-corrected: Invoices always represent money_coming_in"
    
    if doc_type == "bill" and category != "money_going_out":
        classification_data["category"] = "money_going_out"
        classification_data["reasoning"] = "Auto-corrected: Bills always represent money_going_out"
    
    return classification_data

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
            "version": "3.0-enhanced-structure-analysis",
            "anthropic_configured": bool(os.getenv('ANTHROPIC_API_KEY')),
            "aws_configured": bool(os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY')),
            "s3_bucket": os.getenv('S3_BUCKET_NAME', 'company-documents-2025')
        }
        
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e)
        }