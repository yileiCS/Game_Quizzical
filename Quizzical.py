import requests
import random
import html
from time import sleep
import time
import threading
import curses
from curses_ui import curses_main, QuizUI
from functools import partial
import json
import os
from config import (  
    TIME_ANSWER_MAX,
    RETRY_CHANCE,
    RETRY_DELAY,
    RANKINGBOARD_FILE,
    load_best_score,
    update_best_score,
    update_rankingboard,
    load_rankingboard,
    API_BASIC,
    TOKEN_URL,
    CATEGORY_URL,
    get_session_token,
    fetch_questions,
    get_categories
)

def get_session_token():   # Get the session token
    try:
        response = requests.get(f"{TOKEN_URL}?command=request")   # Request the token from the API
        response.raise_for_status()                               # Raise an exception for bad status codes
        data = response.json()                                    # Get the data from the API
        if data['response_code'] == 0:                            # Check if the response code is 0
            return data['token']                                  # Return the token
        else:
            print("Failed to request token! Response Code:", data['response_code'])
            return None
    except requests.exceptions.RequestException as e:   # Handle the exception if the request fails
        print("Error in requesting token:", str(e))     # Print the error message
        return None   # Return None

def reset_session_token(token):   # Reset the session token
    try:
      response = requests.get(f"{TOKEN_URL}?command=reset&token={token}")
      return response.json()['response_code'] == 0
    except:
      return False
    
def get_categories():  # Get the categories
    try:
        response = requests.get(CATEGORY_URL)
        response.raise_for_status()
        categories = response.json()['trivia_categories']
        return {cat['id']: cat['name'] for cat in categories}
    except:
        return {}

def select_bonus_category():   # Select the bonus category
    categories = get_categories()
    if not categories:
        return None
    selected = random.sample(list(categories.items()), 4)
    print("\nPlease select the bonus category(Get double points for correct answer!):")
    for i, (id, name) in enumerate(selected, 1):   # Display the categories
        print(f"{i}. {name}")
    choice = get_valid_input("Select (1-4): ", 1, 4)
    if choice == 'quit':
        return None
    return selected[choice-1][0]  

def fetch_questions(token, amount=30, difficulty=None, category=None):     # Fetch the questions
    params = {
        'amount': amount,
        'token': token,
        'encode': 'url3986',   # Encode the URL
        'type': 'multiple'
    }
    if difficulty: 
        params['difficulty'] = difficulty
    if category:
        params['category'] = category
    for _ in range(RETRY_CHANCE):  # Retry the request
        try:
            response = requests.get(API_BASIC, params=params)   
            response.raise_for_status()      # Raise an exception for bad status codes
            data = response.json()  
            if data['response_code'] == 0:   # Check if the response code is 0
                valid_questions = []         # Initialize the valid questions list
                for q in data['results']:  
                    if len(q['incorrect_answers']) == 3:
                        valid_questions.append(q)
                if len(valid_questions) >= amount:   # Check if the number of valid questions is greater than or equal to the amount
                    return valid_questions[:amount]   
                else:
                    return valid_questions   
            elif data['response_code'] == 4:   
                if reset_session_token(token):
                    continue
            print(f"Error: Response code {data['response_code']}")
        except requests.exceptions.RequestException as e:   # Handle the exception if the request fails
            print("Error in fetching questions:", str(e))
        time.sleep(RETRY_DELAY)
    return None

def handle_api_errors(code, token):   # Handle the API errors
  errors = {
    1: "No Results 𖦹ࡇ𖦹 (Could not return results. The API doesn't have enough questions for your query.)",
    2: "Invalid Parameters 𖦹ࡇ𖦹 (Contains an invalid parameter. Arguements passed in aren't valid.)",
    3: "Token Not Found 𖦹ࡇ𖦹 (Session Token does not exist.)",
    4: "Token Empty 𖦹ࡇ𖦹 (Session Token has returned all possible questions for the specified query. Resetting the Token is necessary.)",
    5: "Rate Limit 𖦹ࡇ𖦹 (Too many requests have occurred. Each IP can only access the API once every 5 seconds.)"
  }
  print(errors.get(code, f"Unknown error code: {code}"))  
  if code == 3:
    return get_session_token()
  elif code == 4:
    return reset_session_token(token)
  return None

def display_question(q):   # Display the question
  print('\n' + q['question'])
  for i, answer in enumerate(q['answers'], 1):
    print(f"{i}. {answer}")

def get_valid_input(prompt, min_val, max_val):   # Get the valid input
    while True:
        choice = input(prompt).strip().lower()
        if choice == 'q':
            return 'quit'
        if choice in ['p', 'a']:
            return choice
        if choice.isdigit() and min_val <= int(choice) <= max_val:
            return int(choice)
        print(f"Please input {min_val}-{max_val} or q to exit" )
    
def calculate_score(difficulty):   # Calculate the score
    scores = {'easy': 1, 'medium': 2, 'hard': 3}
    return scores.get(difficulty, 1)

def use_hint(question):   # Use the hint
    if question['remaining_hints'] <= 0:   
        return False    
    correct = question['correct']   
    incorrect = [ans for ans in question['answers'] if ans != correct]
    remove_count = len(incorrect) // 2  
    remaining_incorrect = random.sample(incorrect, len(incorrect) - remove_count)   # Remaining incorrect answers
    question['answers'] = remaining_incorrect + [correct]
    random.shuffle(question['answers'])  
    question['remaining_hints'] = 0
    return True

def get_difficulty_choice():   # Get the difficulty choice
    print("\nChoose difficulty for next question:")
    print("1. Easy")
    print("2. Medium")
    print("3. Hard")
    choice = get_valid_input("Select difficulty (1-3): ", 1, 3)   
    if choice == 'quit':  
        return None   
    difficulties = {1: 'easy', 2: 'medium', 3: 'hard'}
    return difficulties[choice]

def display_rankingboard():   # Display the ranking board
    try:
        if not os.path.exists(RANKINGBOARD_FILE):   # Check if the ranking board file exists
            print("\nEmpty Rank Board. No records.")   
            return    
        with open(RANKINGBOARD_FILE, 'r') as f:     # Open the ranking board file
            leaders = json.load(f)    
        print("\n🏆 Ranking Board 🏆")
        for i, entry in enumerate(leaders, 1):   
            print(f"{i}. {entry['name']}: {entry['score']}分")
    except:
        print("Failed to load Ranking Board")

def game_loop(questions, bonus_category):   # Game loop
    score = 0
    wrong = 0
    best_score = load_best_score()
    time_left = TIME_ANSWER_MAX
    timer_paused = False
    pause_available = True
    host_ask_available = True
    def countdown():   # Countdown
        nonlocal time_left
        while time_left > 0 and not timer_paused:
            sleep(1)
            time_left -= 1
        if time_left <= 0:
            print("\nTime's up！")
    timer = threading.Thread(target=countdown)   # Create a thread for the countdown
    timer.start()
    for i, q in enumerate(questions, 1):  # Process the question
        processed = process_question(q, bonus_category)    
        if i < len(questions):
            difficulty = get_difficulty_choice()
            if not difficulty:
                break
        print(f"\nCurrent Score: {score} | Best Score: {best_score}")
        print(f"Question Difficulty: {processed['difficulty'].upper()}")
        display_question(processed)
        start_time = time.time()
        print("\nOptions:")
        print("Enter number to answer")
        print("H: Use hint (remove half of wrong answers)")
        print("Q: Quit game")
        print("P: Pause timer (Chance Remaining: {})".format(1 if pause_available else 0))
        print("A: Ask host (Chance Remaining: {})".format(1 if host_ask_available else 0))
        while True:   # Input the choice
            choice = input("Your choice: ").strip().lower()    
            if choice == 'h':   
                if use_hint(processed):
                    print("\nHint used! New options:")
                    display_question(processed)
                else:
                    print("No hints remaining!")
                continue    
            if choice == 'q':   # Quit the game
                return score   
            if choice == 'p' and pause_available:  # Pause the timer
                timer_paused = True
                time_left += 60
                pause_available = False
                print(f"Time paused, remaining time: {time_left} seconds")
                sleep(2)
                timer_paused = False
                continue
            if choice == 'a' and host_ask_available:   # Ask the host
                host_ask_available = False
                confidence = random.random()
                difficulty = processed['difficulty']    
                if difficulty == 'easy':   
                    correct_chance = 0.8
                elif difficulty == 'medium':   
                    correct_chance = 0.5
                else:
                    correct_chance = 0.3        
                if confidence < correct_chance:   # Host's confidence setting
                    answer = processed['correct']
                    print(f"Host said: I'm sure the answer is {answer}！（Confidence: {confidence*100:.0f}%）")
                else:
                    if random.random() < 0.5:
                        wrong = random.choice([a for a in processed['answers'] if a != processed['correct']])
                        print(f"Host said: Maybe it's {wrong}...（Confidence: {confidence*100:.0f}%）")
                    else:
                        print("Host said: I have no idea...")
                continue
            if choice.isdigit() and 1 <= int(choice) <= len(processed['answers']):   
                choice = int(choice)
                break        
            print(f"Please enter 1-{len(processed['answers'])}, H for hint, or Q to quit")
        end_time = time.time()
        question_time = end_time - start_time    
        if processed['answers'][choice-1] == processed['correct']:   # Correct answer
            points = calculate_score(processed['difficulty'])
            if processed['is_bonus']:
                points *= 2
                print("Double points for bonus category!")
            score += points
            print(f"Correct! ᖰ⌯'▾'⌯ᖳ (+{points} points)")
            print(f"Time taken: {question_time:.1f} seconds")
        else:
            wrong += 1
            print(f"Wrong! 😑\nThe answer is: {processed['correct']}")
            print(f"Time taken: {question_time:.1f} seconds")
            
            if wrong >= 3:   # Game over if wrong answers exceed 3
                print("Game Over! 🫠\nToo many errors.")
                return 0    
        if score > best_score:   # Update best score
            best_score = score
            update_best_score(best_score)    
        if i < len(questions):   # Continue to next question
            cont = input("Continue to next question? (y/n)").lower()
            if cont != 'y':
                break
    if question_time:   # Show statistics
        avg_time = question_time
        fastest = avg_time
        slowest = avg_time
        print("\nGame Statistics:")
        print(f"Average time per question: {avg_time:.1f} seconds")
        print(f"Fastest answer: {fastest:.1f} seconds")
        print(f"Slowest answer: {slowest:.1f} seconds") 
    name = input("Please enter your name to record the score on the board: ")[:20]
    update_rankingboard(name, score)   # Update the ranking board
    display_rankingboard()             # Display the ranking board
    return score

def process_question(raw_question, bonus_category=None):   # Process the question
    if not raw_question or 'incorrect_answers' not in raw_question:
        return None   
    if len(raw_question['incorrect_answers']) != 3:
        return None  
    return {
        'category': raw_question['category'],
        'question': html.unescape(raw_question['question']),
        'answers': random.sample(
            [html.unescape(ans) for ans in raw_question['incorrect_answers']] + 
            [html.unescape(raw_question['correct_answer'])],
            4
        ),
        'correct': html.unescape(raw_question['correct_answer']), 
        'difficulty': raw_question['difficulty'],
        'remaining_hints': 1,
        'is_bonus': bonus_category and (raw_question['category'] == bonus_category)
    }

def main():  
    print(f"""
    ---------------------------------
      Quizzical - Version 2025.0
      Produced by 240021230 for assessment 1 of CS5003
    ---------------------------------
    """)
    print("\n⚠️ Please MAXIMIZE the TERMINAL WINDOW!")   # Reminder before starting the game
    print("\n⚠️ Make sure to MAXIMAZE the terminal size to ensure the game interface display correctly.")
    print("\n⚠️ Press ENTER to continue...")
    input()
    token = get_session_token()   # Get the session token
    if not token:
        print("Unable to connect to the server, please check the network")
        return
    while True:  # Main game loop
        user_input = input("\nPress ENTER to start the game 👾 (or Q to quit) ")
        if user_input.lower() == 'q':
            break
        categories = get_categories()     # Get the categories
        if not categories:
            print("Failed to get categories")
            continue   
        selected = random.sample(list(categories.items()), 4)
        
        def select_bonus_category_curses(stdscr):   # Select the bonus category
            ui = QuizUI(stdscr)
            return ui.show_bonus_category_selection(selected)
        choice = curses.wrapper(select_bonus_category_curses)
        if not choice:
            continue   
        bonus_category = selected[choice-1][0]
        questions = fetch_questions(token, amount=30, category=bonus_category)   # Fetch the questions
        if not questions:
            token = get_session_token()
            questions = fetch_questions(token, amount=30, category=bonus_category)
            if not questions:
                print("Failed to obtain questions, please try again later")
                continue
        if len(questions) == 0:
            print("No valid questions received")
            continue
        game_state = {   
            'questions': questions,
            'bonus_category': bonus_category,
            'best_score': load_best_score(),
            'time_left': TIME_ANSWER_MAX,
            'hints_remaining': 1,   
            'pauses_remaining': 1,
            'score': 0
        }
        final_score = curses.wrapper(partial(
            curses_main,
            game_logic=game_state,
            process_question=process_question,
            calculate_score=calculate_score
        ))
        print(f"\nFinal Score: {final_score}")
        if input("\nPlay again? (y/n)").lower() != 'y':
            break

if __name__ == "__main__":
    main()