# Pull Request: Fix email sending - SMTP implementation & conversation flow

## Summary

This PR fixes the broken email sending functionality in the Emily chatbot. Previously, emails were not being sent because the system required Gmail OAuth authentication that never happened. Additionally, Emily wasn't asking users for their contact details before attempting to send emails.

### Changes Made

1. **SMTP Email Implementation**
   - Replaced Gmail OAuth API with SMTP (no authentication required from users)
   - Added `send_email_via_smtp()` function for reliable email sending
   - Works with Gmail App Passwords, Office365, or any SMTP provider
   - Kept Gmail API code as legacy backup method

2. **Conversation History & Contact Collection**
   - Added conversation history support to `/ask-with-tools` endpoint
   - Emily now asks for contact details before sending emails (name, email, phone)
   - Maintains conversation context across multiple messages
   - Added `parent_email` and `parent_phone` fields to `ConversationTracker`

3. **Configuration & Documentation**
   - Created `.env.example` with all required configuration
   - Created `SMTP_SETUP.md` with detailed setup instructions
   - Added clear error messages for missing SMTP configuration

### How It Works Now

**Example Conversation:**
```
User: "I'd like to book a tour"
Emily: "I'd be delighted to arrange that for you! May I have your name,
       email address, and phone number so I can send this enquiry to
       our admissions team?"
User: "John Smith, john@example.com, 07700900000"
Emily: [sends email via SMTP and confirms]
```

### Files Changed
- `app.py` - SMTP implementation, conversation history, email flow
- `.env.example` - Configuration template
- `SMTP_SETUP.md` - Setup documentation

### Commits Included
1. Fix email sending by implementing SMTP (no OAuth required)
2. Add conversation history support for email collection flow

### Setup Required After Merge

1. Create Gmail App Password: https://myaccount.google.com/apppasswords
2. Add to `.env`:
   ```bash
   SMTP_USER=your-school-email@gmail.com
   SMTP_PASSWORD=your-16-char-app-password
   ADMISSIONS_EMAIL=office@morehousemail.org.uk
   ```
3. Restart the server

### Testing Checklist

- [ ] Ask Emily: "I'd like to book a tour"
- [ ] Verify she asks for your contact details
- [ ] Provide: name, email, phone
- [ ] Check that email is sent to admissions successfully
- [ ] Verify email arrives at ADMISSIONS_EMAIL address

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
