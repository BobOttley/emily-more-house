from static_qa_config import STATIC_QA_LIST  # Import the correct list
from difflib import SequenceMatcher

RELATED_TOPICS = {
    # Financial
    'fees': ['bursaries', 'scholarships', 'enquiry', 'admissions'],
    'bursaries': ['fees', 'scholarships', 'enquiry', 'admissions'],
    'scholarships': ['fees', 'bursaries', 'enquiry', 'subjects'],

    # Academic
    'subjects': ['academic life', 'learning support', 'results', 'sixth form'],
    'academic life': ['subjects', 'learning support', 'results', 'pastoral care'],
    'results': ['academic life', 'subjects', 'inspection', 'sixth form'],
    'inspection': ['results', 'academic life', 'pastoral care', 'safeguarding'],
    'learning support': ['subjects', 'academic life', 'pastoral care', 'admissions'],
    'sixth form': ['subjects', 'results', 'admissions', 'enquiry'],

    # Pastoral & Wellbeing
    'pastoral care': ['safeguarding', 'learning support', 'co-curricular', 'faith life'],
    'safeguarding': ['pastoral care', 'policies', 'contact', 'admissions'],

    # Open Days & Visits (now shows dates first, then booking options)
    'open events': ['enquiry', 'private tour', 'virtual tour', 'admissions'],
    'book open day': ['open events', 'private tour', 'enquiry', 'admissions'],
    'private tour': ['open events', 'enquiry', 'admissions', 'virtual tour'],
    'virtual tour': ['open events', 'private tour', 'location', 'facilities'],

    # Admissions Journey
    'enquiry': ['open events', 'fees', 'admissions', 'tailored prospectus'],
    'admissions': ['enquiry', 'open events', 'fees', 'entry points'],
    'entry points': ['admissions', 'enquiry', 'registration deadlines', 'fees'],
    'registration deadlines': ['admissions', 'enquiry', 'open events', 'entry points'],
    'tailored prospectus': ['enquiry', 'admissions', 'subjects', 'open events'],

    # Practical Information
    'contact': ['location', 'enquiry', 'admissions', 'open events'],
    'location': ['contact', 'virtual tour', 'open events', 'facilities'],
    'term dates': ['contact', 'admissions', 'calendar', 'lunch menu'],
    'uniform': ['fees', 'contact', 'admissions', 'lunch menu'],
    'lunch menu': ['uniform', 'fees', 'contact', 'term dates'],

    # Activities
    'sport': ['co-curricular', 'pastoral care', 'facilities', 'subjects'],
    'co-curricular': ['sport', 'faith life', 'pastoral care', 'subjects'],
    'faith life': ['pastoral care', 'co-curricular', 'ethos', 'subjects'],
    'facilities': ['virtual tour', 'sport', 'location', 'subjects'],
}

DEFAULT_BUTTONS = {
    'en': ['open events', 'enquiry', 'fees', 'subjects', 'admissions', 'pastoral care'],
    'zh': ['open events', 'enquiry', 'fees', 'subjects', 'admissions', 'pastoral care'],
    'de': ['open events', 'enquiry', 'fees', 'subjects', 'admissions', 'pastoral care'],
    'fr': ['open events', 'enquiry', 'fees', 'subjects', 'admissions', 'pastoral care'],
    'es': ['open events', 'enquiry', 'fees', 'subjects', 'admissions', 'pastoral care']
}

# High-intent topics that should always show 'enquiry' as first button
HIGH_INTENT_TOPICS = {
    'fees', 'bursaries', 'scholarships', 'admissions', 'entry points',
    'registration deadlines', 'open events', 'book open day'
}

# Topics where showing 'open events' first makes sense
VISIT_INTENT_TOPICS = {
    'location', 'facilities', 'virtual tour', 'subjects', 'pastoral care'
}

def get_suggestions(user_input, language='en', max_buttons=6):
    """Generate contextual button suggestions based on user input

    Args:
        user_input: The user's question or matched topic key
        language: Language code (en, fr, es, de, zh)
        max_buttons: Maximum number of buttons to return (default 6)

    Returns:
        List of button dicts with 'label' and 'query' keys
    """
    user_input = user_input.lower()
    best_score = 0
    best_key = None

    print(f"🔍 get_suggestions called with: '{user_input}' | Language: {language}")

    # Fuzzy match the input to known keys/variants
    for qa in STATIC_QA_LIST:
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
    if best_key and best_score > 0.3:
        related = RELATED_TOPICS.get(best_key, DEFAULT_BUTTONS.get(language, []))
        print(f"📋 Found related topics for '{best_key}': {related}")
    else:
        related = DEFAULT_BUTTONS.get(language, [])
        best_key = None  # No match, use defaults
        print(f"📋 Using default buttons: {related}")

    # Smart button ordering based on context
    if best_key:
        # Already got good related topics in priority order
        final_keys = list(related)
    else:
        # Using defaults - no reordering needed
        final_keys = list(related)

    # Remove duplicates while preserving order
    seen = set()
    final_keys = [k for k in final_keys if not (k in seen or seen.add(k))]

    # Limit to max_buttons
    final_keys = final_keys[:max_buttons]

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