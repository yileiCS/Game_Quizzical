import requests
API_BASIC = "https://opentdb.com/api.php"
TOKEN_URL = "https://opentdb.com/api_token.php"
CATEGORY_URL = "https://opentdb.com/api_category.php"
TIME_ANSWER_MAX = 20
RETRY_CHANCE = 3
RETRY_DELAY = 1
SCORE_FILE = 'best_score.txt'
RANKINGBOARD_FILE = 'rankingboard.json'

def load_best_score():   # Load the best score from the file
    try:
        with open(SCORE_FILE, 'r') as f:
            return int(f.read().strip())
    except:
        return 0

def update_best_score(score):   # Update the best score to the file
    current_best = load_best_score()
    if score > current_best:
        with open(SCORE_FILE, 'w') as f:
            f.write(str(score))
        return score
    return current_best

def update_rankingboard(name, score):   # Update the ranking board to the file
    import json
    import os
    try:
        leaders = []  # Initialize the leaders list
        if os.path.exists(RANKINGBOARD_FILE):
            with open(RANKINGBOARD_FILE, 'r') as f:
                leaders = json.load(f)
        leaders.append({'name': name, 'score': score})  # Append the new score to the leaders list
        leaders = sorted(leaders, key=lambda x: x['score'], reverse=True)[:10]
        with open(RANKINGBOARD_FILE, 'w') as f:
            json.dump(leaders, f)
    except Exception as e:
        print(f"Failed to update Ranking Board: {str(e)}")

def load_rankingboard():   # Load the ranking board from the file
    import json
    import os
    try:
        if os.path.exists(RANKINGBOARD_FILE):
            with open(RANKINGBOARD_FILE, 'r') as f:
                return json.load(f)
        return []
    except:
        return []

def get_session_token():   # Get the session token from the API
    try:
        response = requests.get(f"{TOKEN_URL}?command=request")
        response.raise_for_status()
        data = response.json()
        if data['response_code'] == 0:
            return data['token']
        else:
            print("Failed to request token! Response Code:", data['response_code'])
            return None
    except requests.exceptions.RequestException as e:
        print("Error in requesting token:", str(e))
        return None

def fetch_questions(token, amount=30, category=None):   # Fetch the questions from the API
    pass

def get_categories():                          # Get the categories from the API
    try:
        response = requests.get(CATEGORY_URL)  
        response.raise_for_status()            # Raise an exception for bad status codes
        data = response.json()                 # Get the data from the API
        categories = {}
        for category in data['trivia_categories']:   
            categories[category['id']] = category['name']
        return categories
    except requests.exceptions.RequestException as e:   # Handle the exception if the request fails
        print("Error in fetching categories:", str(e))
        return None 