from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
import json
import time
import re



def main(data):
    success = False
    company_name = data["company_name"]
    registration_number = data["registration_number"]
    # You can customize the search parameters here
    result = search_cyprus_company(
        reg_number=registration_number, 
        company_name=company_name
    )
    
    if result:
        print("Search completed!")
        print(f"Success: {result['success']}")
        
        # Pretty print the JSON response
        print("\n" + "="*50)
        print("JSON RESPONSE:")
        print("="*50)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # Save to file
        save_json_response(result)
        
        if result['success']:
            success= True
            print(f"\nFound company info: {result.get('company_info', {})}")
        else:
            print(f"\nErrors: {result.get('errors', [])}")
    else:
        print("Search failed - no response received")
    # Safe access with fallback
    search_params = result.get('search_params', {}) 

    return {"success": success, "search_params":search_params}
    


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
        # Look for common patterns in Cyprus company registry
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

def search_cyprus_company(reg_number="474078", company_name="KYRASTEL ENTERPRISES LTD"):
    """
    Search for a Cyprus company and return JSON response
    
    Args:
        reg_number (str): Company registration number
        company_name (str): Company name
    
    Returns:
        dict: JSON response with company data or error information
    """
    
    # ============================================================================
    # PROCESS INPUT PARAMETERS WITH REGEX FUNCTIONS
    # ============================================================================
    
    print("=== PROCESSING INPUT PARAMETERS ===")
    
    # Process the input parameters using our regex functions
    processed_data = process_company_data(company_name, reg_number)
    
    print(f"Original name: '{company_name}'")
    print(f"Processed name: '{processed_data['processed']['name']}'")
    print(f"Original reg number: '{reg_number}'")
    print(f"Processed reg number: '{processed_data['processed']['registration']}'")
    print(f"Validation results: {processed_data['validation']}")
    
    # Use processed values for the search
    search_name = processed_data['processed']['name']
    search_reg_number = processed_data['processed']['registration']
    
    # Validate inputs before proceeding
    if not processed_data['validation']['cyprus_name_valid']:
        return {
            "success": False,
            "errors": [f"Invalid company name format: '{company_name}'"],
            "search_params": {
                "registration_number": reg_number,
                "company_name": company_name,
                "processed_registration_number": search_reg_number,
                "processed_company_name": search_name,
                "validation": processed_data['validation'],
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        }
    
    if not processed_data['validation']['cyprus_reg_number_valid']:
        return {
            "success": False,
            "errors": [f"Invalid registration number format: '{reg_number}' (must be 6 digits)"],
            "search_params": {
                "registration_number": reg_number,
                "company_name": company_name,
                "processed_registration_number": search_reg_number,
                "processed_company_name": search_name,
                "validation": processed_data['validation'],
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        }
    
    # ============================================================================
    # SELENIUM SEARCH PROCESS
    # ============================================================================
    
    # Initialize the WebDriver with Chrome options
    from selenium.webdriver.chrome.options import Options
    
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--remote-debugging-port=9222")
    chrome_options.add_argument("--user-data-dir=/tmp/chrome_selenium_profile")
    # Optionally run headless
    # chrome_options.add_argument("--headless")
    
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        # Navigate to the webpage
        print("Navigating to Cyprus eFiling website...")
        driver.get("https://efiling.drcor.mcit.gov.cy/DrcorPublic/SearchForm.aspx?sc=0")
        
        # Wait for page to load
        wait = WebDriverWait(driver, 15)
        
        # Fill registration number field
        print(f"Filling registration number: {search_reg_number}")
        reg_number_field = wait.until(
            EC.presence_of_element_located((By.ID, "ctl00_cphMyMasterCentral_ucSearch_txtNumber"))
        )
        reg_number_field.clear()
        reg_number_field.send_keys(search_reg_number)
        
        # Fill name field
        print(f"Filling company name: {search_name}")
        name_field = driver.find_element(By.ID, "ctl00_cphMyMasterCentral_ucSearch_txtName")
        name_field.clear()
        name_field.send_keys(search_name)
        
        # Click the Go button
        print("Clicking search button...")
        go_button = driver.find_element(By.XPATH, "//*[@id='ctl00_cphMyMasterCentral_ucSearch_lbtnSearch']")
        go_button.click()
        
        # Wait for results to load
        print("Waiting for search results...")
        time.sleep(3)
        
        # Wait for the page to change or results to appear
        try:
            wait.until(lambda driver: driver.current_url != "https://efiling.drcor.mcit.gov.cy/DrcorPublic/SearchForm.aspx?sc=0")
        except TimeoutException:
            print("Page didn't change - checking for results on same page...")
        
        # Wait a bit more for dynamic content to load
        time.sleep(2)
        
        # Get the response and parse it
        html_response = driver.page_source
        print("Search completed! Parsing results...")
        
        # Parse HTML to JSON
        json_response = parse_company_data(html_response)
        
        # Add search metadata with processed values
        json_response["search_params"] = {
            "registration_number": reg_number,
            "company_name": company_name,
            "processed_registration_number": search_reg_number,
            "processed_company_name": search_name,
            "validation": processed_data['validation'],
            "search_url": driver.current_url,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        print(f"Parsing completed! Found {len(json_response.get('raw_tables', []))} tables")
        
        return json_response
        
    except TimeoutException:
        print("Timeout error: Page elements took too long to load")
        return {
            "success": False,
            "errors": ["Timeout error: Page elements took too long to load"],
            "search_params": {
                "registration_number": reg_number,
                "company_name": company_name,
                "processed_registration_number": search_reg_number,
                "processed_company_name": search_name,
                "validation": processed_data['validation'],
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        }
    except Exception as e:
        print(f"An error occurred: {e}")
        return {
            "success": False,
            "errors": [f"An error occurred: {str(e)}"],
            "search_params": {
                "registration_number": reg_number,
                "company_name": company_name,
                "processed_registration_number": search_reg_number,
                "processed_company_name": search_name,
                "validation": processed_data['validation'],
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        }
    finally:
        # Close the browser
        print("Closing browser...")
        driver.quit()

def save_json_response(json_data, filename="cyprus_search_results.json"):
    """Save JSON response to file"""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"Results saved to '{filename}'")

def process_bulk_companies(companies):
    """
    Process multiple companies at once
    Args:
        companies (list): List of {name, registration} dictionaries
    Returns:
        list: List of processed results
    """
    if not isinstance(companies, list):
        return []
    
    return [process_company_data(company.get('name', ''), company.get('registration', '')) 
            for company in companies]

def filter_valid_companies(processed_results):
    """
    Filter valid companies from processed results
    Args:
        processed_results (list): Results from process_bulk_companies
    Returns:
        list: Only valid companies
    """
    return [result for result in processed_results 
            if result['validation']['cyprus_name_valid'] and result['validation']['cyprus_reg_number_valid']]

# ============================================================================
# EXAMPLE USAGE AND TESTING
# ============================================================================

def test_regex_functions():
    """Test the regex processing functions"""
    print("\n=== TESTING REGEX FUNCTIONS ===")
    
    test_cases = [
        {"name": "  kyrastel enterprises ltd  ", "reg": "ΗΕ474078"},
        {"name": "MICROSOFT CYPRUS LTD", "reg": "123456"},
        {"name": "  google cyprus  ", "reg": "ΗΕ654321"},
        {"name": "Amazon Web Services (Cyprus) Ltd", "reg": "789012"},
        {"name": "", "reg": "invalid"},
        {"name": "Valid Company Name", "reg": "12345"}  # Too short
    ]
    
    for i, test_case in enumerate(test_cases):
        print(f"\nTest Case {i + 1}:")
        result = process_company_data(test_case['name'], test_case['reg'])
        print(f"Input: '{test_case['name']}' | '{test_case['reg']}'")
        print(f"Output: '{result['processed']['name']}' | '{result['processed']['registration']}'")
        print(f"Valid: {result['validation']['cyprus_name_valid'] and result['validation']['cyprus_reg_number_valid']}")


    
    
    

