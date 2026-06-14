"""Clear all data in the douyin_research database.

Usage:
    python scripts/clear_db.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymongo import MongoClient
from common.config import get_config


def main():
    config = get_config()
    client = MongoClient(config["mongodb"]["uri"])
    db = client.get_database(config["mongodb"]["database"])

    for name in db.list_collection_names():
        count = db[name].count_documents({})
        if count > 0:
            db[name].delete_many({})
            print(f"  {name}: deleted {count} docs")
        else:
            print(f"  {name}: already empty")

    client.close()
    print("Done.")


if __name__ == "__main__":
    main()
