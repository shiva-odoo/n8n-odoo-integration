#!/usr/bin/env python3
"""
Quick verification script to confirm all portal endpoints are implemented
"""

import re

def verify_endpoints():
    print("🔍 Verifying Portal API Implementation...\n")
    
    # Read app.py
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Define expected endpoints
    endpoints = {
        "Dashboard": [
            r'@app\.route\("/api/dashboard/metrics"',
            r'@app\.route\("/api/dashboard/recent-documents"',
            r'@app\.route\("/api/dashboard/compliance-items"',
        ],
        "Company Profile": [
            r'@app\.route\("/api/company/profile", methods=\["GET"\]',
            r'@app\.route\("/api/company/profile", methods=\["PUT", "POST"\]',
        ],
        "Bank Reconciliation": [
            r'@app\.route\("/api/bank/transactions"',
            r'@app\.route\("/api/bank/accounts"',
            r'@app\.route\("/api/bank/reconcile"',
        ],
        "Compliance Center": [
            r'@app\.route\("/api/compliance/items", methods=\["GET"\]',
            r'@app\.route\("/api/compliance/items", methods=\["POST"\]',
            r'@app\.route\("/api/compliance/items/<compliance_id>", methods=\["PUT"\]',
            r'@app\.route\("/api/compliance/items/<compliance_id>", methods=\["DELETE"\]',
        ]
    }
    
    # Verify modules
    print("📦 Checking Python Modules:")
    modules = ['dashboard', 'profile', 'bank_reconciliation', 'compliance']
    for module in modules:
        pattern = f'import {module}'
        if re.search(pattern, content):
            print(f"  ✅ {module}.py - IMPORTED")
        else:
            print(f"  ❌ {module}.py - NOT IMPORTED")
    
    print()
    
    # Verify endpoints
    total_found = 0
    total_expected = sum(len(v) for v in endpoints.values())
    
    for category, patterns in endpoints.items():
        print(f"🎯 {category} Endpoints:")
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                # Get line number
                line_num = content[:match.start()].count('\n') + 1
                print(f"  ✅ Found at line {line_num}")
                total_found += 1
            else:
                print(f"  ❌ NOT FOUND: {pattern}")
        print()
    
    # Summary
    print("=" * 60)
    print(f"📊 SUMMARY:")
    print(f"  Total Endpoints Expected: {total_expected}")
    print(f"  Total Endpoints Found: {total_found}")
    print(f"  Status: {'✅ ALL IMPLEMENTED' if total_found == total_expected else '❌ MISSING ENDPOINTS'}")
    print("=" * 60)
    
    return total_found == total_expected

if __name__ == "__main__":
    success = verify_endpoints()
    exit(0 if success else 1)

