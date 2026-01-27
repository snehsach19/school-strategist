import ssl
from imapclient import IMAPClient
from elasticsearch import Elasticsearch, helpers
from datetime import datetime, timedelta
import json
import time
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- 1. CREDENTIALS (loaded from .env) ---
GMAIL_USER = os.getenv("GMAIL_EMAIL")
GMAIL_PASS = os.getenv("GMAIL_PASSWORD")
ELASTIC_CLOUD_ID = os.getenv("ELASTIC_CLOUD_ID")
ELASTIC_API_KEY = os.getenv("ELASTIC_API_KEY")

# --- 2. CONFIGURATION ---
INDEX_NAME = "school-agent-final-data"
LAST_CHECK_FILE = "last_check.txt"
VECTORIZATION_PIPELINE = "school-rag-vectorizer" # The pipeline created in Kibana

# --- 3. ELASTICSEARCH CLIENT INITIALIZATION ---
try:
    es = Elasticsearch(
        cloud_id=ELASTIC_CLOUD_ID,
        api_key=ELASTIC_API_KEY
    )
    es.info() 
    print("Elasticsearch client initialized successfully.")
except Exception as e:
    print(f"FATAL ELASTICSEARCH ERROR: Could not connect to Elastic Cloud. {e}")
    exit()

# --- 4. INGESTION UTILITIES ---
def get_last_check_date():
    """Reads the last successful sync date for incremental ingestion."""
    try:
        with open(LAST_CHECK_FILE, 'r') as f:
            date_str = f.read().strip()
            return datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=1)
    except (FileNotFoundError, ValueError):
        return datetime.now() - timedelta(days=7)

def update_last_check_date():
    """Writes the current run date to the file."""
    with open(LAST_CHECK_FILE, 'w') as f:
        f.write(datetime.now().strftime('%Y-%m-%d'))

def ingest_emails():
    last_check_date = get_last_check_date()
    # IMAP search requires date format: "07-Nov-2025"
    search_date = last_check_date.strftime("%d-%b-%Y")
    
    context = ssl.create_default_context() 

    try:
        with IMAPClient('imap.gmail.com', port=993, ssl=True, ssl_context=context) as client:
            client.login(GMAIL_USER, GMAIL_PASS)
            client.select_folder('INBOX')

            messages = client.search([b'SINCE', search_date.encode('utf-8')])
            
            if not messages:
                print(f"No new emails found since {search_date}.")
                return

            print(f"Found {len(messages)} emails for processing. Starting ingestion...")

            fetch_items = [b'BODY[]', b'ENVELOPE', b'BODY[HEADER.FIELDS (FROM)]']
            response = client.fetch(messages, fetch_items)
            
            actions = []
            for msg_id, data in response.items():
                
                raw_from_header = data.get(b'BODY[HEADER.FIELDS (FROM)]', b'').decode('utf-8', errors='ignore')
                
                # --- FILTER: STRICTLY ENFORCE "via ParentSquare" ---
                if 'via ParentSquare' not in raw_from_header:
                    continue 

                # --- EXTRACT METADATA ---
                envelope = data[b'ENVELOPE']
                try:
                    sender_info = envelope.from_[0]
                    sender_address = sender_info.address.decode('utf-8') if sender_info.address else 'unknown@sender.com'
                except Exception:
                    sender_address = 'unknown@sender.com'

                subject = envelope.subject.decode('utf-8') if envelope.subject else 'No Subject'
                raw_body = data[b'BODY[]'].decode('utf-8', errors='ignore')

                # Construct the document for Elasticsearch
                doc = {
                    '@timestamp': datetime.now().isoformat(), 
                    'subject': subject,
                    'sender_address': sender_address,
                    'body_full': raw_body, 
                }
                
                # --- THE CORRECTED ACTIONS.APPEND BLOCK (Inside the loop) ---
                actions.append({
                    '_op_type': 'index',    # Defines the operation type
                    '_index': INDEX_NAME,
                    '_id': str(msg_id),
                    '_source': doc,                     # The document data
                })
            # --- END OF 'for' LOOP ---

            # --- BULK INDEXING (Robust Error Handling) ---
            if actions:
                try:
                    success, errors = helpers.bulk(es, actions, raise_on_error=True)
                    print(f"Successfully indexed {success} documents. Errors: {len(errors)}")
                
                except helpers.BulkIndexError as e:
                    print("\n--- ELASTICSEARCH BULK ERRORS FOUND ---")
                    if hasattr(e, 'errors'):
                        print(json.dumps(e.errors, indent=2)) 
                    print("---------------------------------------")
                    # Re-raise error to halt system for review
                    raise SystemExit(f"FATAL INDEXING ERROR: {e.args[0]}") from e
                
                update_last_check_date() # Update history only if indexing was attempted

    except Exception as e:
        print(f"FATAL IMAP CONNECTION ERROR: {e}")

if __name__ == "__main__":
    ingest_emails()
