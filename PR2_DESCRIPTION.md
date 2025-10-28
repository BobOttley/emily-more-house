# Pull Request #2: Complete Email Fix - Frontend & Voice Support

## Summary

This PR contains the **2 missing commits** that were pushed AFTER PR #1 was merged. These are CRITICAL for email functionality to work.

**Without these commits, email sending will NOT work!**

### What Was Missing from PR #1:

PR #1 only included the backend SMTP implementation and conversation history. But the **frontend was still calling the old endpoint** and **voice had no email tool**.

### These 2 Commits Fix That:

#### Commit 1: Fix frontend to use /ask-with-tools endpoint
- Changed `static/script.js` from `/ask` to `/ask-with-tools`
- Added session_id tracking for conversation history
- **Without this: Text chat won't ask for email/name/phone**

#### Commit 2: Add email sending functionality to voice/realtime sessions
- Added `send_enquiry_email` tool to voice session
- Created `/realtime/tool/send_enquiry_email` endpoint
- Updated voice instructions to collect contact details
- **Without this: Voice chat won't ask for email/name/phone**

### Files Changed
- `static/script.js` - Frontend endpoint fix
- `app.py` - Voice email tool and endpoint

### Testing Checklist

After merging:
- [ ] TEXT: Type "Can I book a tour?" - Emily should ask for name/email/phone
- [ ] VOICE: Say "Can I book a tour?" - Emily should ask for name/email/phone
- [ ] Verify emails arrive at ADMISSIONS_EMAIL address

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
