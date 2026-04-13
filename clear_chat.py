import os
from pymongo import MongoClient
from dotenv import load_dotenv

def clear_chat_history():
    # Load environment variables (MONGODB_URI)
    load_dotenv()
    
    uri = os.getenv('MONGODB_URI')
    if not uri:
        print("Error: MONGODB_URI not found in .env file!")
        return

    try:
        # Connect to the MongoDB cluster
        client = MongoClient(uri)
        
        # Access the specific database and collection
        db = client.spareparts_db
        chat_col = db.chat_messages
        
        # Delete all documents in the collection
        result = chat_col.delete_many({})
        
        print(f"✅ Success! Deleted {result.deleted_count} messages from the chat history.")
        
    except Exception as e:
        print(f"❌ Failed to connect to MongoDB. Error: {e}")

if __name__ == "__main__":
    confirm = input("⚠️ Are you sure you want to completely wipe all chat history? (y/n): ")
    if confirm.lower() == 'y':
        clear_chat_history()
    else:
        print("Aborted.")
