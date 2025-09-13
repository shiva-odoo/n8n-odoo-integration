import re
import time
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
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

def process_director_name(name):
    """
    Process director name: convert to uppercase and trim spaces
    Args:
        name (str): The director name to process
    Returns:
        str: Processed director name (uppercase, trimmed)
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

def parse_directors_data(html_content):
    """Parse HTML content from directors page and extract director information"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    directors_data = {
        "success": False,
        "directors": [],
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
                if error_text and error_text not in directors_data["errors"]:
                    directors_data["errors"].append(error_text)
        
        # Look for director tables or data containers
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
                directors_data["raw_tables"].append({
                    "table_index": i,
                    "data": table_data
                })
        
        # Extract director names from tables
        text_content = soup.get_text()
        
        # Look for director names in tables
        for table in directors_data["raw_tables"]:
            for row in table["data"]:
                for cell in row:
                    # Check if cell contains a person's name (basic heuristic)
                    if len(cell) > 3 and any(char.isalpha() for char in cell):
                        # Filter out common non-name entries
                        exclude_terms = ['Όνομα', 'Name', 'Διευθυντής', 'Director', 'Γραμματέας', 'Secretary', 
                                       'Ημερομηνία', 'Date', 'Στοιχεία', 'Details', 'Τύπος', 'Type']
                        
                        if not any(term.lower() in cell.lower() for term in exclude_terms):
                            # Process as potential director name
                            processed_name = process_director_name(cell)
                            if processed_name and processed_name not in directors_data["directors"]:
                                directors_data["directors"].append(processed_name)
        
        # Check if we found any directors
        if directors_data["directors"] or directors_data["raw_tables"]:
            directors_data["success"] = True
        
        # If no directors found but no errors
        if not directors_data["errors"] and not directors_data["directors"]:
            directors_data["errors"].append("No directors found on this page")
        
    except Exception as e:
        directors_data["errors"].append(f"Parsing error: {str(e)}")
    
    return directors_data

def validate_director(director_name, directors_list):
    """
    Check if director name matches any name in the directors list
    Args:
        director_name (str): Director name to validate
        directors_list (list): List of director names from the website
    Returns:
        dict: Validation result
    """
    processed_director = process_director_name(director_name)
    
    validation_result = {
        "director_name": director_name,
        "processed_director_name": processed_director,
        "directors_found": directors_list,
        "director_valid": False,
        "matched_name": None
    }
    
    # Greek to English name mappings (common conversions)
    name_mappings = {
        "ΚΟΙΡΑΝΙΔΗΣ ΣΤΕΛΙΟΣ": "STELIOS KYRANIDES",
        "ΚΥΡΑΝΙΔΗΣ ΣΤΕΛΙΟΣ": "STELIOS KYRANIDES", 
        "ΣΤΕΛΙΟΣ ΚΟΙΡΑΝΙΔΗΣ": "STELIOS KYRANIDES",
        "ΣΤΕΛΙΟΣ ΚΥΡΑΝΙΔΗΣ": "STELIOS KYRANIDES"
    }
    
    # Check for exact match
    if processed_director in directors_list:
        validation_result["director_valid"] = True
        validation_result["matched_name"] = processed_director
        return validation_result
    
    # Check for Greek name mappings
    for greek_name, english_name in name_mappings.items():
        if greek_name in directors_list and english_name.upper() == processed_director:
            validation_result["director_valid"] = True
            validation_result["matched_name"] = greek_name
            return validation_result
    
    # Check for partial match (in case of slight variations)
    for director in directors_list:
        if processed_director in director or director in processed_director:
            validation_result["director_valid"] = True
            validation_result["matched_name"] = director
            break
    
    # Check if any director contains parts of the name (word-based matching)
    director_words = processed_director.split()
    for director in directors_list:
        director_upper = director.upper()
        # Check if all words from the search name appear in this director entry
        if len(director_words) >= 2 and all(word in director_upper for word in director_words):
            validation_result["director_valid"] = True
            validation_result["matched_name"] = director
            break
    
    return validation_result

def search_cyprus_company_with_director_validation(data):
    """
    Main function to search Cyprus company registry with director validation
    
    Expected data format:
    {
        "company_name": "KYRASTEL ENTERPRISES LTD",
        "registration_number": "474078",
        "director_name": "STELIOS KYRANIDES",  # Required for director validation
        "perform_search": true  # Set to true to perform actual search
    }
    
    Returns:
        dict: Validation results and search results with director validation
    """
    
    # Validate required fields
    if not data.get('company_name') and not data.get('registration_number'):
        return {
            'success': False,
            'error': 'Either company_name or registration_number is required'
        }
    
    company_name = data.get('company_name', '')
    registration_number = data.get('registration_number', '')
    director_name = data.get('director_name', '')
    perform_search = data.get('perform_search', False)
    
    # Process and validate the company data
    processed_data = process_company_data(company_name, registration_number)
    processed_director = process_director_name(director_name)
    
    # Prepare initial response
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
            'director_name': {
                'original': director_name,
                'processed': processed_director,
                'is_valid': bool(processed_director)
            },
            'overall_valid': (
                processed_data['validation']['cyprus_name_valid'] and 
                processed_data['validation']['cyprus_reg_number_valid'] and
                bool(processed_director)
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
    if not processed_director:
        validation_issues.append("Director name is required for director validation")
    
    if validation_issues:
        response['validation_issues'] = validation_issues
    
    # Perform actual search if requested and basic validation passed
    if perform_search and response['validation']['overall_valid']:
        try:
            search_results = search_cyprus_company_with_selenium(
                processed_data['processed']['registration'],
                processed_data['processed']['name'],
                processed_director
            )
            response['search'] = search_results
            
            # Update overall success based on search results
            response['success'] = search_results.get('success', False)
            
        except Exception as e:
            response['search'] = {
                'search_performed': False,
                'error': f"Search failed: {str(e)}"
            }
            response['success'] = False
    elif perform_search and not response['validation']['overall_valid']:
        response['search'] = {
            'search_performed': False,
            'error': "Search skipped due to validation failures"
        }
    
    return response

def search_cyprus_company_with_selenium(reg_number, company_name, director_name):
    """
    Perform the actual Cyprus company registry search with director validation using Selenium
    """
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--remote-debugging-port=9222")
    chrome_options.add_argument("--user-data-dir=/tmp/chrome_selenium_profile")
    chrome_options.add_argument("--headless")  # Run headless for production
    
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
        
        # Get the company search results
        html_response = driver.page_source
        company_search_result = parse_company_data(html_response)
        
        search_response = {
            "success": False,
            "company_search": company_search_result,
            "director_validation": {},
            "search_url": driver.current_url
        }
        
        # If company search failed, return early
        if not company_search_result["success"]:
            search_response["errors"] = company_search_result.get("errors", [])
            return search_response
        
        # Try to click on the first result and navigate to directors page
        try:
            # Look for the results table row
            result_row = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "tr.basket"))
            )
            result_row.click()
            time.sleep(3)
            
            # Click on directors tab
            directors_tab = wait.until(
                EC.element_to_be_clickable((By.ID, "ctl00_cphMyMasterCentral_directors"))
            )
            directors_tab.click()
            time.sleep(3)
            
            # Parse directors page
            directors_html = driver.page_source
            directors_result = parse_directors_data(directors_html)
            
            # Validate director
            director_validation = validate_director(director_name, directors_result.get('directors', []))
            search_response["director_validation"] = director_validation
            search_response["success"] = director_validation["director_valid"]
            
        except (TimeoutException, NoSuchElementException) as e:
            search_response["director_validation"] = {
                "error": f"Could not access directors page: {str(e)}",
                "director_valid": False
            }
        
        return search_response
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Search error: {str(e)}"
        }
    finally:
        driver.quit()

def validate_bulk_companies_with_directors(companies_data):
    """
    Validate multiple companies with director validation
    
    Expected data format:
    {
        "companies": [
            {
                "company_name": "Company 1",
                "registration_number": "123456",
                "director_name": "Director 1"
            },
            {
                "company_name": "Company 2", 
                "registration_number": "654321",
                "director_name": "Director 2"
            }
        ],
        "perform_search": false  # Set to true to perform actual searches
    }
    """
    
    if not companies_data.get('companies') or not isinstance(companies_data['companies'], list):
        return {
            'success': False,
            'error': 'companies array is required'
        }
    
    results = []
    valid_count = 0
    perform_search = companies_data.get('perform_search', False)
    
    for i, company in enumerate(companies_data['companies']):
        try:
            # Add perform_search flag to individual company data
            company_data = company.copy()
            company_data['perform_search'] = perform_search
            
            result = search_cyprus_company_with_director_validation(company_data)
            result['index'] = i
            results.append(result)
            
            if result.get('validation', {}).get('overall_valid') and result.get('success'):
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

# Main execution function
def main():
    """
    Example usage of the Cyprus company registry validator with director validation
    """
    
    # Example data for single company validation with director
    example_data = {
        "company_name": "KYRASTEL ENTERPRISES LTD",
        "registration_number": "474078",
        "director_name": "STELIOS KYRANIDES",
        "perform_search": False  # Set to True to perform actual search
    }
    
    print("=== CYPRUS COMPANY REGISTRY VALIDATOR WITH DIRECTOR VALIDATION ===")
    print("Example single company validation:")
    print(json.dumps(example_data, indent=2))
    
    # Perform validation
    result = search_cyprus_company_with_director_validation(example_data)
    
    print("\nValidation Result:")
    print(json.dumps(result, indent=2))
    
    # Example bulk validation
    bulk_data = {
        "companies": [
            {
                "company_name": "KYRASTEL ENTERPRISES LTD",
                "registration_number": "474078",
                "director_name": "STELIOS KYRANIDES"
            },
            {
                "company_name": "TEST COMPANY LTD",
                "registration_number": "123456",
                "director_name": "JOHN DOE"
            }
        ],
        "perform_search": False
    }
    
    print("\n=== BULK VALIDATION EXAMPLE ===")
    bulk_result = validate_bulk_companies_with_directors(bulk_data)
    print(json.dumps(bulk_result, indent=2))

if __name__ == "__main__":
    main()