from database import evaluations_collection

evaluations_collection.insert_one({
    "test": "mongodb working"
})

print("Inserted successfully")