import pickle
import json
import os

TOKEN_FILE = "token.pkl"

def main():
    if not os.path.exists(TOKEN_FILE):
        print(f"Error: {TOKEN_FILE} not found. Please run the app locally once to generate it.")
        return

    try:
        with open(TOKEN_FILE, "rb") as token:
            creds = pickle.load(token)
            
        # Convert credentials to dictionary
        creds_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes
        }
        
        print("\n=== COPY THE FOLLOWING INTO YOUR STREAMLIT SECRETS ===\n")
        print("[gmail_token]")
        for key, value in creds_data.items():
            if value:
                print(f'{key} = "{value}"')
        print("\n====================================================\n")
        
    except Exception as e:
        print(f"Error reading token file: {e}")

if __name__ == "__main__":
    main()
