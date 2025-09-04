import re
import time
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import os

# ============================================================================
# CYPRUS COMPANY REGISTRY - NAME AND REGISTRATION PROCESSING FUNCTIONS
# ============================================================================

def process_company_name(name):
    """
    Process company name: convert to uppercase and trim spaces
    Args:
        name (str): The company name to process
    Returns:
        str: Processed company name (uppercase, trimmed)
    """
    if not name or not isinstance(name, str):
        return ''
    
    # Trim spaces from both sides and convert to uppercase
    return name.strip().upper()

def process_registration_number(reg_number):
    """
    Extract and validate registration number (numbers only)
    Args:
        reg_number (str): The registration number to process
    Returns:
        str: Extracted numbers only, or empty string if invalid
    """
    if not reg_number or not isinstance(reg_number, str):
        return ''
    
    # Extract only numbers using regex (removes ΗΕ prefix and any non-digits)
    numbers_only = re.sub(r'\D', '', reg_number)
    
    # Validate that we have at least one digit
    if re.match(r'^\d+$', numbers_only):
        return numbers_only
    return ''

def is_valid_company_name(name):
    """
    Validate company name format (basic validation)
    Args:
        name (str): The company name to validate
    Returns:
        bool: True if valid format
    """
    if not name or not isinstance(name, str):
        return False
    
    # Basic validation: should contain at least one letter and not be empty after trimming
    name_regex = re.compile(r'^[A-Za-z0-9\s&.,\'-]+$')
    trimmed_name = name.strip()
    
    return len(trimmed_name) > 0 and name_regex.match(trimmed_name) is not None

def is_valid_registration_number(reg_number):
    """
    Validate registration number format (numbers only, specific length if needed)
    Args:
        reg_number (str): The registration number to validate
    Returns:
        bool: True if valid format
    """
    if not reg_number or not isinstance(reg_number, str):
        return False
    
    # For Cyprus companies, typically 6 digits (like 474078)
    number_regex = re.compile(r'^\d{4,8}$')  # Allow 4-8 digits for flexibility
    clean_number = re.sub(r'\D', '', reg_number)
    
    return number_regex.match(clean_number) is not None

# ============================================================================
# CYPRUS-SPECIFIC STRICT VALIDATION
# ============================================================================

# More specific regex patterns for Cyprus companies
cyprus_company_name_regex = re.compile(r'^[A-Z0-9\s&.,\'-]+$')  # For processed names (uppercase)
cyprus_registration_regex = re.compile(r'^\d{6}$')  # Exactly 6 digits for Cyprus companies

def is_valid_cyprus_company_name(name):
    """
    Strict Cyprus company name validation
    Args:
        name (str): Processed company name (should be uppercase, trimmed)
    Returns:
        bool: True if matches Cyprus company name pattern
    """
    return cyprus_company_name_regex.match(name) is not None and len(name) > 0

def is_valid_cyprus_registration_number(reg_number):
    """
    Strict Cyprus registration number validation
    Args:
        reg_number (str): Registration number (should be numbers only)
    Returns:
        bool: True if matches Cyprus registration pattern
    """
    return cyprus_registration_regex.match(reg_number) is not None

def process_company_data(raw_name, raw_reg_number):
    """
    Process and validate both company name and registration number
    Args:
        raw_name (str): Raw company name input
        raw_reg_number (str): Raw registration number input
    Returns:
        dict: Object with processed values and validation results
    """
    processed_name = process_company_name(raw_name)
    processed_reg_number = process_registration_number(raw_reg_number)
    
    return {
        "original": {
            "name": raw_name,
            "registration": raw_reg_number
        },
        "processed": {
            "name": processed_name,
            "registration": processed_reg_number
        },
        "validation": {
            "name_valid": is_valid_company_name(processed_name),
            "reg_number_valid": is_valid_registration_number(processed_reg_number),
            "cyprus_name_valid": is_valid_cyprus_company_name(processed_name),
            "cyprus_reg_number_valid": is_valid_cyprus_registration_number(processed_reg_number)
        }
    }

def parse_company_data(html_content):
    """Parse HTML content and extract company information as JSON"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    company_data = {
        "success": False,
        "company_info": {},
        "errors": [],
        "raw_tables": []
    }
    
    try:
        # Look for error messages first
        error_selectors = [
            '.error', '.alert', '[class*="error"]', '.message',
            '#ctl00_cphMyMasterCentral_lblMessage',
            '[id*="Message"]', '[id*="Error"]'
        ]
        
        for selector in error_selectors:
            error_elements = soup.select(selector)
            for error in error_elements:
                error_text = error.get_text(strip=True)
                if error_text and error_text not in company_data["errors"]:
                    company_data["errors"].append(error_text)
        
        # Look for result tables or data containers
        tables = soup.find_all('table')
        
        for i, table in enumerate(tables):
            table_data = []
            rows = table.find_all('tr')
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if cells:
                    row_data = [cell.get_text(strip=True) for cell in cells]
                    if any(row_data):  # Only add non-empty rows
                        table_data.append(row_data)
            
            if table_data:
                company_data["raw_tables"].append({
                    "table_index": i,
                    "data": table_data
                })
        
        # Try to extract specific company information
        text_content = soup.get_text()
        
        # Extract registration number
        reg_match = re.search(r'Registration\s*(?:Number|No\.?)\s*:?\s*(\d+)', text_content, re.IGNORECASE)
        if reg_match:
            raw_reg = reg_match.group(1)
            company_data["company_info"]["registration_number"] = process_registration_number(raw_reg)
        
        # Extract company name
        name_patterns = [
            r'Company\s*Name\s*:?\s*([^\n\r]+)',
            r'Name\s*:?\s*([^\n\r]+)',
        ]
        
        for pattern in name_patterns:
            name_match = re.search(pattern, text_content, re.IGNORECASE)
            if name_match:
                raw_name = name_match.group(1).strip()
                if len(raw_name) > 3:  # Avoid capturing short/empty matches
                    company_data["company_info"]["company_name"] = process_company_name(raw_name)
                    break
        
        # Extract status
        status_match = re.search(r'Status\s*:?\s*([^\n\r]+)', text_content, re.IGNORECASE)
        if status_match:
            company_data["company_info"]["status"] = status_match.group(1).strip()
        
        # Extract incorporation date
        date_patterns = [
            r'Incorporation\s*Date\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
            r'Date\s*of\s*Incorporation\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
            r'Registered\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})'
        ]
        
        for pattern in date_patterns:
            date_match = re.search(pattern, text_content, re.IGNORECASE)
            if date_match:
                company_data["company_info"]["incorporation_date"] = date_match.group(1)
                break
        
        # Look for address information
        address_match = re.search(r'Address\s*:?\s*([^\n\r]+(?:\n[^\n\r]+)*)', text_content, re.IGNORECASE)
        if address_match:
            company_data["company_info"]["address"] = address_match.group(1).strip()
        
        # Check if we found any meaningful data
        if company_data["company_info"] or company_data["raw_tables"]:
            company_data["success"] = True
        
        # If no structured data but no errors, might be a "no results" case
        if not company_data["errors"] and not company_data["company_info"] and not company_data["raw_tables"]:
            if "no results" in text_content.lower() or "not found" in text_content.lower():
                company_data["errors"].append("No results found for the search criteria")
            else:
                company_data["errors"].append("Unable to parse response - no recognizable data structure found")
        
    except Exception as e:
        company_data["errors"].append(f"Parsing error: {str(e)}")
    
    return company_data

def search_cyprus_company_registry(reg_number, company_name):
    """
    Perform actual search on Cyprus company registry
    """
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--remote-debugging-port=9222")
    chrome_options.add_argument("--user-data-dir=/tmp/chrome_selenium_profile")
    chrome_options.add_argument("--headless")  # Run headless for API
    
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        # Navigate to the webpage
        driver.get("https://efiling.drcor.mcit.gov.cy/DrcorPublic/SearchForm.aspx?sc=0")
        
        # Wait for page to load
        wait = WebDriverWait(driver, 15)
        
        # Fill registration number field
        reg_number_field = wait.until(
            EC.presence_of_element_located((By.ID, "ctl00_cphMyMasterCentral_ucSearch_txtNumber"))
        )
        reg_number_field.clear()
        reg_number_field.send_keys(reg_number)
        
        # Fill name field
        name_field = driver.find_element(By.ID, "ctl00_cphMyMasterCentral_ucSearch_txtName")
        name_field.clear()
        name_field.send_keys(company_name)
        
        # Click the Go button
        go_button = driver.find_element(By.XPATH, "//*[@id='ctl00_cphMyMasterCentral_ucSearch_lbtnSearch']")
        go_button.click()
        
        # Wait for results to load
        time.sleep(3)
        
        # Wait for the page to change or results to appear
        try:
            wait.until(lambda driver: driver.current_url != "https://efiling.drcor.mcit.gov.cy/DrcorPublic/SearchForm.aspx?sc=0")
        except TimeoutException:
            pass  # Page might not change
        
        # Wait a bit more for dynamic content to load
        time.sleep(2)
        
        # Get the response and parse it
        html_response = driver.page_source
        
        # Parse HTML to JSON
        search_results = parse_company_data(html_response)
        
        return {
            "search_performed": True,
            "search_url": driver.current_url,
            "results": search_results
        }
        
    except Exception as e:
        return {
            "search_performed": False,
            "error": f"Search error: {str(e)}"
        }
    finally:
        driver.quit()

def main(data):
    """
    Main API function to validate company data and optionally search Cyprus registry
    
    Expected data format:
    {
        "company_name": "KYRASTEL ENTERPRISES LTD",
        "registration_number": "474078",
        "perform_search": false  # optional, defaults to false
    }
    
    Returns:
        dict: Validation results and optional search results
    """
    
    # Validate required fields
    if not data.get('company_name') and not data.get('registration_number'):
        return {
            'success': False,
            'error': 'Either company_name or registration_number is required'
        }
    
    company_name = data.get('company_name', '')
    registration_number = data.get('registration_number', '')
    perform_search = data.get('perform_search', False)
    
    # Process and validate the company data
    processed_data = process_company_data(company_name, registration_number)
    
    # Prepare response
    response = {
        'success': True,
        'validation': {
            'company_name': {
                'original': processed_data['original']['name'],
                'processed': processed_data['processed']['name'],
                'is_valid': processed_data['validation']['name_valid'],
                'cyprus_valid': processed_data['validation']['cyprus_name_valid']
            },
            'registration_number': {
                'original': processed_data['original']['registration'],
                'processed': processed_data['processed']['registration'],
                'is_valid': processed_data['validation']['reg_number_valid'],
                'cyprus_valid': processed_data['validation']['cyprus_reg_number_valid']
            },
            'overall_valid': (
                processed_data['validation']['cyprus_name_valid'] and 
                processed_data['validation']['cyprus_reg_number_valid']
            )
        },
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Add validation summary
    validation_issues = []
    if not processed_data['validation']['cyprus_name_valid']:
        validation_issues.append("Company name format is invalid for Cyprus registry")
    if not processed_data['validation']['cyprus_reg_number_valid']:
        validation_issues.append("Registration number format is invalid (must be exactly 6 digits)")
    
    if validation_issues:
        response['validation_issues'] = validation_issues
    
    # Perform actual search if requested and validation passed
    if perform_search and response['validation']['overall_valid']:
        try:
            search_results = search_cyprus_company_registry(
                processed_data['processed']['registration'],
                processed_data['processed']['name']
            )
            response['search'] = search_results
        except Exception as e:
            response['search'] = {
                'search_performed': False,
                'error': f"Search failed: {str(e)}"
            }
    elif perform_search and not response['validation']['overall_valid']:
        response['search'] = {
            'search_performed': False,
            'error': "Search skipped due to validation failures"
        }
    
    return response

def validate(data):
    """Alias for main function to maintain compatibility"""
    return main(data)

# Bulk validation function
def validate_bulk(companies_data):
    """
    Validate multiple companies at once
    
    Expected data format:
    {
        "companies": [
            {
                "company_name": "Company 1",
                "registration_number": "123456"
            },
            {
                "company_name": "Company 2", 
                "registration_number": "654321"
            }
        ]
    }
    """
    
    if not companies_data.get('companies') or not isinstance(companies_data['companies'], list):
        return {
            'success': False,
            'error': 'companies array is required'
        }
    
    results = []
    valid_count = 0
    
    for i, company in enumerate(companies_data['companies']):
        try:
            result = main(company)
            result['index'] = i
            results.append(result)
            
            if result.get('validation', {}).get('overall_valid'):
                valid_count += 1
                
        except Exception as e:
            results.append({
                'success': False,
                'error': str(e),
                'index': i
            })
    
    return {
        'success': True,
        'total_companies': len(companies_data['companies']),
        'valid_companies': valid_count,
        'invalid_companies': len(companies_data['companies']) - valid_count,
        'results': results,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }