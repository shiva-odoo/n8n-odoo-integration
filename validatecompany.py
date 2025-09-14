from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import json
import time
import re

# Initialize variables as requested
company_name = "KYRASTEL ENTERPRISES LTD"
registration_number = "474078"
director_name = "STELIOS KYRANIDES"

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

def trigger_chrome_translate(driver):
    """
    Trigger Chrome's built-in Google Translate feature
    Args:
        driver: Selenium WebDriver instance
    """
    try:
        # Try to trigger translation by executing JavaScript
        print("Attempting to trigger Chrome translate...")
        
        # Method 1: Try to find and click translate button if visible
        try:
            translate_button = driver.find_element(By.CSS_SELECTOR, "[data-translate-button]")
            if translate_button.is_displayed():
                translate_button.click()
                time.sleep(3)
                print("Translate button clicked successfully")
                return True
        except:
            pass
        
        # Method 2: Execute JavaScript to trigger translation
        try:
            driver.execute_script("""
                if (typeof google !== 'undefined' && google.translate) {
                    google.translate.TranslateElement();
                }
            """)
            time.sleep(3)
            print("Translation triggered via JavaScript")
            return True
        except:
            pass
        
        # Method 3: Try to detect Greek text and suggest translation
        page_text = driver.find_element(By.TAG_NAME, "body").text
        if any(char in page_text for char in "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩαβγδεζηθικλμνξοπρστυφχψω"):
            print("Greek text detected - Chrome should offer translation")
            # Add a small delay to allow Chrome to detect the language
            time.sleep(2)
            return True
        
        return False
    except Exception as e:
        print(f"Could not trigger translation: {e}")
        return False

def search_cyprus_company_with_director(reg_number="474078", company_name="KYRASTEL ENTERPRISES LTD", director_name="STELIOS KYRANIDES"):
    """
    Search for a Cyprus company, click on the result, navigate to directors page, and validate director
    
    Args:
        reg_number (str): Company registration number
        company_name (str): Company name
        director_name (str): Director name to validate
    
    Returns:
        dict: JSON response with company data, director validation, and overall validation
    """
    
    # ============================================================================
    # PROCESS INPUT PARAMETERS WITH REGEX FUNCTIONS
    # ============================================================================
    
    print("=== PROCESSING INPUT PARAMETERS ===")
    
    # Process the input parameters using our regex functions
    processed_data = process_company_data(company_name, reg_number)
    processed_director = process_director_name(director_name)
    
    print(f"Original name: '{company_name}'")
    print(f"Processed name: '{processed_data['processed']['name']}'")
    print(f"Original reg number: '{reg_number}'")
    print(f"Processed reg number: '{processed_data['processed']['registration']}'")
    print(f"Original director: '{director_name}'")
    print(f"Processed director: '{processed_director}'")
    print(f"Validation results: {processed_data['validation']}")
    
    # Use processed values for the search
    search_name = processed_data['processed']['name']
    search_reg_number = processed_data['processed']['registration']
    
    # Initialize response structure
    response = {
        "success": False,
        "overall_valid": False,
        "director_valid": False,
        "company_search": {},
        "director_validation": {},
        "errors": [],
        "search_params": {
            "registration_number": reg_number,
            "company_name": company_name,
            "director_name": director_name,
            "processed_registration_number": search_reg_number,
            "processed_company_name": search_name,
            "processed_director_name": processed_director,
            "validation": processed_data['validation'],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    }
    
    # Validate inputs before proceeding
    if not processed_data['validation']['cyprus_name_valid']:
        response["errors"].append(f"Invalid company name format: '{company_name}'")
        return response
    
    if not processed_data['validation']['cyprus_reg_number_valid']:
        response["errors"].append(f"Invalid registration number format: '{reg_number}' (must be 6 digits)")
        return response
    
    if not processed_director:
        response["errors"].append(f"Invalid director name format: '{director_name}'")
        return response
    
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
        # Navigate to the webpage (English version)
        print("Navigating to Cyprus eFiling website (English)...")
        driver.get("https://efiling.drcor.mcit.gov.cy/DrcorPublic/SearchForm.aspx?sc=0&lang=en")
        
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
        company_search_result = parse_company_data(html_response)
        response["company_search"] = company_search_result
        
        # Check if company search was successful
        if not company_search_result["success"]:
            response["errors"].extend(company_search_result.get("errors", []))
            response["errors"].append("Company search failed - no valid results found")
            return response
        
        # Company search successful - set overall_valid to True initially
        response["overall_valid"] = True
        
        # ============================================================================
        # CLICK ON THE FIRST RESULT (0th element)
        # ============================================================================
        
        print("Looking for search results table...")
        
        try:
            # Look for the results table row with class "basket"
            result_row = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "tr.basket"))
            )
            
            print("Found search result row, clicking on it...")
            result_row.click()
            
            # Wait for new page to load
            time.sleep(3)
            
        except (TimeoutException, NoSuchElementException) as e:
            response["errors"].append(f"Could not find or click on search result: {str(e)}")
            return response
        
        # ============================================================================
        # CLICK ON DIRECTORS TAB
        # ============================================================================
        
        print("Looking for directors tab...")
        
        try:
            # Look for the directors tab with the specific ID
            directors_tab = wait.until(
                EC.element_to_be_clickable((By.ID, "ctl00_cphMyMasterCentral_directors"))
            )
            
            print("Found directors tab, clicking on it...")
            directors_tab.click()
            
            # Wait for directors content to load
            time.sleep(3)
            
            # Try to trigger Chrome's built-in translate feature
            trigger_chrome_translate(driver)
            
            # Wait a bit more after translation attempt
            time.sleep(2)
            
        except (TimeoutException, NoSuchElementException) as e:
            response["errors"].append(f"Could not find or click on directors tab: {str(e)}")
            return response
        
        # ============================================================================
        # PARSE DIRECTORS PAGE AND VALIDATE DIRECTOR
        # ============================================================================
        
        print("Parsing directors page...")
        directors_html = driver.page_source
        directors_result = parse_directors_data(directors_html)
        
        print(f"Found directors: {directors_result.get('directors', [])}")
        
        # Validate director
        director_validation = validate_director(director_name, directors_result.get('directors', []))
        response["director_validation"] = director_validation
        response["director_valid"] = director_validation["director_valid"]
        
        if director_validation["director_valid"]:
            print(f"✅ Director validation successful! Matched: {director_validation['matched_name']}")
        else:
            print(f"❌ Director validation failed. Directors found: {directors_result.get('directors', [])}")
        
        # Final success determination
        response["success"] = True
        
        print(f"Final results:")
        print(f"- Overall Valid: {response['overall_valid']}")
        print(f"- Director Valid: {response['director_valid']}")
        
        return response
        
    except TimeoutException:
        print("Timeout error: Page elements took too long to load")
        response["errors"].append("Timeout error: Page elements took too long to load")
        return response
    except Exception as e:
        print(f"An error occurred: {e}")
        response["errors"].append(f"An error occurred: {str(e)}")
        return response
    finally:
        # Close the browser
        print("Closing browser...")
        driver.quit()

def save_json_response(json_data, filename="cyprus_search_results.json"):
    """Save JSON response to file"""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"Results saved to '{filename}'")

# ============================================================================
# EXAMPLE USAGE AND TESTING
# ============================================================================

def test_regex_functions():
    """Test the regex processing functions"""
    print("\n=== TESTING REGEX FUNCTIONS ===")
    
    test_cases = [
        {"name": "  kyrastel enterprises ltd  ", "reg": "ΗΕ474078", "director": "  stelios kyranides  "},
        {"name": "MICROSOFT CYPRUS LTD", "reg": "123456", "director": "John Doe"},
        {"name": "  google cyprus  ", "reg": "ΗΕ654321", "director": "Jane Smith"},
        {"name": "Amazon Web Services (Cyprus) Ltd", "reg": "789012", "director": "Bob Johnson"},
        {"name": "", "reg": "invalid", "director": ""},
        {"name": "Valid Company Name", "reg": "12345", "director": "Valid Director"}  # Too short reg
    ]
    
    for i, test_case in enumerate(test_cases):
        print(f"\nTest Case {i + 1}:")
        result = process_company_data(test_case['name'], test_case['reg'])
        processed_director = process_director_name(test_case['director'])
        print(f"Input: '{test_case['name']}' | '{test_case['reg']}' | '{test_case['director']}'")
        print(f"Output: '{result['processed']['name']}' | '{result['processed']['registration']}' | '{processed_director}'")
        print(f"Valid: {result['validation']['cyprus_name_valid'] and result['validation']['cyprus_reg_number_valid']}")

def main(data):
    """
    Main function to execute the enhanced Cyprus company search with director validation
    
    Args:
        reg_number (str): Company registration number
        company_name (str): Company name
        director_name (str): Director name to validate
    
    Returns:
        dict: JSON response with complete search and validation results
    """
    
    # Test the regex functions first
    test_regex_functions()
    
    print("\n" + "="*60)
    print("STARTING ENHANCED CYPRUS COMPANY SEARCH WITH DIRECTOR VALIDATION")
    print("="*60)

    reg_number = data.get("registration_number")
    company_name = data.get("company_name")
    director_name = data.get("director_name")
    
    # Execute the enhanced search
    result = search_cyprus_company_with_director(
        reg_number=reg_number, 
        company_name=company_name,
        director_name=director_name
    )
    
    if result:
        print("Enhanced search completed!")
        print(f"Success: {result['success']}")
        print(f"Overall Valid: {result['overall_valid']}")
        print(f"Director Valid: {result['director_valid']}")
        
        # Pretty print the JSON response
        print("\n" + "="*50)
        print("JSON RESPONSE:")
        print("="*50)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # Save to file
        save_json_response(result, "cyprus_enhanced_search_results.json")
        
        if result['success']:
            print(f"\nCompany search info: {result.get('company_search', {}).get('company_info', {})}")
            print(f"Director validation: {result.get('director_validation', {})}")
        else:
            print(f"\nErrors: {result.get('errors', [])}")
    else:
        print("Enhanced search failed - no response received")
        result = {
            "success": False,
            "overall_valid": False,
            "director_valid": False,
            "errors": ["No response received from search function"],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    
    return result