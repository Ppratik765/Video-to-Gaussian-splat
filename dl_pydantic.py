import urllib.request
import json

# Find the correct URL for pydantic 1.10.18 wheel
url = "https://pypi.org/pypi/pydantic/1.10.18/json"
data = json.loads(urllib.request.urlopen(url, timeout=10).read())
for u in data["urls"]:
    if u["filename"].endswith("-py3-none-any.whl"):
        print(u["url"])
        urllib.request.urlretrieve(u["url"], u["filename"])
        print(f"Downloaded {u['filename']}")
        break
else:
    print("No pure-python wheel found, listing all:")
    for u in data["urls"]:
        print(f"  {u['filename']}")
