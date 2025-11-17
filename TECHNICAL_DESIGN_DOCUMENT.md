# Technical Design Document
## Financial Document Processing and ERP Integration System

**Version:** 1.0
**Date:** November 17, 2025
**Status:** Implementation Complete

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Architecture](#system-architecture)
3. [Core Components](#core-components)
4. [Data Flow](#data-flow)
5. [Technology Stack](#technology-stack)
6. [Key Features](#key-features)
7. [API Architecture](#api-architecture)
8. [Security Model](#security-model)
9. [Integration Points](#integration-points)
10. [Document Processing Pipeline](#document-processing-pipeline)
11. [Deployment Architecture](#deployment-architecture)

---

## Executive Summary

This system is a comprehensive financial document processing and ERP integration platform built using Python Flask. It automates the extraction, classification, and processing of financial documents (invoices, bills, payroll, transactions) and integrates with ERP systems to create accounting records.

### Purpose
- Automate financial document processing workflows
- Reduce manual data entry in accounting systems
- Provide intelligent document classification using AI
- Enable multi-company financial management
- Deliver real-time financial reporting and analytics

### Key Capabilities
- AI-powered document classification (bills, invoices, payroll, transactions)
- Automated data extraction from PDF documents
- ERP integration via XML-RPC protocol
- Multi-company and multi-user support
- Real-time financial reporting
- Compliance tracking and management
- Bank reconciliation workflows

---

## System Architecture

### High-Level Architecture

```
┌─────────────────┐
│   Client Apps   │ (Web/Mobile Frontends)
└────────┬────────┘
         │ HTTPS/REST
         ▼
┌─────────────────────────────────────────────────────┐
│              Flask API Gateway                      │
│  - JWT Authentication                               │
│  - CORS Management                                  │
│  - Request Routing                                  │
└────────┬────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│          Business Logic Layer                       │
│  ┌──────────────┐  ┌──────────────┐                │
│  │  Document    │  │  Transaction │                │
│  │  Processing  │  │  Management  │                │
│  └──────────────┘  └──────────────┘                │
│  ┌──────────────┐  ┌──────────────┐                │
│  │  Company     │  │  Reporting   │                │
│  │  Management  │  │  & Analytics │                │
│  └──────────────┘  └──────────────┘                │
└────────┬──────────────────────┬─────────────────────┘
         │                      │
         ▼                      ▼
┌─────────────────┐    ┌─────────────────┐
│   AWS DynamoDB  │    │   ERP System    │
│   (Data Store)  │    │   (XML-RPC)     │
└─────────────────┘    └─────────────────┘
         │
         ▼
┌─────────────────┐
│   AWS S3        │
│   (Documents)   │
└─────────────────┘
```

### Architecture Principles

1. **Modular Design**: Each business function is encapsulated in separate Python modules
2. **Stateless API**: RESTful API design with JWT-based authentication
3. **Microservice-Ready**: Loosely coupled components that can be independently deployed
4. **Cloud-Native**: Leverages AWS services (DynamoDB, S3) for scalability
5. **AI-First**: Integrated AI for document classification and data extraction

---

## Core Components

### 1. API Gateway (`app.py`)
- **Lines of Code**: ~4,500
- **Responsibilities**:
  - HTTP request routing
  - CORS configuration
  - Module orchestration
  - Error handling and logging
  - Health check endpoints

### 2. Authentication & Authorization
- **Module**: `auth.py`, `middleware.py`
- **Features**:
  - JWT token generation and validation
  - Password hashing using bcrypt
  - Role-based access control (admin, user)
  - Company-level data isolation
  - Token expiry and refresh mechanisms

### 3. Document Processing Pipeline
- **Key Modules**:
  - `classifydocument.py`: AI-based document classification
  - `process_bill.py`: Vendor bill processing
  - `process_invoice.py`: Customer invoice processing
  - `process_payroll.py`: Payroll document processing
  - `processtransaction.py`: Bank transaction processing
  - `process_share_documents.py`: Share/equity transaction processing

### 4. ERP Integration Layer
- **Integration Modules**:
  - `createcompany.py`: Company/entity management
  - `createvendor.py`: Vendor master data
  - `createCustomer.py`: Customer master data
  - `createbill.py`: Accounts payable transactions
  - `createInvoice.py`: Accounts receivable transactions
  - `createjournal.py`: General ledger entries
  - `createtransaction.py`: Bank transactions
  - `createsharetransaction.py`: Equity transactions
  - `create_payroll_transaction.py`: Payroll posting

### 5. Business Logic
- **Accounting Logic**: `odoo_accounting_logic.py`
  - Chart of accounts mapping
  - Account classification rules
  - VAT/Tax handling
  - Asset vs. expense categorization
  - Property development accounting (IAS 40)

### 6. Reporting & Analytics
- **Module**: `reports.py` (~2,500 lines)
- **Report Types**:
  - Profit & Loss statements
  - Balance sheets
  - Cash flow analysis
  - Trial balance
  - Accounts payable/receivable aging
  - Tax reports
  - Custom financial analytics

### 7. Portal Features
- **Dashboard**: `dashboard.py`
  - KPI metrics (documents processed, revenue, compliance status)
  - Recent documents feed
  - Compliance item tracking

- **Company Profile**: `company_profile.py`
  - Company information management
  - Profile updates and retrieval

- **Bank Reconciliation**: `bank_reconciliation.py`
  - Bank transaction listing
  - Account management
  - Reconciliation workflows

- **Compliance Center**: `compliance.py`
  - Compliance item tracking
  - Task management
  - Status monitoring

---

## Data Flow

### Document Upload and Processing Flow

```
1. User uploads document
   ↓
2. File stored in S3
   ↓
3. Document metadata saved to DynamoDB
   ↓
4. AI classification triggered
   ↓
5. Document type identified (bill/invoice/payroll/transaction)
   ↓
6. Type-specific processing pipeline invoked
   ↓
7. Data extracted and validated
   ↓
8. ERP records created via XML-RPC
   ↓
9. Transaction metadata updated in DynamoDB
   ↓
10. User notified of completion
```

### Authentication Flow

```
1. User submits credentials (username/password)
   ↓
2. System validates against DynamoDB users table
   ↓
3. Password verified using bcrypt
   ↓
4. JWT token generated with user claims
   ↓
5. Token returned to client
   ↓
6. Client includes token in Authorization header
   ↓
7. Middleware validates token on each request
   ↓
8. User context extracted and attached to request
```

### ERP Integration Flow

```
1. Business logic prepares transaction data
   ↓
2. Account mapping applied
   ↓
3. Validation rules executed
   ↓
4. XML-RPC connection established
   ↓
5. Transaction posted to ERP
   ↓
6. ERP returns record ID
   ↓
7. Local database updated with ERP reference
   ↓
8. Audit trail created
```

---

## Technology Stack

### Backend Framework
- **Flask**: Python web framework
- **Flask-CORS**: Cross-origin resource sharing support

### AI & Machine Learning
- **Anthropic Claude**: Document classification and data extraction
- **OpenAI GPT**: Alternative AI processing
- **LangChain**: AI workflow orchestration
- **LangChain-OpenAI**: OpenAI integration
- **LangChain-Experimental**: Advanced AI features
- **Datasets**: ML dataset management

### Document Processing
- **PyPDF**: PDF parsing and text extraction
- **PyMuPDF (Fitz)**: Advanced PDF manipulation
- **Selenium**: Web scraping for online documents
- **BeautifulSoup4**: HTML parsing

### Authentication & Security
- **PyJWT**: JSON Web Token implementation
- **bcrypt**: Password hashing

### Cloud Services (AWS)
- **boto3**: AWS SDK for Python
- **DynamoDB**: NoSQL database for user data, transactions, metadata
- **S3**: Object storage for document files

### Database & Storage
- **Neo4j**: Graph database for relationship mapping
- **LangChain-Neo4j**: Neo4j integration for AI workflows

### Data Validation
- **Pydantic**: Data validation and settings management

### Reporting
- **FPDF**: PDF report generation

### Utilities
- **python-dotenv**: Environment variable management
- **googletrans**: Multi-language support

---

## Key Features

### 1. Multi-Company Support
- Isolated data by company
- Company-specific configurations
- Cross-company reporting (admin only)

### 2. Intelligent Document Classification
- Automatic document type detection
- Confidence scoring
- Support for multiple document formats
- Multi-language document processing

### 3. Automated Data Extraction
- Field-level extraction from documents
- Validation against business rules
- Error detection and flagging
- Manual override capabilities

### 4. Comprehensive CRUD Operations
The system supports full lifecycle management:
- **Create**: Companies, vendors, customers, products, bills, invoices, journals, transactions
- **Read**: All entity types with filtering and pagination
- **Update**: Vendors, bills, audit status, company profiles
- **Delete**: Companies, vendors, bills (with safety checks)

### 5. Advanced Financial Workflows
- Split invoice processing
- Batch document updates
- Matching workflows for reconciliation
- Credit note and refund processing
- Payment processing (customer and vendor)

### 6. Compliance & Audit
- Audit status tracking
- Compliance item management
- Document retention
- Change history logging

### 7. Onboarding
- New company onboarding workflows
- Financial profile configuration
- Company validation

---

## API Architecture

### API Design Patterns
- RESTful resource-based endpoints
- JSON request/response format
- Standard HTTP status codes
- Consistent error response structure

### API Endpoint Categories

#### Authentication (4 endpoints)
- `POST /api/auth/login` - User authentication
- `POST /api/auth/refresh` - Token refresh
- `POST /api/auth/logout` - User logout
- `GET /api/auth/me` - Current user info

#### Dashboard (3 endpoints)
- `GET /api/dashboard/metrics` - KPI metrics
- `GET /api/dashboard/recent-documents` - Document feed
- `GET /api/dashboard/compliance-items` - Compliance tasks

#### Company Profile (2 endpoints)
- `GET /api/company/profile` - Retrieve company profile
- `PUT/POST /api/company/profile` - Update company profile

#### Bank Reconciliation (3 endpoints)
- `GET /api/bank/transactions` - Bank transactions
- `GET /api/bank/accounts` - Bank account list
- `POST /api/bank/reconcile` - Reconcile transaction

#### Compliance Center (4 endpoints)
- `GET /api/compliance/items` - List compliance items
- `POST /api/compliance/items` - Create compliance item
- `PUT /api/compliance/items/<id>` - Update compliance item
- `DELETE /api/compliance/items/<id>` - Delete compliance item

#### Document Processing (4 endpoints)
- `POST /api/extract-pdf-data` - Extract data from PDF
- `POST /api/process-document` - Complete document processing
- `POST /api/extract-from-url` - Process document from URL
- `GET /api/extraction-status` - Check processing status

#### Reference Data (11+ endpoints)
- `GET /api/vendors` - List vendors
- `GET /api/companies` - List companies
- `GET /api/customers` - List customers
- `GET /api/products` - List products
- `GET /api/bills` - List bills
- `GET /api/invoices` - List invoices
- `GET /api/accounts` - Chart of accounts
- And more...

#### Create Operations (12+ endpoints)
- `POST /api/create/vendor` - Create vendor
- `POST /api/create/company` - Create company
- `POST /api/create/customer` - Create customer
- `POST /api/create/bill` - Create bill
- `POST /api/create/invoice` - Create invoice
- `POST /api/create/journal` - Create journal entry
- And more...

#### Update Operations (2+ endpoints)
- `PUT /api/modify/vendor` - Update vendor
- `PUT /api/modify/bill` - Update bill

#### Delete Operations (3 endpoints)
- `DELETE /api/delete/vendor` - Delete vendor
- `DELETE /api/delete/company` - Delete company
- `DELETE /api/delete/bill` - Delete bill

### Response Structure

**Success Response:**
```json
{
  "success": true,
  "data": { /* response data */ },
  "message": "Operation completed successfully"
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Error description",
  "details": { /* optional error details */ }
}
```

---

## Security Model

### Authentication Layers
1. **JWT-based Authentication**
   - Tokens expire after configurable period
   - Tokens include user claims (role, company_id)
   - Tokens cryptographically signed

2. **Middleware Protection**
   - `@jwt_required` decorator for protected endpoints
   - `@admin_required` decorator for admin-only operations
   - Request context includes authenticated user

3. **Company Data Isolation**
   - Users can only access their company's data
   - Company ID validated on every request
   - Admin users can access cross-company data

### Password Security
- Passwords hashed using bcrypt (adaptive hashing)
- Salt automatically generated per password
- No plaintext password storage

### API Security
- CORS configured for approved origins
- Request validation using Pydantic models
- SQL injection prevention (parameterized queries)
- Input sanitization for DynamoDB

---

## Integration Points

### ERP System Integration (XML-RPC)
- **Protocol**: XML-RPC over HTTPS
- **Authentication**: Username/API key
- **Operations**:
  - Search and read records
  - Create records
  - Update records
  - Delete records
  - Execute business methods

### AWS Services Integration

#### DynamoDB Tables
- `users` - User accounts and authentication
- `companies` - Company master data
- `transactions` - Transaction metadata
- `bills` - Bill metadata
- `invoices` - Invoice metadata
- `batch_processing` - Batch job tracking
- `compliance_items` - Compliance tracking
- `bank_accounts` - Bank account data
- `company_profiles` - Extended company information
- `payroll_transactions` - Payroll metadata
- `share_transactions` - Share/equity metadata

#### S3 Buckets
- Document storage
- Processed document archive
- Report storage

### External AI Services
- Anthropic Claude API for document processing
- OpenAI API for supplementary AI tasks

---

## Document Processing Pipeline

### Classification Algorithm

The system uses a multi-stage classification process:

1. **Document Type Detection**
   - Payroll documents
   - Vendor bills
   - Customer invoices
   - Bank statements
   - Share/equity documents
   - Onboarding documents

2. **Perspective Analysis**
   - Determines if document is FROM or TO the user's company
   - Applies appropriate accounting treatment

3. **Field Extraction**
   - Vendor/customer information
   - Line items and amounts
   - Dates and reference numbers
   - Tax/VAT information
   - Payment terms

4. **Validation**
   - Required field presence
   - Data type validation
   - Business rule validation
   - Cross-reference validation

### Processing Workflows

#### Bill Processing Workflow
1. Document classified as "bill"
2. Vendor information extracted
3. Vendor matched or created in ERP
4. Line items extracted and categorized
5. Account codes assigned based on accounting logic
6. Journal entry created in ERP
7. Bill record created with payable
8. Metadata stored in DynamoDB

#### Invoice Processing Workflow
1. Document classified as "invoice"
2. Customer information extracted
3. Customer matched or created in ERP
4. Products/services extracted
5. Tax calculations applied
6. Invoice created in ERP
7. Receivable recorded
8. Metadata stored in DynamoDB

#### Payroll Processing Workflow
1. Document classified as "payroll"
2. Employee records extracted
3. Earnings and deductions calculated
4. Journal entries created for:
   - Salary expense
   - Tax withholdings
   - Social insurance
   - Net pay liability
5. Payroll posted to ERP
6. Metadata stored in DynamoDB

---

## Deployment Architecture

### Hosting Platform
- Platform-as-a-Service (PaaS) deployment
- Container-based deployment
- Auto-scaling capabilities
- Load balancing

### Environment Variables
The system requires configuration through environment variables:
- Database connection strings
- API credentials (non-sensitive structure only)
- AWS region configuration
- JWT secret key
- Feature flags

### Database Design

#### DynamoDB Schema Design
- Partition keys for optimal data distribution
- Global secondary indexes for query patterns
- Sparse indexes for conditional attributes
- Time-to-live (TTL) for temporary data

### Monitoring & Logging
- Application logging via Python logging module
- Request/response logging
- Error tracking and alerting
- Performance metrics

---

## Accounting Logic Implementation

### Chart of Accounts Mapping

The system implements a tiered account mapping strategy:

#### Common Accounts (80% usage)
- Operating expenses (rent, utilities, professional fees)
- Cost of goods sold
- Revenue accounts
- Payables and receivables

#### Specialized Accounts (20% usage)
- Asset capitalization
- Property development (IAS 40 compliance)
- Investment accounting
- Multi-currency handling

### Tax Handling
- VAT calculation and allocation
- Reverse charge mechanism
- Tax rate determination
- Non-recoverable VAT handling

### Journal Entry Logic
- Automatic debit/credit balancing
- Multi-line entry support
- Account validation
- Period lock checking

---

## Module Breakdown

### Processing Modules (~15,000 lines)
- Document classification and extraction
- Type-specific processors (bills, invoices, payroll)
- Validation and error handling
- ERP posting logic

### CRUD Modules (~10,000 lines)
- Create operations for all entity types
- Update and modify operations
- Delete with cascade handling
- Batch operations

### Reporting Modules (~2,500 lines)
- Financial statement generation
- Custom analytics
- Data aggregation
- Export functionality

### Infrastructure Modules (~3,000 lines)
- Authentication and authorization
- API gateway and routing
- Middleware and decorators
- Utility functions

### Portal Modules (~1,000 lines)
- Dashboard and metrics
- Company profile management
- Bank reconciliation
- Compliance tracking

---

## Summary

This financial document processing system represents a comprehensive solution for automating accounting workflows. Built on modern cloud-native architecture with AI-powered document processing, it bridges the gap between physical/digital documents and structured ERP data.

### Key Achievements
- **50+ REST API endpoints** serving various business functions
- **38,000+ lines of Python code** organized in modular components
- **Multi-company support** with complete data isolation
- **AI-powered automation** reducing manual data entry by estimated 80%+
- **Cloud-native architecture** enabling scalability and reliability
- **Comprehensive financial reporting** providing real-time insights

### Technical Highlights
- Modular, maintainable codebase
- Stateless API design for horizontal scaling
- Robust security model with JWT and role-based access
- Integration with enterprise ERP systems
- Advanced document processing pipeline
- Real-time financial analytics

---

**Document Classification**: Public - Technical Overview
**Contains**: Architecture, design patterns, technology choices
**Does Not Contain**: Credentials, API keys, customer data, proprietary algorithms
