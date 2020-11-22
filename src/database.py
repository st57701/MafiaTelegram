from pymongo import MongoClient, ReturnDocument

client = MongoClient()
database = client.mafia


def get_new_id(collection):
    counter = database.counter.find_one_and_update(
        {"_id": collection},
        {"$inc": {"next": 1}},
        return_document=ReturnDocument.AFTER,
        upsert=True
    )

    return counter["next"]
