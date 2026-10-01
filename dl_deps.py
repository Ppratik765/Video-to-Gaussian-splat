import json
import urllib.request

packages = ["pytest", "iniconfig", "pluggy", "exceptiongroup", "tomli", "packaging"]
for pkg in packages:
    try:
        url = f"https://pypi.org/pypi/{pkg}/json"
        data = json.loads(urllib.request.urlopen(url, timeout=15).read())
        # Find py3-none-any wheel for latest
        for u in data["urls"]:
            if u["filename"].endswith("-py3-none-any.whl"):
                print(f"Downloading {u['filename']}...")
                urllib.request.urlretrieve(u["url"], u["filename"])
                print(f"  OK: {u['filename']}")
                break
        else:
            # Try any wheel
            for u in data["urls"]:
                if u["filename"].endswith(".whl"):
                    print(f"Downloading {u['filename']}...")
                    urllib.request.urlretrieve(u["url"], u["filename"])
                    print(f"  OK: {u['filename']}")
                    break
            else:
                print(f"  No wheel found for {pkg}")
    except Exception as e:
        print(f"  FAILED {pkg}: {e}")
