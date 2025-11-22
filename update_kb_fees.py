#!/usr/bin/env python3
"""
Script to update fees information in the knowledge base
"""
import pickle
import re

# Load the knowledge base
with open('kb_chunks/kb_chunks.pkl', 'rb') as f:
    data = pickle.load(f)

print(f"📚 Loaded knowledge base with {len(data)} items")
print(f"Keys in data: {data.keys() if isinstance(data, dict) else 'Not a dict'}")

# Show structure
if isinstance(data, dict):
    for key in data.keys():
        value = data[key]
        if isinstance(value, list):
            print(f"  {key}: list with {len(value)} items")
            if len(value) > 0:
                print(f"    First item type: {type(value[0])}")
                if isinstance(value[0], dict):
                    print(f"    First item keys: {value[0].keys()}")
        else:
            print(f"  {key}: {type(value)}")

# Look for fees-related chunks
print("\n🔍 Searching for fees-related chunks...")

updated_count = 0

# New fees text for 2025-26
new_fees_text = """More House School Fees 2025-26

Tuition Fees:
- Years 5 and 6: £7,800 per term (inclusive of VAT)
- Years 7-13: £10,950 per term (inclusive of VAT)

Registration Fee:
£150 per application

Deposit:
Upon acceptance, a deposit of 50% of one term's fees is required. This deposit is refundable at the end of your daughter's time at the school, but is non-refundable if she does not take up the offered place.

Additional Costs:
- Private music lessons: £295 per term for 10 individual 30-minute lessons (various instruments and singing available)
- Some trips may incur additional costs (some optional, others part of academic curriculum such as Activities Week)

Payment Terms:
- Fees are due by the first day of each term
- Full term's notice of withdrawal required in writing to the Head, or a term's fees payable in lieu

Family Discount:
An allowance of up to 15% off the fees is available for the eldest daughter when there are three or more sisters attending the school at the same time.

Payment Methods:
Payments can be made via direct debit. A form is available for this purpose.
"""

# Function to check if text contains old fees
def contains_old_fees(text):
    if not isinstance(text, str):
        return False
    return '£10,530' in text or '2024-2025' in text or '2024/25' in text

# Try to update
if isinstance(data, dict) and 'chunks' in data:
    chunks = data['chunks']
    for i, chunk in enumerate(chunks):
        if isinstance(chunk, dict) and 'text' in chunk:
            if contains_old_fees(chunk['text']):
                print(f"✏️  Found old fees in chunk {i}")
                print(f"    Old text preview: {chunk['text'][:200]}...")
                chunk['text'] = new_fees_text
                updated_count += 1

elif isinstance(data, list):
    for i, item in enumerate(data):
        if isinstance(item, dict) and 'text' in item:
            if contains_old_fees(item['text']):
                print(f"✏️  Found old fees in item {i}")
                print(f"    Old text preview: {item['text'][:200]}...")
                item['text'] = new_fees_text
                updated_count += 1

print(f"\n✅ Updated {updated_count} chunk(s)")

if updated_count > 0:
    # Save updated data
    with open('kb_chunks/kb_chunks.pkl', 'wb') as f:
        pickle.dump(data, f)
    print("💾 Saved updated knowledge base")
else:
    print("⚠️  No chunks were updated. The data structure might be different.")
    print("   You may need to manually inspect the pickle file structure.")
