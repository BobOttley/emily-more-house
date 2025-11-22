/**
 * Emily's Conversational Booking System
 * Handles the complete booking flow conversationally in the chatbox
 */

// Booking state management
const EmilyBooking = {
    // Callback for when booking completes (for voice integration)
    onBookingComplete: null,

    // Current booking session data
    session: {
        stage: null,           // current stage in the flow
        isNewFamily: null,     // whether family is new or returning
        verifiedFamily: null,  // verified family data
        enquiryData: {},       // collected enquiry form data
        selectedEvent: null,   // selected open day event
        bookingData: {},       // booking details
        inquiryId: null,       // inquiry ID from prospectus app
        prospectusSlug: null   // prospectus slug
    },

    // Booking stages
    stages: {
        IDLE: 'idle',
        DETECTING_INTENT: 'detecting_intent',
        ASKING_REGISTRATION: 'asking_registration',
        VERIFYING_FAMILY: 'verifying_family',
        COLLECTING_ENQUIRY: 'collecting_enquiry',
        CHOOSING_EVENT_TYPE: 'choosing_event_type',
        SHOWING_EVENTS: 'showing_events',
        COLLECTING_BOOKING_DETAILS: 'collecting_booking_details',
        CONFIRMING_BOOKING: 'confirming_booking',
        COMPLETED: 'completed'
    },

    // Enquiry form fields to collect
    enquiryFields: [
        { key: 'parentName', question: 'What is your name?', type: 'text' },
        { key: 'firstName', question: 'And what is your daughter\'s first name?', type: 'text' },
        { key: 'familySurname', question: 'What is your family surname?', type: 'text' },
        { key: 'parentEmail', question: 'What is your email address?', type: 'email' },
        { key: 'contactNumber', question: 'And your contact number?', type: 'tel' },
        {
            key: 'ageGroup',
            question: 'What age group is your daughter in?',
            type: 'choice',
            options: [
                { value: '9-11', label: 'Ages 9-11 (Years 5-6)' },
                { value: '11-16', label: 'Ages 11-16 (Years 7-11)' },
                { value: '16-18', label: 'Ages 16-18 (Sixth Form)' }
            ]
        },
        {
            key: 'entryYear',
            question: 'When are you planning for your daughter to join us?',
            type: 'choice',
            options: [
                { value: '2025', label: 'September 2025' },
                { value: '2026', label: 'September 2026' },
                { value: '2027', label: 'September 2027' },
                { value: '2028', label: 'September 2028' },
                { value: '2029', label: 'September 2029' }
            ]
        },
        {
            key: 'hearAboutUs',
            question: 'How did you hear about More House School?',
            type: 'choice',
            options: [
                { value: 'Website', label: 'School Website' },
                { value: 'Search Engine', label: 'Search Engine' },
                { value: 'Social Media', label: 'Social Media' },
                { value: 'Word of Mouth', label: 'Word of Mouth' },
                { value: 'Current Parent', label: 'Current Parent' },
                { value: 'Open Day', label: 'Open Day/Event' },
                { value: 'Other', label: 'Other' }
            ]
        },
        {
            key: 'academicInterests',
            question: 'What are your daughter\'s academic interests? (Select all that apply)',
            type: 'multichoice',
            options: [
                { value: 'sciences', label: 'Sciences' },
                { value: 'mathematics', label: 'Mathematics' },
                { value: 'english', label: 'English & Literature' },
                { value: 'languages', label: 'Modern Languages' },
                { value: 'humanities', label: 'History & Geography' },
                { value: 'business', label: 'Business Studies' }
            ]
        },
        {
            key: 'creativeInterests',
            question: 'What about creative and performance interests?',
            type: 'multichoice',
            options: [
                { value: 'drama', label: 'Drama & Theatre' },
                { value: 'music', label: 'Music & Singing' },
                { value: 'art', label: 'Art & Design' },
                { value: 'creative_writing', label: 'Creative Writing' }
            ]
        },
        {
            key: 'cocurricularInterests',
            question: 'And co-curricular interests?',
            type: 'multichoice',
            options: [
                { value: 'sport', label: 'Sport & PE' },
                { value: 'leadership', label: 'Leadership & Student Voice' },
                { value: 'community_service', label: 'Community Service' },
                { value: 'outdoor_education', label: 'Outdoor Education' }
            ]
        },
        {
            key: 'familyPriorities',
            question: 'Finally, what matters most to your family?',
            type: 'multichoice',
            options: [
                { value: 'academic_excellence', label: 'Academic Excellence' },
                { value: 'pastoral_care', label: 'Outstanding Pastoral Care' },
                { value: 'university_preparation', label: 'University Preparation' },
                { value: 'personal_development', label: 'Personal Development' },
                { value: 'career_guidance', label: 'Career Guidance' },
                { value: 'extracurricular_opportunities', label: 'Extracurricular Opportunities' }
            ]
        }
    ],

    currentEnquiryFieldIndex: 0,

    /**
     * Initialize the booking system
     */
    init() {
        console.log('🎯 Emily Booking System initialized');
        this.session.stage = this.stages.IDLE;
    },

    /**
     * Reset the booking session
     */
    reset() {
        this.session = {
            stage: this.stages.IDLE,
            isNewFamily: null,
            verifiedFamily: null,
            enquiryData: {},
            selectedEvent: null,
            bookingData: {},
            inquiryId: null,
            prospectusSlug: null
        };
        this.currentEnquiryFieldIndex = 0;
    },

    /**
     * Detect if user message indicates booking intent
     */
    detectBookingIntent(message) {
        const lowerMessage = message.toLowerCase().trim();

        console.log(`🔍 detectBookingIntent checking: "${lowerMessage}"`);

        // First check if it's an informational query (asking ABOUT open days, not booking)
        const infoQueries = [
            'when are', 'when is', 'what are', 'what is',
            'tell me about', 'do you have', 'are there',
            'upcoming', 'next', 'dates'
        ];

        const isInfoQuery = infoQueries.some(phrase => lowerMessage.includes(phrase));

        if (isInfoQuery) {
            console.log(`ℹ️ Detected informational query - NOT triggering booking`);
            return false;
        }

        // Only check for SPECIFIC open day/tour/visit booking phrases
        // Don't intercept general "book" or "appointment" - let AI handle those intelligently
        const bookingKeywords = [
            'book open day', 'book an open day', 'book the open day',
            'book a visit', 'book a tour', 'book a private tour',
            'i want to book a visit', 'i would like to book a tour',
            'i\'d like to book an open day',
            'reserve open day', 'schedule open day', 'schedule a visit',
            'come see the school', 'come visit the school'
        ];

        // ONLY trigger if explicitly about booking school visits/tours/open days
        // Let the AI handle other "book" requests (e.g., "book a meeting with registrar")

        const matched = bookingKeywords.some(keyword => lowerMessage.includes(keyword));
        console.log(`🔍 Keyword match result: ${matched}`);
        return matched;
    },

    /**
     * Helper to show user message in chat
     */
    showUserMessage(message) {
        const history = document.getElementById('chat-history');
        if (!history) {
            console.error('❌ chat-history element not found');
            return;
        }

        // Create exchange div like the normal flow
        const exchangeDiv = document.createElement("div");
        exchangeDiv.className = "exchange";

        const userDiv = document.createElement("div");
        userDiv.className = "message user";
        const userP = document.createElement("p");
        userP.textContent = `Me: ${message}`;
        userDiv.appendChild(userP);

        exchangeDiv.appendChild(userDiv);
        history.appendChild(exchangeDiv);
        history.scrollTop = history.scrollHeight;
    },

    /**
     * Handle user message during booking flow
     */
    async handleMessage(message, appendFunction) {
        const stage = this.session.stage;

        console.log(`📍 Current stage: ${stage}`);
        console.log(`💬 User message: ${message}`);

        // Handle prospectus view button click (works in any stage)
        if (message.startsWith('view_prospectus|')) {
            const url = message.replace('view_prospectus|', '');
            console.log(`🔗 Opening prospectus URL: ${url}`);
            if (url !== 'http://localhost:3000/null' && url !== 'null') {
                window.open(url, '_blank');
            } else {
                console.error('Invalid prospectus URL');
            }
            // Don't show user message for button clicks, just return true to keep buttons
            return true;
        }

        // Handle continue to booking button
        if (message === 'continue_booking') {
            if (stage === 'WAITING_FOR_PROSPECTUS_VIEW' || stage === this.stages.SHOWING_EVENTS || stage === this.stages.CHOOSING_EVENT_TYPE) {
                appendFunction(`Now, let's get that visit booked for you...`, []);
                this.session.stage = this.stages.CHOOSING_EVENT_TYPE;
                setTimeout(() => this.askEventType(appendFunction), 500);
                return true;
            }
        }

        // Detect booking intent if idle
        if (stage === this.stages.IDLE && this.detectBookingIntent(message)) {
            // Don't show user message - user doesn't want "Me: open events" shown
            return this.startBookingFlow(appendFunction);
        }

        // If we're in a booking flow, DON'T show the user's message
        // User explicitly said: "i dont want this Me: pastoral_care"

        // Handle responses based on current stage
        switch (stage) {
            case this.stages.ASKING_REGISTRATION:
                return this.handleRegistrationResponse(message, appendFunction);

            case this.stages.VERIFYING_FAMILY:
                return this.handleVerificationInput(message, appendFunction);

            case this.stages.COLLECTING_ENQUIRY:
                return this.handleEnquiryFieldResponse(message, appendFunction);

            case this.stages.CHOOSING_EVENT_TYPE:
                return this.handleEventTypeChoice(message, appendFunction);

            case this.stages.SHOWING_EVENTS:
                return this.handleEventSelection(message, appendFunction);

            case this.stages.COLLECTING_BOOKING_DETAILS:
                return this.handleBookingDetailsResponse(message, appendFunction);

            default:
                return false; // Not handling this message
        }
    },

    /**
     * Start the booking flow
     */
    async startBookingFlow(appendFunction) {
        console.log('🎬 startBookingFlow called');
        this.session.stage = this.stages.ASKING_REGISTRATION;

        const response = "Lovely! I'd be delighted to help you book an open day. First, have you already registered or enquired with More House School before?";

        console.log('📤 Calling appendFunction with response and buttons');
        appendFunction(response, [
            { label: 'Yes, I have', value: 'yes_registered' },
            { label: 'No, I\'m new', value: 'no_new' }
        ]);

        console.log('✅ startBookingFlow completed');
        return true;
    },

    /**
     * Handle registration question response
     */
    async handleRegistrationResponse(message, appendFunction) {
        const lowerMessage = message.toLowerCase();

        if (lowerMessage.includes('yes') || lowerMessage === 'yes_registered') {
            // Existing family - verify
            this.session.isNewFamily = false;
            this.session.stage = this.stages.VERIFYING_FAMILY;

            appendFunction("Brilliant! Let me quickly verify your details. What's your email address?", []);
            return true;
        } else if (lowerMessage.includes('no') || lowerMessage === 'no_new') {
            // New family - collect enquiry
            this.session.isNewFamily = true;
            this.session.stage = this.stages.COLLECTING_ENQUIRY;
            this.currentEnquiryFieldIndex = 0;

            const welcomeMessage = "Welcome to More House! Please complete this form to register. You'll also receive a personalised prospectus tailored to your daughter's interests and your family's priorities.";

            appendFunction(welcomeMessage, []);

            // Show the form immediately
            setTimeout(() => this.askNextEnquiryField(appendFunction), 500);
            return true;
        }

        return false;
    },

    /**
     * Handle verification input (email)
     */
    async handleVerificationInput(message, appendFunction) {
        const email = message.trim();

        // Basic email validation
        if (!email.includes('@')) {
            appendFunction("That doesn't look like a valid email address. Could you please try again?", []);
            return true;
        }

        // Show loading
        appendFunction("Just a moment, let me check our system...", []);

        try {
            const response = await fetch('/api/emily/verify-family', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email })
            });

            const data = await response.json();

            if (data.found && data.parent) {
                // Family found!
                this.session.verifiedFamily = data.parent;
                this.session.inquiryId = data.parent.inquiry_id;
                this.session.stage = this.stages.CHOOSING_EVENT_TYPE;

                const parentName = data.parent.name || 'there';
                appendFunction(`Perfect! I found your details. Welcome back, ${parentName}!`, []);

                // Ask what type of visit they want
                setTimeout(() => this.askEventType(appendFunction), 500);
                return true;
            } else {
                // Not found - seamlessly move to new registration
                this.session.isNewFamily = true;
                this.session.stage = this.stages.COLLECTING_ENQUIRY;
                this.currentEnquiryFieldIndex = 0;

                appendFunction(
                    "I couldn't find your details in our system, but no problem! Let me take you through our quick registration form. You'll also receive a personalised prospectus tailored to your daughter's interests and your family's priorities.",
                    []
                );

                // Show the form immediately
                setTimeout(() => this.askNextEnquiryField(appendFunction), 500);
                return true;
            }
        } catch (error) {
            console.error('Verification error:', error);
            appendFunction("Sorry, I'm having trouble checking our system right now. Would you like to continue as a new registration instead?", [
                { label: 'Yes, continue', value: 'no_new' },
                { label: 'Try again later', value: 'cancel' }
            ]);
            return true;
        }
    },

    /**
     * Display the complete enquiry form with all fields visible
     */
    askNextEnquiryField(appendFunction) {
        // Display the complete form in the chat
        this.showEnquiryForm(appendFunction);
    },

    /**
     * Show the complete enquiry form (form-based UI like inquiry-form.html)
     */
    showEnquiryForm(appendFunction) {
        const formHTML = `
            <div class="emily-enquiry-form" style="background: white; padding: 20px; border-radius: 10px; margin: 10px 0;">
                <div class="form-section">
                    <label style="display: block; font-weight: bold; color: #1a2b5c; margin: 15px 0 8px;">Parent/Guardian Name <span style="color: #FF6B9D;">*</span></label>
                    <input type="text" id="emily-parentName" required style="width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 8px; font-size: 14px;">

                    <label style="display: block; font-weight: bold; color: #1a2b5c; margin: 15px 0 8px;">Daughter's First Name <span style="color: #FF6B9D;">*</span></label>
                    <input type="text" id="emily-firstName" required style="width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 8px; font-size: 14px;">

                    <label style="display: block; font-weight: bold; color: #1a2b5c; margin: 15px 0 8px;">Family Surname <span style="color: #FF6B9D;">*</span></label>
                    <input type="text" id="emily-familySurname" required style="width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 8px; font-size: 14px;">

                    <label style="display: block; font-weight: bold; color: #1a2b5c; margin: 15px 0 8px;">Email Address <span style="color: #FF6B9D;">*</span></label>
                    <input type="email" id="emily-parentEmail" required style="width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 8px; font-size: 14px;">

                    <label style="display: block; font-weight: bold; color: #1a2b5c; margin: 15px 0 8px;">Contact Number <span style="color: #FF6B9D;">*</span></label>
                    <input type="tel" id="emily-contactNumber" required style="width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 8px; font-size: 14px;">

                    <label style="display: block; font-weight: bold; color: #1a2b5c; margin: 15px 0 8px;">Age Group <span style="color: #FF6B9D;">*</span></label>
                    <select id="emily-ageGroup" required style="width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 8px; font-size: 14px;">
                        <option value="">Select age group...</option>
                        <option value="9-11">Ages 9-11 (Years 5-6)</option>
                        <option value="11-16">Ages 11-16 (Years 7-11)</option>
                        <option value="16-18">Ages 16-18 (Sixth Form)</option>
                    </select>

                    <label style="display: block; font-weight: bold; color: #1a2b5c; margin: 15px 0 8px;">Entry Year <span style="color: #FF6B9D;">*</span></label>
                    <select id="emily-entryYear" required style="width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 8px; font-size: 14px;">
                        <option value="">Select entry year...</option>
                        <option value="2025">September 2025</option>
                        <option value="2026">September 2026</option>
                        <option value="2027">September 2027</option>
                        <option value="2028">September 2028</option>
                        <option value="2029">September 2029</option>
                    </select>

                    <label style="display: block; font-weight: bold; color: #1a2b5c; margin: 15px 0 8px;">How did you hear about More House? <span style="color: #FF6B9D;">*</span></label>
                    <select id="emily-hearAboutUs" required style="width: 100%; padding: 10px; border: 2px solid #ddd; border-radius: 8px; font-size: 14px;">
                        <option value="">Please select...</option>
                        <option value="Website">School Website</option>
                        <option value="Search Engine">Search Engine</option>
                        <option value="Social Media">Social Media</option>
                        <option value="Word of Mouth">Word of Mouth</option>
                        <option value="Current Parent">Current Parent</option>
                        <option value="Open Day">Open Day/Event</option>
                        <option value="Other">Other</option>
                    </select>

                    <label style="display: block; font-weight: bold; color: #1a2b5c; margin: 20px 0 10px; font-size: 1.1em; border-bottom: 2px solid #FFB3C1; padding-bottom: 5px;">Academic Interests</label>
                    <div class="emily-checkbox-group" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; background: #FFE5EC; padding: 15px; border-radius: 10px; border: 2px solid #FFB3C1;">
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-sciences" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-sciences" style="cursor: pointer; margin: 0; font-size: 0.9em;">Sciences</label>
                        </div>
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-mathematics" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-mathematics" style="cursor: pointer; margin: 0; font-size: 0.9em;">Mathematics</label>
                        </div>
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-english" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-english" style="cursor: pointer; margin: 0; font-size: 0.9em;">English & Literature</label>
                        </div>
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-languages" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-languages" style="cursor: pointer; margin: 0; font-size: 0.9em;">Modern Languages</label>
                        </div>
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-humanities" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-humanities" style="cursor: pointer; margin: 0; font-size: 0.9em;">History & Geography</label>
                        </div>
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-business" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-business" style="cursor: pointer; margin: 0; font-size: 0.9em;">Business Studies</label>
                        </div>
                    </div>

                    <label style="display: block; font-weight: bold; color: #1a2b5c; margin: 20px 0 10px; font-size: 1.1em; border-bottom: 2px solid #FFB3C1; padding-bottom: 5px;">Creative & Performance Interests</label>
                    <div class="emily-checkbox-group" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; background: #FFE5EC; padding: 15px; border-radius: 10px; border: 2px solid #FFB3C1;">
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-drama" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-drama" style="cursor: pointer; margin: 0; font-size: 0.9em;">Drama & Theatre</label>
                        </div>
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-music" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-music" style="cursor: pointer; margin: 0; font-size: 0.9em;">Music & Singing</label>
                        </div>
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-art" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-art" style="cursor: pointer; margin: 0; font-size: 0.9em;">Art & Design</label>
                        </div>
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-creative_writing" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-creative_writing" style="cursor: pointer; margin: 0; font-size: 0.9em;">Creative Writing</label>
                        </div>
                    </div>

                    <label style="display: block; font-weight: bold; color: #1a2b5c; margin: 20px 0 10px; font-size: 1.1em; border-bottom: 2px solid #FFB3C1; padding-bottom: 5px;">Co-curricular Interests</label>
                    <div class="emily-checkbox-group" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; background: #FFE5EC; padding: 15px; border-radius: 10px; border: 2px solid #FFB3C1;">
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-sport" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-sport" style="cursor: pointer; margin: 0; font-size: 0.9em;">Sport & PE</label>
                        </div>
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-leadership" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-leadership" style="cursor: pointer; margin: 0; font-size: 0.9em;">Leadership & Student Voice</label>
                        </div>
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-community_service" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-community_service" style="cursor: pointer; margin: 0; font-size: 0.9em;">Community Service</label>
                        </div>
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-outdoor_education" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-outdoor_education" style="cursor: pointer; margin: 0; font-size: 0.9em;">Outdoor Education</label>
                        </div>
                    </div>

                    <label style="display: block; font-weight: bold; color: #1a2b5c; margin: 20px 0 10px; font-size: 1.1em; border-bottom: 2px solid #FFB3C1; padding-bottom: 5px;">What matters most to your family?</label>
                    <div class="emily-checkbox-group" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; background: #FFE5EC; padding: 15px; border-radius: 10px; border: 2px solid #FFB3C1;">
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-academic_excellence" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-academic_excellence" style="cursor: pointer; margin: 0; font-size: 0.9em;">Academic Excellence</label>
                        </div>
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-pastoral_care" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-pastoral_care" style="cursor: pointer; margin: 0; font-size: 0.9em;">Pastoral Care</label>
                        </div>
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-university_preparation" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-university_preparation" style="cursor: pointer; margin: 0; font-size: 0.9em;">University Preparation</label>
                        </div>
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-personal_development" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-personal_development" style="cursor: pointer; margin: 0; font-size: 0.9em;">Personal Development</label>
                        </div>
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-career_guidance" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-career_guidance" style="cursor: pointer; margin: 0; font-size: 0.9em;">Career Guidance</label>
                        </div>
                        <div class="emily-checkbox-item" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 8px; border: 2px solid #ddd; cursor: pointer;">
                            <input type="checkbox" id="emily-extracurricular_opportunities" style="cursor: pointer; width: 16px; height: 16px; accent-color: #FF6B9D;">
                            <label for="emily-extracurricular_opportunities" style="cursor: pointer; margin: 0; font-size: 0.9em;">Extracurricular Opportunities</label>
                        </div>
                    </div>

                    <button id="emily-submit-form" style="background: linear-gradient(135deg, #FF6B9D, #1a2b5c); color: white; padding: 15px 40px; border: none; border-radius: 50px; font-size: 1.1em; cursor: pointer; width: 100%; margin-top: 25px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px;">
                        Submit & Create Prospectus
                    </button>
                </div>
            </div>
        `;

        // Add form to chat
        const history = document.getElementById('chat-history');
        if (!history) return;

        const bubble = document.createElement("div");
        bubble.className = "message bot";
        bubble.innerHTML = formHTML;
        history.appendChild(bubble);

        // Scroll to the top of the form, not the bottom
        bubble.scrollIntoView({ behavior: 'smooth', block: 'start' });

        // Add event listeners for checkboxes (click anywhere on item to toggle)
        setTimeout(() => {
            document.querySelectorAll('.emily-checkbox-item').forEach(item => {
                item.addEventListener('click', (e) => {
                    if (e.target.type !== 'checkbox') {
                        const checkbox = item.querySelector('input[type="checkbox"]');
                        if (checkbox) {
                            checkbox.checked = !checkbox.checked;
                        }
                    }
                });
            });

            // Submit button handler
            const submitBtn = document.getElementById('emily-submit-form');
            if (submitBtn) {
                submitBtn.addEventListener('click', () => this.collectFormDataAndSubmit(appendFunction));
            }
        }, 100);
    },

    /**
     * Collect all form data and submit
     */
    collectFormDataAndSubmit(appendFunction) {
        // Collect all form values
        this.session.enquiryData = {
            parentName: document.getElementById('emily-parentName')?.value?.trim() || '',
            firstName: document.getElementById('emily-firstName')?.value?.trim() || '',
            familySurname: document.getElementById('emily-familySurname')?.value?.trim() || '',
            parentEmail: document.getElementById('emily-parentEmail')?.value?.trim() || '',
            contactNumber: document.getElementById('emily-contactNumber')?.value?.trim() || '',
            ageGroup: document.getElementById('emily-ageGroup')?.value || '',
            entryYear: document.getElementById('emily-entryYear')?.value || '',
            hearAboutUs: document.getElementById('emily-hearAboutUs')?.value || '',
            academicInterests: [],
            creativeInterests: [],
            cocurricularInterests: [],
            familyPriorities: []
        };

        // Validate required fields
        if (!this.session.enquiryData.parentName || !this.session.enquiryData.firstName ||
            !this.session.enquiryData.familySurname || !this.session.enquiryData.parentEmail ||
            !this.session.enquiryData.contactNumber || !this.session.enquiryData.ageGroup ||
            !this.session.enquiryData.entryYear || !this.session.enquiryData.hearAboutUs) {
            appendFunction("Please fill in all required fields marked with *", []);
            return;
        }

        // Validate email
        if (!this.session.enquiryData.parentEmail.includes('@')) {
            appendFunction("Please enter a valid email address", []);
            return;
        }

        // Collect checkbox selections
        if (document.getElementById('emily-sciences')?.checked) this.session.enquiryData.academicInterests.push('sciences');
        if (document.getElementById('emily-mathematics')?.checked) this.session.enquiryData.academicInterests.push('mathematics');
        if (document.getElementById('emily-english')?.checked) this.session.enquiryData.academicInterests.push('english');
        if (document.getElementById('emily-languages')?.checked) this.session.enquiryData.academicInterests.push('languages');
        if (document.getElementById('emily-humanities')?.checked) this.session.enquiryData.academicInterests.push('humanities');
        if (document.getElementById('emily-business')?.checked) this.session.enquiryData.academicInterests.push('business');

        if (document.getElementById('emily-drama')?.checked) this.session.enquiryData.creativeInterests.push('drama');
        if (document.getElementById('emily-music')?.checked) this.session.enquiryData.creativeInterests.push('music');
        if (document.getElementById('emily-art')?.checked) this.session.enquiryData.creativeInterests.push('art');
        if (document.getElementById('emily-creative_writing')?.checked) this.session.enquiryData.creativeInterests.push('creative_writing');

        if (document.getElementById('emily-sport')?.checked) this.session.enquiryData.cocurricularInterests.push('sport');
        if (document.getElementById('emily-leadership')?.checked) this.session.enquiryData.cocurricularInterests.push('leadership');
        if (document.getElementById('emily-community_service')?.checked) this.session.enquiryData.cocurricularInterests.push('community_service');
        if (document.getElementById('emily-outdoor_education')?.checked) this.session.enquiryData.cocurricularInterests.push('outdoor_education');

        if (document.getElementById('emily-academic_excellence')?.checked) this.session.enquiryData.familyPriorities.push('academic_excellence');
        if (document.getElementById('emily-pastoral_care')?.checked) this.session.enquiryData.familyPriorities.push('pastoral_care');
        if (document.getElementById('emily-university_preparation')?.checked) this.session.enquiryData.familyPriorities.push('university_preparation');
        if (document.getElementById('emily-personal_development')?.checked) this.session.enquiryData.familyPriorities.push('personal_development');
        if (document.getElementById('emily-career_guidance')?.checked) this.session.enquiryData.familyPriorities.push('career_guidance');
        if (document.getElementById('emily-extracurricular_opportunities')?.checked) this.session.enquiryData.familyPriorities.push('extracurricular_opportunities');

        // Submit the enquiry
        this.submitEnquiry(appendFunction);
    },

    /**
     * Handle response to enquiry field (now unused but kept for compatibility)
     */
    async handleEnquiryFieldResponse(message, appendFunction) {
        // This is now handled by the form submission
        return false;
    },

    /**
     * Submit enquiry to prospectus app
     */
    async submitEnquiry(appendFunction) {
        console.log('📤 submitEnquiry called');
        appendFunction("Brilliant! I'm just submitting your details and creating your personalised prospectus...", []);

        try {
            // Format data for prospectus app
            console.log('🔧 Formatting enquiry data...');
            const enquiryPayload = this.formatEnquiryForProspectusApp();
            console.log('📦 Enquiry payload:', JSON.stringify(enquiryPayload, null, 2));

            console.log('🌐 Sending POST to /api/emily/submit-enquiry');
            const response = await fetch('/api/emily/submit-enquiry', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(enquiryPayload)
            });

            console.log('📨 Response status:', response.status);
            const data = await response.json();
            console.log('📦 Response data:', data);

            if (data.success) {
                console.log('✅ Enquiry submitted successfully');
                console.log('Response data:', data);
                this.session.inquiryId = data.inquiryId;
                this.session.prospectusSlug = data.slug;

                // Try to open prospectus in new tab
                if (data.prospectusUrl) {
                    console.log('🔗 Attempting to open prospectus:', data.prospectusUrl);
                    const newWindow = window.open(data.prospectusUrl, '_blank');

                    if (!newWindow || newWindow.closed || typeof newWindow.closed === 'undefined') {
                        console.warn('⚠️ Popup was blocked by browser');
                        // Popup was blocked - provide a clickable link instead
                        appendFunction(
                            `Perfect! Your personalised prospectus for ${this.session.enquiryData.firstName} has been created and emailed to you.\n\nYou can also view it here:`,
                            [
                                { label: 'View Prospectus', value: `open_prospectus_${data.prospectusUrl}` }
                            ]
                        );

                        // Move to choosing event type
                        this.session.stage = this.stages.CHOOSING_EVENT_TYPE;
                        setTimeout(() => this.askEventType(appendFunction), 2000);
                        return true;
                    } else {
                        console.log('✅ Prospectus opened successfully');
                    }
                }

                // Success message with prospectus link button
                const parentName = this.session.enquiryData.firstName || 'your daughter';

                // Store the prospectus URL for later
                this.session.prospectusUrl = data.prospectusUrl;

                appendFunction(
                    `Perfect! Your personalised prospectus for ${parentName} has been created and emailed to you.\n\nClick below to view it, then we'll continue with booking your tour:`,
                    [
                        { label: 'View Prospectus', value: `view_prospectus|${data.prospectusUrl}` },
                        { label: 'Continue to Booking', value: 'continue_booking' }
                    ]
                );

                // Move to a waiting state
                this.session.stage = 'WAITING_FOR_PROSPECTUS_VIEW';

                return true;
            } else {
                console.error('❌ Submission failed:', data.error);
                throw new Error(data.error || 'Submission failed');
            }
        } catch (error) {
            console.error('❌ Enquiry submission error:', error);
            console.error('Error details:', {
                message: error.message,
                stack: error.stack,
                enquiryData: this.session.enquiryData
            });
            appendFunction(
                "I'm terribly sorry, but I'm having trouble submitting your details right now. Would you like to try again, or shall I connect you with our admissions team directly?",
                [
                    { label: 'Try again', value: 'retry_enquiry' },
                    { label: 'Speak to admissions', value: 'contact_admissions' }
                ]
            );
            return true;
        }
    },

    /**
     * Format enquiry data for prospectus app webhook
     */
    formatEnquiryForProspectusApp() {
        const data = this.session.enquiryData;

        // Convert multi-select arrays to boolean fields
        const formatMultiChoice = (key) => {
            const arr = data[key] || [];
            const result = {};
            arr.forEach(value => {
                result[value] = true;
            });
            return result;
        };

        return {
            parentName: data.parentName,
            firstName: data.firstName,
            familySurname: data.familySurname,
            parentEmail: data.parentEmail,
            contactNumber: data.contactNumber,
            ageGroup: data.ageGroup,
            entryYear: data.entryYear,
            hearAboutUs: data.hearAboutUs,
            // Academic interests
            ...formatMultiChoice('academicInterests'),
            // Creative interests
            ...formatMultiChoice('creativeInterests'),
            // Co-curricular interests
            ...formatMultiChoice('cocurricularInterests'),
            // Family priorities
            ...formatMultiChoice('familyPriorities')
        };
    },

    /**
     * Ask user to choose between Open Day and Private Tour
     */
    askEventType(appendFunction) {
        appendFunction(
            "What type of visit would you like to book?",
            [
                { label: 'Open Day', value: 'open_day' },
                { label: 'Private Tour', value: 'private_tour' }
            ]
        );
    },

    /**
     * Handle event type choice
     */
    async handleEventTypeChoice(message, appendFunction) {
        if (message === 'open_day') {
            this.session.stage = this.stages.SHOWING_EVENTS;
            await this.showAvailableEvents(appendFunction);
            return true;
        } else if (message === 'private_tour') {
            // Set booking type to private tour
            this.session.bookingType = 'private_tour';
            this.session.stage = this.stages.COLLECTING_BOOKING_DETAILS;

            appendFunction(
                "Perfect! I'll help you request a private tour. How many people will be attending?",
                [
                    { label: '1 person', value: '1' },
                    { label: '2 people', value: '2' },
                    { label: '3 people', value: '3' },
                    { label: '4 people', value: '4' },
                    { label: '5+ people', value: '5' }
                ]
            );
            return true;
        }
        return false;
    },

    /**
     * Show available open day events
     */
    async showAvailableEvents(appendFunction) {
        appendFunction("Let me check what open days we have coming up...", []);

        try {
            const response = await fetch('/api/emily/get-events');
            const data = await response.json();

            const events = (data.events || []).filter(e => {
                const eventDate = new Date(e.event_date);
                return eventDate >= new Date();
            });

            if (events.length === 0) {
                appendFunction(
                    "I'm sorry, we don't have any open days scheduled at the moment. Would you like to request a private tour instead?",
                    [
                        { label: 'Yes, private tour', value: 'private_tour' },
                        { label: 'I\'ll check back later', value: 'cancel' }
                    ]
                );
                return;
            }

            // Create a properly formatted message with HTML-style line breaks
            let eventsList = events.map((event, index) => {
                const date = new Date(event.event_date);
                const formattedDate = date.toLocaleDateString('en-GB', {
                    weekday: 'long',
                    day: 'numeric',
                    month: 'long',
                    year: 'numeric'
                });
                const spotsLeft = event.max_capacity - event.current_bookings;

                return `${event.title}\nDate: ${formattedDate}\nTime: ${event.start_time} - ${event.end_time}\nAvailability: ${spotsLeft} places remaining`;
            }).join('\n\n');

            const eventMessage = `Here are our upcoming open days:\n\n${eventsList}\n\nWhich one would you like to attend?`;

            // Create buttons for each event with full date
            const eventButtons = events.map(event => {
                const date = new Date(event.event_date);
                const label = date.toLocaleDateString('en-GB', {
                    day: 'numeric',
                    month: 'short',
                    year: 'numeric'
                });
                return {
                    label: label,
                    value: `event_${event.id}`
                };
            });

            appendFunction(eventMessage, eventButtons);

            this.session.availableEvents = events;

        } catch (error) {
            console.error('Error fetching events:', error);
            appendFunction(
                "I'm having trouble loading our open days right now. Would you like to request a private tour instead, or try again?",
                [
                    { label: 'Private tour', value: 'private_tour' },
                    { label: 'Try again', value: 'retry_events' }
                ]
            );
        }
    },

    /**
     * Handle event selection
     */
    async handleEventSelection(message, appendFunction) {
        if (message.startsWith('event_')) {
            const eventId = parseInt(message.replace('event_', ''));
            const event = this.session.availableEvents?.find(e => e.id === eventId);

            if (event) {
                this.session.selectedEvent = event;
                this.session.stage = this.stages.COLLECTING_BOOKING_DETAILS;

                const date = new Date(event.event_date).toLocaleDateString('en-GB', {
                    weekday: 'long',
                    month: 'long',
                    day: 'numeric'
                });

                appendFunction(
                    `Wonderful choice! I've selected the ${event.title} on ${date}.\n\nHow many people will be attending?`,
                    [
                        { label: '1 person', value: '1' },
                        { label: '2 people', value: '2' },
                        { label: '3 people', value: '3' },
                        { label: '4 people', value: '4' }
                    ]
                );

                return true;
            }
        }

        return false;
    },

    /**
     * Handle booking details responses
     */
    async handleBookingDetailsResponse(message, appendFunction) {
        const isPrivateTour = this.session.bookingType === 'private_tour';

        if (!this.session.bookingData.num_attendees) {
            // First response: number of attendees
            this.session.bookingData.num_attendees = parseInt(message);

            if (isPrivateTour) {
                appendFunction(
                    "Great! Please select your preferred date for the private tour:",
                    [{ type: 'date', label: 'Select Date' }]
                );
            } else {
                appendFunction(
                    "Perfect! And finally, do you have any dietary requirements or special needs we should know about? (Or just say 'none')",
                    []
                );
            }
            return true;
        } else if (isPrivateTour && !this.session.bookingData.preferred_date) {
            // Second response for private tour: preferred date
            this.session.bookingData.preferred_date = message;

            appendFunction(
                "Thanks! Now please select your preferred time:",
                [{ type: 'time', label: 'Select Time' }]
            );
            return true;
        } else if (isPrivateTour && !this.session.bookingData.preferred_time) {
            // Third response for private tour: preferred time
            this.session.bookingData.preferred_time = message;

            appendFunction(
                "Perfect! Finally, do you have any dietary requirements or special needs we should know about? (Or just say 'none')",
                []
            );
            return true;
        } else {
            // Final response: special requirements
            this.session.bookingData.special_requirements = message === 'none' ? '' : message;

            // Now submit the booking
            return this.submitBooking(appendFunction);
        }
    },

    /**
     * Submit the booking
     */
    async submitBooking(appendFunction) {
        const isPrivateTour = this.session.bookingType === 'private_tour';
        appendFunction(isPrivateTour ? "Excellent! Let me submit your private tour request..." : "Excellent! Let me confirm your booking...", []);

        try {
            // Build booking payload
            const bookingPayload = {
                school_id: 2, // More House
                booking_type: isPrivateTour ? 'private_tour' : 'open_day',
                inquiry_id: this.session.inquiryId,
                num_attendees: this.session.bookingData.num_attendees,
                special_requirements: this.session.bookingData.special_requirements
            };

            // Only add event_id for open days (private tours don't have a pre-selected event)
            if (!isPrivateTour && this.session.selectedEvent) {
                bookingPayload.event_id = this.session.selectedEvent.id;
            }

            // Add preferred date/time for private tours
            if (isPrivateTour) {
                bookingPayload.preferred_date = this.session.bookingData.preferred_date || '';
                bookingPayload.preferred_time = this.session.bookingData.preferred_time || '';
            }

            // Add parent/student info based on whether they're verified or new
            if (this.session.verifiedFamily) {
                const parent = this.session.verifiedFamily;
                const nameParts = (parent.name || '').split(' ');
                bookingPayload.parent_first_name = nameParts[0] || '';
                bookingPayload.parent_last_name = nameParts.slice(1).join(' ') || '';
                bookingPayload.email = parent.email;
                bookingPayload.phone = parent.contact_number || '';
                bookingPayload.student_first_name = parent.first_name || '';
                bookingPayload.student_last_name = parent.family_surname || '';
                bookingPayload.age_group = parent.age_group || '';
            } else {
                const data = this.session.enquiryData;
                const parentParts = (data.parentName || '').split(' ');
                bookingPayload.parent_first_name = parentParts[0] || '';
                bookingPayload.parent_last_name = parentParts.slice(1).join(' ') || '';
                bookingPayload.email = data.parentEmail;
                bookingPayload.phone = data.contactNumber;
                bookingPayload.student_first_name = data.firstName;
                bookingPayload.student_last_name = data.familySurname;
                bookingPayload.age_group = data.ageGroup || '';
            }

            const response = await fetch('/api/emily/create-booking', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(bookingPayload)
            });

            const data = await response.json();

            if (response.ok && data.booking) {
                // Success!
                this.session.stage = this.stages.COMPLETED;

                // Get parent's first name
                const parentFirstName = this.session.enquiryData?.parentName?.split(' ')[0] ||
                                       this.session.verifiedFamily?.name?.split(' ')[0] || '';

                if (isPrivateTour) {
                    appendFunction(
                        `All done! Your private tour request has been submitted.\n\nOur admissions team will check availability for your preferred date and time. If your requested slot is available, you'll receive a confirmation email shortly. If not, we'll offer alternative dates and times that work for you.\n\n${parentFirstName}, is there anything else I can help you with? Anything you'd like to know about the school?`,
                        []
                    );
                } else {
                    const event = this.session.selectedEvent;
                    const date = new Date(event.event_date).toLocaleDateString('en-GB', {
                        weekday: 'long',
                        month: 'long',
                        day: 'numeric'
                    });

                    appendFunction(
                        `All done! Your booking is confirmed for ${event.title} on ${date} at ${event.start_time}.\n\nYou'll receive a confirmation email shortly with all the details. We look forward to welcoming you to More House School!\n\n${parentFirstName}, is there anything else I can help you with? Anything you'd like to know about the school?`,
                        []
                    );
                }

                // Trigger voice Emily callback if set
                if (typeof this.onBookingComplete === 'function') {
                    console.log('📞 Calling onBookingComplete callback for voice resumption');
                    setTimeout(() => {
                        this.onBookingComplete();
                    }, 1000);
                }

                // Don't reset session immediately - let them ask more questions
                // setTimeout(() => this.reset(), 5000);

                return true;
            } else {
                throw new Error(data.error || 'Booking failed');
            }
        } catch (error) {
            console.error('Booking submission error:', error);
            appendFunction(
                "I'm terribly sorry, but I encountered an issue while confirming your booking. Please contact our admissions team directly at office@morehousemail.org.uk or call 020 7235 2855.",
                []
            );
            return true;
        }
    }
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    EmilyBooking.init();
});

// Export for use in other scripts
window.EmilyBooking = EmilyBooking;
