import os
import base64
import json
import random
import firebase_admin
from firebase_admin import credentials, firestore
import chess
from stockfish import Stockfish

STOCKFISH_PATH = "/usr/games/stockfish"  # Default path in GitHub Actions runner; change if needed.

def get_firestore_client():
    b64_creds = os.environ.get('FIREBASE_CREDENTIALS')
    if not b64_creds:
        raise RuntimeError("FIREBASE_CREDENTIALS environment variable is missing")
    service_account_info = base64.b64decode(b64_creds).decode("utf-8")
    service_account_dict = json.loads(service_account_info)
    cred = credentials.Certificate(service_account_dict)
    firebase_admin.initialize_app(cred)
    return firestore.client()

def get_grandmaster_names(db):
    gm_names = []
    try:
        metadata_ref = db.collection('metadata')
        docs = metadata_ref.stream()
        for doc in docs:
            data = doc.to_dict()
            name = data.get('name')
            if name:
                gm_names.append(name)
    except Exception as e:
        print(f"Error fetching grandmaster names: {e}")
    return gm_names

def find_mate_in_n(stockfish, n):
    # Try random positions until a mate in n is found
    tries = 0
    while tries < 1000:
        board = chess.Board()
        for _ in range(random.randint(6, 16)):
            if board.is_game_over():
                break
            moves = list(board.legal_moves)
            board.push(random.choice(moves))
        if board.is_game_over():
            tries += 1
            continue

        stockfish.set_fen_position(board.fen())
        info = stockfish.get_top_moves(1)
        if info and info[0].get("Mate") == n:
            solution_moves = []
            temp_board = board.copy()
            for _ in range(n):
                move = stockfish.get_best_move()
                if not move:
                    break
                solution_moves.append(move)
                temp_board.push(chess.Move.from_uci(move))
                stockfish.set_fen_position(temp_board.fen())
            if temp_board.is_checkmate() and len(solution_moves) == n:
                return board.fen(), solution_moves
        tries += 1
    raise Exception(f"Could not generate mate in {n} puzzle after 1000 tries")

def generate_title_description(mate_type, gm_names):
    gm_name = random.choice(gm_names) if gm_names else "Unknown Grandmaster"
    title = f"{gm_name} - {mate_type.capitalize()}"
    description = f"A chess puzzle ({mate_type}) inspired by {gm_name}."
    return title, description

def upload_puzzle_and_solution():
    db = get_firestore_client()
    gm_names = get_grandmaster_names(db)

    stockfish = Stockfish(path=STOCKFISH_PATH, parameters={"Threads": 2, "Minimum Thinking Time": 30})

    n = random.choice([1, 2, 3])
    mate_type = f"mate in {n}"

    try:
        fen, solution_moves = find_mate_in_n(stockfish, n)
    except Exception as e:
        print(f"Error generating puzzle: {e}")
        return

    title, description = generate_title_description(mate_type, gm_names)

    puzzle_doc = {
        'title': title,
        'description': description,
        'fen': fen,
        'mate_type': mate_type,
        'created_by': 'github-action',
        'source': 'stockfish',
    }
    try:
        puzzle_ref = db.collection('puzzles').add(puzzle_doc)
        puzzle_id = puzzle_ref[1].id
        print(f"Puzzle uploaded with ID: {puzzle_id}")
    except Exception as e:
        print(f"Error uploading puzzle: {e}")
        return

    solution_doc = {
        'puzzle_id': puzzle_id,
        'solution_moves': solution_moves,
        'mate_type': mate_type,
        'fen': fen,
    }
    try:
        db.collection('solutions').add(solution_doc)
        print(f"Solution uploaded for puzzle ID: {puzzle_id}")
    except Exception as e:
        print(f"Error uploading solution: {e}")

if __name__ == "__main__":
    upload_puzzle_and_solution()
