from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
import copy
import random
from typing import Iterable


HEARTS = "hearts"
DIAMONDS = "diamonds"
CLUBS = "clubs"
SPADES = "spades"
JOKER = "joker"

SUIT_SYMBOLS = {
    HEARTS: "♥",
    DIAMONDS: "♦",
    CLUBS: "♣",
    SPADES: "♠",
    JOKER: "★",
}

CARD_VALUES = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "J": 10,
    "Q": 10,
    "K": 10,
    "A": 14,
}

RANKS = list(CARD_VALUES.keys())
LETTER_HIERARCHY = {"J": 1, "Q": 2, "K": 3, "A": 4}
ROULETTE_SEGMENTS = [3, 2.5, 2, 1.5, 0.75, 0.5]
ROULETTE_LABELS = ["x3", "x2½", "x2", "x1½", "x¾", "x½"]


@dataclass
class Shield:
    value: int
    suit: str = CLUBS
    rank: str = ""
    from_joker: bool = False


@dataclass
class Trap:
    value: int
    suit: str = SPADES
    rank: str = ""


@dataclass
class Card:
    id: str
    suit: str
    rank: str
    value: int
    is_joker: bool = False
    color: str | None = None
    is_life: bool = False
    damage_taken: int = 0
    face_up: bool = False
    shield: Shield | None = None
    trap: Trap | None = None
    is_dying: bool = False
    is_sacrifice: bool = False

    @property
    def symbol(self) -> str:
        return SUIT_SYMBOLS.get(self.suit, "?")

    @property
    def label(self) -> str:
        if self.is_joker:
            return "BJ" if self.color == "black" else "RJ"
        return f"{self.rank}{self.symbol}"

    @property
    def hp_left(self) -> int:
        return max(0, self.value - (self.damage_taken or 0))

    @property
    def is_black_joker(self) -> bool:
        return self.is_joker and self.color == "black"

    @property
    def is_red_joker(self) -> bool:
        return self.is_joker and self.color == "red"


@dataclass
class Player:
    id: int
    name: str
    hand: list[Card]
    lives: list[Card]
    luck: int = 5
    money: int = 5
    attack_buff: float = 1
    ambush: bool = False

    def alive_lives(self) -> list[Card]:
        return [life for life in self.lives if not life.is_dying]


@dataclass
class Stats:
    damage_dealt: int = 0
    kills: int = 0
    resources_banked: int = 0
    shop_purchases: int = 0
    shields_placed: int = 0
    lives_placed: int = 0
    cards_played: int = 0


@dataclass
class AttackMeta:
    kills: int = 0
    perfect_blocks: int = 0
    clutch_saves: list[tuple[int, float]] = field(default_factory=list)
    is_lethal: bool = False
    trap_damage: int = 0
    splash_damage: int = 0
    drain_heal: int = 0


@dataclass
class GameState:
    game_started: bool = False
    deck: list[Card] = field(default_factory=list)
    graveyard: list[Card] = field(default_factory=list)
    discard_pile: list[Card] = field(default_factory=list)
    players: list[Player] = field(default_factory=list)
    turn: int = 0
    actions_per_turn: int = 3
    actions_left: int = 3
    logs: list[str] = field(default_factory=list)
    winner: str | None = None
    life_placed_this_turn: bool = False
    last_attacker_idx: int | None = None
    last_attack_meta: AttackMeta | None = None
    stats: list[Stats] = field(default_factory=lambda: [Stats(), Stats()])
    espionage_mode: tuple[int, int] | None = None  # (remaining, target_player_idx)


class GameEngine:
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.state = GameState()
        self._next_id = 0

    def clone(self) -> "GameEngine":
        other = GameEngine(self.rng)
        other.state = copy.deepcopy(self.state)
        other._next_id = self._next_id
        return other

    def _uid(self, prefix: str) -> str:
        self._next_id += 1
        return f"{prefix}-{self._next_id}"

    def make_card(self, suit: str, rank: str, **extra) -> Card:
        return Card(
            id=self._uid(f"{suit}-{rank}"),
            suit=suit,
            rank=rank,
            value=CARD_VALUES.get(rank, 0),
            **extra,
        )

    def log(self, text: str) -> None:
        self.state.logs.insert(0, text)
        del self.state.logs[50:]

    def current_player(self) -> Player:
        return self.state.players[self.state.turn]

    def opponent_idx(self, idx: int | None = None) -> int:
        base = self.state.turn if idx is None else idx
        return (base + 1) % len(self.state.players)

    def generate_deck(self, include_jokers: bool = True) -> tuple[list[Card], list[Card]]:
        deck: list[Card] = []
        for suit in (DIAMONDS, CLUBS, SPADES):
            for rank in RANKS:
                deck.append(self.make_card(suit, rank))

        hearts = [
            self.make_card(HEARTS, rank, is_life=True, damage_taken=0)
            for rank in RANKS
        ]
        self.rng.shuffle(hearts)
        heart_for_deck = hearts.pop()
        hearts_for_players = hearts
        deck.append(heart_for_deck)

        if include_jokers:
            deck.append(Card(self._uid("joker-black"), JOKER, "JOKER", 99, is_joker=True, color="black"))
            deck.append(Card(self._uid("joker-red"), JOKER, "JOKER", 0, is_joker=True, color="red"))

        self.rng.shuffle(deck)
        return deck, hearts_for_players

    def start_game(
        self,
        *,
        initial_lives: int = 6,
        include_jokers: bool = True,
        quick_mode: bool = False,
        names: tuple[str, str] = ("Jugador 1", "Jugador 2"),
    ) -> None:
        lives_count = 4 if initial_lives == 4 else 6
        actions = 2 if quick_mode else 3
        deck, hearts_for_players = self.generate_deck(include_jokers)

        p1_lives = [copy.deepcopy(c) for c in hearts_for_players[:lives_count]]
        p2_lives = [copy.deepcopy(c) for c in hearts_for_players[lives_count : lives_count * 2]]
        for life in p1_lives + p2_lives:
            life.face_up = False
            life.is_life = True

        p1_hand = [deck.pop() for _ in range(5)]
        p2_hand = [deck.pop() for _ in range(6)]

        self.state = GameState(
            game_started=True,
            deck=deck,
            players=[
                Player(0, names[0] or "Jugador 1", p1_hand, p1_lives),
                Player(1, names[1] or "Jugador 2", p2_hand, p2_lives),
            ],
            actions_per_turn=actions,
            actions_left=actions,
            logs=["¡Bienvenidos a Stratecorum!"],
            stats=[Stats(), Stats()],
        )

    def draw_cards(self, count: int) -> list[Card]:
        drawn: list[Card] = []
        for _ in range(count):
            if not self.state.deck:
                if not self.state.discard_pile:
                    break
                self.rng.shuffle(self.state.discard_pile)
                self.state.deck = self.state.discard_pile
                self.state.discard_pile = []
                self.log("Mazo rebarajado.")
            drawn.append(self.state.deck.pop())
        return drawn

    def next_turn(self) -> None:
        if not self.state.players or self.state.winner:
            return
        next_idx = (self.state.turn + 1) % len(self.state.players)
        player = self.state.players[next_idx]
        draw_count = min(2, max(0, 8 - len(player.hand)))
        drawn = self.draw_cards(draw_count)
        player.hand.extend(drawn)
        if draw_count == 0:
            self.log("Mano llena — no robas cartas.")
        elif len(drawn) < draw_count:
            self.log("¡No quedan suficientes cartas!")

        base = self.state.actions_per_turn
        actions = base + 1 if len(player.lives) <= 2 else base
        self.state.turn = next_idx
        self.state.actions_left = actions
        self.state.life_placed_this_turn = False
        self.state.espionage_mode = None
        self.state.last_attack_meta = None
        if actions > base:
            self.log("¡Adrenalina! +1 acción por pocas vidas.")
        self.log(f"Turno de {player.name}.")

    def consume_actions(self, count: int) -> None:
        self.state.actions_left -= count

    def bank_resources(self, player_idx: int, card_indices: Iterable[int]) -> bool:
        indices = sorted(set(card_indices), reverse=True)
        player = self.state.players[player_idx]
        cards = [player.hand[i] for i in indices if 0 <= i < len(player.hand)]
        if not cards or any(c.suit not in (CLUBS, DIAMONDS) for c in cards):
            return False

        total = 0
        for card in cards:
            if card.suit == CLUBS:
                player.luck += card.value
            else:
                player.money += card.value
            total += card.value

        for idx in indices:
            if 0 <= idx < len(player.hand):
                self.state.discard_pile.append(player.hand.pop(idx))

        self.state.stats[player_idx].resources_banked += total
        self.state.stats[player_idx].cards_played += len(cards)
        self.log(f"{player.name} guardó recursos.")
        return True

    def place_life(self, player_idx: int, card_index: int) -> bool:
        if self.state.life_placed_this_turn:
            return False
        player = self.state.players[player_idx]
        if not (0 <= card_index < len(player.hand)):
            return False
        card = player.hand[card_index]
        if card.suit != HEARTS:
            return False
        life = copy.deepcopy(card)
        life.is_life = True
        life.face_up = False
        life.damage_taken = 0
        life.shield = None
        life.trap = None
        player.lives.append(life)
        player.hand.pop(card_index)
        self.state.life_placed_this_turn = True
        self.state.stats[player_idx].lives_placed += 1
        self.state.stats[player_idx].cards_played += 1
        self.log(f"{player.name} colocó una nueva vida.")
        return True

    def place_shield(self, player_idx: int, card_index: int, life_idx: int) -> bool:
        player = self.state.players[player_idx]
        if not (0 <= card_index < len(player.hand) and 0 <= life_idx < len(player.lives)):
            return False
        card = player.hand[card_index]
        life = player.lives[life_idx]
        if card.suit != CLUBS or life.shield:
            return False
        life.shield = Shield(card.value, card.suit, card.rank)
        self.state.discard_pile.append(player.hand.pop(card_index))
        self.state.stats[player_idx].shields_placed += 1
        self.state.stats[player_idx].cards_played += 1
        self.log(f"{player.name} colocó un escudo ({card.value}) en una vida.")
        return True

    def place_trap(self, player_idx: int, card_index: int, life_idx: int) -> bool:
        player = self.state.players[player_idx]
        if not (0 <= card_index < len(player.hand) and 0 <= life_idx < len(player.lives)):
            return False
        card = player.hand[card_index]
        life = player.lives[life_idx]
        if card.suit != SPADES or card.is_joker or life.trap:
            return False
        life.trap = Trap(card.value, card.suit, card.rank)
        self.state.discard_pile.append(player.hand.pop(card_index))
        self.state.stats[player_idx].cards_played += 1
        self.log(f"{player.name} colocó una trampa en una vida.")
        return True

    def heal_life(self, player_idx: int, card_index: int, life_idx: int) -> bool:
        player = self.state.players[player_idx]
        if not (0 <= card_index < len(player.hand) and 0 <= life_idx < len(player.lives)):
            return False
        card = player.hand[card_index]
        life = player.lives[life_idx]
        if card.suit != DIAMONDS or life.damage_taken <= 0:
            return False
        amount = min(card.value, life.damage_taken)
        life.damage_taken -= amount
        self.state.discard_pile.append(player.hand.pop(card_index))
        self.state.stats[player_idx].cards_played += 1
        self.log(f"{player.name} curó una vida (+{amount} HP).")
        return True

    def revive_joker(self, player_idx: int, card_index: int, graveyard_index: int | None = None) -> bool:
        player = self.state.players[player_idx]
        if not (0 <= card_index < len(player.hand)) or not self.state.graveyard:
            return False
        card = player.hand[card_index]
        if not card.is_red_joker:
            return False
        idx = graveyard_index if graveyard_index is not None else len(self.state.graveyard) - 1
        if not (0 <= idx < len(self.state.graveyard)):
            return False
        revived = self.state.graveyard.pop(idx)
        revived.damage_taken = 0
        revived.face_up = False
        revived.trap = None
        revived.is_life = True
        revived.is_dying = False
        revived.is_sacrifice = False
        revived.shield = Shield(revived.value, from_joker=True)
        player.lives.append(revived)
        self.state.discard_pile.append(player.hand.pop(card_index))
        self.state.stats[player_idx].cards_played += 1
        self.log(f"{player.name} usó Joker Rojo — ¡{revived.rank}♥ revivida con escudo!")
        return True

    def execute_attack(self, targets: list[tuple[int, int]], card_indices: Iterable[int]) -> bool:
        attacker_idx = self.state.turn
        attacker = self.state.players[attacker_idx]
        indices = sorted(set(card_indices), reverse=True)
        selected = [attacker.hand[i] for i in sorted(indices) if 0 <= i < len(attacker.hand)]
        if not selected or not targets:
            return False

        is_black_joker = any(card.is_black_joker for card in selected)
        is_ambush = attacker.ambush
        attacker.ambush = False
        meta = AttackMeta()
        raw_total_damage = 0

        if is_black_joker:
            unique_targets = []
            seen = set()
            for target in targets:
                if target not in seen:
                    seen.add(target)
                    unique_targets.append(target)
            for player_idx, life_idx in unique_targets:
                if not (0 <= player_idx < len(self.state.players)):
                    continue
                defender = self.state.players[player_idx]
                if not (0 <= life_idx < len(defender.lives)):
                    continue
                life = defender.lives[life_idx]
                life.face_up = True
                life.is_dying = True
                life.damage_taken = 0
                life.shield = None
                life.trap = None
                meta.kills += 1
                self.log("¡Muerte Negra! Vida eliminada.")

            strongest_idx = self._strongest_alive_life_index(attacker)
            if strongest_idx is not None:
                sacrifice = attacker.lives[strongest_idx]
                sacrifice.face_up = True
                sacrifice.is_dying = True
                sacrifice.is_sacrifice = True
                sacrifice.damage_taken = 0
                sacrifice.shield = None
                sacrifice.trap = None
                self.log(f"{attacker.name} sacrificó su vida más fuerte.")
        else:
            attack_buff = attacker.attack_buff or 1
            attacker.attack_buff = 1
            spade_count = sum(1 for c in selected if c.suit == SPADES)
            combo_bonus = 3 if spade_count == 2 else 7 if spade_count >= 3 else 0
            has_ace = any(c.rank == "A" and c.suit == SPADES for c in selected)
            has_jack_spade = not has_ace and any(c.rank == "J" and c.suit == SPADES for c in selected)
            has_queen_spade = not has_ace and any(c.rank == "Q" and c.suit == SPADES for c in selected)

            raw_total_damage = round((sum(c.value for c in selected) + combo_bonus) * attack_buff)
            if combo_bonus:
                self.log(f"¡Combo de {spade_count} picas! +{combo_bonus} daño.")
            if attack_buff != 1:
                self.log(f"Buff de ataque: {format_multiplier(attack_buff)}")

            damage_per_target = raw_total_damage // len(targets) if len(targets) > 1 else raw_total_damage
            total_effective = 0

            grouped: dict[int, list[int]] = {}
            for player_idx, life_idx in targets:
                grouped.setdefault(player_idx, []).append(life_idx)

            for player_idx, life_indices in grouped.items():
                if not (0 <= player_idx < len(self.state.players)):
                    continue
                defender = self.state.players[player_idx]
                for life_idx in sorted(life_indices, reverse=True):
                    if not (0 <= life_idx < len(defender.lives)):
                        continue
                    life = defender.lives[life_idx]
                    if life.is_dying:
                        continue

                    self._activate_trap(life, attacker, meta)
                    effective = self._apply_shield(life, damage_per_target, is_ambush, meta)
                    if effective is None:
                        continue

                    killed = self._damage_life(life, effective, selected, has_ace, meta)
                    total_effective += effective
                    self.log("¡Vida Eliminada!" if killed else f"Vida dañada ({effective}).")

                    if has_queen_spade:
                        self._apply_splash(defender, life_idx, is_ambush, meta)

            if has_jack_spade and total_effective > 0:
                self._apply_drain(attacker, total_effective, meta)

        for idx in indices:
            if 0 <= idx < len(attacker.hand):
                self.state.discard_pile.append(attacker.hand.pop(idx))

        defender_idx = self.opponent_idx(attacker_idx)
        defender = self.state.players[defender_idx]
        meta.is_lethal = all(life.is_dying for life in defender.lives)
        stats = self.state.stats[attacker_idx]
        stats.damage_dealt += raw_total_damage
        stats.kills += meta.kills
        stats.cards_played += len(selected)
        self.state.last_attacker_idx = attacker_idx
        self.state.last_attack_meta = meta
        return True

    def _strongest_alive_life_index(self, player: Player) -> int | None:
        best_idx = None
        best_hp = -1
        for idx, life in enumerate(player.lives):
            if life.is_dying:
                continue
            hp = life.hp_left
            if hp > best_hp:
                best_hp = hp
                best_idx = idx
        return best_idx

    def _activate_trap(self, life: Card, attacker: Player, meta: AttackMeta) -> None:
        if not life.trap:
            return
        trap_value = life.trap.value
        life.trap = None
        target_idx = None
        most_damage = -1
        for idx, candidate in enumerate(attacker.lives):
            if candidate.is_dying:
                continue
            damage = candidate.damage_taken or 0
            if damage > most_damage or (damage == most_damage and target_idx is None):
                most_damage = damage
                target_idx = idx
        if target_idx is None:
            return
        target = attacker.lives[target_idx]
        if trap_value + target.damage_taken >= target.value:
            target.face_up = True
            target.is_dying = True
            target.damage_taken = 0
            target.shield = None
            target.trap = None
            self.log(f"¡Trampa activada! Contra-daño {trap_value} — ¡Vida del atacante eliminada!")
        else:
            target.damage_taken += trap_value
            target.face_up = True
            self.log(f"¡Trampa activada! Contra-daño {trap_value} al atacante.")
        meta.trap_damage += trap_value

    def _apply_shield(self, life: Card, damage: int, is_ambush: bool, meta: AttackMeta) -> int | None:
        if not life.shield:
            return damage
        if is_ambush:
            self.log("¡Emboscada! Escudo ignorado.")
            return damage
        shield_value = life.shield.value
        if damage <= shield_value:
            life.shield = None
            life.face_up = True
            meta.perfect_blocks += 1
            self.log(f"¡Escudo absorbió {damage} de daño y se rompió!")
            return None
        life.shield = None
        remaining = damage - shield_value
        self.log(f"Escudo roto ({shield_value}). {remaining} de daño pasó.")
        return remaining

    def _damage_life(
        self,
        life: Card,
        damage: int,
        selected: list[Card],
        has_ace: bool,
        meta: AttackMeta,
    ) -> bool:
        accumulated = damage + (life.damage_taken or 0)
        kill = False
        if has_ace:
            kill = accumulated >= life.value
        elif accumulated >= life.value:
            if life.rank in ("J", "Q", "K"):
                best_rank = max((LETTER_HIERARCHY.get(c.rank, 0) for c in selected), default=0)
                life_rank = LETTER_HIERARCHY.get(life.rank, 0)
                if best_rank and life_rank:
                    kill = accumulated > life.value or best_rank >= life_rank
                else:
                    kill = True
            else:
                kill = True

        if kill:
            life.face_up = True
            life.is_dying = True
            life.damage_taken = 0
            life.shield = None
            life.trap = None
            meta.kills += 1
            return True

        life.damage_taken += damage
        life.face_up = True
        remaining_percent = life.hp_left / life.value if life.value else 0
        if 0 < remaining_percent < 0.2:
            meta.clutch_saves.append((0, remaining_percent))
        return False

    def _apply_splash(self, defender: Player, life_idx: int, is_ambush: bool, meta: AttackMeta) -> None:
        for adj_idx in (life_idx - 1, life_idx + 1):
            if not (0 <= adj_idx < len(defender.lives)):
                continue
            adj = defender.lives[adj_idx]
            if adj.is_dying:
                continue
            splash = 2
            if adj.shield and not is_ambush:
                shield_value = adj.shield.value
                if splash <= shield_value:
                    adj.shield = None
                    adj.face_up = True
                    self.log(f"Q♠ Splash: escudo adyacente absorbió {splash} y se rompió.")
                    continue
                splash -= shield_value
                adj.shield = None
                self.log(f"Q♠ Splash: escudo adyacente roto. {splash} pasó.")
            if splash + adj.damage_taken >= adj.value:
                adj.face_up = True
                adj.is_dying = True
                adj.damage_taken = 0
                adj.shield = None
                adj.trap = None
                meta.kills += 1
                meta.splash_damage += splash
                self.log("Q♠ Onda Expansiva: ¡vida adyacente eliminada!")
            else:
                adj.damage_taken += splash
                adj.face_up = True
                meta.splash_damage += splash
                self.log(f"Q♠ Onda Expansiva: {splash} daño a vida adyacente.")

    def _apply_drain(self, attacker: Player, total_effective: int, meta: AttackMeta) -> None:
        heal_amount = ceil(total_effective / 3)
        target_idx = None
        most_damage = 0
        for idx, life in enumerate(attacker.lives):
            if life.is_dying:
                continue
            if life.damage_taken > most_damage:
                most_damage = life.damage_taken
                target_idx = idx
        if target_idx is None or most_damage <= 0:
            return
        target = attacker.lives[target_idx]
        actual = min(heal_amount, target.damage_taken)
        target.damage_taken -= actual
        meta.drain_heal = actual
        self.log(f"J♠ Drenaje: curó {actual} HP en vida propia.")

    def cleanup_dead_lives(self) -> None:
        if not self.state.players:
            return
        for player in self.state.players:
            living = []
            for life in player.lives:
                if life.is_dying:
                    life.is_dying = False
                    life.face_up = True
                    life.damage_taken = 0
                    life.shield = None
                    life.trap = None
                    self.state.graveyard.append(life)
                else:
                    living.append(life)
            player.lives = living

        attacker_idx = self.state.last_attacker_idx if self.state.last_attacker_idx is not None else self.state.turn
        for idx, player in enumerate(self.state.players):
            if player.lives:
                continue
            all_dead = all(not p.lives for p in self.state.players)
            winner_idx = self.opponent_idx(attacker_idx) if all_dead or idx == attacker_idx else attacker_idx
            self.state.winner = self.state.players[winner_idx].name
            self.state.game_started = False
            self.log(f"¡{self.state.winner} HA GANADO!")
            break

    def has_dying_lives(self) -> bool:
        return any(life.is_dying for player in self.state.players for life in player.lives)

    def buy_money_item(self, item: str, selected_indices: Iterable[int] | None = None) -> tuple[bool, int | None]:
        player = self.current_player()
        if item == "draw3":
            if player.money < 10 or len(player.hand) >= 8:
                return False, None
            player.money -= 10
            draw_count = min(3, max(0, 8 - len(player.hand)))
            drawn = self.draw_cards(draw_count)
            player.hand.extend(drawn)
            self.log(f"Comprado: Robar {len(drawn)} cartas.")
        elif item == "roulette":
            if player.money < 15:
                return False, None
            player.money -= 15
            idx = self.rng.randrange(len(ROULETTE_SEGMENTS))
            player.attack_buff = ROULETTE_SEGMENTS[idx]
            self.log(f"Ruleta: {ROULETTE_LABELS[idx]} en el próximo ataque.")
            self.state.stats[self.state.turn].shop_purchases += 1
            return True, idx
        elif item == "discard":
            if player.money < 8 or not player.hand:
                return False, None
            player.money -= 8
            chosen = sorted(set(selected_indices or []), reverse=True)
            chosen = [i for i in chosen if 0 <= i < len(player.hand)][:2]
            if not chosen:
                ordered = sorted(range(len(player.hand)), key=lambda i: player.hand[i].value)
                chosen = sorted(ordered[: min(2, len(player.hand))], reverse=True)
            count = len(chosen)
            for idx in chosen:
                self.state.discard_pile.append(player.hand.pop(idx))
            drawn = self.draw_cards(count)
            player.hand.extend(drawn)
            self.log(f"Comprado: Descartó {count} y robó {len(drawn)}.")
        elif item == "revive":
            if player.money < 25 or not self.state.graveyard:
                return False, None
            player.money -= 25
            card = self.state.graveyard.pop()
            card.damage_taken = 0
            card.face_up = False
            card.is_life = True
            card.shield = None
            card.trap = None
            card.is_dying = False
            player.lives.append(card)
            self.log("Comprado: Vida revivida del cementerio.")
        else:
            return False, None

        self.state.stats[self.state.turn].shop_purchases += 1
        return True, None

    def buy_luck_item(self, item: str, life_idx: int | None = None) -> bool:
        player = self.current_player()
        opponent = self.state.players[self.opponent_idx()]
        if item == "espionage":
            hidden = [life for life in opponent.lives if not life.face_up]
            if player.luck < 12 or not hidden:
                return False
            player.luck -= 12
            reveal_count = min(2, len(hidden))
            self.state.espionage_mode = (reveal_count, self.opponent_idx())
            self.log(f"Espionaje activado — elige {reveal_count} vida{'s' if reveal_count > 1 else ''} para revelar.")
        elif item == "ambush":
            if player.luck < 20 or player.ambush:
                return False
            player.luck -= 20
            player.ambush = True
            self.log("¡Emboscada! Tu próximo ataque ignora escudos.")
        elif item == "shuffle":
            if player.luck < 8:
                return False
            player.luck -= 8
            self.rng.shuffle(player.lives)
            self.log(f"{player.name} reorganizó sus vidas.")
        elif item == "hide":
            if player.luck < 10 or life_idx is None or not (0 <= life_idx < len(player.lives)):
                return False
            life = player.lives[life_idx]
            if not life.face_up:
                return False
            player.luck -= 10
            life.face_up = False
            self.log(f"{player.name} ocultó una vida.")
        elif item == "sabotage":
            if player.luck < 15 or life_idx is None or not (0 <= life_idx < len(opponent.lives)):
                return False
            life = opponent.lives[life_idx]
            if not life.shield:
                return False
            player.luck -= 15
            life.shield = None
            self.log(f"{player.name} saboteó un escudo enemigo.")
        else:
            return False

        self.state.stats[self.state.turn].shop_purchases += 1
        return True

    def espionage_reveal(self, life_idx: int) -> bool:
        if not self.state.espionage_mode:
            return False
        remaining, target_idx = self.state.espionage_mode
        target = self.state.players[target_idx]
        if not (0 <= life_idx < len(target.lives)):
            return False
        life = target.lives[life_idx]
        if life.face_up:
            return False
        life.face_up = True
        remaining -= 1
        self.state.espionage_mode = (remaining, target_idx) if remaining > 0 else None
        self.log(f"Espionaje: {life.rank}{life.symbol} revelada.")
        return True


def format_multiplier(value: float) -> str:
    if value == 2.5:
        return "x2½"
    if value == 1.5:
        return "x1½"
    if value == 0.75:
        return "x¾"
    if value == 0.5:
        return "x½"
    return f"x{int(value) if value == int(value) else value}"
