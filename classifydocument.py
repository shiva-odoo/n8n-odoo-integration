import boto3
import base64
import anthropic
import os
import json
import re

def get_classification_prompt(company_name):
    """Create classification prompt with ultra-strict company role identification"""
    
    # Generate company name variations for better matching
    company_variations = generate_company_variations(company_name)
    
    return f"""You are a highly accurate document classification AI assistant. Perform strict OCR analysis on the uploaded document and extract key information in the specified JSON format.

**CRITICAL OUTPUT REQUIREMENT:**
Your response must contain ONLY valid JSON. No explanations, comments, or markdown.
Start directly with {{{{ and end with }}}}.

**USER'S COMPANY:** "{company_name}"

**COMPANY NAME MATCHING:**
Match ANY of these variations:
{company_variations}

═══════════════════════════════════════════════════════════════════════════════
CLASSIFICATION ALGORITHM - FOLLOW EXACTLY IN THIS ORDER
═══════════════════════════════════════════════════════════════════════════════

**STEP 1: SHARE DOCUMENT CHECK (HIGHEST PRIORITY)**
Does document contain: share certificates, stock documents, equity allocations, ESOP, shareholder agreements, dividend declarations?

✓ YES → Output: {{"document_type": "share_document", "category": "money_coming_in", ...}}
✗ NO → Continue to Step 2

═══════════════════════════════════════════════════════════════════════════════

**STEP 2: EXTRACT DOCUMENT STRUCTURE**

You MUST identify these fields from the document:

A. **DOCUMENT ISSUER** (Who created/sent this document?)
   Look at the TOP/HEADER area for:
   - Company name in largest text at top
   - Logo position (top left/center)
   - Fields: "FROM:", "VENDOR:", "SELLER:", "ISSUED BY:"
   - GST/Tax number in header area
   - Contact details at top (phone/email/address)
   
   Write down: **ISSUER = [Company Name]**

B. **DOCUMENT RECIPIENT** (Who receives/must pay this document?)
   Look in the BODY/MIDDLE area for:
   - Fields: "TO:", "BILL TO:", "CUSTOMER:", "CLIENT:", "BUYER:", "RECEIVER:", "SOLD TO:"
   - Company name appearing AFTER header section
   - Labeled as purchaser/client/customer
   
   Write down: **RECIPIENT = [Company Name]**

C. **BANK ACCOUNT OWNER** (Whose account for payment?)
   Look at BOTTOM area for:
   - "Pay to:", "Remit to:", "Bank details:", "Account holder:"
   - Bank account name
   
   Write down: **BANK ACCOUNT BELONGS TO = [Company Name]**

═══════════════════════════════════════════════════════════════════════════════

**STEP 3: APPLY THE ABSOLUTE CLASSIFICATION RULES**

🚨🚨🚨 **THE FUNDAMENTAL RULE - READ THIS CAREFULLY** 🚨🚨🚨

**FROM THE USER'S COMPANY PERSPECTIVE:**

A document is an **INVOICE** when:
- The user's company ({company_name}) ISSUED/CREATED the document
- The user's company is REQUESTING payment FROM a customer
- The user's company will RECEIVE money
- The user's company appears as the SELLER/VENDOR/SERVICE PROVIDER

A document is a **BILL** when:
- Another company ISSUED/CREATED the document
- The user's company RECEIVED the document
- The user's company must PAY money TO the vendor
- The user's company appears as the BUYER/CUSTOMER/CLIENT

**SIMPLE TEST:** "Who issued this document?"
- {company_name} issued it → INVOICE (money_coming_in)
- Another company issued it → BILL (money_going_out)

═══════════════════════════════════════════════════════════════════════════════

🚨 **RULE A: WHO IS THE CUSTOMER/RECIPIENT? (CHECK THIS FIRST)**

Is "{company_name}" mentioned in ANY of these fields?
- "TO:", "BILL TO:", "CUSTOMER:", "CLIENT:", "BUYER:", "RECEIVER:", "SOLD TO:", "SHIP TO:"

✓ **YES** → {company_name} is the CUSTOMER receiving the document
   → Another company issued this document TO {company_name}
   → From {company_name}'s perspective: This is a BILL they must pay
   
   **MANDATORY OUTPUT:**
   - document_type = "bill"
   - category = "money_going_out"
   - reasoning = "{company_name} appears in CUSTOMER/RECEIVER/TO field. They are receiving this document from a vendor and must pay. This is a BILL from their perspective."
   
   **STOP HERE. DO NOT CONTINUE TO OTHER RULES.**

✗ **NO** → Continue to Rule B

---

🚨 **RULE B: WHO IS THE ISSUER/VENDOR? (CHECK THIS SECOND)**

Is "{company_name}" in the HEADER/TOP section AS THE ISSUER?
- Company name at top of page (largest text)
- Next to logo in header
- In "FROM:", "VENDOR:", "SELLER:" fields
- GST/Tax number at top belongs to them

✓ **YES** → {company_name} is the ISSUER of this document
   → AND another company appears in TO:/CUSTOMER: field?
   → From {company_name}'s perspective: This is an INVOICE they issued to collect payment
   
   **MANDATORY OUTPUT:**
   - document_type = "invoice"
   - category = "money_coming_in"
   - reasoning = "{company_name} issued this document to [customer name]. They are requesting payment. This is an INVOICE from their perspective."
   
   **STOP HERE.**

✗ **NO** → Continue to Rule C

---

🚨 **RULE C: BANK ACCOUNT RULE**

Whose bank account is listed for payment?

✓ Bank account belongs to "{company_name}"
   → Output: document_type = "invoice", category = "money_coming_in"
   
✓ Bank account belongs to ANOTHER company
   → Output: document_type = "bill", category = "money_going_out"

✗ No clear bank account or unclear → Continue to Rule D

---

🚨 **RULE D: PAYMENT LOGIC TEST**

Based on ALL the information, answer this question:
**"In this transaction, will {company_name} SEND money or RECEIVE money?"**

- If {company_name} will **SEND/PAY** money → document_type = "bill", category = "money_going_out"
- If {company_name} will **RECEIVE/GET PAID** money → document_type = "invoice", category = "money_coming_in"
- Cannot determine → document_type = null, category = "illegible_document"

═══════════════════════════════════════════════════════════════════════════════

**STEP 4: CRITICAL VALIDATION BEFORE OUTPUT**

Before generating JSON, verify:

✓ If "{company_name}" is in TO:/CUSTOMER:/RECEIVER: field → MUST be bill + money_going_out
✓ If "{company_name}" is in FROM:/VENDOR:/header → MUST be invoice + money_coming_in
✓ Document type and category must match:
  - invoice → money_coming_in
  - bill → money_going_out
  - share_document → money_coming_in

❌ **FORBIDDEN COMBINATIONS:**
- "{company_name}" in CUSTOMER field + document_type="invoice" → WRONG! Must be "bill"
- "{company_name}" in CUSTOMER field + category="money_coming_in" → WRONG! Must be "money_going_out"
- document_type="bill" + category="money_coming_in" → WRONG!
- document_type="invoice" + category="money_going_out" → WRONG!

═══════════════════════════════════════════════════════════════════════════════

**STEP 5: COMMON MISTAKE PREVENTION**

⚠️ **CRITICAL: UNDERSTANDING PERSPECTIVE**

The classification is ALWAYS from the user's company perspective ({company_name}).

**Scenario 1: Document titled "INVOICE" with {company_name} in CUSTOMER field**
- Document header: "VENDOR COMPANY XYZ - INVOICE #123"
- Body: "TO: {company_name}" or "CUSTOMER: {company_name}"
- Amount: €400

**Analysis:**
- Who issued this? VENDOR COMPANY XYZ (NOT {company_name})
- Who must pay? {company_name}
- From {company_name}'s perspective: They RECEIVED an invoice FROM a vendor

**CORRECT CLASSIFICATION:**
- document_type = "bill" (because {company_name} received it and must pay)
- category = "money_going_out" (money leaves {company_name} to pay vendor)
- reasoning = "{company_name} is in CUSTOMER/TO field. They received this from a vendor and must pay. This is a BILL from their perspective, even though the document says 'INVOICE'."

---

**Scenario 2: Document issued BY {company_name} with customer in TO field**
- Document header: "{company_name} - INVOICE #456"
- Body: "TO: ABC CUSTOMER LTD" or "CUSTOMER: ABC CUSTOMER LTD"
- Amount: €500

**Analysis:**
- Who issued this? {company_name}
- Who must pay? ABC CUSTOMER LTD
- From {company_name}'s perspective: They ISSUED an invoice TO a customer

**CORRECT CLASSIFICATION:**
- document_type = "invoice" (because {company_name} issued it)
- category = "money_coming_in" (money comes to {company_name} from customer)
- reasoning = "{company_name} issued this document to ABC CUSTOMER LTD. They are requesting payment. This is an INVOICE from their perspective."

---

⚠️ **THE GOLDEN RULE:**
**If {company_name} is in the TO/CUSTOMER/RECEIVER field → They are RECEIVING the document → It's a BILL from their perspective**

**If {company_name} is in the FROM/HEADER/ISSUER field → They are ISSUING the document → It's an INVOICE from their perspective**

**IGNORE the document title (INVOICE/BILL). Trust the field positions and document structure.**

═══════════════════════════════════════════════════════════════════════════════

**DOCUMENT TYPES:**
- "share_document": Share/stock/equity docs (always money_coming_in)
- "invoice": User issued it, requesting payment (money_coming_in)
- "bill": User received it, must pay vendor (money_going_out)
- "bank_statement": Bank statement
- null: Illegible only

**CATEGORIES:**
- "money_coming_in": User receives money
- "money_going_out": User pays money
- "bank_statement": Bank statement
- "illegible_document": Cannot determine

**REQUIRED JSON OUTPUT:**
{{{{
  "document_type": "invoice|bill|bank_statement|share_document|null",
  "category": "money_coming_in|money_going_out|bank_statement|illegible_document",
  "company_name": "{company_name}",
  "total_amount": 1250.00,
  "confidence_score": 0.95,
  "reasoning": "Brief explanation"
}}}}

═══════════════════════════════════════════════════════════════════════════════

**FINAL DECISION TREE (USE THIS):**

Start here and follow exactly:

1. **Is this a share document?**
   YES → share_document + money_coming_in | NO → Go to 2

2. **Does "{company_name}" appear in TO:/CUSTOMER:/RECEIVER:/BILL TO:/CLIENT: field?**
   YES → {company_name} is RECEIVING the document from a vendor
         → bill + money_going_out
         → STOP
   NO → Go to 3

3. **Does "{company_name}" appear in FROM:/VENDOR:/HEADER (as issuer) AND another company in TO:/CUSTOMER: field?**
   YES → {company_name} is ISSUING the document to a customer
         → invoice + money_coming_in
         → STOP
   NO → Go to 4

4. **Does the bank account for payment belong to "{company_name}"?**
   YES → {company_name} receives payment
         → invoice + money_coming_in
         → STOP
   NO → Go to 5

5. **Does the bank account for payment belong to another company?**
   YES → {company_name} must pay to that account
         → bill + money_going_out
         → STOP
   NO → Go to 6

6. **Cannot determine who issued the document or payment direction?**
   YES → null + illegible_document

═══════════════════════════════════════════════════════════════════════════════

⚠️ **REMEMBER:** 
- **If {company_name} is in CUSTOMER/TO/RECEIVER field** → They RECEIVED the document → bill + money_going_out
- **If {company_name} is in FROM/VENDOR/HEADER field** → They ISSUED the document → invoice + money_coming_in
- **Document title (INVOICE/BILL) is NOT reliable** - a document titled "INVOICE" can be a BILL from the user's perspective if they are the recipient
- **Perspective matters**: Classification is ALWAYS from {company_name}'s perspective, not the document creator's perspective"""

def generate_company_variations(company_name):
    """Generate common variations of company name for better matching"""
    variations = [company_name]
    
    # Remove common suffixes for matching
    suffixes = [
        ' Pvt Ltd', ' Private Limited', ' Pvt. Ltd.', ' Private Ltd',
        ' Ltd', ' Limited', ' LLC', ' Inc', ' Corp', ' Corporation',
        ' LLP', ' LP', ' PLC', ' Co.', ' Company', ' ENTERPRISES LIMITED',
        ' Enterprises Limited', ' ENTERPRISES LTD', ' Enterprises Ltd'
    ]
    
    name_without_suffix = company_name
    for suffix in suffixes:
        if company_name.upper().endswith(suffix.upper()):
            name_without_suffix = company_name[:len(company_name)-len(suffix)].strip()
            variations.append(name_without_suffix)
            break
    
    # Add common abbreviations
    if len(name_without_suffix.split()) > 1:
        words = name_without_suffix.split()
        acronym = ''.join([w[0].upper() for w in words if w])
        if len(acronym) > 1:
            variations.append(acronym)
    
    # Format variations as bullet list
    return '\n'.join([f"  - {var}" for var in set(variations)])

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
        
        # Send to Claude
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2500,
            temperature=0,
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
        bucket_name = data.get('bucket_name')
        
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
                
                # CRITICAL: Post-processing validation and auto-correction
                validation_result = validate_and_correct_classification(
                    classification_data, 
                    company_name,
                    result["classification"]
                )
                
                if validation_result["corrected"]:
                    print(f"⚠️ AUTO-CORRECTED: {validation_result['correction_reason']}")
                    classification_data = validation_result["corrected_data"]
                
                if validation_result["warnings"]:
                    print(f"⚠️ Validation warnings: {validation_result['warnings']}")
                
                return {
                    "success": True,
                    "result": classification_data,
                    "metadata": {
                        "token_usage": result["token_usage"],
                        "s3_key": s3_key,
                        "company_name": company_name,
                        "validation": {
                            "corrected": validation_result["corrected"],
                            "correction_reason": validation_result.get("correction_reason"),
                            "warnings": validation_result.get("warnings")
                        }
                    }
                }
                
            except json.JSONDecodeError as e:
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

def validate_and_correct_classification(classification_data, company_name, raw_response):
    """
    Validate classification and auto-correct obvious errors
    Returns dict with correction status and warnings
    """
    doc_type = classification_data.get("document_type")
    category = classification_data.get("category")
    reasoning = classification_data.get("reasoning", "").lower()
    
    corrected = False
    correction_reason = None
    warnings = []
    
    # CRITICAL CHECK 1: Detect reasoning contradictions
    # If reasoning says "must pay" or "customer" but classified as invoice
    customer_keywords = [
        "customer who must pay", "kyrastel.*must pay", "kyrastel.*customer",
        "kyrastel.*receiver", "kyrastel.*client", "receiving this invoice",
        "kyrastel.*are the customer", "pay this invoice"
    ]
    
    is_customer_in_reasoning = any(
        re.search(pattern, reasoning, re.IGNORECASE) 
        for pattern in customer_keywords
    )
    
    if is_customer_in_reasoning and (doc_type == "invoice" or category == "money_coming_in"):
        # CRITICAL ERROR: Reasoning says customer but classified as invoice
        classification_data["document_type"] = "bill"
        classification_data["category"] = "money_going_out"
        classification_data["reasoning"] = (
            f"CORRECTED: {company_name} is the CUSTOMER/RECEIVER, "
            "therefore they must PAY. This is a bill, not an invoice."
        )
        corrected = True
        correction_reason = "Reasoning indicated customer role but was classified as invoice"
    
    # CRITICAL CHECK 2: Logical consistency rules
    if doc_type == "share_document" and category != "money_coming_in":
        classification_data["category"] = "money_coming_in"
        classification_data["reasoning"] = "Auto-corrected: Share documents always represent money_coming_in"
        corrected = True
        correction_reason = "Share document must be money_coming_in"
    
    if doc_type == "invoice" and category != "money_coming_in":
        classification_data["category"] = "money_coming_in"
        corrected = True
        correction_reason = "Invoice must be money_coming_in"
        warnings.append("Invoice was incorrectly categorized")
    
    if doc_type == "bill" and category != "money_going_out":
        classification_data["category"] = "money_going_out"
        corrected = True
        correction_reason = "Bill must be money_going_out"
        warnings.append("Bill was incorrectly categorized")
    
    # CRITICAL CHECK 3: Category-to-type consistency
    if category == "money_coming_in" and doc_type not in ["invoice", "share_document", "bank_statement"]:
        if doc_type == "bill":
            # This is a critical error - bill cannot be money_coming_in
            classification_data["category"] = "money_going_out"
            corrected = True
            correction_reason = "Bill cannot be money_coming_in, corrected to money_going_out"
        else:
            warnings.append(f"Inconsistent: category='money_coming_in' but document_type='{doc_type}'")
    
    if category == "money_going_out" and doc_type not in ["bill", "bank_statement"]:
        if doc_type == "invoice":
            # Critical error - invoice cannot be money_going_out
            classification_data["category"] = "money_coming_in"
            corrected = True
            correction_reason = "Invoice cannot be money_going_out, corrected to money_coming_in"
        elif doc_type == "share_document":
            # CRITICAL: share_document can NEVER be money_going_out
            classification_data["category"] = "money_coming_in"
            corrected = True
            correction_reason = "Share document can NEVER be money_going_out"
        else:
            warnings.append(f"Inconsistent: category='money_going_out' but document_type='{doc_type}'")
    
    # Check confidence score
    confidence = classification_data.get("confidence_score", 1.0)
    if confidence < 0.6:
        warnings.append(f"Low confidence ({confidence}). Manual review recommended.")
    
    return {
        "corrected": corrected,
        "correction_reason": correction_reason,
        "warnings": " | ".join(warnings) if warnings else None,
        "corrected_data": classification_data if corrected else None
    }

def health_check():
    """Health check for the classification service"""
    try:
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
            "version": "3.1-strict-customer-field-validation",
            "anthropic_configured": bool(os.getenv('ANTHROPIC_API_KEY')),
            "aws_configured": bool(os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY')),
            "s3_bucket": os.getenv('S3_BUCKET_NAME', 'company-documents-2025')
        }
        
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e)
        }