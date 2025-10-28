# SMTP Email Setup Guide

The Emily chatbot now uses SMTP to send emails to admissions. This is more reliable than OAuth and works automatically without requiring user authentication.

## How Email Sending Works

When a parent asks to book a tour or contact admissions:

1. **Emily asks for their details** - She'll politely request:
   - Full name
   - Email address
   - Phone number

2. **Parent provides information** - This can happen in one message or across multiple messages:
   - "My name is John Smith, email john@example.com, phone 07700900000"
   - OR multiple messages in a conversation

3. **Emily sends the email** - Once she has all the required information, she automatically sends an email to admissions with the parent's enquiry

4. **Confirmation** - Emily confirms the email was sent successfully

**Important:** The frontend must send the same `session_id` with each request to maintain conversation history.

## Quick Setup (Gmail)

### 1. Enable 2-Factor Authentication on Gmail
1. Go to https://myaccount.google.com/security
2. Enable "2-Step Verification"

### 2. Create an App Password
1. Go to https://myaccount.google.com/apppasswords
2. Select "Mail" and "Other (Custom name)"
3. Enter "Emily Chatbot" as the name
4. Click "Generate"
5. **Copy the 16-character password** (e.g., `abcd efgh ijkl mnop`)

### 3. Configure Environment Variables
Add these to your `.env` file:

```bash
# SMTP Email Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-school-email@gmail.com
SMTP_PASSWORD=abcdefghijklmnop  # 16-character app password (no spaces)
SMTP_FROM_NAME=Emily - More House School
ADMISSIONS_EMAIL=office@morehousemail.org.uk
```

### 4. Restart the Server
```bash
python app.py
```

You should see:
```
✅ SMTP email configured
```

## Testing

### Test via cURL:
```bash
curl -X POST http://localhost:5000/ask-with-tools \
  -H "Content-Type: application/json" \
  -d '{
    "question": "I would like to book a tour. My name is John Smith, email john@example.com, phone 07700900000",
    "language": "en"
  }'
```

## Troubleshooting

### Error: "SMTP not configured"
- Check that `SMTP_USER` and `SMTP_PASSWORD` are set in `.env`
- Restart the Flask server

### Error: "SMTP authentication failed"
- Double-check the app password (no spaces, 16 characters)
- Ensure 2FA is enabled on the Gmail account
- Try regenerating the app password

### Error: "SMTP connection timeout"
- Check your firewall allows port 587 (SMTP with STARTTLS)
- Try port 465 with SSL: `SMTP_PORT=465` and update code to use `SMTP_SSL`

### Emails not arriving?
- Check spam folder
- Verify `ADMISSIONS_EMAIL` is correct in `.env`
- Check server logs for error messages

## Using Other Email Services

### Microsoft 365 / Outlook
```bash
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USER=your-email@yourschool.org.uk
SMTP_PASSWORD=your-password
```

### SendGrid (Production Recommended)
```bash
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=your-sendgrid-api-key
```

## Security Notes

- ⚠️ **Never commit your `.env` file to Git**
- Use environment variables or secret managers in production
- Rotate app passwords periodically
- Use SendGrid or similar service for production (better deliverability)
