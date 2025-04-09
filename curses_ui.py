import curses
import time
from functools import partial
import urllib.parse
import random
from config import (
    TIME_ANSWER_MAX,
    load_best_score,
    update_best_score,
    update_rankingboard,
    load_rankingboard,
    fetch_questions,
    get_session_token,
    get_categories
)

class QuizUI:
    COLORS = {
        'normal': 1,
        'correct': 2,
        'wrong': 3,
        'highlight': 4,
        'timer': 5
    }

    def __init__(self, stdscr):   # Initialize the UI
        self.stdscr = stdscr
        self.init_colors()
        self.win_height, self.win_width = stdscr.getmaxyx()
        self.current_selection = 0
        self.input_buffer = ''
        self.options = []
        self.current_score = 0
        self.best_score = 0
        self.current_question = ""
        self.hints_remaining = 1
        self.pauses_remaining = 1
        self.current_message = None  
        self.message_color = 'normal'  
        self.time_left = 0  
        self.timer = None
        self.stop_timer = False 

    def init_colors(self):   # Initialize the colors 
        curses.start_color()
        curses.init_pair(self.COLORS['normal'], curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(self.COLORS['correct'], curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(self.COLORS['wrong'], curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(self.COLORS['highlight'], curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(self.COLORS['timer'], curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.A_STRIKE = curses.A_UNDERLINE  

    def draw_header(self, score, best_score, time_left):  
        title = [
            " ██████  ██    ██ ██ ███████ ███████ ██  ██████  █████  ██      ",
            "██    ██ ██    ██ ██    ███     ███  ██ ██      ██   ██ ██      ",
            "██    ██ ██    ██ ██   ███     ███   ██ ██      ███████ ██      ",
            "██ ▄▄ ██ ██    ██ ██  ███     ███    ██ ██      ██   ██ ██      ",
            " ██████   ██████  ██ ███████ ███████ ██  ██████ ██   ██ ███████ ",
            "    ▀▀                                                       "
        ]
        title_height = len(title)   # Title height
        for i, line in enumerate(title):
            start_x = (self.win_width - len(line)) // 2
            self.stdscr.addstr(1 + i, start_x, line, curses.color_pair(self.COLORS['highlight']))
        score_y = title_height + 3   # Score y position
        info_line = f"Score: {score} | Best: {best_score} | Time: {time_left:.2f}s"
        start_x = (self.win_width - len(info_line)) // 2
        self.stdscr.addstr(score_y, start_x, info_line, curses.color_pair(self.COLORS['normal']) | curses.A_BOLD)
        self.stdscr.hline(score_y + 1, 0, curses.ACS_HLINE, self.win_width)

    def draw_question(self, question, options):   # Draw the question
        if not question or not options:
            return
        self.options = options
        title_height = 6   
        score_height = 2
        padding = 3
        question_start_y = title_height + score_height + padding
        try:   # Decode the question and wrap the text
            decoded_question = urllib.parse.unquote(question)
            question_lines = self.wrap_text(decoded_question, self.win_width - 4)
            for i, line in enumerate(question_lines):  # Draw the question
                if question_start_y + i < self.win_height - 15:
                    self.stdscr.addstr(question_start_y + i, 2, line, 
                                     curses.color_pair(self.COLORS['normal']))
            options_start = question_start_y + len(question_lines) + 2   # Options start position
            for idx, opt in enumerate(options):   # Draw the options
                if options_start + idx < self.win_height - 12:
                    color = self.COLORS['highlight'] if idx == self.current_selection else self.COLORS['normal']
                    decoded_opt = urllib.parse.unquote(opt)
                    option_text = f"{idx+1}. {decoded_opt}"
                    if len(option_text) > self.win_width - 6:   # If the option text is too long, truncate it
                        option_text = option_text[:self.win_width - 10] + "..."
                    if hasattr(self, 'removed_options') and opt in self.removed_options:
                        option_text = f"✗ {option_text}"    # Add ✗ mark for removed options
                        color = self.COLORS['wrong']
                    
                    self.stdscr.addstr(options_start + idx, 4, option_text,   
                                     curses.color_pair(color))
        except curses.error:
            pass

    def draw_footer(self, hints_remaining, pauses_remaining):   # Draw the footer
        controls = [
            "┌─────────────────────── CONTROLS ────────────────────┐",
            "│  ↑/↓ - Navigate   |   A - Ask Host  |   Q - Quit    │",
            "│  Enter - Select   |   H - Hint      |   P - Pause   │",
            "└─────────────────────────────────────────────────────┘",
            f"Hints remaining: {hints_remaining} | Pauses remaining: {pauses_remaining}"
        ]
        production_info = [
            "─" * self.win_width,
            "Produced by 240021230 for assessment 1 of CS5003"
        ]
        controls_start_y = self.win_height - len(controls) - len(production_info) - 2   # Controls start position
        for i, line in enumerate(controls):                                             # Draw the controls panel
            start_x = (self.win_width - len(line)) // 2
            self.stdscr.addstr(controls_start_y + i, start_x, line, curses.color_pair(self.COLORS['normal']))
        for i, line in enumerate(production_info):                                      # Draw the production info
            y_pos = self.win_height - len(production_info) + i
            if i == 0:  
                self.stdscr.addstr(y_pos, 0, line, curses.color_pair(self.COLORS['normal']))
            else:  
                start_x = (self.win_width - len(line)) // 2
                self.stdscr.addstr(y_pos, start_x, line, curses.color_pair(self.COLORS['normal']) | curses.A_BOLD)

    def start_timer(self):                              # Start the timer
        import threading
        self.stop_timer = True                          # Stop the former timer
        if self.timer and self.timer.is_alive():
            self.timer.join()
        self.stop_timer = False
        def timer_thread():                             # Timer thread
            while not self.stop_timer and self.time_left > 0:
                time.sleep(1)  
                if not self.stop_timer and not self.pause_timer:
                    self.time_left -= 1  
        self.timer = threading.Thread(target=timer_thread)
        self.timer.daemon = True
        self.pause_timer = False
        self.timer.start()

    def get_input(self, timeout):   # Get the input
        self.time_left = timeout  
        self.start_timer()  
        self.stdscr.nodelay(True)   # Enable non-blocking input
        last_refresh = time.time()
        refresh_interval = 0.1  
        while True:
            if self.time_left <= 0:   # If the timer is up, refresh the screen and stop the timer
                self._refresh_screen(0)  
                time.sleep(1)  
                self.stop_timer = True  
                return None
            try:
                key = self.stdscr.getch()    # Get the input
                current_time = time.time()   # Current time
                if current_time - last_refresh >= refresh_interval:   # Refresh the screen if the interval has passed
                    self._refresh_screen(self.time_left)
                    last_refresh = current_time
                if key != -1:   
                    if key == curses.KEY_UP:  
                        self.current_selection = max(0, self.current_selection - 1)
                        self._refresh_screen(self.time_left)
                    elif key == curses.KEY_DOWN:   # Move down
                        self.current_selection = min(len(self.options) - 1, self.current_selection + 1)
                        self._refresh_screen(self.time_left)
                    elif key == curses.KEY_ENTER or key in [10, 13]:   # Select the option
                        self.stop_timer = True
                        return self.current_selection + 1
                    elif key == ord('q') or key == ord('Q'):   # Quit the game
                        self.stop_timer = True
                        return 'quit'
                    elif key == ord('h') or key == ord('H'):   # Use hint
                        return 'hint'
                    elif key == ord('p') or key == ord('P'):   # Pause the timer
                        return 'pause'
                    elif key == ord('a') or key == ord('A'):   # Ask the host
                        return 'ask'
                    self._refresh_screen(self.time_left)
                time.sleep(0.01)  
            except curses.error:
                continue

    def _refresh_screen(self, remaining):   # Refresh the screen
        try:   
            self.stdscr.erase()
            self.draw_header(self.current_score, self.best_score, remaining)   
            self.draw_question(self.current_question, self.options)
            self.draw_inline_message()
            self.draw_footer(self.hints_remaining, self.pauses_remaining)
            self.stdscr.noutrefresh()
            curses.doupdate()
        except curses.error:   # Ignore the error
            pass

    def show_message(self, message, color='normal', wait_time=1):   # Show the message
        self.stdscr.clear()
        lines = message.split('\n')
        for idx, line in enumerate(lines):
            y = self.win_height//2 - len(lines)//2 + idx
            x = self.win_width//2 - len(line)//2
            self.stdscr.addstr(y, x, line, curses.color_pair(self.COLORS[color]))
        self.stdscr.refresh()
        time.sleep(wait_time)  

    def show_inline_message(self, message, color='normal'):   # Show the inline message
        self.current_message = message
        self.message_color = color
        self._refresh_screen(self.time_left)  

    def show_difficulty_choice(self):   # Show the difficulty choice
        self.stdscr.clear()
        message = [
            "Choose difficulty for next question:",
            "",
            "1.Easy   ｜   2.Medium   ｜   3.Hard",
            "",
            "(Use number keys to select)"
        ]
        for idx, line in enumerate(message):   # Draw the message
            y = self.win_height//2 - len(message)//2 + idx
            x = self.win_width//2 - len(line)//2
            self.stdscr.addstr(y, x, line, curses.color_pair(self.COLORS['normal']))
        self.stdscr.refresh()   # Refresh the screen
        while True:   # Wait for user to select the difficulty
            try:
                key = self.stdscr.getch()   # Get the input
                if key in [ord('1'), ord('2'), ord('3')]:
                    difficulties = {ord('1'): 'easy', ord('2'): 'medium', ord('3'): 'hard'}
                    return difficulties[key]
                elif key == ord('q'):
                    return None
            except curses.error:   
                continue

    def show_ranking_board(self, rankings, start_y=None):   
        self.stdscr.clear()
        if start_y is None:
            start_y = self.win_height//2 - 10  # Display from the middle to the top of the screen
        title = "🏆 RANKING BOARD 🏆"
        self.stdscr.addstr(start_y, (self.win_width - len(title))//2, title, 
                          curses.color_pair(self.COLORS['highlight']) | curses.A_BOLD)
        header = "Rank  |  Name                |  Score"
        self.stdscr.addstr(start_y + 2, (self.win_width - len(header))//2, header, 
                          curses.color_pair(self.COLORS['normal']))
        separator = "─" * 40
        self.stdscr.addstr(start_y + 3, (self.win_width - len(separator))//2, separator, 
                          curses.color_pair(self.COLORS['normal']))
        if not rankings:   # If the rankings are not loaded
            rankings = [{'name': 'No records', 'score': 0}]
        for idx, entry in enumerate(rankings[:10], 1):  # Display the top 10 players
            name = entry.get('name', 'Anonymous')[:20]  # Limit the username length
            score = int(entry.get('score', 0))
            rank_text = f"{idx:2d}    |  {name:<20}|  {score:5d}"  # Draw the rank text
            y = start_y + 4 + idx
            if y < self.win_height - 3:
                self.stdscr.addstr(y, (self.win_width - len(rank_text))//2, rank_text, 
                                 curses.color_pair(self.COLORS['normal']))
        prompt = "Press to continue..."   
        self.stdscr.addstr(self.win_height-2, (self.win_width - len(prompt))//2, prompt, 
                          curses.color_pair(self.COLORS['normal']))
        self.stdscr.refresh()
        self.stdscr.getch()  

    @staticmethod   # Wrap the text
    def wrap_text(text, width):  
        words = text.split()
        lines = []
        current_line = []
        current_length = 0
        for word in words:   
            if current_length + len(word) + 1 > width:   
                lines.append(' '.join(current_line))
                current_line = [word]
                current_length = len(word)
            else:  
                current_line.append(word)
                current_length += len(word) + 1
        if current_line:  
            lines.append(' '.join(current_line))
        return lines

    def get_user_name(self):
        self.stdscr.clear()
        prompt = "Enter your name (max 20 chars): "
        y = self.win_height // 2
        x = (self.win_width - len(prompt)) // 2
        self.stdscr.addstr(y, x, prompt, curses.color_pair(self.COLORS['highlight']))
        name = ""
        curses.echo()  # Display user's input
        while True:
            try:
                char = self.stdscr.getch()
                if char == ord('\n'):                    # Enter
                    break
                elif char == ord('\b') or char == 127:   # Backspace
                    if name:
                        name = name[:-1]
                        self.stdscr.addstr(y, x + len(prompt), " " * 20)  # clear the current display 
                        self.stdscr.addstr(y, x + len(prompt), name)
                elif len(name) < 20:                                      # limitation for the name length
                    name += chr(char)
                    self.stdscr.addstr(y, x + len(prompt), name)
            except:
                pass
        curses.noecho()  # Close the echo
        return name.strip() if name.strip() else "Anonymous"

    def show_game_over(self, final_score):   
        self.stdscr.clear()
        messages = [
            "Game Over! 🫠",
            f"Final Score: {final_score}",
            "",
            "Play again? (Y/N)"
        ]
        for idx, msg in enumerate(messages):   # Draw the message when game over
            y = self.win_height//2 - len(messages)//2 + idx  
            x = self.win_width//2 - len(msg)//2
            self.stdscr.addstr(y, x, msg, curses.color_pair(self.COLORS['normal']))   
        self.stdscr.refresh()  
        while True:   # Wait for user to select whether to restart
            try:
                key = self.stdscr.getch()
                if key in [ord('y'), ord('Y')]:
                    return True
                elif key in [ord('n'), ord('N')]:
                    return False
            except curses.error:
                continue

    def show_hint(self, correct_answer, all_answers):                                   # Show the hint
        incorrect_answers = [ans for ans in all_answers if ans != correct_answer]       # Get all incorrect answers
        to_remove = random.sample(incorrect_answers, 2)                                 # Randomly select two wrong answers to mark
        self.removed_options = to_remove                                                # Store removed options
        self.show_inline_message("Hint: ✗ marks indicate wrong answers", 'highlight')   # Show the hint
        return to_remove

    def show_bonus_category_selection(self, categories):   # Show the bonus category selection
        self.stdscr.clear()   
        messages = [
            "Please select the bonus category",
            "(Get double points for correct answer!)",
            "",
        ]
        for i, (id, name) in enumerate(categories, 1):   # Draw the message
            messages.append(f"{i}. {name}")
        messages.extend(["", "(Use number keys to select)"])
        for idx, msg in enumerate(messages):   # Draw the message
            y = self.win_height//2 - len(messages)//2 + idx
            x = self.win_width//2 - len(msg)//2
            self.stdscr.addstr(y, x, msg, curses.color_pair(self.COLORS['normal']))
        self.stdscr.refresh()
        while True:   # Wait for user to select the bonus category
            try:    
                key = self.stdscr.getch() 
                if key in [ord('1'), ord('2'), ord('3'), ord('4')]: 
                    return int(chr(key))
            except curses.error:
                continue

    def draw_inline_message(self):   # Draw the inline message
        if self.current_message:
            title_height = 6
            score_height = 2
            padding = 3
            question_lines = self.wrap_text(self.current_question, self.win_width - 4)
            options_height = len(self.options)
            message_y = title_height + score_height + padding + len(question_lines) + options_height + 3   
            if message_y < self.win_height - 5:
                self.stdscr.addstr(message_y, 4, self.current_message,
                                 curses.color_pair(self.COLORS[self.message_color]))

def curses_main(stdscr, game_logic, process_question, calculate_score):   # Main function
    while True:               # Game loop
        ui = QuizUI(stdscr)   # Initialize the UI
        curses.curs_set(0)    # Hide the cursor
        score = 0             # Initialize the score
        wrong_answers = 0     # Initialize the wrong answers
        while wrong_answers < 3:  
            if not game_logic['questions']:   # If the questions are not loaded
                token = get_session_token()
                if not token:
                    ui.show_message("Failed to get token!", 'wrong')
                    return score
                categories = get_categories()   # Get the categories
                if not categories:              # If the categories are not loaded
                    ui.show_message("Failed to get categories!", 'wrong')
                    return score
                selected = random.sample(list(categories.items()), 4)   # Randomly select 4 categories
                choice = ui.show_bonus_category_selection(selected)     # Show the bonus category selection
                if not choice:                                          # If the choice is not made
                    return score
                bonus_category = selected[choice-1][0]   # Get the bonus category
                game_logic['questions'] = fetch_questions(token, amount=30, category=bonus_category)
                if not game_logic['questions']:          # If the questions are not loaded
                    ui.show_message("Failed to get questions!", 'wrong')
                    return score
            processed = process_question(game_logic['questions'].pop(0))   # Process the question
            processed['is_bonus'] = processed.get('category') == game_logic.get('bonus_category')
            ui.time_left = TIME_ANSWER_MAX   # Set the time left
            if len(game_logic['questions']) > 0:
                difficulty = ui.show_difficulty_choice()
                if not difficulty:  # If the user chooses to exit
                    return score
                game_logic['questions'][0]['difficulty'] = difficulty 
            ui.current_message = None  # Clear the previous message
            while True:  # Handle hint/pause etc. commands
                ui.stdscr.clear()
                ui.current_score = score                               # Set the current score
                ui.best_score = game_logic['best_score']               # Set the best score
                ui.current_question = processed['question']            # Set the current question
                ui.hints_remaining = game_logic['hints_remaining']     # Set the hints remaining
                ui.pauses_remaining = game_logic['pauses_remaining']   # Set the pauses remaining
                ui.draw_header(score, game_logic['best_score'], ui.time_left)   # Draw the header
                ui.draw_question(processed['question'], processed['answers'])   # Draw the question
                ui.draw_footer(game_logic['hints_remaining'], game_logic['pauses_remaining'])   # Draw the footer
                ui.stdscr.refresh()
                
                choice = ui.get_input(ui.time_left)   # Use the current remaining time
                if choice == 'quit':   # Handle the quit command
                    return score
                elif choice == 'hint' and game_logic['hints_remaining'] > 0:   # Handle the hint command
                    game_logic['hints_remaining'] -= 1
                    removed = ui.show_hint(processed['correct'], processed['answers'])
                    ui._refresh_screen(ui.time_left)   # Refresh the screen when hint is used
                    continue   
                elif choice == 'pause' and game_logic['pauses_remaining'] > 0:   # Handle the pause command
                    game_logic['pauses_remaining'] -= 1
                    ui.pause_timer = True
                    ui.show_message("Game paused for 60 seconds...", 'highlight')   # Show the message when paused
                    start_time = time.time()
                    while time.time() - start_time < 60:
                        ui.stdscr.addstr(ui.win_height - 2, 2, f"Time remaining: {60 - int(time.time() - start_time)}s", 
                                        curses.color_pair(ui.COLORS['timer']))
                        ui.stdscr.refresh()
                        time.sleep(1)
                    ui.pause_timer = False
                    ui.current_message = None
                    continue   
                elif choice == 'ask':   # Handle the ask command
                    difficulty = processed.get('difficulty', 'medium')   # Get the difficulty
                    confidence = {'easy': 0.8, 'medium': 0.5, 'hard': 0.3}[difficulty]   # Get the confidence
                    if random.random() < confidence:
                        decoded_answer = urllib.parse.unquote(processed['correct'])   # Decode the answer
                        message = f"Host: I'm {int(confidence*100)}% sure it's '{decoded_answer}'"
                    else:   # If the answer is not correct
                        incorrect_answers = [a for a in processed['answers'] if a != processed['correct']]   # Get all incorrect answers
                        if random.random() < 0.5:   # If the random number is less than 0.5
                            wrong = random.choice(incorrect_answers)   # Randomly select a wrong answer
                            message = f"Host: I think it's '{urllib.parse.unquote(wrong)}' but I'm not sure..."
                        else:
                            message = "Host: Sorry, I have no idea..."
                    ui.show_inline_message(message, 'highlight')
                    ui._refresh_screen(ui.time_left)
                    continue
                else:
                    break  # Handle normal answer selection
            ui.current_message = None   # Clear the current message
            if choice and isinstance(choice, int) and 1 <= choice <= len(processed['answers']):   # If the choice is valid
                if processed['answers'][choice-1] == processed['correct']:                        # If the answer is correct
                    points = calculate_score(processed['difficulty'])                             # Calculate the points
                    if processed.get('is_bonus'):                                                 # If the answer is a bonus answer
                        points *= 2                                                               # Double the points
                    score += points                                                               # Add the points to the score
                    ui.show_message(f"Correct! ᖰ⌯'▾'⌯ᖳ (+{points} points)", 'correct')             # Show the message when the answer is correct
                else:
                    wrong_answers += 1
                    ui.show_message(f"Wrong! 😑\nThe answer is: {urllib.parse.unquote(processed['correct'])}", 
                                  'wrong')
            if wrong_answers >= 3:   # When game over
                # 1. Display the game over message
                ui.stdscr.clear()
                game_over_msg = [
                    " ██████   █████  ███    ███ ███████     ██████  ██    ██ ███████ ██████  ",
                    "██       ██   ██ ████  ████ ██          ██   ██ ██    ██ ██      ██   ██ ",
                    "██   ███ ███████ ██ ████ ██ █████       ██   ██ ██    ██ █████   ██████  ",
                    "██    ██ ██   ██ ██  ██  ██ ██          ██   ██  ██  ██  ██      ██   ██ ",
                    " ██████  ██   ██ ██      ██ ███████     ██████    ████   ███████ ██   ██ ",
                    ""
                ]
                for idx, msg in enumerate(game_over_msg):
                    y = idx + 2
                    x = ui.win_width//2 - len(msg)//2
                    ui.stdscr.addstr(y, x, msg, curses.color_pair(ui.COLORS['wrong']) | curses.A_BOLD)
                # 2. Display the final score for this turn
                final_score_msg = f"Final Score: {score}"
                y = len(game_over_msg) + 4
                x = ui.win_width//2 - len(final_score_msg)//2
                ui.stdscr.addstr(y, x, final_score_msg, curses.color_pair(ui.COLORS['highlight']))
                # 3. Wait for user confirmation
                continue_msg = "Press any key to continue..."
                y = len(game_over_msg) + 6
                x = ui.win_width//2 - len(continue_msg)//2
                ui.stdscr.addstr(y, x, continue_msg, curses.color_pair(ui.COLORS['normal']))
                ui.stdscr.refresh()
                # 4. Wait for user key press
                while True:
                    try:
                        key = ui.stdscr.getch()
                        if key != -1:
                            break
                    except curses.error:
                        continue
                # 5. Get the user name and update the ranking board
                name = ui.get_user_name()
                if name:
                    update_rankingboard(name, score)
                # 5. Display the ranking board
                rankings = load_rankingboard()
                ui.show_ranking_board(rankings)
                # 6. Ask if the user wants to play again
                restart_msg = "Play again? (Y/N)"
                y = ui.win_height - 3
                x = ui.win_width//2 - len(restart_msg)//2
                ui.stdscr.addstr(y, x, restart_msg, curses.color_pair(ui.COLORS['highlight']))
                ui.stdscr.refresh()
                while True:
                    key = ui.stdscr.getch()
                    if key in [ord('y'), ord('Y')]:
                        game_logic['questions'] = []
                        game_logic['hints_remaining'] = 1
                        game_logic['pauses_remaining'] = 1
                        wrong_answers = 0
                        score = 0
                        ui.current_message = None
                        ui.current_selection = 0
                        break
                    elif key in [ord('n'), ord('N')]:
                        return score
                
                if wrong_answers == 0:  # If the game has been reset, continue
                    continue