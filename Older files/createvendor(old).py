import xmlrpc.client
import logging
from typing import Dict, Optional, Union
import os
from dotenv import load_dotenv

load_dotenv()

class OdooVendorManager:
    def __init__(self, url: str, db: str, username: str, password: str):
        """
        Initialize Odoo connection for vendor management
        
        Args:
            url: Odoo server URL (e.g., 'https://omnithrive-technologies1.odoo.com')
            db: omnithrive-technologies1
            username = os.getenv("ODOO_USERNAME")
            password = os.getenv("ODOO_API_KEY")
        """
        self.url = url
        self.db = db
        self.username = username
        self.password = password
        
        # Initialize XML-RPC connections
        self.common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        self.models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        # Authenticate and get user ID
        self.uid = self.authenticate()
        
    def authenticate(self) -> int:
        """Authenticate with Odoo and return user ID"""
        try:
            uid = self.common.authenticate(self.db, self.username, self.password, {})
            if not uid:
                raise Exception("Authentication failed")
            logging.info(f"Successfully authenticated. User ID: {uid}")
            return uid
        except Exception as e:
            logging.error(f"Authentication error: {e}")
            raise

    def check_vendor_exists(self, vat: str = None, name: str = None, email: str = None) -> Optional[int]:
        """
        Check if vendor already exists based on VAT, name, or email
        
        Args:
            vat: VAT number
            name: Company name
            email: Email address
            
        Returns:
            Vendor ID if found, None otherwise
        """
        try:
            domain = [('is_company', '=', True), ('supplier_rank', '>', 0)]
            
            if vat:
                domain.append(('vat', '=', vat))
            elif email:
                domain.append(('email', '=', email))
            elif name:
                domain.append(('name', '=', name))
            else:
                return None
                
            vendor_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'res.partner', 'search',
                [domain], {'limit': 1}
            )
            
            return vendor_ids[0] if vendor_ids else None
            
        except Exception as e:
            logging.error(f"Error checking vendor existence: {e}")
            return None

    def create_vendor_basic(self, name: str, email: str = None) -> int:
        """
        Create a basic vendor with minimal information
        
        Args:
            name: Vendor/Company name
            email: Email address (optional)
            
        Returns:
            Created vendor ID
        """
        vendor_data = {
            'name': name,
            'is_company': True,
            'supplier_rank': 1,  # Mark as vendor
            'customer_rank': 0,  # Not a customer
        }
        
        if email:
            vendor_data['email'] = email
            
        try:
            vendor_id = self.models.execute_kw(
                self.db, self.uid, self.password,
                'res.partner', 'create',
                [vendor_data]
            )
            logging.info(f"Basic vendor created successfully. ID: {vendor_id}")
            return vendor_id
            
        except Exception as e:
            logging.error(f"Error creating basic vendor: {e}")
            raise

    def create_vendor_comprehensive(self, vendor_info: Dict) -> int:
        """
        Create a comprehensive vendor with full details
        
        Args:
            vendor_info: Dictionary containing vendor information
            
        Expected vendor_info structure:
        {
            'name': 'Company Name',
            'vat': 'VAT Number',
            'email': 'email@example.com',
            'phone': '+1234567890',
            'website': 'https://website.com',
            'street': 'Street Address',
            'city': 'City',
            'zip': 'Postal Code',
            'country_code': 'US',  # ISO country code
            'state_code': 'CA',    # State code (if applicable)
            'payment_terms': 30,   # Payment terms in days
            'currency_code': 'USD' # Currency code
        }
        
        Returns:
            Created vendor ID
        """
        # Check if vendor already exists
        existing_vendor = self.check_vendor_exists(
            vat=vendor_info.get('vat'),
            name=vendor_info.get('name'),
            email=vendor_info.get('email')
        )
        
        if existing_vendor:
            logging.info(f"Vendor already exists with ID: {existing_vendor}")
            return existing_vendor

        # Prepare vendor data
        vendor_data = {
            'name': vendor_info['name'],
            'is_company': True,
            'supplier_rank': 1,
            'customer_rank': 0,
        }
        
        # Add optional fields if provided
        optional_fields = {
            'vat': 'vat',
            'email': 'email', 
            'phone': 'phone',
            'website': 'website',
            'street': 'street',
            'city': 'city',
            'zip': 'zip'
        }
        
        for key, field in optional_fields.items():
            if vendor_info.get(key):
                vendor_data[field] = vendor_info[key]

        # Handle country
        if vendor_info.get('country_code'):
            country_id = self._get_country_id(vendor_info['country_code'])
            if country_id:
                vendor_data['country_id'] = country_id

        # Handle state
        if vendor_info.get('state_code') and vendor_info.get('country_code'):
            state_id = self._get_state_id(vendor_info['state_code'], vendor_info['country_code'])
            if state_id:
                vendor_data['state_id'] = state_id

        # Handle payment terms
        if vendor_info.get('payment_terms'):
            payment_term_id = self._get_payment_term_id(vendor_info['payment_terms'])
            if payment_term_id:
                vendor_data['property_supplier_payment_term_id'] = payment_term_id

        # Handle currency
        if vendor_info.get('currency_code'):
            currency_id = self._get_currency_id(vendor_info['currency_code'])
            if currency_id:
                vendor_data['property_purchase_currency_id'] = currency_id

        try:
            vendor_id = self.models.execute_kw(
                self.db, self.uid, self.password,
                'res.partner', 'create',
                [vendor_data]
            )
            logging.info(f"Comprehensive vendor created successfully. ID: {vendor_id}")
            return vendor_id
            
        except Exception as e:
            logging.error(f"Error creating comprehensive vendor: {e}")
            raise

    def _get_country_id(self, country_code: str) -> Optional[int]:
        """Get country ID from country code"""
        try:
            country_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'res.country', 'search',
                [[('code', '=', country_code.upper())]], {'limit': 1}
            )
            return country_ids[0] if country_ids else None
        except Exception as e:
            logging.error(f"Error getting country ID for {country_code}: {e}")
            return None

    def _get_state_id(self, state_code: str, country_code: str) -> Optional[int]:
        """Get state ID from state code and country"""
        try:
            country_id = self._get_country_id(country_code)
            if not country_id:
                return None
                
            state_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'res.country.state', 'search',
                [[('code', '=', state_code.upper()), ('country_id', '=', country_id)]], 
                {'limit': 1}
            )
            return state_ids[0] if state_ids else None
        except Exception as e:
            logging.error(f"Error getting state ID for {state_code}: {e}")
            return None

    def _get_payment_term_id(self, days: int) -> Optional[int]:
        """Get or create payment term for specified days"""
        try:
            # Search for existing payment term
            term_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'account.payment.term', 'search',
                [[('name', 'ilike', f'{days} days')]], {'limit': 1}
            )
            
            if term_ids:
                return term_ids[0]
            
            # Create new payment term if not found
            term_data = {
                'name': f'{days} Days',
                'line_ids': [(0, 0, {
                    'value': 'balance',
                    'days': days
                })]
            }
            
            term_id = self.models.execute_kw(
                self.db, self.uid, self.password,
                'account.payment.term', 'create',
                [term_data]
            )
            return term_id
            
        except Exception as e:
            logging.error(f"Error getting payment term for {days} days: {e}")
            return None

    def _get_currency_id(self, currency_code: str) -> Optional[int]:
        """Get currency ID from currency code"""
        try:
            currency_ids = self.models.execute_kw(
                self.db, self.uid, self.password,
                'res.currency', 'search',
                [[('name', '=', currency_code.upper())]], {'limit': 1}
            )
            return currency_ids[0] if currency_ids else None
        except Exception as e:
            logging.error(f"Error getting currency ID for {currency_code}: {e}")
            return None

    def update_vendor(self, vendor_id: int, update_data: Dict) -> bool:
        """Update existing vendor information"""
        try:
            self.models.execute_kw(
                self.db, self.uid, self.password,
                'res.partner', 'write',
                [[vendor_id], update_data]
            )
            logging.info(f"Vendor {vendor_id} updated successfully")
            return True
        except Exception as e:
            logging.error(f"Error updating vendor {vendor_id}: {e}")
            return False

    def get_vendor_info(self, vendor_id: int) -> Optional[Dict]:
        """Get vendor information by ID"""
        try:
            vendor_data = self.models.execute_kw(
                self.db, self.uid, self.password,
                'res.partner', 'read',
                [[vendor_id]], {'fields': ['name', 'vat', 'email', 'phone', 'street', 'city', 'country_id']}
            )
            return vendor_data[0] if vendor_data else None
        except Exception as e:
            logging.error(f"Error getting vendor info for ID {vendor_id}: {e}")
            return None


# Usage Examples
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Initialize Odoo connection
    odoo_vendor = OdooVendorManager(
        url='https://omnithrive-technologies1.odoo.com',
        db='omnithrive-technologies1',
        username = os.getenv("ODOO_USERNAME"),
        password = os.getenv("ODOO_API_KEY")
    )
    
    # Example 1: Create basic vendor
    try:
        basic_vendor_id = odoo_vendor.create_vendor_basic(
            name="Simple Supplier Ltd",
            email="contact@simplesupplier.com"
        )
        print(f"Basic vendor created with ID: {basic_vendor_id}")
    except Exception as e:
        print(f"Failed to create basic vendor: {e}")
    
    # Example 2: Create comprehensive vendor
    vendor_info = {
        'name': 'Advanced Technologies Inc',
        'vat': 'US123456789',
        'email': 'billing@advancedtech.com',
        'phone': '+1-555-123-4567',
        'website': 'https://www.advancedtech.com',
        'street': '123 Technology Drive',
        'city': 'San Francisco',
        'zip': '94105',
        'country_code': 'US',
        'state_code': 'CA',
        'payment_terms': 30,
        'currency_code': 'USD'
    }
    
    try:
        comprehensive_vendor_id = odoo_vendor.create_vendor_comprehensive(vendor_info)
        print(f"Comprehensive vendor created with ID: {comprehensive_vendor_id}")
    except Exception as e:
        print(f"Failed to create comprehensive vendor: {e}")
    
    # Example 3: Check if vendor exists and get info
    existing_vendor = odoo_vendor.check_vendor_exists(vat='US123456789')
    if existing_vendor:
        vendor_details = odoo_vendor.get_vendor_info(existing_vendor)
        print(f"Found existing vendor: {vendor_details}")