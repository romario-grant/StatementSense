import base64
import os
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from bank_email_parsers import parse_bank_email

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def authenticate():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials/credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as f:
            f.write(creds.to_json())
    return creds

def extract_body(payload):
    if 'parts' in payload:
        for part in payload['parts']:
            result = extract_body(part)
            if result:
                return result
    else:
        if payload.get('mimeType') == 'text/plain':
            data = payload.get('body', {}).get('data', '')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    return ''

def detect_bank(subject, body):
    subject_upper = subject.upper()
    if 'TRANSACTION APPROVED' in subject_upper or \
       'TRANSACTION REVERSED' in subject_upper or \
       'WITHDRAWAL' in subject_upper:
        return 'NCB'
    if 'PURCHASE MADE OUTSIDE' in subject_upper or \
       'PURCHASE' in subject_upper and 'scotiabank' in body.lower():
        return 'Scotiabank'
    return None

service = build('gmail', 'v1', credentials=authenticate())

# Fetch the forwarded bank emails
results = service.users().messages().list(
    userId='me',
    q='from:browne.jada@gmail.com subject:Fwd',
    maxResults=10
).execute()
messages = results.get('messages', [])

print(f'Found {len(messages)} forwarded emails\n')
print('-' * 60)

for msg in messages:
    msg_data = service.users().messages().get(
        userId='me', id=msg['id'], format='full'
    ).execute()

    internal_timestamp = int(msg_data.get('internalDate', 0)) // 1000
    date_str = datetime.fromtimestamp(internal_timestamp, tz=timezone.utc).strftime('%Y-%m-%d')

    headers = {h['name']: h['value'] for h in msg_data['payload']['headers']}
    subject = headers.get('Subject', '')
    body = extract_body(msg_data['payload'])

    bank = detect_bank(subject, body)

    print(f'Subject : {subject}')
    print(f'Bank    : {bank}')
    print(f'Date    : {date_str}')

    if bank:
        result = parse_bank_email(body, bank)
        if result:
            # Inject date for Scotiabank (no date in body)
            if bank == 'Scotiabank' and not result.get('date'):
                result['date'] = date_str
            print(f'Parsed  : {result}')
        else:
            print(f'Parsed  : None — parser returned no match')
            print(f'--- BODY PREVIEW ---')
            print(body[:800])
    print('-' * 60)
