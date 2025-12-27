# RefCheck AI - Production Multi-Tenant Reference Verification System

A production-ready, multi-tenant SaaS application for automated phone reference checks. Features user authentication, isolated data storage, searchable candidate database, and AI-powered phone interviews.

## Features

### Multi-Tenant Architecture
- **User Registration & Authentication**: Secure account creation with password validation
- **Data Isolation**: Each user's data (candidates, references, CVs) is completely isolated
- **Per-User API Keys**: Users configure their own Vapi and Twilio credentials
- **Audit Logging**: All actions are logged for security and compliance

### Candidate Management
- **Resume Upload & Parsing**: Upload PDF/DOC/TXT resumes, automatically extract work history
- **Searchable Database**: Full-text search across candidate names, positions, skills, notes
- **Status Tracking**: Track candidates through intake → in_progress → completed pipeline
- **Notes & Annotations**: Add private notes to candidate profiles

### Reference Verification
- **AI Phone Calls**: Automated reference calls via Vapi.ai
- **Transcript Analysis**: Claude analyzes transcripts to detect discrepancies
- **Verification Scoring**: 0-100 score based on confirmation of claims
- **Red Flag Detection**: Automatically flags contradictions and concerns

### SMS Follow-up
- **Automatic SMS**: Sends SMS when calls go unanswered
- **Customizable Templates**: Per-user and per-candidate SMS templates
- **Scheduling**: Schedule follow-up calls with timezone support

## Technology Stack

- **Backend**: Python/Flask
- **Database**: SQLite (dev) / PostgreSQL (production)
- **ORM**: SQLAlchemy with Flask-Migrate
- **Authentication**: Flask-Login with secure password hashing
- **AI Phone Calls**: Vapi.ai
- **AI Analysis**: Anthropic Claude
- **SMS**: Twilio

## Installation

### Local Development

```bash
# Clone and setup
git clone <repository>
cd reference-checker

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Initialize database
flask db upgrade
# Or: flask init-db

# Run development server
python app.py
```

### Production Deployment (Heroku/Railway)

1. Create a new app on your platform
2. Add PostgreSQL addon
3. Set environment variables:
   - `SECRET_KEY`: Generate with `python -c "import secrets; print(secrets.token_hex(32))"`
   - `DATABASE_URL`: Provided by PostgreSQL addon
   - `ANTHROPIC_API_KEY`: Your Anthropic API key
4. Deploy the code
5. Run migrations: `flask db upgrade`

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000", "--workers", "2"]
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Flask secret key for sessions |
| `DATABASE_URL` | Yes | Database connection string |
| `ANTHROPIC_API_KEY` | No | Default API key for resume parsing |
| `PORT` | No | Server port (default: 5000) |
| `FLASK_DEBUG` | No | Enable debug mode (default: false) |

### User Settings (configured in-app)

Each user configures their own:
- **Vapi API Key**: For making phone calls
- **Vapi Phone Number ID**: Their outbound phone number
- **Twilio Credentials**: For SMS (optional)
- **SMS Template**: Custom follow-up message

## API Endpoints

### Authentication
- `POST /register` - Create new account
- `POST /login` - Sign in
- `GET /logout` - Sign out

### Candidates
- `GET /api/candidates` - List all (with search: `?q=query&status=filter`)
- `POST /api/candidates` - Create from resume upload
- `GET /api/candidates/<id>` - Get details
- `PATCH /api/candidates/<id>` - Update
- `DELETE /api/candidates/<id>` - Delete

### References
- `POST /api/candidates/<id>/references` - Add reference
- `PATCH /api/candidates/<id>/references/<ref_id>` - Update
- `DELETE /api/candidates/<id>/references/<ref_id>` - Delete
- `POST /api/candidates/<id>/references/<ref_id>/schedule` - Schedule call
- `POST /api/candidates/<id>/references/<ref_id>/send-sms` - Send SMS

### Calls
- `POST /api/start-reference-check` - Start single call
- `POST /api/candidates/<id>/start-outreach` - Start all pending
- `GET /api/check-status/<call_id>` - Get call status/results

### Settings
- `GET /api/settings` - Get user settings
- `PATCH /api/settings` - Update settings
- `POST /api/settings/password` - Change password

### Search
- `GET /api/search?q=query` - Search candidates

## Data Model

```
User
├── Candidates (isolated per user)
│   ├── Jobs (work history)
│   │   └── References
│   └── ResumeFiles
└── Settings (API keys, preferences)

AuditLog (tracks all actions)
```

## Security Features

- **Password Requirements**: 8+ chars, uppercase, lowercase, number
- **Password Hashing**: Werkzeug secure hashing
- **Session Security**: Secure Flask sessions
- **Data Isolation**: All queries filtered by user_id
- **Ownership Verification**: All resource access verified
- **Audit Logging**: Action tracking for compliance
- **CSRF Protection**: Built into Flask-WTF forms

## Search Functionality

The search feature uses a pre-computed search vector that includes:
- Candidate name and email
- Position applied for
- Professional summary
- Skills
- Notes
- Resume text
- Company names and job titles

Search is case-insensitive and supports partial matching.

## Scaling Considerations

### Database
- SQLite for development
- PostgreSQL for production with connection pooling
- Indexed columns for common queries
- Optimized search vectors

### Application
- Stateless design for horizontal scaling
- Gunicorn with multiple workers
- Background job support ready (add Celery for scheduled calls)

## Legal Considerations

⚠️ Before deploying, ensure compliance with:
- FCC regulations on automated calling
- TCPA requirements for SMS
- State call recording laws
- Employment verification regulations

Recommendations:
- Obtain candidate consent before contacting references
- Inform references about call recording
- Maintain audit logs for compliance

## License

MIT License - See LICENSE file
