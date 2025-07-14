import base64
import json
import logging
import os
import re
from datetime import datetime
from typing import Dict, Any, Optional, List
from io import BytesIO

import openai
import fitz  # PyMuPDF
from PIL import Image
import PyPDF2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PDFExtractor:
    def __init__(self):
        """Initialize PDF extraction with OpenAI API"""
        self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.supported_formats = ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg']
        
    def extract_text_from_pdf(self, pdf_content: bytes) -> str:
        """Extract text from PDF using PyMuPDF for better accuracy"""
        try:
            doc = fitz.open(stream=pdf_content, filetype="pdf")
            text = ""
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text += page.get_text()
            doc.close()
            return text.strip()
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {str(e)}")
            # Fallback to PyPDF2
            try:
                pdf_reader = PyPDF2.PdfReader(BytesIO(pdf_content))
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text()
                return text.strip()
            except Exception as e2:
                logger.error(f"Fallback PDF extraction also failed: {str(e2)}")
                return ""
    
    def pdf_to_image_base64(self, pdf_content: bytes, page_num: int = 0) -> Optional[str]:
        """Convert PDF page to base64 image for vision API"""
        try:
            doc = fitz.open(stream=pdf_content, filetype="pdf")
            page = doc.load_page(page_num)
            # Increase resolution for better OCR
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            doc.close()
            
            # Convert to base64
            img_base64 = base64.b64encode(img_data).decode()
            return f"data:image/png;base64,{img_base64}"
        except Exception as e:
            logger.error(f"Error converting PDF to image: {str(e)}")
            return None

    def get_extraction_prompt(self) -> str:
        """Get the comprehensive prompt for LLM extraction"""
        return """
You are an expert at extracting structured data from business documents (invoices, bills, receipts, etc.).

CRITICAL RULES:
1. Extract information EXACTLY as it appears in the document
2. Use null for missing fields, never empty strings or made-up data
3. For dates, use YYYY-MM-DD format only
4. For amounts, extract as numbers without currency symbols
5. For country codes, use 2-letter ISO codes (CY=Cyprus, GR=Greece, US=USA, etc.)
6. Be very careful to distinguish between VENDOR (who issued the document) and CUSTOMER (who received it)

VENDOR = The company/person issuing the invoice/bill (FROM)
CUSTOMER = The company/person receiving the invoice/bill (TO/BILL TO)

Return ONLY valid JSON in this exact format:

{
  "document_analysis": {
    "document_type": "invoice|bill|receipt|credit_note|utility_bill|other",
    "confidence_level": 0.95,
    "currency_detected": "EUR|USD|GBP|null",
    "total_pages": 1
  },
  "vendor": {
    "name": "exact company name as shown",
    "email": "email@domain.com or null",
    "phone": "phone number or null", 
    "vat": "VAT/Tax ID number or null",
    "street": "full address or null",
    "city": "city name or null",
    "zip": "postal code or null",
    "country_code": "2-letter code or null"
  },
  "customer": {
    "name": "customer/client name or null",
    "email": "customer email or null",
    "phone": "customer phone or null",
    "vat": "customer VAT or null",
    "street": "customer address or null", 
    "city": "customer city or null",
    "zip": "customer postal code or null",
    "country_code": "2-letter code or null"
  },
  "bill_details": {
    "invoice_date": "YYYY-MM-DD or null",
    "due_date": "YYYY-MM-DD or null",
    "vendor_ref": "invoice/document number or null",
    "description": "main description or first item description",
    "total_amount": 0.00,
    "tax_amount": 0.00,
    "subtotal": 0.00,
    "line_items": [
      {
        "description": "item description",
        "quantity": 1.0,
        "price_unit": 0.00,
        "total": 0.00
      }
    ]
  },
  "extraction_notes": {
    "warnings": ["any issues or unclear items"],
    "missing_fields": ["list of fields that couldn't be found"],
    "confidence_scores": {
      "vendor_info": 0.95,
      "customer_info": 0.90,
      "amounts": 0.95,
      "dates": 0.90
    }
  }
}

IMPORTANT FIELD MAPPING:
- If document shows "Bill To" or "Invoice To" → that's the CUSTOMER
- If document shows company header/logo/sender info → that's the VENDOR  
- Extract ALL line items if multiple products/services are listed
- If only total amount is visible, create one line item with that total
- For utility bills: utility company = VENDOR, account holder = CUSTOMER
- For service invoices: service provider = VENDOR, client = CUSTOMER

Return ONLY the JSON, no explanations or markdown formatting.
"""

    def extract_with_vision_api(self, image_base64: str) -> Dict[str, Any]:
        """Extract data using OpenAI Vision API"""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o", #gpt-4o because this supports images
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at extracting structured data from business documents. Return only valid JSON."
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": self.get_extraction_prompt()},
                            {"type": "image_url", "image_url": {"url": image_base64}}
                        ]
                    }
                ],
                max_tokens=2000,
                temperature=0.1
            )
            
            content = response.choices[0].message.content
            return self._parse_llm_response(content)
            
        except Exception as e:
            logger.error(f"Vision API error: {str(e)}")
            return {"error": f"Vision API failed: {str(e)}"}

    def extract_with_text_api(self, text: str) -> Dict[str, Any]:
        """Extract data using text-based GPT-4 as fallback"""
        try:
            prompt = f"{self.get_extraction_prompt()}\n\nDocument text to analyze:\n{text}"
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini", #gpt-4o-mini because this supports text
                messages=[
                    {"role": "system", "content": "You are an expert at extracting structured data from business documents. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.1
            )
            
            content = response.choices[0].message.content
            return self._parse_llm_response(content)
            
        except Exception as e:
            logger.error(f"Text API error: {str(e)}")
            return {"error": f"Text API failed: {str(e)}"}

    def _parse_llm_response(self, content: str) -> Dict[str, Any]:
        """Parse and clean LLM response"""
        try:
            # Clean the response
            content = content.strip()
            content = re.sub(r'^```json\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
            content = content.strip()
            
            # Parse JSON
            data = json.loads(content)
            
            # Validate and clean the data
            return self._validate_and_clean_data(data)
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
            logger.error(f"Raw content: {content[:500]}...")
            return {"error": "Invalid JSON response from LLM", "raw_content": content}
        except Exception as e:
            logger.error(f"Response parsing error: {str(e)}")
            return {"error": f"Response parsing failed: {str(e)}"}

    def _validate_and_clean_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and clean extracted data to match Odoo API requirements"""
        
        # Ensure required structure exists
        required_sections = ['document_analysis', 'vendor', 'customer', 'bill_details']
        for section in required_sections:
            if section not in data:
                data[section] = {}
        
        # Clean vendor data
        vendor = data['vendor']
        if vendor.get('name'):
            vendor['name'] = str(vendor['name']).strip()
        
        # Clean customer data  
        customer = data['customer']
        if customer.get('name'):
            customer['name'] = str(customer['name']).strip()
        
        # Clean bill details
        bill = data['bill_details']
        
        # Ensure amounts are numbers
        amount_fields = ['total_amount', 'tax_amount', 'subtotal']
        for field in amount_fields:
            if field in bill:
                try:
                    bill[field] = float(bill[field]) if bill[field] is not None else 0.0
                except (ValueError, TypeError):
                    bill[field] = 0.0
        
        # Clean line items
        if 'line_items' not in bill or not isinstance(bill['line_items'], list):
            # If no line items, create one from total amount
            if bill.get('total_amount', 0) > 0:
                bill['line_items'] = [{
                    'description': bill.get('description', 'Invoice item'),
                    'quantity': 1.0,
                    'price_unit': bill.get('total_amount', 0.0),
                    'total': bill.get('total_amount', 0.0)
                }]
            else:
                bill['line_items'] = []
        
        # Clean each line item
        for item in bill['line_items']:
            if 'quantity' in item:
                try:
                    item['quantity'] = float(item['quantity']) if item['quantity'] is not None else 1.0
                except (ValueError, TypeError):
                    item['quantity'] = 1.0
            
            if 'price_unit' in item:
                try:
                    item['price_unit'] = float(item['price_unit']) if item['price_unit'] is not None else 0.0
                except (ValueError, TypeError):
                    item['price_unit'] = 0.0
                    
            if 'total' in item:
                try:
                    item['total'] = float(item['total']) if item['total'] is not None else 0.0
                except (ValueError, TypeError):
                    item['total'] = item.get('quantity', 1.0) * item.get('price_unit', 0.0)
        
        # Validate dates
        date_fields = ['invoice_date', 'due_date']
        for field in date_fields:
            if field in bill and bill[field]:
                if not self._validate_date_format(bill[field]):
                    logger.warning(f"Invalid date format for {field}: {bill[field]}")
                    bill[field] = None
        
        return data

    def _validate_date_format(self, date_str: str) -> bool:
        """Validate YYYY-MM-DD date format"""
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError:
            return False

    def extract_from_pdf(self, pdf_content: bytes, file_name: str) -> Dict[str, Any]:
        """Main extraction method that tries multiple approaches"""
        logger.info(f"Starting extraction for: {file_name}")
        
        result = {
            "success": False,
            "file_name": file_name,
            "extraction_method": None,
            "extracted_data": None,
            "error": None,
            "processing_time": datetime.now().isoformat()
        }
        
        try:
            # Method 1: Try Vision API with PDF as image (best for complex layouts)
            image_base64 = self.pdf_to_image_base64(pdf_content)
            if image_base64:
                logger.info("Trying Vision API extraction...")
                vision_result = self.extract_with_vision_api(image_base64)
                
                if "error" not in vision_result:
                    result["success"] = True
                    result["extraction_method"] = "vision_api"
                    result["extracted_data"] = vision_result
                    logger.info("Vision API extraction successful")
                    return result
                else:
                    logger.warning(f"Vision API failed: {vision_result['error']}")
            
            # Method 2: Fallback to text extraction + GPT-4
            logger.info("Trying text extraction fallback...")
            extracted_text = self.extract_text_from_pdf(pdf_content)
            
            if extracted_text and len(extracted_text.strip()) > 50:
                text_result = self.extract_with_text_api(extracted_text)
                
                if "error" not in text_result:
                    result["success"] = True
                    result["extraction_method"] = "text_api"
                    result["extracted_data"] = text_result
                    logger.info("Text API extraction successful")
                    return result
                else:
                    logger.warning(f"Text API failed: {text_result['error']}")
            
            # If all methods fail
            result["error"] = "All extraction methods failed"
            logger.error("All extraction methods failed")
            return result
            
        except Exception as e:
            logger.error(f"Extraction error: {str(e)}")
            result["error"] = f"Extraction failed: {str(e)}"
            return result

    def extract_from_image(self, image_base64: str, file_name: str) -> Dict[str, Any]:
        """Extract data from image files directly"""
        logger.info(f"Starting image extraction for: {file_name}")
        
        result = {
            "success": False,
            "file_name": file_name,
            "extraction_method": "vision_api",
            "extracted_data": None,
            "error": None,
            "processing_time": datetime.now().isoformat()
        }
        
        try:
            vision_result = self.extract_with_vision_api(image_base64)
            
            if "error" not in vision_result:
                result["success"] = True
                result["extracted_data"] = vision_result
                logger.info("Image extraction successful")
            else:
                result["error"] = vision_result["error"]
                logger.error(f"Image extraction failed: {vision_result['error']}")
            
            return result
            
        except Exception as e:
            logger.error(f"Image extraction error: {str(e)}")
            result["error"] = f"Image extraction failed: {str(e)}"
            return result

    def format_for_odoo_apis(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format extracted data to match your existing Odoo API structure"""
        
        if not extracted_data or "error" in extracted_data:
            return {"error": "No valid data to format"}
        
        # Extract the main sections
        vendor = extracted_data.get('vendor', {})
        customer = extracted_data.get('customer', {})
        bill = extracted_data.get('bill_details', {})
        
        # Format for your APIs
        formatted = {
            # For createvendor.py
            "vendor_data": {
                "name": vendor.get('name'),
                "email": vendor.get('email'),
                "phone": vendor.get('phone'),
                "vat": vendor.get('vat'),
                "street": vendor.get('street'),
                "city": vendor.get('city'),
                "zip": vendor.get('zip'),
                "country_code": vendor.get('country_code')
            },
            
            # For createcompany.py (using customer as company)
            "company_data": {
                "name": customer.get('name'),
                "email": customer.get('email'),
                "phone": customer.get('phone'),
                "street": customer.get('street'),
                "city": customer.get('city'),
                "zip": customer.get('zip'),
                "country_code": customer.get('country_code')
            },
            
            # For createbill.py
            "bill_data": {
                "invoice_date": bill.get('invoice_date'),
                "vendor_ref": bill.get('vendor_ref'),
                "description": bill.get('description'),
                "amount": bill.get('total_amount'),
                "line_items": bill.get('line_items', [])
            },
            
            # Additional metadata
            "document_info": extracted_data.get('document_analysis', {}),
            "extraction_notes": extracted_data.get('extraction_notes', {})
        }
        
        return formatted

# Utility function for testing
def test_extraction(pdf_file_path: str):
    """Test function for development"""
    extractor = PDFExtractor()
    
    with open(pdf_file_path, 'rb') as f:
        pdf_content = f.read()
    
    result = extractor.extract_from_pdf(pdf_content, os.path.basename(pdf_file_path))
    
    print("Extraction Result:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    if result["success"]:
        formatted = extractor.format_for_odoo_apis(result["extracted_data"])
        print("\nFormatted for Odoo APIs:")
        print(json.dumps(formatted, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    # Example usage
    # test_extraction("sample_invoice.pdf")
    pass