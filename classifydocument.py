import boto3
import base64
import anthropic
import os
import json

def get_classification_prompt(company_name):
    """Create streamlined classification prompt focused on essential fields only"""
    return f"""You are a document classification AI. Analyze the uploaded document and extract information in JSON format.

**CRITICAL OUTPUT REQUIREMENT:**
- Your response must contain ONLY valid JSON. No explanations, comments, markdown, or any other content.
- Start with opening brace {{ and end with closing brace }}.

**COMPANY CONTEXT:**
The user's company is: "{company_name}"

**CLASSIFICATION RULES:**

1. **DOCUMENT RELEVANCE CHECK (Do this FIRST):**
   - Is this document a bill, invoice, bank statement, or legal document with financial implications?
   - If NO (e.g., contracts, memos, letters, reports, certificates without financial data) → classify as illegible_document

2. **ILLEGIBLE DOCUMENT CHECK (Do this SECOND):**
   - Can you extract document number/ID? (YES/NO)
   - Can you extract total monetary amount? (YES/NO)
   - If BOTH answers are NO → classify as illegible_document

3. **COMPANY ROLE IDENTIFICATION (CRITICAL):**
   **WHO ISSUED THE DOCUMENT?**
   - Look for company letterhead, "From:", "Issued by:", logo at top
   
   **WHO RECEIVES THE MONEY?**
   - Look for bank account details, "Pay to:", "Remit to:"
   
   **CLASSIFICATION LOGIC:**
   - If user's company ISSUED document + user's company RECEIVES money → "invoice" + "money_coming_in"
   - If another company ISSUED document + user's company PAYS money → "bill" + "money_going_out"
   - If bank statement → "bank_statement" + "bank_statement"
   - If illegible or unclear → null + "illegible_document"

**DOCUMENT TYPES:**
- "invoice": User's company issued it, requesting payment
- "bill": User's company received it, must pay another company
- "bank_statement": Bank-issued statement with transactions
- "legal_document": Legal/corporate filing with financial impact
- null: Only for illegible documents

**CATEGORIES:**
- "money_coming_in": User's company receives money
- "money_going_out": User's company pays money
- "bank_statement": Bank statement
- "illegible_document": Cannot extract key financial data

**REQUIRED JSON OUTPUT FORMAT:**
{{
  "document_type": "invoice|bill|bank_statement|legal_document|null",
  "category": "money_coming_in|money_going_out|bank_statement|illegible_document",
  "company_name": "{company_name}",
  "total_amount": 1250.00
}}

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