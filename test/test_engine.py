import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stratecorum_terminal.bot import execute_bot_step
from stratecorum_terminal.engine import CLUBS, HEARTS, SPADES, Card, GameEngine, Shield


def life(engine: GameEngine, rank: str):
    card = engine.make_card(HEARTS, rank, is_life=True, face_up=True)
    return card


def spade(engine: GameEngine, rank: str):
    return engine.make_card(SPADES, rank)


def test_start_game_shape():
    engine = GameEngine(random.Random(1))
    engine.start_game(initial_lives=6, include_jokers=True)
    assert len(engine.state.players) == 2
    assert len(engine.state.players[0].lives) == 6
    assert len(engine.state.players[1].lives) == 6
    assert len(engine.state.players[0].hand) == 5
    assert len(engine.state.players[1].hand) == 6
    assert engine.state.actions_left == 3


def test_combo_attack_kills_and_moves_to_graveyard():
    engine = GameEngine(random.Random(2))
    engine.start_game()
    p0, p1 = engine.state.players
    p0.hand = [spade(engine, "5"), spade(engine, "5")]
    p1.lives = [life(engine, "9")]

    assert engine.execute_attack([(1, 0)], [0, 1])
    assert p1.lives[0].is_dying
    engine.cleanup_dead_lives()
    assert len(p1.lives) == 0
    assert len(engine.state.graveyard) == 1
    assert engine.state.winner == p0.name


def test_shield_breaks_and_excess_damage_passes():
    engine = GameEngine(random.Random(3))
    engine.start_game()
    p0, p1 = engine.state.players
    p0.hand = [spade(engine, "5")]
    target = life(engine, "9")
    target.shield = Shield(3)
    p1.lives = [target]

    assert engine.execute_attack([(1, 0)], [0])
    assert not p1.lives[0].is_dying
    assert p1.lives[0].damage_taken == 2
    assert p1.lives[0].shield is None


def test_black_joker_kills_two_and_sacrifices_strongest():
    engine = GameEngine(random.Random(4))
    engine.start_game()
    p0, p1 = engine.state.players
    p0.hand = [Card("bj", "joker", "JOKER", 99, is_joker=True, color="black")]
    p0.lives = [life(engine, "4"), life(engine, "A")]
    p1.lives = [life(engine, "2"), life(engine, "3")]

    assert engine.execute_attack([(1, 0), (1, 1)], [0])
    assert all(card.is_dying for card in p1.lives)
    assert p0.lives[1].is_dying
    engine.cleanup_dead_lives()
    assert engine.state.winner == p0.name


def test_bot_step_executes_without_crashing():
    engine = GameEngine(random.Random(5))
    engine.start_game(names=("Human", "Bot"))
    engine.next_turn()
    assert engine.state.turn == 1
    result = execute_bot_step(engine, "normal")
    assert result
