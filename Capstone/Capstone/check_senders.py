import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
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

service = build('gmail', 'v1', credentials=creds)
results = service.users().messages().list(userId='me', maxResults=20).execute()
messages = results.get('messages', [])

for msg in messages:
    m = service.users().messages().get(
        userId='me', id=msg['id'],
        format='metadata',
        metadataHeaders=['From', 'Subject']
    ).execute()
    headers = {h['name']: h['value'] for h in m['payload']['headers']}
    print(headers.get('From', ''), '|', headers.get('Subject', ''))

