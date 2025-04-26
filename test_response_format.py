import requests
import json

def test_response_format():
    print("Testing response format from /scrape endpoint...")
    try:
        response = requests.post(
            "http://localhost:5000/scrape",
            json={
                "url": "https://www.example.com",
                "method": "static",
                "elements": ["title", "headings", "text", "links", "images", "tables"]
            },
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Status code: {response.status_code}")
        result = response.json()
        print("Response structure:")
        print(json.dumps(result, indent=2))
        
        # Check if the response has the expected structure
        if "success" in result:
            print(f"Success field present: {result['success']}")
        else:
            print("Success field missing!")
            
        if "data" in result:
            print("Data field present")
        else:
            print("Data field missing!")
            
        return True
    except Exception as e:
        print(f"Error: {str(e)}")
        return False

if __name__ == "__main__":
    test_response_format() 