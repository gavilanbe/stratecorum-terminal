from __future__ import annotations

from dataclasses import dataclass, field
import random

from .engine import (
    CLUBS,
    DIAMONDS,
    HEARTS,
    JOKER,
    LETTER_HIERARCHY,
    SPADES,
    Card,
    GameEngine,
    Player,
)


BOT_PLAYER_IDX = 1
HUMAN_PLAYER_IDX = 0


@dataclass
class BotAction:
    kind: str
    score: float
    card_indices: list[int] = field(default_factory=list)
    targets: list[tuple[int, int]] = field(default_factory=list)
    card_index: int | None = None
    life_idx: int | None = None
    graveyard_index: int | None = None


def execute_bot_step(engine: GameEngine, difficulty: str = "normal") -> str:
    state = engine.state
    if state.winner or state.turn != BOT_PLAYER_IDX:
        return "idle"

    if state.espionage_mode and state.espionage_mode[1] == HUMAN_PLAYER_IDX:
        human = state.players[HUMAN_PLAYER_IDX]
        hidden = [i for i, life in enumerate(human.lives) if not life.face_up]
        if hidden:
            engine.espionage_reveal(random.choice(hidden))
            return "espionage"
        return "idle"

    if state.actions_left <= 0:
        engine.next_turn()
        return "turn"

    action = evaluate_best_action(engine, difficulty)
    if not action:
        engine.next_turn()
        return "pass"
    execute_action(engine, action)
    return action.kind


def evaluate_best_action(engine: GameEngine, difficulty: str = "normal") -> BotAction | None:
    state = engine.state
    bot = state.players[BOT_PLAYER_IDX]
    human = state.players[HUMAN_PLAYER_IDX]
    candidates: list[BotAction] = []

    hand = bot.hand
    spades = [c for c in hand if c.suit == SPADES]
    hearts = [c for c in hand if c.suit == HEARTS]
    clubs = [c for c in hand if c.suit == CLUBS]
    diamonds = [c for c in hand if c.suit == DIAMONDS]
    black_joker = next((c for c in hand if c.is_black_joker), None)
    red_joker = next((c for c in hand if c.is_red_joker), None)

    bot_lives = bot.alive_lives()
    human_lives = human.alive_lives()

    if spades:
        sorted_spades = sorted(spades, key=lambda c: c.value, reverse=True)

        for spade in sorted_spades:
            card_idx = hand.index(spade)
            if state.actions_left < 1:
                continue
            target = find_best_attack_target(human, [spade], bot)
            if not target:
                continue
            life = human.lives[target[1]]
            would_kill = check_if_kills(life, [spade], bot)
            score = 80 + life.value * 2 if would_kill else 20 + spade.value
            if not would_kill and life.face_up and life.damage_taken:
                score += life.damage_taken * 1.5
            if spade.rank == "Q":
                score += adjacent_count(human, target[1]) * 5
            if spade.rank == "J" and any(l.damage_taken > 0 for l in bot_lives):
                score += 5
            candidates.append(BotAction("ATTACK", score, [card_idx], [target]))

        if len(spades) >= 2 and state.actions_left >= 2:
            combo = sorted_spades[:2]
            indices = [hand.index(c) for c in combo]
            combo_value = sum(c.value for c in combo) + 3
            target = find_best_attack_target(human, combo, bot)
            if target:
                would_kill = check_if_kills(human.lives[target[1]], combo, bot)
                score = 90 + combo_value if would_kill else 30 + combo_value
                has_king = any(c.rank == "K" for c in combo)
                targets = find_multi_targets(human, 2) if has_king and len(human_lives) >= 2 else [target]
                candidates.append(BotAction("ATTACK", score, indices, targets))

        if len(spades) >= 3 and state.actions_left >= 3:
            combo = sorted_spades[:3]
            indices = [hand.index(c) for c in combo]
            combo_value = sum(c.value for c in combo) + 7
            target = find_best_attack_target(human, combo, bot)
            if target:
                would_kill = check_if_kills(human.lives[target[1]], combo, bot)
                score = 95 + combo_value if would_kill else 35 + combo_value
                candidates.append(BotAction("ATTACK", score, indices, [target]))

    low_spades = [c for c in spades if c.value <= 5]
    if low_spades and state.actions_left >= 1:
        for spade in low_spades:
            untrapped = [life for life in bot_lives if not life.trap]
            if not untrapped:
                continue
            target = max(untrapped, key=lambda life: life.value)
            candidates.append(BotAction("PLACE_TRAP", 25 + spade.value, card_index=hand.index(spade), life_idx=bot.lives.index(target)))

    if black_joker and state.actions_left >= 1 and len(human_lives) >= 2:
        would_win = len(human_lives) == 2
        if would_win or len(bot_lives) >= 4:
            candidates.append(BotAction("ATTACK", 200 if would_win else 100, [hand.index(black_joker)], find_multi_targets(human, 2)))

    if red_joker and state.graveyard and state.actions_left >= 1:
        best_idx, best_card = max(enumerate(state.graveyard), key=lambda item: item[1].value)
        candidates.append(BotAction("REVIVE_JOKER", 60 + best_card.value, card_index=hand.index(red_joker), graveyard_index=best_idx))

    if hearts and not state.life_placed_this_turn and len(bot_lives) < 5 and state.actions_left >= 1:
        best = max(hearts, key=lambda c: c.value)
        candidates.append(BotAction("PLACE_LIFE", 50 + best.value / 2, card_index=hand.index(best)))

    if clubs and state.actions_left >= 1:
        unshielded = [life for life in bot_lives if not life.shield]
        for club in clubs:
            if not unshielded:
                continue
            target = max(unshielded, key=lambda life: life.value + life.damage_taken * 2)
            candidates.append(BotAction("PLACE_SHIELD", 40 + target.value + target.damage_taken * 2, card_index=hand.index(club), life_idx=bot.lives.index(target)))

    if diamonds and state.actions_left >= 1:
        damaged = [life for life in bot_lives if life.damage_taken > 0]
        if damaged:
            target = max(damaged, key=lambda life: life.damage_taken)
            percent = target.damage_taken / target.value
            threshold = 0.3 if target.value >= 10 else 0.5
            if percent > threshold:
                diamond = max(diamonds, key=lambda c: c.value)
                candidates.append(BotAction("HEAL_LIFE", 50 + percent * 10, card_index=hand.index(diamond), life_idx=bot.lives.index(target)))

    if bot.money >= 25 and state.graveyard and len(bot_lives) <= 3 and state.actions_left >= 1:
        candidates.append(BotAction("BUY_REVIVE", 60))
    if bot.money >= 10 and len(hand) < 8 and state.actions_left >= 1:
        candidates.append(BotAction("BUY_DRAW3", 45 if len(hand) <= 3 else 25))
    if bot.money >= 8 and len(hand) >= 2 and state.actions_left >= 1:
        if len([c for c in hand if c.value <= 4 and not c.is_joker]) >= 2:
            candidates.append(BotAction("BUY_DISCARD", 30))
    if bot.money >= 15 and spades and bot.attack_buff == 1 and state.actions_left >= 2:
        candidates.append(BotAction("BUY_ROULETTE", 45 + len(spades) * 5 + max(c.value for c in spades)))

    if bot.luck >= 20 and spades and not bot.ambush and state.actions_left >= 1:
        if any(life.shield for life in human_lives):
            candidates.append(BotAction("BUY_AMBUSH", 50))
    if bot.luck >= 12 and state.actions_left >= 1:
        if len([life for life in human_lives if not life.face_up]) >= 3:
            candidates.append(BotAction("BUY_ESPIONAGE", 30))
    if bot.luck >= 15 and state.actions_left >= 1:
        shielded = [life for life in human_lives if life.shield]
        if shielded:
            candidates.append(BotAction("BUY_SABOTAGE", 35, life_idx=human.lives.index(shielded[0])))
    if bot.luck >= 8 and state.actions_left >= 1:
        revealed = [life for life in bot_lives if life.face_up]
        if len(revealed) >= 2:
            candidates.append(BotAction("BUY_SHUFFLE", 20 + len(revealed) * 5))
    if bot.luck >= 10 and state.actions_left >= 1:
        revealed = [life for life in bot_lives if life.face_up]
        if revealed:
            best = max(revealed, key=lambda life: life.value)
            candidates.append(BotAction("BUY_HIDE", 25 + best.value, life_idx=bot.lives.index(best)))

    if state.actions_left >= 1:
        money_near = 5 <= bot.money < 25
        luck_near = 4 <= bot.luck < 20
        for card in hand:
            if card.is_joker:
                continue
            idx = hand.index(card)
            if card.suit == CLUBS:
                base = 20 if all(life.shield for life in bot_lives) else 12
                candidates.append(BotAction("BANK", base + card.value / 2 + (8 if luck_near else 0), card_indices=[idx]))
            elif card.suit == DIAMONDS:
                base = 20 if all(life.damage_taken == 0 for life in bot_lives) else 12
                candidates.append(BotAction("BANK", base + card.value / 2 + (8 if money_near else 0), card_indices=[idx]))

    candidates.append(BotAction("PASS", 1))
    noise = {"easy": 25, "hard": 3}.get(difficulty, 6)
    for candidate in candidates:
        if candidate.score < 150:
            candidate.score += random.uniform(-noise, noise)

    candidates.sort(key=lambda action: action.score, reverse=True)
    if difficulty == "easy" and len(candidates) > 1 and random.random() < 0.2:
        return candidates[1]
    return candidates[0] if candidates else None


def execute_action(engine: GameEngine, action: BotAction) -> None:
    if action.kind == "ATTACK":
        if engine.execute_attack(action.targets, action.card_indices):
            engine.consume_actions(len(action.card_indices))
    elif action.kind == "REVIVE_JOKER":
        if engine.revive_joker(BOT_PLAYER_IDX, action.card_index or 0, action.graveyard_index):
            engine.consume_actions(1)
    elif action.kind == "PLACE_LIFE":
        if engine.place_life(BOT_PLAYER_IDX, action.card_index or 0):
            engine.consume_actions(1)
    elif action.kind == "PLACE_TRAP":
        if engine.place_trap(BOT_PLAYER_IDX, action.card_index or 0, action.life_idx or 0):
            engine.consume_actions(1)
    elif action.kind == "PLACE_SHIELD":
        if engine.place_shield(BOT_PLAYER_IDX, action.card_index or 0, action.life_idx or 0):
            engine.consume_actions(1)
    elif action.kind == "HEAL_LIFE":
        if engine.heal_life(BOT_PLAYER_IDX, action.card_index or 0, action.life_idx or 0):
            engine.consume_actions(1)
    elif action.kind == "BUY_REVIVE":
        if engine.buy_money_item("revive")[0]:
            engine.consume_actions(1)
    elif action.kind == "BUY_DRAW3":
        if engine.buy_money_item("draw3")[0]:
            engine.consume_actions(1)
    elif action.kind == "BUY_DISCARD":
        if engine.buy_money_item("discard")[0]:
            engine.consume_actions(1)
    elif action.kind == "BUY_ROULETTE":
        if engine.buy_money_item("roulette")[0]:
            engine.consume_actions(1)
    elif action.kind == "BUY_AMBUSH":
        if engine.buy_luck_item("ambush"):
            engine.consume_actions(1)
    elif action.kind == "BUY_ESPIONAGE":
        if engine.buy_luck_item("espionage"):
            engine.consume_actions(1)
    elif action.kind == "BUY_SABOTAGE":
        if engine.buy_luck_item("sabotage", action.life_idx):
            engine.consume_actions(1)
    elif action.kind == "BUY_SHUFFLE":
        if engine.buy_luck_item("shuffle"):
            engine.consume_actions(1)
    elif action.kind == "BUY_HIDE":
        if engine.buy_luck_item("hide", action.life_idx):
            engine.consume_actions(1)
    elif action.kind == "BANK":
        if engine.bank_resources(BOT_PLAYER_IDX, action.card_indices):
            engine.consume_actions(len(action.card_indices))
    else:
        engine.next_turn()


def adjacent_count(player: Player, life_idx: int) -> int:
    return sum(1 for idx in (life_idx - 1, life_idx + 1) if 0 <= idx < len(player.lives) and not player.lives[idx].is_dying)


def find_best_attack_target(human: Player, attack_cards: list[Card], bot: Player) -> tuple[int, int] | None:
    lives = human.alive_lives()
    if not lives:
        return None
    raw_damage = raw_attack_damage(attack_cards, bot)
    best_idx = None
    best_score = -10**9
    for life in lives:
        life_idx = human.lives.index(life)
        total_hp = life.hp_left + (life.shield.value if life.shield and not bot.ambush else 0)
        if raw_damage >= total_hp:
            score = 1000 + life.value * 10 - total_hp
        elif life.face_up:
            score = 500 + raw_damage - total_hp
        else:
            score = 100
        if score > best_score:
            best_score = score
            best_idx = life_idx
    return (HUMAN_PLAYER_IDX, best_idx) if best_idx is not None else None


def find_multi_targets(human: Player, count: int) -> list[tuple[int, int]]:
    lives = human.alive_lives()
    lives = sorted(lives, key=lambda life: (not life.face_up, life.hp_left))
    return [(HUMAN_PLAYER_IDX, human.lives.index(life)) for life in lives[:count]]


def raw_attack_damage(cards: list[Card], bot: Player) -> int:
    if any(card.is_black_joker for card in cards):
        return 999
    spades = sum(1 for card in cards if card.suit == SPADES)
    combo = 3 if spades == 2 else 7 if spades >= 3 else 0
    return round((sum(card.value for card in cards) + combo) * (bot.attack_buff or 1))


def check_if_kills(life: Card, attack_cards: list[Card], bot: Player) -> bool:
    if life.is_dying:
        return False
    if any(card.is_black_joker for card in attack_cards):
        return True
    damage = raw_attack_damage(attack_cards, bot)
    if life.shield and not bot.ambush:
        damage -= life.shield.value
    if damage <= 0:
        return False
    accumulated = damage + life.damage_taken
    has_ace = any(card.rank == "A" and card.suit == SPADES for card in attack_cards)
    if has_ace:
        return accumulated >= life.value
    if accumulated < life.value:
        return False
    if life.rank in ("J", "Q", "K"):
        best_rank = max((LETTER_HIERARCHY.get(card.rank, 0) for card in attack_cards), default=0)
        life_rank = LETTER_HIERARCHY.get(life.rank, 0)
        if best_rank and life_rank:
            return accumulated > life.value or best_rank >= life_rank
    return True
