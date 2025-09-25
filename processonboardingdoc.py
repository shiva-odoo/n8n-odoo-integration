import os
import boto3
import base64
import anthropic
import json
import re

def get_company_extraction_prompt():
    """Create company information extraction prompt for onboarding documents"""
    return """# Company Information Extraction from Onboarding Documents

## Task
Extract company information from the provided document and convert it into the exact JSON format required for company registration. The document may contain company registration details, incorporation documents, or other business formation paperwork.

## Input Analysis
You will receive a document (PDF, image, or text) containing company information. Extract all available company details including:
1. **Company Name**: The official legal name of the company
2. **Contact Information**: Email, phone number, website
3. **Business Registration Details**: VAT number, company registry number, tax ID
4. **Address Information**: Street address, city, postal/ZIP code, state/province
5. **Jurisdiction**: Country of incorporation or registration
6. **Additional Details**: Any other relevant business information

## CRITICAL OUTPUT REQUIREMENTS
- Return ONLY a valid JSON object
- No markdown code blocks (no ```json```)
- No explanatory text before or after the JSON
- No comments or additional formatting
- Start response with { and end with }
- Ensure valid JSON syntax with proper escaping
- All string values must be properly escaped (quotes, backslashes, etc.)

## Required Output Format
Return a JSON object with this EXACT structure:

{
  "name": "Company Name",
  "email": "contact@company.com",
  "phone": "+1234567890",
  "website": "https://website.com",
  "vat": "VAT123456",
  "company_registry": "REG123456",
  "street": "123 Main St",
  "city": "City Name",
  "zip": "12345",
  "state": "State Name",
  "country_code": "CY",
  "currency_code": "EUR"
}

## Field Extraction Rules

### Required Fields
- **name**: The complete legal company name (string, required)

### Optional Fields (set to null if not found)
- **email**: Primary business email address (string or null)
- **phone**: Business phone number with country code if available (string or null)
- **website**: Company website URL (string or null)
- **vat**: VAT registration number or tax identification number (string or null)
- **company_registry**: Company registration number from companies registry (string or null)
- **street**: Street address including building number (string or null)
- **city**: City name (string or null)
- **zip**: Postal code or ZIP code (string or null)
- **state**: State, province, or region name (string or null)
- **country_code**: ISO 2-letter country code (string, default to "CY" if not found)
- **currency_code**: ISO 3-letter currency code (string, default to "EUR" if not found)

## Data Processing Rules

### Country Code Detection
- Look for country names and convert to ISO 2-letter codes:
  - Cyprus → "CY"
  - United Kingdom → "GB"
  - United States → "US"
  - Germany → "DE"
  - France → "FR"
  - etc.
- If no country is specified or unclear, default to "CY"

### Currency Code Detection
- Look for currency mentions and convert to ISO codes:
  - Euro/EUR/€ → "EUR"
  - Pound Sterling/GBP/£ → "GBP"
  - US Dollar/USD/$ → "USD"
  - etc.
- If no currency is specified, default to "EUR"

### Phone Number Formatting
- Include country codes where possible
- Format as international number (e.g., "+357 12345678")
- Remove extra spaces and formatting for consistency

### Address Processing
- Extract street address as a single line
- Separate city, state/province, and postal code
- Clean up formatting and remove unnecessary punctuation

### Website URL Formatting
- Ensure URLs start with http:// or https://
- Clean up formatting issues

### Registration Number Processing
- Extract company registration numbers, certificate numbers
- Clean up formatting and remove unnecessary text
- Look for numbers following terms like "Registration No.", "Certificate No.", "Company No."

## Processing Instructions

1. **Scan the entire document** for any company-related information
2. **Prioritize official/legal names** over trade names or abbreviations
3. **Extract contact details** from headers, footers, letterheads, and content
4. **Look for registration details** in certificates, forms, or official documents
5. **Process addresses carefully** separating components correctly
6. **Apply defaults** for country_code ("CY") and currency_code ("EUR") if not found
7. **Validate extracted data** ensuring proper formatting
8. **Set null values** for any fields that cannot be reliably extracted
9. **Ensure all string values are properly escaped** for JSON format

## Example Processing Scenarios

### Scenario 1: Cyprus Company Registration Certificate
If document shows:
- Company Name: "Kyrastel Investments Limited"
- Registration No.: "HE 123456"
- Address: "123 Makarios Avenue, Nicosia 1065, Cyprus"
- Email: "info@kyrastel.com"

Output:
```json
{
  "name": "Kyrastel Investments Limited",
  "email": "info@kyrastel.com",
  "phone": null,
  "website": null,
  "vat": null,
  "company_registry": "HE 123456",
  "street": "123 Makarios Avenue",
  "city": "Nicosia",
  "zip": "1065",
  "state": null,
  "country_code": "CY",
  "currency_code": "EUR"
}
```

### Scenario 2: UK Company Documents
If document shows UK company with full details, set country_code to "GB" and currency_code to "GBP"

### Scenario 3: Incomplete Information
If only company name is clear, set other fields to null but keep defaults for country_code and currency_code

## Quality Assurance
- Double-check company name spelling and formatting
- Ensure email addresses are valid format
- Verify phone numbers include country codes where possible
- Confirm addresses are properly separated
- Validate that country and currency codes are correct ISO standards

**CRITICAL: Return ONLY the JSON object. No markdown formatting, no code blocks, no explanatory text. The response must start with '{' and end with '}'.**
"""

def extract_company_json_from_response(response_text):
    """Extract company JSON from Claude's response, handling various formats"""
    try:
        # Remove any leading/trailing whitespace
        response_text = response_text.strip()
        
        # Try to parse directly first
        try:
            parsed = json.loads(response_text)
            return parsed
        except json.JSONDecodeError:
            pass
        
        # Look for JSON wrapped in markdown code blocks
        json_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
        matches = re.findall(json_pattern, response_text, re.IGNORECASE)
        
        if matches:
            # Try each match
            for match in matches:
                try:
                    parsed = json.loads(match.strip())
                    return parsed
                except json.JSONDecodeError:
                    continue
        
        # Look for JSON objects without code blocks
        # Find content between first '{' and last '}'
        if '{' in response_text and '}' in response_text:
            start_idx = response_text.find('{')
            
            # Find matching closing brace
            brace_count = 0
            end_idx = -1
            
            for i in range(start_idx, len(response_text)):
                char = response_text[i]
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            
            if end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                try:
                    parsed = json.loads(json_str)
                    return parsed
                except json.JSONDecodeError:
                    pass
        
        # If all else fails, raise an error with the raw response
        raise json.JSONDecodeError(f"Could not extract valid JSON from response. Response starts with: {response_text[:200]}...")
        
    except Exception as e:
        raise Exception(f"JSON extraction failed: {str(e)}")

def validate_company_json(company_data):
    """Validate the extracted company JSON structure"""
    try:
        if not isinstance(company_data, dict):
            raise ValueError("Expected JSON object for company data")
        
        # Check required field
        if 'name' not in company_data or not company_data['name']:
            raise ValueError("Company name is required")
        
        # Define expected fields with their types
        expected_fields = {
            'name': str,
            'email': (str, type(None)),
            'phone': (str, type(None)),
            'website': (str, type(None)),
            'vat': (str, type(None)),
            'company_registry': (str, type(None)),
            'street': (str, type(None)),
            'city': (str, type(None)),
            'zip': (str, type(None)),
            'state': (str, type(None)),
            'country_code': str,
            'currency_code': str
        }
        
        # Validate field types
        for field, expected_type in expected_fields.items():
            if field in company_data:
                if not isinstance(company_data[field], expected_type):
                    raise ValueError(f"Field '{field}' should be of type {expected_type}")
        
        # Set defaults if missing
        if 'country_code' not in company_data or not company_data['country_code']:
            company_data['country_code'] = 'CY'
            
        if 'currency_code' not in company_data or not company_data['currency_code']:
            company_data['currency_code'] = 'EUR'
        
        return True
        
    except Exception as e:
        raise Exception(f"Company data validation failed: {str(e)}")

def download_document_from_s3(s3_key, bucket_name=None):
    """Download document from S3 using key"""
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

def process_company_document_extraction(document_content):
    """Process onboarding document with Claude for company information extraction"""
    try:
        # Initialize Anthropic client
        anthropic_client = anthropic.Anthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY')
        )
        
        # Encode to base64
        document_base64 = base64.b64encode(document_content).decode('utf-8')
        
        # Determine media type (assume PDF for now, but could be extended)
        media_type = "application/pdf"
        
        # Get company extraction prompt
        prompt = get_company_extraction_prompt()
        
        # Send to Claude with parameters optimized for structured output
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            temperature=0.0,  # Maximum determinism for consistent parsing
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": document_base64
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
        
        # Log the raw response for debugging (first 500 chars)
        print(f"Raw Claude response (first 500 chars): {response_text[:500]}...")
        
        # Extract and parse JSON
        try:
            extracted_json = extract_company_json_from_response(response_text)
            
            # Validate the JSON structure
            validate_company_json(extracted_json)
            
            # Log token usage for monitoring
            print(f"Token usage - Input: {message.usage.input_tokens}, Output: {message.usage.output_tokens}")
            print(f"Successfully extracted company information for: {extracted_json.get('name', 'Unknown Company')}")
            
            return {
                "success": True,
                "extraction_result": extracted_json,
                "raw_response": response_text,
                "token_usage": {
                    "input_tokens": message.usage.input_tokens,
                    "output_tokens": message.usage.output_tokens
                }
            }
            
        except Exception as json_error:
            print(f"JSON processing failed: {str(json_error)}")
            return {
                "success": False,
                "error": f"JSON processing failed: {str(json_error)}",
                "raw_response": response_text
            }
        
    except Exception as e:
        print(f"Claude API error: {str(e)}")
        return {
            "success": False,
            "error": f"Claude API error: {str(e)}"
        }

def process_onboarding_document(data):
    """
    Process onboarding document to extract company information
    
    Args:
        data (dict): Request data containing:
            - s3_key (str): S3 key path to the document
            - bucket_name (str, optional): S3 bucket name
    
    Returns:
        dict: Processing result with success status and extracted company data
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
        
        print(f"Processing onboarding document for company information extraction")
        print(f"S3 key: {s3_key}")
        
        # Download document from S3
        document_content = download_document_from_s3(s3_key, bucket_name)
        print(f"Downloaded document, size: {len(document_content)} bytes")
        
        # Process document for company information extraction
        result = process_company_document_extraction(document_content)
        
        if result["success"]:
            # Return the extracted company data directly
            extracted_data = result["extraction_result"]
            
            # Log successful extraction
            print(f"Successfully extracted company data: {extracted_data.get('name', 'Unknown')}")
            
            return extracted_data
        else:
            return {
                "success": False,
                "error": result["error"],
                "raw_response": result.get("raw_response")
            }
            
    except Exception as e:
        print(f"Onboarding document processing error: {str(e)}")
        return {
            "success": False,
            "error": f"Internal processing error: {str(e)}"
        }
import os
import boto3
import base64
import anthropic
import json
import re

def get_company_extraction_prompt():
    """Create company information extraction prompt for multiple onboarding documents"""
    return """# Company Information Extraction from Multiple Onboarding Documents

## Task
Extract company information from the provided documents and return it as a JSON object. You will receive multiple documents (PDFs, images, or text) that may contain company registration details, incorporation documents, or other business formation paperwork for the same company.

## Input Analysis
You will receive multiple documents containing company information. Extract all available company details by combining information from all documents, prioritizing the most complete and official information:

1. **Company Name**: The official legal name of the company
2. **Contact Information**: Email, phone number, website
3. **Business Registration Details**: VAT number, company registry number, tax ID
4. **Address Information**: Street address, city, postal/ZIP code, state/province
5. **Jurisdiction**: Country of incorporation or registration
6. **Additional Details**: Any other relevant business information

## Output Format
Please return your response as a JSON object with this structure:

```json
{
  "name": "Company Name",
  "email": "contact@company.com",
  "phone": "+1234567890",
  "website": "https://website.com",
  "vat": "VAT123456",
  "company_registry": "REG123456",
  "street": "123 Main St",
  "city": "City Name",
  "zip": "12345",
  "state": "State Name",
  "country_code": "CY",
  "currency_code": "EUR"
}
```

## Field Extraction Rules

### Required Fields
- **name**: The complete legal company name (string, required)

### Optional Fields (set to null if not found)
- **email**: Primary business email address (string or null)
- **phone**: Business phone number with country code if available (string or null)
- **website**: Company website URL (string or null)
- **vat**: VAT registration number or tax identification number (string or null)
- **company_registry**: Company registration number from companies registry (string or null)
- **street**: Street address including building number (string or null)
- **city**: City name (string or null)
- **zip**: Postal code or ZIP code (string or null)
- **state**: State, province, or region name (string or null)
- **country_code**: ISO 2-letter country code (string, default to "CY" if not found)
- **currency_code**: ISO 3-letter currency code (string, default to "EUR" if not found)

## Multi-Document Processing Rules

### Information Priority
When extracting information from multiple documents:
1. **Prioritize official documents**: Company certificates over correspondence
2. **Use most complete information**: If one document has partial address and another has complete address, use the complete one
3. **Cross-validate**: Ensure company name is consistent across documents
4. **Combine contact details**: Collect all available contact information, prioritizing official sources

### Conflict Resolution
If documents contain conflicting information:
1. **Company Name**: Use the most official/legal version (from certificates or registration documents)
2. **Registration Numbers**: Use the most official source
3. **Addresses**: Prioritize registered office address over correspondence address
4. **Contact Details**: Use the most recent or official contact information

## Data Processing Rules

### Country Code Detection
- Look for country names and convert to ISO 2-letter codes:
  - Cyprus → "CY"
  - United Kingdom → "GB"
  - United States → "US"
  - Germany → "DE"
  - France → "FR"
  - etc.
- If no country is specified or unclear, default to "CY"

### Currency Code Detection
- Look for currency mentions and convert to ISO codes:
  - Euro/EUR/€ → "EUR"
  - Pound Sterling/GBP/£ → "GBP"
  - US Dollar/USD/$ → "USD"
  - etc.
- If no currency is specified, default to "EUR"

### Phone Number Formatting
- Include country codes where possible
- Format as international number (e.g., "+357 12345678")
- Remove extra spaces and formatting for consistency

### Address Processing
- Extract street address as a single line
- Separate city, state/province, and postal code
- Clean up formatting and remove unnecessary punctuation

### Website URL Formatting
- Ensure URLs start with http:// or https://
- Clean up formatting issues

### Registration Number Processing
- Extract company registration numbers, certificate numbers
- Clean up formatting and remove unnecessary text
- Look for numbers following terms like "Registration No.", "Certificate No.", "Company No."

## Processing Instructions

1. **Scan all documents** for any company-related information
2. **Prioritize official/legal names** over trade names or abbreviations
3. **Combine contact details** from all documents, choosing the most complete set
4. **Cross-reference information** between documents for accuracy
5. **Process addresses carefully** separating components correctly
6. **Apply defaults** for country_code ("CY") and currency_code ("EUR") if not found
7. **Validate extracted data** ensuring proper formatting and consistency across documents
8. **Set null values** for any fields that cannot be reliably extracted from any document

## Quality Assurance
- Double-check company name consistency across all documents
- Ensure email addresses are valid format
- Verify phone numbers include country codes where possible
- Confirm addresses are properly separated
- Validate that country and currency codes are correct ISO standards
- Cross-check registration numbers and official details for consistency

## Response Format
Please return only the JSON object as your response. Use proper JSON formatting with double quotes for strings and appropriate null values where data is not available.
"""

def download_document_from_s3(s3_key, bucket_name=None):
    """Download document from S3 using key"""
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
        raise Exception(f"Error downloading from S3 (key: {s3_key}): {str(e)}")

def download_multiple_documents_from_s3(s3_keys, bucket_name=None):
    """Download multiple documents from S3"""
    documents = []
    
    # Remove duplicates while preserving order
    unique_s3_keys = list(dict.fromkeys(s3_keys))
    
    for s3_key in unique_s3_keys:
        try:
            document_content = download_document_from_s3(s3_key, bucket_name)
            documents.append({
                's3_key': s3_key,
                'content': document_content,
                'size': len(document_content)
            })
            print(f"Successfully downloaded: {s3_key} ({len(document_content)} bytes)")
        except Exception as e:
            print(f"Failed to download {s3_key}: {str(e)}")
            # Continue with other documents even if one fails
            continue
    
    return documents

def process_multiple_company_documents_extraction(documents):
    """Process multiple onboarding documents with Claude for company information extraction"""
    try:
        if not documents:
            raise Exception("No documents provided for processing")
        
        # Initialize Anthropic client
        anthropic_client = anthropic.Anthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY')
        )
        
        # Prepare content array for Claude API
        content_array = []
        
        # Add each document to the content array
        for i, doc in enumerate(documents):
            # Encode to base64
            document_base64 = base64.b64encode(doc['content']).decode('utf-8')
            
            # Determine media type (assume PDF for now, but could be extended based on file extension)
            media_type = "application/pdf"
            
            content_array.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": document_base64
                }
            })
            
            print(f"Added document {i+1}/{len(documents)} to processing queue: {doc['s3_key']}")
        
        # Add the prompt as the last content item
        prompt = get_company_extraction_prompt()
        content_array.append({
            "type": "text",
            "text": prompt
        })
        
        print(f"Sending {len(documents)} documents to Claude for processing...")
        
        # Send to Claude with parameters optimized for structured output
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            temperature=0.0,  # Maximum determinism for consistent parsing
            messages=[
                {
                    "role": "user",
                    "content": content_array
                }
            ]
        )
        
        # Extract response
        response_text = message.content[0].text.strip()
        
        # Log the raw response for debugging (first 500 chars)
        print(f"Raw Claude response (first 500 chars): {response_text[:500]}...")
        
        # Try to parse as JSON directly
        try:
            # Look for JSON in the response (could be wrapped in code blocks or plain)
            json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response_text
            
            extracted_json = json.loads(json_str)
            
            # Set defaults if missing
            if 'country_code' not in extracted_json or not extracted_json['country_code']:
                extracted_json['country_code'] = 'CY'
                
            if 'currency_code' not in extracted_json or not extracted_json['currency_code']:
                extracted_json['currency_code'] = 'EUR'
            
            # Log token usage for monitoring
            print(f"Token usage - Input: {message.usage.input_tokens}, Output: {message.usage.output_tokens}")
            print(f"Successfully extracted company information for: {extracted_json.get('name', 'Unknown Company')}")
            
            return {
                "success": True,
                "extraction_result": extracted_json,
                "raw_response": response_text,
                "documents_processed": len(documents),
                "token_usage": {
                    "input_tokens": message.usage.input_tokens,
                    "output_tokens": message.usage.output_tokens
                }
            }
            
        except json.JSONDecodeError as json_error:
            print(f"JSON parsing failed: {str(json_error)}")
            return {
                "success": False,
                "error": f"JSON parsing failed: {str(json_error)}",
                "raw_response": response_text,
                "documents_processed": len(documents)
            }
        
    except Exception as e:
        print(f"Claude API error: {str(e)}")
        return {
            "success": False,
            "error": f"Claude API error: {str(e)}"
        }

def process_onboarding_document(data):
    """
    Process multiple onboarding documents to extract consolidated company information
    
    Args:
        data (dict): Request data containing:
            - s3_key (list): List of S3 key paths to the documents
            - bucket_name (str, optional): S3 bucket name
    
    Returns:
        dict: Processing result with success status and extracted company data
    """
    try:
        # Validate required fields
        if 's3_key' not in data:
            return {
                "success": False,
                "error": "s3_key is required"
            }
        
        s3_keys = data['s3_key']
        bucket_name = data.get('bucket_name')  # Optional
        
        # Handle both single string and list of strings
        if isinstance(s3_keys, str):
            s3_keys = [s3_keys]
        
        if not isinstance(s3_keys, list):
            return {
                "success": False,
                "error": "s3_key must be a string or list of strings"
            }
        
        if not s3_keys:
            return {
                "success": False,
                "error": "At least one s3_key is required"
            }
        
        print(f"Processing {len(s3_keys)} onboarding documents for company information extraction")
        print(f"S3 keys: {s3_keys}")
        
        # Download all documents from S3
        documents = download_multiple_documents_from_s3(s3_keys, bucket_name)
        
        if not documents:
            return {
                "success": False,
                "error": "Failed to download any documents from S3"
            }
        
        print(f"Successfully downloaded {len(documents)} documents")
        total_size = sum(doc['size'] for doc in documents)
        print(f"Total document size: {total_size} bytes")
        
        # Process all documents for company information extraction
        result = process_multiple_company_documents_extraction(documents)
        
        if result["success"]:
            # Return the extracted company data directly
            extracted_data = result["extraction_result"]
            
            # Add processing metadata
            extracted_data["_metadata"] = {
                "documents_processed": result["documents_processed"],
                "total_document_size": total_size,
                "s3_keys_processed": [doc['s3_key'] for doc in documents],
                "token_usage": result["token_usage"]
            }
            
            # Log successful extraction
            print(f"Successfully extracted company data: {extracted_data.get('name', 'Unknown')}")
            print(f"Processed {result['documents_processed']} documents")
            
            return extracted_data
        else:
            return {
                "success": False,
                "error": result["error"],
                "raw_response": result.get("raw_response"),
                "documents_processed": result.get("documents_processed", 0)
            }
            
    except Exception as e:
        print(f"Onboarding documents processing error: {str(e)}")
        return {
            "success": False,
            "error": f"Internal processing error: {str(e)}"
        }
