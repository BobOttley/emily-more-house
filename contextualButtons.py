from static_qa_config import STATIC_QA_LIST  # Import the correct list
from difflib import SequenceMatcher

RELATED_TOPICS = {
    'fees': ['bursaries', 'scholarships', 'admissions'],
    'bursaries': ['fees', 'scholarships', 'admissions'],
    'scholarships': ['fees', 'bursaries', 'subjects'],
    'subjects': ['academic life', 'learning support', 'results'],
    'academic life': ['subjects', 'learning support', 'results'],
    'results': ['academic life', 'subjects', 'inspection'],
    'inspection': ['results', 'pastoral care', 'safeguarding'],
    'pastoral care': ['safeguarding', 'co-curricular', 'faith life'],
    'safeguarding': ['pastoral care', 'policies', 'contact'],
    'open events': ['enquiry', 'registration deadlines', 'virtual tour'],
    'virtual tour': ['open events', 'location', 'facilities'],
    'enquiry': ['open events', 'registration deadlines', 'fees'],
    'admissions': ['fees', 'entry points', 'enquiry'],
    'entry points': ['admissions', 'age groups', 'registration deadlines'],
    'contact': ['location', 'enquiry', 'transport'],
    'tailored prospectus': ['enquiry', 'admissions', 'subjects', 'open events'],
    'registration deadlines': ['admissions', 'enquiry', 'open events'],
    'term dates': ['calendar', 'contact', 'admissions'],
    'uniform': ['fees', 'contact', 'admissions'],
    'lunch menu': ['fees', 'contact', 'uniform'],
    'sixth form': ['subjects', 'admissions', 'results'],
    'sport': ['co-curricular', 'faith life', 'pastoral care'],
    'co-curricular': ['sport', 'faith life', 'pastoral care'],
    'faith life': ['pastoral care', 'co-curricular', 'ethos'],
}

DEFAULT_BUTTONS = {
    'en': ['enquiry', 'fees', 'subjects', 'admissions', 'open events', 'pastoral care'],
    'zh': ['enquiry', 'fees', 'subjects', 'admissions', 'open events', 'pastoral care'],
    'de': ['enquiry', 'fees', 'subjects', 'admissions', 'open events', 'pastoral care'],
    'fr': ['enquiry', 'fees', 'subjects', 'admissions', 'open events', 'pastoral care'],
    'es': ['enquiry', 'fees', 'subjects', 'admissions', 'open events', 'pastoral care']
}

def get_suggestions(user_input, language='en'):
    """Generate contextual button suggestions based on user input"""
    user_input = user_input.lower()
    best_score = 0
    best_key = None

    print(f"🔍 get_suggestions called with: '{user_input}' | Language: {language}")

    # Fuzzy match the input to known keys/variants
    for qa in STATIC_QA_LIST:  # Use the correct list variable
        if qa['language'] != language:
            continue
        variants = [qa['key']] + qa.get('variants', [])
        for variant in variants:
            score = SequenceMatcher(None, user_input, variant.lower()).ratio()
            if score > best_score:
                best_score = score
                best_key = qa['key']

    print(f"🎯 Best match: '{best_key}' with score {best_score:.2f}")

    # Use RELATED_TOPICS if best_key found, otherwise use defaults
    if best_key and best_score > 0.3:  # Lower threshold for better matching
        related = RELATED_TOPICS.get(best_key, DEFAULT_BUTTONS.get(language, []))
        print(f"📋 Found related topics for '{best_key}': {related}")
    else:
        related = DEFAULT_BUTTONS.get(language, [])
        print(f"📋 Using default buttons: {related}")

    # Ensure 'enquiry' is first, then add related topics
    final_keys = ['enquiry'] + [k for k in related if k != 'enquiry']
    final_keys = final_keys[:6]  # Limit to 6 buttons
    
    print(f"🎲 Final button keys: {final_keys}")

    # Convert to button format
    buttons = []
    for key in final_keys:
        # Find the matching QA entry
        match = next((q for q in STATIC_QA_LIST if q['key'] == key and q['language'] == language), None)
        if match:
            # Use the 'label' field if it exists, otherwise use the key
            label = match.get('label', key.title())
            buttons.append({'label': label, 'query': key})
            print(f"✅ Added button: {label} -> {key}")
        else:
            print(f"❌ No match found for key: {key}")

    print(f"🏁 Final buttons: {buttons}")
    return buttons