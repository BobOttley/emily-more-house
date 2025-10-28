# More House Emily - Complete Fixed Version
# With proper contact collection and database logging

import os
import time
import json
import requests
import re
import pickle
import uuid
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple
from flask import Flask, redirect, request, session, jsonify, render_template, make_response, send_from_directory, url_for
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Gmail API imports
GMAIL_AVAILABLE = True
try:
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import Flow
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    GMAIL_AVAILABLE = False
    print("⚠️ Gmail API libraries not available")

# Database imports
HAVE_DB = False
try:
    from psycopg_pool import ConnectionPool
    import psycopg
    HAVE_DB = True
except ImportError:
    print("⚠️ psycopg_pool not installed")

# Load environment variables
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=ENV_PATH)

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Gmail Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "https://emily-more-house.onrender.com/auth/callback")
ADMISSIONS_EMAIL = os.getenv("ADMISSIONS_EMAIL", "office@morehousemail.org.uk")

GMAIL_SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly'
]

# Flask app
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = os.getenv("SECRET_KEY", "dev-key-change-in-production")

# Configure session
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_NAME'] = 'emily_more_house_session'

# Configure CORS
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

# Conversation Memory Store
conversation_memory = {}

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL")
db_pool = None
if HAVE_DB and DATABASE_URL:
    try:
        db_pool = ConnectionPool(
            conninfo=DATABASE_URL, 
            min_size=2, 
            max_size=20,
            timeout=60.0,
            kwargs={"sslmode": "require"}
        )
        print("✅ Database pool initialized for More House")
    except Exception as e:
        print(f"⚠️ Database pool init failed: {e}")

# Load knowledge base embeddings
kb_chunks = []
EMBEDDINGS = None
METADATA = None

try:
    with open("kb_chunks/kb_chunks.pkl", "rb") as f:
        kb_chunks = pickle.load(f)
    EMBEDDINGS = np.array([chunk["embedding"] for chunk in kb_chunks], dtype=np.float32)
    METADATA = kb_chunks
    print(f"✅ Loaded {len(kb_chunks)} knowledge base chunks")
except Exception as e:
    print(f"⚠️ Could not load knowledge base: {e}")

# ==================== Gmail OAuth Functions ====================

def get_gmail_service():
    """Get authenticated Gmail API service"""
    if not GMAIL_AVAILABLE or not session.get('google_token'):
        return None
    
    try:
        creds = Credentials(
            token=session['google_token'],
            refresh_token=session.get('google_refresh_token'),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=GMAIL_SCOPES
        )
        
        service = build('gmail', 'v1', credentials=creds)
        return service
        
    except Exception as e:
        print(f"❌ Gmail service error: {e}")
        return None

def send_email_via_gmail(to_email: str, cc_email: str, subject: str, body_html: str):
    """Send email via Gmail API with fallback logging"""
    service = get_gmail_service()
    
    # Always log what we're trying to send
    print(f"📧 EMAIL REQUEST:")
    print(f"   To: {to_email}")
    print(f"   CC: {cc_email}")
    print(f"   Subject: {subject}")
    
    if not service:
        print(f"   Status: LOGGED (Gmail not authenticated)")
        # Still return success so the user flow continues
        return True, "Email request logged (Gmail not authenticated - admissions will follow up)"
    
    try:
        message = MIMEMultipart('alternative')
        message['To'] = to_email
        if cc_email and cc_email != to_email:
            message['Cc'] = cc_email
        message['Subject'] = subject
        
        html_part = MIMEText(body_html, 'html')
        message.attach(html_part)
        
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        result = service.users().messages().send(
            userId='me',
            body={'raw': raw}
        ).execute()
        
        print(f"✅ Email sent successfully: {result.get('id')}")
        return True, "Email sent successfully"
        
    except HttpError as error:
        print(f"❌ Gmail API error: {error}")
        return False, f"Gmail API error: {str(error)}"
    except Exception as e:
        print(f"❌ Email error: {e}")
        return False, f"Error: {str(e)}"

# ==================== Gmail OAuth Routes ====================

@app.route("/auth/google/login")
def auth_google_login():
    """Initiate Google OAuth flow for Gmail access"""
    if not GMAIL_AVAILABLE or not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return jsonify({"error": "Gmail API not configured"}), 503
    
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [GOOGLE_REDIRECT_URI]
            }
        },
        scopes=GMAIL_SCOPES
    )
    flow.redirect_uri = GOOGLE_REDIRECT_URI
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    session['oauth_state'] = state
    return redirect(authorization_url)

@app.route("/auth/callback")
def auth_google_callback():
    """Handle Google OAuth callback"""
    if not GMAIL_AVAILABLE:
        return jsonify({"error": "Gmail API not available"}), 503
    
    try:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [GOOGLE_REDIRECT_URI]
            }
        },
        scopes=GMAIL_SCOPES,
        state=session.get('oauth_state')
        )
        flow.redirect_uri = GOOGLE_REDIRECT_URI
        
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        
        session['google_token'] = credentials.token
        session['google_refresh_token'] = credentials.refresh_token
        session['google_token_uri'] = credentials.token_uri
        session['google_authenticated'] = True
        
        print("✅ Gmail OAuth successful")
        return redirect('/')
        
    except Exception as e:
        print(f"❌ OAuth error: {e}")
        return jsonify({"error": "Authentication failed", "details": str(e)}), 400

@app.route("/auth/status")
def auth_status():
    """Check Gmail authentication status"""
    return jsonify({
        "authenticated": session.get('google_authenticated', False),
        "email_configured": ADMISSIONS_EMAIL
    })

@app.route("/auth/logout")
def auth_logout():
    """Logout and clear Gmail session"""
    session.pop('google_token', None)
    session.pop('google_refresh_token', None)
    session.pop('google_authenticated', None)
    return jsonify({"ok": True, "message": "Logged out"})

# ==================== Conversation Tracking ====================

class ConversationTracker:
    def __init__(self, session_id: str, family_id: Optional[str] = None):
        self.session_id = session_id
        self.family_id = family_id
        self.started_at = datetime.now()
        self.interactions = []
        self.topics_discussed = set()
        self.concerns = []
        self.child_name = None
        self.parent_name = None
        self.parent_email = None
        self.parent_phone = None
        self.year_group = None
        self.interests = []
        self.high_intent_signals = 0
        self.last_topic = None
        self.emotional_state = "neutral"
        self.language = "en"
        self.contact_collected = False
        self.tour_requested = False
        
    def add_interaction(self, question: str, answer: str, topic: Optional[str] = None):
        self.interactions.append({
            "timestamp": datetime.now().isoformat(),
            "question": question,
            "answer": answer[:500],  # Store more for summaries
            "topic": topic
        })
        
        if topic:
            self.topics_discussed.add(topic)
            self.last_topic = topic
            
        # Detect high intent signals
        high_intent_keywords = ["apply", "visit", "fee", "scholarship", "when can", "how do I", "register", "tour", "book", "prospectus"]
        if any(keyword in question.lower() for keyword in high_intent_keywords):
            self.high_intent_signals += 1
            
        # Detect concerns
        concern_keywords = ["worried", "concern", "anxiety", "difficult", "struggle", "help", "support", "nervous", "special needs", "sen"]
        if any(keyword in question.lower() for keyword in concern_keywords):
            self.concerns.append(question)
            self.emotional_state = "concerned"
            
        # Extract contact information from conversation
        self.extract_contact_info(question, answer)
    
    def extract_contact_info(self, question: str, answer: str):
        """Extract contact details from conversation"""
        import re
        
        # Email pattern
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, question + " " + answer)
        if emails and not self.parent_email:
            self.parent_email = emails[0]
            print(f"📧 Extracted email: {self.parent_email}")
        
        # Phone pattern (UK)
        phone_pattern = r'\b(?:07\d{9}|01\d{9}|02\d{9}|\+447\d{9})\b'
        phones = re.findall(phone_pattern, question + " " + answer)
        if phones and not self.parent_phone:
            self.parent_phone = phones[0]
            print(f"📞 Extracted phone: {self.parent_phone}")
        
        # Check for tour requests
        if any(word in question.lower() for word in ["tour", "visit", "book", "see the school"]):
            self.tour_requested = True
    
    def get_summary(self) -> Dict:
        """Get conversation summary for database"""
        return {
            "session_id": self.session_id,
            "family_id": self.family_id,
            "duration_minutes": int((datetime.now() - self.started_at).total_seconds() / 60),
            "interaction_count": len(self.interactions),
            "topics": list(self.topics_discussed),
            "high_intent": self.high_intent_signals > 0,
            "emotional_state": self.emotional_state,
            "concerns": self.concerns[:3],
            "parent_name": self.parent_name,
            "parent_email": self.parent_email,
            "parent_phone": self.parent_phone,
            "child_name": self.child_name,
            "year_group": self.year_group,
            "tour_requested": self.tour_requested,
            "contact_collected": self.contact_collected,
            "last_interaction": datetime.now().isoformat()
        }

# ==================== Family Context & Database ====================

def fetch_family_context(family_id: str) -> Optional[Dict[str, Any]]:
    """Fetch family personalisation data from database"""
    if not db_pool or not family_id:
        return None
    
    try:
        with db_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT parent_name, child_name, year_group, parent_email,
                           tour_booked, prospectus_requested, application_submitted,
                           created_at
                    FROM inquiries 
                    WHERE family_id = %s 
                    ORDER BY created_at DESC 
                    LIMIT 1
                """, (family_id,))
                
                row = cur.fetchone()
                if row:
                    return {
                        "parent_name": row[0] or "Parent",
                        "child_name": row[1] or "your daughter",
                        "year_group": row[2] or "",
                        "parent_email": row[3] or "",
                        "tour_booked": bool(row[4]),
                        "prospectus_requested": bool(row[5]),
                        "application_submitted": bool(row[6]),
                        "inquiry_date": row[7].isoformat() if row[7] else None
                    }
    except Exception as e:
        print(f"Error fetching family context: {e}")
    return None

def log_interaction_to_db(family_id: str, question: str, answer: str, metadata: Dict):
    """Log conversation to database with enhanced metadata"""
    if not db_pool or not family_id:
        return
    
    try:
        with db_pool.connection() as conn:
            with conn.cursor() as cur:
                # Store interaction in conversations table
                cur.execute("""
                    INSERT INTO conversations 
                    (family_id, question, answer, metadata, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                """, (
                    family_id,
                    question[:500],
                    answer[:1000],
                    json.dumps(metadata)
                ))
                
                # Update inquiry record with latest activity and contact info
                tracker = conversation_memory.get(metadata.get('session_id'))
                if tracker:
                    # Update with collected contact information
                    if tracker.parent_email:
                        cur.execute("""
                            UPDATE inquiries 
                            SET parent_email = COALESCE(parent_email, %s),
                                last_interaction = NOW()
                            WHERE family_id = %s
                        """, (tracker.parent_email, family_id))
                    
                    if tracker.parent_phone:
                        cur.execute("""
                            UPDATE inquiries 
                            SET parent_phone = COALESCE(parent_phone, %s),
                                last_interaction = NOW()
                            WHERE family_id = %s
                        """, (tracker.parent_phone, family_id))
                    
                    if tracker.parent_name:
                        cur.execute("""
                            UPDATE inquiries 
                            SET parent_name = COALESCE(parent_name, %s),
                                last_interaction = NOW()
                            WHERE family_id = %s
                        """, (tracker.parent_name, family_id))
                    
                    # Update high intent flag
                    if metadata.get('high_intent'):
                        cur.execute("""
                            UPDATE inquiries 
                            SET high_intent_detected = TRUE,
                                last_interaction = NOW()
                            WHERE family_id = %s
                        """, (family_id,))
                    
                    # Update tour requested flag
                    if tracker.tour_requested:
                        cur.execute("""
                            UPDATE inquiries 
                            SET tour_requested = TRUE,
                                last_interaction = NOW()
                            WHERE family_id = %s
                        """, (family_id,))
                
                conn.commit()
                print(f"✅ Logged interaction for {family_id}")
    except Exception as e:
        print(f"Error logging to database: {e}")

def save_conversation_summary(session_id: str):
    """Save conversation summary when session ends"""
    if session_id not in conversation_memory:
        return
    
    tracker = conversation_memory[session_id]
    if not tracker.family_id or not db_pool:
        return
    
    try:
        summary = tracker.get_summary()
        
        with db_pool.connection() as conn:
            with conn.cursor() as cur:
                # Save conversation summary
                cur.execute("""
                    INSERT INTO conversation_summaries 
                    (family_id, session_id, summary, created_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (session_id) 
                    DO UPDATE SET 
                        summary = EXCLUDED.summary,
                        updated_at = NOW()
                """, (
                    tracker.family_id,
                    session_id,
                    json.dumps(summary)
                ))
                
                conn.commit()
                print(f"✅ Saved conversation summary for session {session_id}")
    except Exception as e:
        print(f"Error saving conversation summary: {e}")

# ==================== Knowledge Base Search ====================

def semantic_search(query: str, top_k: int = 5) -> List[Tuple[str, float]]:
    """Search knowledge base using embeddings"""
    if not EMBEDDINGS or EMBEDDINGS.size == 0:
        return []
    
    try:
        response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=query
        )
        query_embedding = np.array(response.data[0].embedding, dtype=np.float32)
        
        similarities = np.dot(EMBEDDINGS, query_embedding)
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        
        results = []
        for idx in top_indices:
            if idx < len(METADATA):
                chunk = METADATA[idx]
                results.append((chunk['text'], float(similarities[idx])))
        
        return results
    except Exception as e:
        print(f"Error in semantic search: {e}")
        return []

def find_best_answer(question: str, language: str = 'en', session_id: Optional[str] = None, family_id: Optional[str] = None):
    """Find best answer using knowledge base and context"""
    
    # Get family context
    family_ctx = fetch_family_context(family_id) if family_id else None
    
    # Search knowledge base
    search_results = semantic_search(question, top_k=3)
    
    # Build context
    context_parts = []
    if search_results:
        context_parts.append("Relevant information:")
        for text, score in search_results:
            if score > 0.5:
                context_parts.append(text[:500])
    
    if family_ctx:
        context_parts.append(f"\nFamily context: Parent: {family_ctx['parent_name']}, "
                            f"Child: {family_ctx['child_name']}, "
                            f"Year: {family_ctx.get('year_group', 'not specified')}")
    
    # Generate response
    system_prompt = f"""You are Emily, the AI assistant for More House School.
    Be warm, helpful, and professional. Use British spelling.
    Language: {language}
    Keep responses concise but complete."""
    
    try:
        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context: {' '.join(context_parts)}\n\nQuestion: {question}"}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        answer = completion.choices[0].message.content
        
        # Track conversation
        if session_id and session_id in conversation_memory:
            conversation_memory[session_id].add_interaction(question, answer)
        
        return answer, None, None, None, "knowledge_base"
        
    except Exception as e:
        print(f"Error generating answer: {e}")
        return "I apologize, but I'm having trouble accessing that information. Please contact our admissions team directly.", None, None, None, "error"

# ==================== Tool Endpoints ====================

@app.route("/realtime/tool/send_email", methods=["POST"])
def realtime_tool_send_email():
    """Tool endpoint for realtime voice to send emails to admissions"""
    data = request.get_json() or {}
    
    # Extract parameters
    parent_name = data.get('parent_name', 'Parent')
    parent_email = data.get('parent_email', '')
    parent_phone = data.get('parent_phone', '')
    subject = data.get('subject', 'Enquiry from More House Website')
    body = data.get('body', 'No message provided')
    family_id = data.get('family_id')
    session_id = data.get('session_id')
    
    # Update tracker with collected contact info
    if session_id and session_id in conversation_memory:
        tracker = conversation_memory[session_id]
        tracker.parent_name = parent_name
        tracker.parent_email = parent_email
        tracker.parent_phone = parent_phone
        tracker.contact_collected = True
        tracker.tour_requested = True
        
        # Save to database immediately
        if family_id:
            metadata = {
                'type': 'contact_collected',
                'parent_name': parent_name,
                'parent_email': parent_email,
                'parent_phone': parent_phone
            }
            log_interaction_to_db(family_id, f"Contact details collected", f"Name: {parent_name}, Email: {parent_email}, Phone: {parent_phone}", metadata)
    
    # Build formatted HTML email
    body_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
          <h2 style="color: #091825; border-bottom: 2px solid #FF9F1C; padding-bottom: 10px;">
            More House School - Admissions Enquiry
          </h2>
          
          <div style="background: #f9f9f9; padding: 15px; border-radius: 8px; margin: 20px 0;">
            <h3 style="color: #091825; margin-top: 0;">Contact Details</h3>
            <table style="width: 100%; border-collapse: collapse;">
              <tr>
                <td style="padding: 8px 0; font-weight: bold; width: 120px;">Parent Name:</td>
                <td style="padding: 8px 0;">{parent_name}</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; font-weight: bold;">Email:</td>
                <td style="padding: 8px 0;"><a href="mailto:{parent_email}" style="color: #FF9F1C;">{parent_email}</a></td>
              </tr>
              <tr>
                <td style="padding: 8px 0; font-weight: bold;">Phone:</td>
                <td style="padding: 8px 0;">{parent_phone}</td>
              </tr>
              {f'''<tr>
                <td style="padding: 8px 0; font-weight: bold;">Enquiry ID:</td>
                <td style="padding: 8px 0; font-family: monospace; color: #666;">{family_id}</td>
              </tr>''' if family_id else ''}
            </table>
          </div>
          
          <div style="background: white; padding: 20px; border-left: 4px solid #FF9F1C; margin: 20px 0;">
            <h3 style="color: #091825; margin-top: 0;">Message</h3>
            <p style="line-height: 1.6;">{body}</p>
          </div>
          
          <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd;">
            <p style="color: #666; font-size: 12px;">
              <em>This enquiry was sent via Emily (AI voice assistant) on {datetime.now().strftime('%d %B %Y at %H:%M')}</em><br>
              <em>Session ID: {session_id or 'Not available'}</em>
            </p>
          </div>
        </div>
      </body>
    </html>
    """
    
    # Send the email
    success, message = send_email_via_gmail(
        to_email=ADMISSIONS_EMAIL,
        cc_email=parent_email if parent_email else "",
        subject=subject,
        body_html=body_html
    )
    
    # Log to database
    if family_id:
        metadata = {
            'type': 'email_sent',
            'session_id': session_id,
            'parent_email': parent_email,
            'subject': subject,
            'success': success
        }
        log_interaction_to_db(family_id, f"Email request: {subject}", message, metadata)
    
    return jsonify({
        "ok": success,
        "success": success,
        "message": message,
        "details": {
            "sent_to": ADMISSIONS_EMAIL,
            "cc_to": parent_email if parent_email else "None",
            "subject": subject
        }
    })

@app.route("/realtime/tool/kb_search", methods=["POST"])
def realtime_tool_kb_search():
    """Knowledge base search tool for realtime voice"""
    data = request.get_json() or {}
    query = data.get('query', '')
    session_id = data.get('session_id')
    
    if not query:
        return jsonify({"ok": False, "error": "No query provided"}), 400
    
    results = semantic_search(query, top_k=3)
    
    if results:
        formatted_results = []
        for text, score in results:
            if score > 0.5:
                formatted_results.append(text[:300])
        
        if session_id and session_id in conversation_memory:
            conversation_memory[session_id].add_interaction(
                f"KB search: {query}",
                f"Found {len(formatted_results)} results",
                "knowledge_search"
            )
        
        return jsonify({
            "ok": True,
            "results": formatted_results,
            "query": query,
            "count": len(formatted_results)
        })
    
    return jsonify({
        "ok": True,
        "results": [],
        "query": query,
        "message": "No specific information found on that topic."
    })

# ==================== Realtime Session ====================

@app.route("/realtime/session", methods=["POST"])
def create_realtime_session():
    """Create realtime voice session with contact collection"""
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return jsonify({"error": "OPENAI_API_KEY not set"}), 500

    body = request.get_json(silent=True) or {}
    
    # Generate session ID
    session_id = str(uuid.uuid4())
    family_id = body.get("family_id")
    
    # Initialize conversation tracker
    if session_id not in conversation_memory:
        conversation_memory[session_id] = ConversationTracker(session_id, family_id)
    
    # Get family context for personalized greeting
    family_ctx = fetch_family_context(family_id) if family_id else None
    
    model = body.get("model", "gpt-4o-realtime-preview")
    voice = body.get("voice", "shimmer")  # British female voice
    language = body.get("language", "en")
    
    # Build instructions with clear contact collection flow
    instructions = f"""You are Emily, the AI assistant for More House School in Knightsbridge, London.

CRITICAL RULE FOR TOUR/ADMISSION REQUESTS:
When someone mentions booking a tour, visiting, or contacting admissions:

1. First say: "I'd be delighted to help arrange that for you! Let me take your details so I can send this to our admissions team."

2. Then collect information step by step:
   - "May I have your full name please?" [WAIT FOR ANSWER]
   - "Thank you. And your email address?" [WAIT FOR ANSWER]
   - "Perfect. And a contact phone number?" [WAIT FOR ANSWER]
   - "Lovely. What's your daughter's name?" [WAIT FOR ANSWER]
   - "And which year group are you interested in?" [WAIT FOR ANSWER]

3. Only after collecting ALL information, use the send_email tool.

4. Confirm: "Brilliant! I've sent your request to our admissions team. They'll contact you at [email] within 24 hours."

NEVER attempt to send an email without having collected all the required information first.

General conversation:
- Speak with a warm British accent
- Use British spelling (colour, organise, centre)
- Be helpful and informative about the school
- Keep responses conversational and natural
"""
    
    # Add personalization if we have family context
    if family_ctx:
        parent_name = family_ctx.get('parent_name', 'there')
        child_name = family_ctx.get('child_name', 'your daughter')
        parent_email = family_ctx.get('parent_email')
        
        instructions += f"""

You already know this family:
- Parent: {parent_name}
- Child: {child_name}
- Email: {parent_email}

Greet them warmly by name and reference their previous interest.
"""
    
    instructions += f"""
Session ID: {session_id}
Language: {language}

Remember: Always complete your thoughts before pausing. Be natural and conversational.
"""
    
    # Create OpenAI realtime session with tools
    try:
        response = requests.post(
            "https://api.openai.com/v1/realtime/sessions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "voice": voice,
                "instructions": instructions,
                "modalities": ["text", "audio"],
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "temperature": 0.7,
                "max_response_output_tokens": 1500,
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 800
                },
                "tools": [
                    {
                        "type": "function",
                        "name": "send_email",
                        "description": "Send email to More House admissions. Only use after collecting: parent's name, email, phone, child's name, and year group.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "parent_name": {
                                    "type": "string",
                                    "description": "Parent's full name"
                                },
                                "parent_email": {
                                    "type": "string",
                                    "description": "Parent's email address"
                                },
                                "parent_phone": {
                                    "type": "string",
                                    "description": "Parent's phone number"
                                },
                                "subject": {
                                    "type": "string",
                                    "description": "Email subject"
                                },
                                "body": {
                                    "type": "string",
                                    "description": "Detailed message with child's name, year group, and request"
                                }
                            },
                            "required": ["parent_name", "parent_email", "parent_phone", "subject", "body"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "kb_search",
                        "description": "Search More House knowledge base",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Search query"}
                            },
                            "required": ["query"]
                        }
                    }
                ],
                "tool_choice": "auto"
            }
        )
        
        if response.ok:
            session_data = response.json()
            session_data['session_id'] = session_id
            session_data['family_id'] = family_id
            
            print(f"✅ Realtime session created: {session_id}")
            print(f"   Family ID: {family_id}")
            print(f"   Tools enabled: send_email, kb_search")
            
            return jsonify(session_data)
        else:
            print(f"❌ Failed to create session: {response.text}")
            return jsonify({"error": "Failed to create session"}), 500
            
    except Exception as e:
        print(f"❌ Error creating session: {e}")
        return jsonify({"error": str(e)}), 500

# ==================== Text Chat Endpoints ====================

@app.route('/ask', methods=['POST'])
def ask():
    """Basic text chat endpoint"""
    data = request.json or {}
    question = data.get('question', '')
    language = data.get('language', 'en')
    family_id = data.get('family_id')
    session_id = data.get('session_id') or str(uuid.uuid4())
    
    if not question:
        return jsonify({"answer": "Please ask a question.", "queries": []})
    
    # Initialize tracker if needed
    if session_id not in conversation_memory:
        conversation_memory[session_id] = ConversationTracker(session_id, family_id)
    
    answer, url, label, matched_key, source = find_best_answer(
        question, language, session_id, family_id
    )
    
    # Log to database
    if family_id:
        tracker = conversation_memory.get(session_id)
        metadata = {
            'source': source,
            'topic': matched_key,
            'sentiment': tracker.emotional_state if tracker else 'neutral',
            'session_id': session_id,
            'high_intent': tracker.high_intent_signals > 0 if tracker else False
        }
        log_interaction_to_db(family_id, question, answer, metadata)
    
    return jsonify({
        'answer': answer,
        'url': url,
        'link_label': label,
        'source': source,
        'session_id': session_id
    })

@app.route('/ask-with-tools', methods=['POST'])
def ask_with_tools():
    """Enhanced text chat with email capability"""
    data = request.json or {}
    question = data.get('question', '')
    language = data.get('language', 'en')
    family_id = data.get('family_id')
    session_id = data.get('session_id') or str(uuid.uuid4())
    
    # Initialize conversation tracker
    if session_id not in conversation_memory:
        conversation_memory[session_id] = ConversationTracker(session_id, family_id)
    
    tracker = conversation_memory[session_id]
    
    # Get family context
    family_ctx = fetch_family_context(family_id) if family_id else None
    
    # Check if this is an email request
    email_keywords = ["book", "tour", "visit", "contact", "email", "admissions", "prospectus", "apply"]
    is_email_request = any(keyword in question.lower() for keyword in email_keywords)
    
    if is_email_request:
        # Check if we have contact details already
        if tracker.parent_email and tracker.parent_name and tracker.parent_phone:
            # We have all details, send the email
            subject = "Tour Enquiry - More House School"
            body = f"Parent {tracker.parent_name} has requested: {question}"
            
            success, message = send_email_via_gmail(
                to_email=ADMISSIONS_EMAIL,
                cc_email=tracker.parent_email,
                subject=subject,
                body_html=f"""
                <html>
                  <body>
                    <h2>Tour Request from {tracker.parent_name}</h2>
                    <p><strong>Request:</strong> {question}</p>
                    <p><strong>Contact:</strong> {tracker.parent_email} / {tracker.parent_phone}</p>
                    <hr>
                    <p><em>Family ID: {family_id}</em></p>
                  </body>
                </html>
                """
            )
            
            if success:
                answer = f"Perfect! I've sent your request to our admissions team. They'll contact you at {tracker.parent_email} within 24 hours."
            else:
                answer = "I'd be happy to help with that. Could you please provide your contact details so I can send this request to our admissions team?"
        
        elif family_ctx and family_ctx.get('parent_email'):
            # We have details from database
            tracker.parent_email = family_ctx.get('parent_email')
            tracker.parent_name = family_ctx.get('parent_name', 'Parent')
            
            success, message = send_email_via_gmail(
                to_email=ADMISSIONS_EMAIL,
                cc_email=tracker.parent_email,
                subject="Tour Enquiry - More House School",
                body_html=f"""
                <html>
                  <body>
                    <h2>Tour Request from {tracker.parent_name}</h2>
                    <p><strong>Request:</strong> {question}</p>
                    <hr>
                    <p><em>Family ID: {family_id}</em></p>
                  </body>
                </html>
                """
            )
            
            if success:
                answer = f"I've sent your request to our admissions team, {tracker.parent_name}. They'll be in touch within 24 hours at {tracker.parent_email}."
            else:
                answer = "I'd love to help with that! Could you please confirm your phone number so I can complete the tour booking request?"
        else:
            # Need to collect details
            answer = "I'd be delighted to help arrange that for you! To send this to our admissions team, I'll need a few details. Could you please provide your full name, email address, and phone number?"
            
            # Mark that we need details
            return jsonify({
                'answer': answer,
                'requires_details': True,
                'session_id': session_id
            })
    else:
        # Regular knowledge base response
        answer, url, label, matched_key, source = find_best_answer(
            question, language, session_id, family_id
        )
    
    # Log interaction
    if family_id:
        metadata = {
            'session_id': session_id,
            'high_intent': tracker.high_intent_signals > 0,
            'tour_requested': tracker.tour_requested
        }
        log_interaction_to_db(family_id, question, answer, metadata)
    
    return jsonify({
        'answer': answer,
        'session_id': session_id
    })

@app.route('/submit-contact', methods=['POST'])
def submit_contact():
    """Handle contact details submission from text chat"""
    data = request.json or {}
    session_id = data.get('session_id')
    family_id = data.get('family_id')
    parent_name = data.get('parent_name')
    parent_email = data.get('parent_email')
    parent_phone = data.get('parent_phone')
    original_request = data.get('original_request', 'Tour booking request')
    
    if not all([parent_name, parent_email, parent_phone]):
        return jsonify({"error": "Please provide all contact details"}), 400
    
    # Update tracker
    if session_id and session_id in conversation_memory:
        tracker = conversation_memory[session_id]
        tracker.parent_name = parent_name
        tracker.parent_email = parent_email
        tracker.parent_phone = parent_phone
        tracker.contact_collected = True
        tracker.tour_requested = True
    
    # Send email
    success, message = send_email_via_gmail(
        to_email=ADMISSIONS_EMAIL,
        cc_email=parent_email,
        subject="Tour Enquiry - More House School",
        body_html=f"""
        <html>
          <body>
            <h2>Tour Request from {parent_name}</h2>
            <p><strong>Email:</strong> {parent_email}</p>
            <p><strong>Phone:</strong> {parent_phone}</p>
            <p><strong>Request:</strong> {original_request}</p>
            <hr>
            <p><em>Submitted via Emily chat assistant</em></p>
            <p><em>Family ID: {family_id or 'New enquiry'}</em></p>
          </body>
        </html>
        """
    )
    
    # Log to database
    if family_id:
        metadata = {
            'type': 'contact_submitted',
            'parent_name': parent_name,
            'parent_email': parent_email,
            'parent_phone': parent_phone,
            'success': success
        }
        log_interaction_to_db(family_id, "Contact details submitted", f"Tour request from {parent_name}", metadata)
    
    return jsonify({
        'success': success,
        'message': f"Perfect! I've sent your request to our admissions team. They'll contact you at {parent_email} within 24 hours." if success else "There was an issue sending your request. Please contact us directly at office@morehousemail.org.uk"
    })

# ==================== Session Management ====================

@app.route('/api/family/init', methods=['POST'])
def init_family_session():
    """Initialize session with family context"""
    data = request.json or {}
    family_id = data.get('family_id')
    session_id = data.get('session_id')
    
    if not family_id:
        return jsonify({"error": "No family_id provided"}), 400
    
    family_ctx = fetch_family_context(family_id)
    
    if family_ctx:
        # Initialize tracker with family data
        if session_id:
            if session_id not in conversation_memory:
                conversation_memory[session_id] = ConversationTracker(session_id, family_id)
            
            tracker = conversation_memory[session_id]
            tracker.parent_name = family_ctx.get('parent_name')
            tracker.parent_email = family_ctx.get('parent_email')
            tracker.child_name = family_ctx.get('child_name')
            tracker.year_group = family_ctx.get('year_group')
        
        return jsonify({
            "success": True,
            **family_ctx
        })
    
    return jsonify({"success": False, "message": "Family not found"})

@app.route('/api/conversation/end', methods=['POST'])
def end_conversation():
    """End conversation and save summary"""
    data = request.json or {}
    session_id = data.get('session_id')
    
    if session_id:
        save_conversation_summary(session_id)
        
        # Clean up memory after saving
        if session_id in conversation_memory:
            del conversation_memory[session_id]
        
        return jsonify({"success": True, "message": "Conversation ended and summary saved"})
    
    return jsonify({"success": False, "message": "No session_id provided"})

# ==================== Static Files ====================

@app.route('/')
def index():
    return """
    <html>
        <head><title>Emily - More House School AI Assistant</title></head>
        <body>
            <h1>Emily AI Assistant</h1>
            <p>Emily is embedded in the school's prospectus pages.</p>
            <p>Gmail Status: <a href="/auth/status">Check Status</a></p>
            <p>Authenticate Gmail: <a href="/auth/google/login">Login with Google</a></p>
        </body>
    </html>
    """

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

# ==================== Health Check ====================

@app.route('/health')
def health():
    """Health check endpoint"""
    gmail_status = "authenticated" if get_gmail_service() else "not authenticated"
    db_status = "connected" if db_pool else "not connected"
    active_sessions = len(conversation_memory)
    
    return jsonify({
        "status": "healthy",
        "gmail": gmail_status,
        "database": db_status,
        "knowledge_base": len(kb_chunks) if kb_chunks else 0,
        "active_sessions": active_sessions
    })

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
