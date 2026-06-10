from dotenv import load_dotenv
import os

load_dotenv()

print("=" * 50)
print("ELASTICSEARCH CONNECTION TEST")
print("=" * 50)

ES_URL = os.getenv("ELASTICSEARCH_URL")
API_KEY = os.getenv("ELASTICSEARCH_API_KEY")

print("URL Found:", bool(ES_URL))
print("API Key Found:", bool(API_KEY))

if not ES_URL:
    print("ERROR: ELASTICSEARCH_URL missing")
    exit()

if not API_KEY:
    print("ERROR: ELASTICSEARCH_API_KEY missing")
    exit()

try:
    from elasticsearch import Elasticsearch

    print("\nCreating client...")

    client = Elasticsearch(
        ES_URL,
        api_key=API_KEY
    )

    print("Client created")

    print("\nTesting connection...")

    info = client.info()

    print("\nSUCCESS!")
    print("Cluster Name:", info["cluster_name"])
    print("Cluster UUID:", info["cluster_uuid"])
    print("Version:", info["version"]["number"])

    print("\nListing indices...")

    indices = client.indices.get_alias(index="*")

    if indices:
        for index in indices:
            print("-", index)
    else:
        print("No indices found")

except Exception as e:
    print("\nFAILED!")
    print("Type:", type(e).__name__)
    print("Message:", str(e))