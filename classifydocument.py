import boto3
import base64
import anthropic
import os
import json

def get_classification_prompt(company_name):
    """Create classification prompt with strict company role identification"""
    return f"""You are a highly accurate document classification AI assistant. Perform strict OCR analysis on the uploaded document and extract key information in the specified JSON format. Misclassification can cause critical errors, so follow all rules strictly.

**CRITICAL OUTPUT REQUIREMENT:**
- Your response must contain ONLY valid JSON. No explanations, comments, markdown, text, or any other content before or after the JSON.
- Start your response directly with the opening brace {{{{ and end with the closing brace }}}}.
- Any additional text will cause system errors.

**COMPANY CONTEXT:**
The user's company is: "{company_name}"

**CLASSIFICATION RULES:**

1. **DOCUMENT RELEVANCE CHECK (Do this FIRST):**
   - Is this document a bill, invoice, bank statement, or share document with financial implications?
   - If NO (e.g., contracts, memos, letters, reports, certificates without financial data) → classify as illegible_document

2. **ILLEGIBLE DOCUMENT CHECK (Do this SECOND):**
   - Can you extract document number/ID? (YES/NO)
   - Can you extract total monetary amount? (YES/NO)
   - If BOTH answers are NO → classify as illegible_document

3. **MANDATORY COMPANY ROLE IDENTIFICATION (CRITICAL):**

**STEP 1: DETERMINE COMPANY'S ROLE IN THE TRANSACTION**
You MUST identify which role the user's company plays by analyzing these document indicators:

**A) ISSUER/SENDER INDICATORS (Company is requesting payment):**
- User's company name appears in "FROM:" field
- User's company name appears in "BILL TO:" field as the issuer
- User's company name appears in "VENDOR:" field
- User's company name appears in "SELLER:" field
- User's company name appears in "SERVICE PROVIDER:" field
- Document header shows user's company letterhead/logo
- Document says "Invoice from [User's Company]"
- User's company address appears in sender/issuer section
- User's company bank details appear for receiving payment

**B) RECIPIENT/CUSTOMER INDICATORS (Company owes payment):**
- User's company name appears in "TO:" field as recipient
- User's company name appears in "CUSTOMER:" field
- User's company name appears in "BILL TO:" field as the customer
- User's company name appears in "BUYER:" field
- User's company name appears in "CLIENT:" field
- Document says "Invoice to [User's Company]"
- User's company address appears in recipient/customer section
- Another company's bank details appear for receiving payment FROM user's company

**STEP 2: MANDATORY COMPANY ROLE VERIFICATION**
Before classifying, you MUST answer these verification questions:

1. **WHO IS ISSUING THIS DOCUMENT?**
   - Look for "Issued by", "From:", company letterhead, logo at top, bank account owner
   - Answer: [Company Name that issued/created the document]
   - Is this the user's company? [YES/NO]
   - ⚠️ CRITICAL: If NOT user's company, then user's company is RECEIVING this bill/invoice!

2. **WHO WILL RECEIVE THE MONEY?**
   - Look for bank account details, "Pay to:", "Remit to:", account owner
   - Answer: [Company Name that will receive payment]
   - Is this the user's company? [YES/NO]
   - ⚠️ CRITICAL: If NOT user's company, then category = "money_going_out"!

3. **WHO WILL SEND THE MONEY?**
   - Look for "Bill to:", "Customer:", "Sold to:", the party being charged
   - Answer: [Company Name that will send payment]
   - Is this the user's company? [YES/NO]
   - ⚠️ CRITICAL: If YES user's company, then category = "money_going_out"!

**STEP 3: APPLY CLASSIFICATION RULES (ONLY AFTER VERIFICATION)**

**IF USER'S COMPANY IS THE ISSUER/MONEY RECEIVER:**
- Document type = "invoice"
- Category = "money_coming_in"
- Logic: User's company issued this document requesting payment FROM another party

**IF USER'S COMPANY IS THE RECIPIENT/MONEY SENDER:**
- Document type = "bill"
- Category = "money_going_out"
- Logic: User's company received this document and must pay TO another party

**CRITICAL ENFORCEMENT RULES:**
1. **NEVER ASSUME** - Always verify company role through document text analysis
2. **DOCUMENT CREATOR ≠ MONEY RECEIVER** - Check who actually gets paid
3. **MULTIPLE VERIFICATION** - Use at least 2 indicators to confirm company role
4. **CONTRADICTION CHECK** - If indicators conflict, classify as illegible_document
5. **EXPLICIT IDENTIFICATION** - The user's company role must be explicitly identifiable in document text

**DOCUMENT TYPES:**
- "invoice": User's company issued it, requesting payment
- "bill": User's company received it, must pay another company
- "bank_statement": Bank-issued statement with transactions
- "share_document": Share-related documents or corporate filings with financial impact
- null: Only for illegible documents

**CATEGORIES:**
- "money_coming_in": User's company receives money
- "money_going_out": User's company pays money
- "bank_statement": Bank statement
- "illegible_document": Cannot extract key financial data

**REQUIRED JSON OUTPUT FORMAT:**
{{{{
  "document_type": "invoice|bill|bank_statement|share_document|null",
  "category": "money_coming_in|money_going_out|bank_statement|illegible_document",
  "company_name": "{company_name}",
  "total_amount": 1250.00
}}}}

**MANDATORY FINAL COMPANY CHECK:**
Before outputting JSON, confirm:
- ✓ I identified the user's company name correctly
- ✓ I determined the user's company role through document analysis
- ✓ I verified who receives payment vs who sends payment
- ✓ My classification matches the user's company position
- ✓ If company role is unclear, I classified as illegible_document

**VALIDATION RULES:**
- document_type and category must follow the logic above
- total_amount must be numeric or null
- If key financial data missing, use null + illegible_document
- Response must be valid JSON only"""

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
            max_tokens=1000,  # Reduced for JSON-only response
            temperature=0.1,
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
                
                return {
                    "success": True,
                    "result": classification_data,
                    "metadata": {
                        "token_usage": result["token_usage"],
                        "s3_key": s3_key,
                        "company_name": company_name
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
            "anthropic_configured": bool(os.getenv('ANTHROPIC_API_KEY')),
            "aws_configured": bool(os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY')),
            "s3_bucket": os.getenv('S3_BUCKET_NAME', 'company-documents-2025')
        }
        
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e)
        }