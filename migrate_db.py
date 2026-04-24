from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

def migrate():
    uri = os.getenv('MONGODB_URI')
    if not uri:
        print("Error: MONGODB_URI not found in .env")
        return

    client = MongoClient(uri)
    old_db = client['spareparts_db']
    
    # New Databases
    db_spareparts = client['car-spareparts']
    db_kanban = client['kanban']
    db_chat = client['buzz-chat']
    db_stats = client['site-stats']

    print("Starting migration from spareparts_db...")

    # 1. Spareparts
    collections_spareparts = ['categories', 'products', 'cart_items', 'orders', 'users', 'counters']
    for coll in collections_spareparts:
        count = old_db[coll].count_documents({})
        if count > 0:
            print(f"Migrating {coll} ({count} docs) to car-spareparts...")
            docs = list(old_db[coll].find())
            db_spareparts[coll].insert_many(docs)

    # 2. Kanban
    kanban_count = old_db['kanban_tasks'].count_documents({})
    if kanban_count > 0:
        print(f"Migrating kanban_tasks ({kanban_count} docs) to kanban...")
        docs = list(old_db['kanban_tasks'].find())
        db_kanban['kanban_tasks'].insert_many(docs)
        # Move counters if they exist for kanban
        k_counter = old_db['counters'].find_one({'_id': 'kanban_tasks'})
        if k_counter:
            db_kanban['counters'].insert_one(k_counter)

    # 3. Chat
    chat_count = old_db['chat_messages'].count_documents({})
    if chat_count > 0:
        print(f"Migrating chat_messages ({chat_count} docs) to buzz-chat...")
        docs = list(old_db['chat_messages'].find())
        db_chat['chat_messages'].insert_many(docs)
        c_counter = old_db['counters'].find_one({'_id': 'chat_messages'})
        if c_counter:
            db_chat['counters'].insert_one(c_counter)

    # 4. Stats
    stats_count = old_db['site_stats'].count_documents({})
    if stats_count > 0:
        print(f"Migrating site_stats ({stats_count} docs) to site-stats...")
        docs = list(old_db['site_stats'].find())
        db_stats['site_stats'].insert_many(docs)

    print("\nMigration complete! You can now safely delete the 'spareparts_db' database if everything looks correct.")

if __name__ == '__main__':
    migrate()
