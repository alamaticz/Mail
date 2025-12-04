import streamlit as st
import os
import base64
import pickle
import datetime
import zipfile
from pathlib import Path

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
SENDER_EMAIL = "noreply@icegate.gov.in"

TOKEN_FILE = "token.pkl"
TEMP_DOWNLOAD = "downloads"

os.makedirs(TEMP_DOWNLOAD, exist_ok=True)

# ---------------------------------------------------------
# GMAIL AUTH
# ---------------------------------------------------------
def authenticate_gmail():
    creds = None

    # 1. Try loading from local token.pkl (Local Development)
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as token:
            creds = pickle.load(token)

    # 2. If no valid local token, try loading from Streamlit Secrets (Cloud Deployment)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        
        # Check if secrets exist for headless auth
        elif "gmail_token" in st.secrets:
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_info(st.secrets["gmail_token"], SCOPES)
            
        # 3. Fallback to Local Interactive Auth (First time run locally)
        else:
            gmail_config = {
                "installed": {
                    "client_id": st.secrets["gmail"]["client_id"],
                    "project_id": st.secrets["gmail"]["project_id"],
                    "auth_uri": st.secrets["gmail"]["auth_uri"],
                    "token_uri": st.secrets["gmail"]["token_uri"],
                    "client_secret": st.secrets["gmail"]["client_secret"],
                    "redirect_uris": st.secrets["gmail"]["redirect_uris"]
                }
            }

            flow = InstalledAppFlow.from_client_config(gmail_config, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run (only useful locally)
        with open(TOKEN_FILE, "wb") as token:
            pickle.dump(creds, token)

    return build("gmail", "v1", credentials=creds)


# ---------------------------------------------------------
# RECURSIVE ATTACHMENT EXTRACTOR (CRITICAL FIX)
# ---------------------------------------------------------
def extract_parts(parts, msg_id, service, total_files):
    for part in parts:
        if "parts" in part:
            total_files = extract_parts(part["parts"], msg_id, service, total_files)

        filename = part.get("filename", "")
        body = part.get("body", {})
        att_id = body.get("attachmentId")

        if filename and filename.lower().endswith(".pdf") and att_id:
            attachment = service.users().messages().attachments().get(
                userId="me",
                messageId=msg_id,
                id=att_id
            ).execute()

            data = base64.urlsafe_b64decode(attachment["data"])
            save_path = os.path.join(TEMP_DOWNLOAD, filename)

            with open(save_path, "wb") as f:
                f.write(data)

            total_files += 1

    return total_files

# ---------------------------------------------------------
# DOWNLOAD PDFs BY DATE (ANY RANGE)
# ---------------------------------------------------------
def download_pdfs_by_date(from_date, to_date):
    service = authenticate_gmail()

    start = from_date.strftime("%Y/%m/%d")
    end = (to_date + datetime.timedelta(days=1)).strftime("%Y/%m/%d")

    query = (
        f'from:{SENDER_EMAIL} '
        f'(subject:Final OR subject:"Final Copy" OR subject:LEO OR subject:FINAL) '
        f'has:attachment '
        f'after:{start} before:{end}'
    )

    st.info("📩 Searching Final ICEGATE mails...")

    # Safe cleanup
    for f in Path(TEMP_DOWNLOAD).glob("*.pdf"):
        try:
            f.unlink()
        except PermissionError:
            st.warning(f"⚠️ File in use, skipped: {f.name}")

    total_files = 0
    next_page = None
    progress = st.empty()

    while True:
        response = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=500,
            pageToken=next_page
        ).execute()

        messages = response.get("messages", [])
        if not messages:
            break

        progress.write(f"Processing {len(messages)} emails...")

        for msg in messages:
            msg_data = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="full"
            ).execute()

            parts = msg_data.get("payload", {}).get("parts", [])
            total_files = extract_parts(parts, msg["id"], service, total_files)

            if total_files > 0:
                progress.info(f"📥 Downloaded {total_files} PDFs so far...")

        next_page = response.get("nextPageToken")
        if not next_page:
            break

    zip_name = f"ICEGATE_{from_date}_to_{to_date}.zip"

    if total_files > 0:
        with zipfile.ZipFile(zip_name, "w") as zipf:
            for f in Path(TEMP_DOWNLOAD).glob("*.pdf"):
                zipf.write(f, arcname=f.name)

    return total_files, zip_name

# ---------------------------------------------------------
# STREAMLIT UI
# ---------------------------------------------------------
st.title("📥 ICEGATE PDF Downloader (Any Date Range)")
st.write("✅ Works for ANY Date Range (Days / Months / Years)")
st.write("✅ Fetches only FINAL / LEO mails")
st.write("✅ Downloads only PDF Attachments")

st.markdown("### 📅 Select Date Range")

from_date = st.date_input("From Date")
to_date = st.date_input("To Date")

st.markdown("### 🔽 Click the button to start extraction")

if st.button("Extract Mails"):
    if from_date > to_date:
        st.error("❌ From Date cannot be greater than To Date")
    else:
        with st.spinner("Fetching ICEGATE mails and downloading PDFs..."):
            count, zip_path = download_pdfs_by_date(from_date, to_date)

        if count == 0:
            st.warning("⚠️ No Final PDF files found for the selected date range.")
        else:
            st.success(f"🎉 Completed! {count} FINAL PDFs downloaded.")

            with open(zip_path, "rb") as zf:
                st.download_button(
                    label="📦 Download ZIP",
                    data=zf,
                    file_name=zip_path,
                    mime="application/zip",
                )
