from __future__ import annotations

import random
import time

from .bot import execute_bot_step
from .engine import (
    CLUBS,
    DIAMONDS,
    HEARTS,
    JOKER,
    ROULETTE_LABELS,
    SPADES,
    Card,
    GameEngine,
    format_multiplier,
)
from .term import Terminal, box_lines, center, gradient_text, pad, style, width


MIN_COLS = 100
MIN_ROWS = 34


SUIT_COLOR = {
    HEARTS: "rose",
    DIAMONDS: "amber",
    CLUBS: "emerald",
    SPADES: "slate",
    JOKER: "purple",
}


class App:
    def __init__(self):
        self.engine = GameEngine(random.Random())
        self.screen = "menu"
        self.mode = "bot"
        self.initial_lives = 6
        self.include_jokers = True
        self.quick_mode = False
        self.bot_difficulty = "normal"
        self.hand_cursor = 0
        self.life_cursor = 0
        self.shop_cursor = 0
        self.graveyard_cursor = 0
        self.selected_cards: set[int] = set()
        self.selected_targets: list[tuple[int, int]] = []
        self.target_mode: str | None = None
        self.message = "Elige modo o ajusta opciones."
        self.running = True
        self._last_bot_step = 0.0

    def run(self) -> int:
        with Terminal() as term:
            while self.running:
                term.draw(self.render(term))
                self.maybe_bot_step(term)
                key = term.read_key(0.05)
                if key:
                    self.handle_key(key, term)
        return 0

    def render(self, term: Terminal) -> list[str]:
        cols, rows = term.size()
        if cols < MIN_COLS or rows < MIN_ROWS:
            return self.render_too_small(cols, rows)
        if self.screen == "menu":
            return self.render_menu(cols, rows)
        if self.screen == "help":
            return self.render_help(cols, rows)
        if self.screen == "shop":
            return self.render_game(cols, rows, overlay="shop")
        if self.screen == "graveyard":
            return self.render_game(cols, rows, overlay="graveyard")
        return self.render_game(cols, rows)

    def render_too_small(self, cols: int, rows: int) -> list[str]:
        title = gradient_text("STRATECORUM TERMINAL", [(245, 158, 11), (244, 63, 94)], bold=True)
        return [
            "",
            center(title, cols),
            "",
            center(style("La ventana es demasiado pequeña para la mesa completa.", color="rose", bold=True), cols),
            center(f"Actual: {cols}x{rows} · recomendado: {MIN_COLS}x{MIN_ROWS} o más", cols),
            "",
            center("Aumenta iTerm o baja el zoom de la fuente.", cols),
            center("Q para salir", cols),
        ]

    def render_menu(self, cols: int, rows: int) -> list[str]:
        title = gradient_text("STRATECORUM", [(255, 255, 255), (245, 158, 11), (244, 63, 94)], bold=True)
        subtitle = style("terminal edition · iTerm truecolor", color="muted")
        options = [
            style("1", color="amber", bold=True) + "  Jugar vs Bot",
            style("2", color="emerald", bold=True) + "  Local pass-and-play",
            "",
            style("4", color="slate", bold=True) + f"  Vidas iniciales: {self.initial_lives}",
            style("J", color="slate", bold=True) + f"  Jokers: {'SI' if self.include_jokers else 'NO'}",
            style("F", color="slate", bold=True) + f"  Modo rápido: {'SI' if self.quick_mode else 'NO'}",
            style("D", color="slate", bold=True) + f"  Dificultad bot: {self.bot_difficulty}",
            "",
            style("Q", color="rose", bold=True) + "  Salir",
        ]
        art = [
            style("       ╭─────────╮ ╭─────────╮ ╭─────────╮ ╭─────────╮", color="dim"),
            style("       │ A♠      │ │ K♥      │ │ Q♦      │ │ J♣      │", color="slate"),
            style("       │    ♠    │ │    ♥    │ │    ♦    │ │    ♣    │", color="muted"),
            style("       │    KO   │ │   VIDA  │ │    $    │ │   LUCK  │", color="muted"),
            style("       ╰─────────╯ ╰─────────╯ ╰─────────╯ ╰─────────╯", color="dim"),
        ]
        box = box_lines(options, inner_width=42, title="MENU", color="amber")
        content = ["", center(title, cols), center(subtitle, cols), "", *[center(line, cols) for line in art], ""]
        content.extend(center(line, cols) for line in box)
        content.append("")
        content.append(center(style(self.message, color="muted"), cols))
        return self.with_background(content, rows)

    def render_help(self, cols: int, rows: int) -> list[str]:
        lines = [
            style("Controles", color="amber", bold=True),
            "←/→ moverte · Space seleccionar carta · Enter confirmar",
            "A atacar · G guardar · L vida · S escudo · H curar · T trampa",
            "R revivir con Joker Rojo · M tienda · P pasar · Esc cancelar",
            "",
            style("Reglas rápidas", color="amber", bold=True),
            "♥ son vidas. ♠ atacan o se colocan como trampas.",
            "♣ son escudos o suerte. ♦ curan o dan dinero.",
            "2 picas: +3 daño. 3+ picas: +7 daño.",
            "A♠ ignora jerarquía. J♠ drena. Q♠ hace splash. K♠ divide a 2.",
            "Joker Negro elimina 2 vidas y sacrifica tu vida más fuerte.",
            "",
            style("Pulsa cualquier tecla para volver.", color="muted"),
        ]
        boxed = box_lines(lines, inner_width=78, title="GUIA RAPIDA", color="amber")
        return self.with_background(["", *[center(line, cols) for line in boxed]], rows)

    def render_game(self, cols: int, rows: int, overlay: str | None = None) -> list[str]:
        state = self.engine.state
        if not state.players:
            return self.render_menu(cols, rows)

        bottom_idx = 0 if self.mode == "bot" else state.turn
        top_idx = (bottom_idx + 1) % 2
        bottom = state.players[bottom_idx]
        top = state.players[top_idx]
        is_my_turn = state.turn == bottom_idx

        lines: list[str] = []
        lines.extend(self.render_header(cols, bottom_idx, top_idx, is_my_turn))
        lines.append("")
        lines.extend(self.render_player_zone(top, top_idx, cols, is_top=True))
        lines.append("")
        lines.extend(self.render_table(cols))
        lines.append("")
        lines.extend(self.render_action_bar(cols, is_my_turn))
        lines.append("")
        lines.extend(self.render_player_zone(bottom, bottom_idx, cols, is_top=False))
        lines.append("")
        lines.extend(self.render_hand(bottom, cols, is_my_turn))
        lines.append("")
        lines.extend(self.render_log_and_footer(cols))

        if state.winner:
            lines = self.overlay_box(cols, rows, lines, self.victory_overlay(cols))
        elif overlay == "shop":
            lines = self.overlay_box(cols, rows, lines, self.shop_overlay())
        elif overlay == "graveyard":
            lines = self.overlay_box(cols, rows, lines, self.graveyard_overlay())
        return self.with_background(lines, rows)

    def render_header(self, cols: int, bottom_idx: int, top_idx: int, is_my_turn: bool) -> list[str]:
        state = self.engine.state
        turn = state.players[state.turn]
        title = gradient_text("STRATECORUM", [(255, 255, 255), (245, 158, 11), (244, 63, 94)], bold=True)
        actions = "".join(
            style("●", color="rose" if len(turn.lives) <= 2 else "amber")
            if i < state.actions_left
            else style("○", color="dim")
            for i in range(max(state.actions_left, state.actions_per_turn + (1 if len(turn.lives) <= 2 else 0)))
        )
        turn_text = style("TU TURNO" if is_my_turn else f"TURNO: {turn.name}", color="emerald" if is_my_turn else "amber", bold=True)
        left = f" {title}  {style('BOT' if self.mode == 'bot' else 'LOCAL', color='muted')} "
        right = f" {turn_text}  {actions} "
        middle = " " * max(1, cols - width(left) - width(right))
        return [left + middle + right]

    def render_player_zone(self, player, player_idx: int, cols: int, *, is_top: bool) -> list[str]:
        state = self.engine.state
        is_target_side = (
            (is_top and self.target_mode in ("attack", "sabotage", "espionage"))
            or (not is_top and self.target_mode in ("shield", "heal", "trap", "hide"))
        )
        name_color = "rose" if is_top else "emerald"
        buff_bits = []
        if player.attack_buff != 1:
            buff_bits.append(style(format_multiplier(player.attack_buff), color="amber", bold=True))
        if player.ambush:
            buff_bits.append(style("AMB", color="purple", bold=True))
        profile = (
            style(player.name, color=name_color, bold=True)
            + f"  {style('♣', color='emerald')}{player.luck}"
            + f"  {style('♦', color='amber')}{player.money}"
            + f"  {style('mano', color='muted')}:{len(player.hand)}"
        )
        if buff_bits:
            profile += "  " + " ".join(buff_bits)
        tag = "RIVAL" if is_top else "JUGADOR"
        title = style(f"{tag} · {profile}", color=name_color)
        blocks = []
        for i, life in enumerate(player.lives):
            hidden = is_top and not life.face_up
            cursor = is_target_side and i == self.life_cursor
            targeted = (player_idx, i) in self.selected_targets
            own_life = not is_top
            blocks.append(card_block(life, hidden=hidden, cursor=cursor, target=targeted, own_life=own_life, caption=str(i + 1)))
        card_lines = join_blocks(blocks) if blocks else [style("sin vidas", color="rose")]
        return [center(title, cols), *[center(line, cols) for line in card_lines]]

    def render_table(self, cols: int) -> list[str]:
        state = self.engine.state
        deck = mini_stack("MAZO", len(state.deck), "slate")
        discard = mini_stack("DESC", len(state.discard_pile), "amber", top=state.discard_pile[-1] if state.discard_pile else None)
        grave = mini_stack("CEM", len(state.graveyard), "rose", top=state.graveyard[-1] if state.graveyard else None)
        joined = join_blocks([deck, discard, grave], gap=4)
        return [center(line, cols) for line in joined]

    def render_action_bar(self, cols: int, is_my_turn: bool) -> list[str]:
        state = self.engine.state
        if state.espionage_mode:
            remaining, _ = state.espionage_mode
            text = style(f"ESPIONAJE · revela {remaining} vida(s)", color="purple", bold=True)
        elif self.target_mode:
            text = style(self.target_prompt(), color="amber", bold=True)
        elif not is_my_turn and self.mode == "bot":
            text = style("Bot pensando...", color="purple", bold=True)
        elif not is_my_turn:
            text = style("Pasa el terminal al otro jugador.", color="amber", bold=True)
        elif self.selected_cards:
            text = self.selected_prompt()
        else:
            text = style("Selecciona carta: Space · A/G/L/S/H/T/R · M tienda · P pasar · ? ayuda", color="muted")
        msg = style(self.message, color="slate")
        return [center(text, cols), center(msg, cols)]

    def render_hand(self, player, cols: int, is_my_turn: bool) -> list[str]:
        blocks = []
        for i, card in enumerate(player.hand):
            blocks.append(
                card_block(
                    card,
                    selected=i in self.selected_cards,
                    cursor=is_my_turn and i == self.hand_cursor and not self.target_mode,
                    caption=f"{i + 1}",
                )
            )
        if not blocks:
            return [center(style("Mano vacía", color="muted"), cols)]
        return [center(line, cols) for line in join_blocks(blocks)]

    def render_log_and_footer(self, cols: int) -> list[str]:
        logs = self.engine.state.logs[:3]
        log_text = "  ".join(style("• " + log, color="dim") for log in logs)
        footer = style("Q salir  ? ayuda  M tienda  P pasar", color="dim")
        return [center(log_text, cols), center(footer, cols)]

    def shop_overlay(self) -> list[str]:
        player = self.engine.current_player()
        items = self.shop_items()
        lines = [
            style(f"Tienda · {player.name}   $ {player.money}   ♣ {player.luck}", color="amber", bold=True),
            "",
        ]
        for i, item in enumerate(items):
            cursor = i == self.shop_cursor
            marker = style("▶", color="amber", bold=True) if cursor else " "
            disabled = not item["enabled"]()
            color = "dim" if disabled else item["color"]
            lines.append(f"{marker} {style(str(i + 1), color=color, bold=True)}  {style(item['label'], color=color, bold=cursor and not disabled)}  {style(item['cost'], color='muted')}")
            lines.append(f"   {style(item['desc'], color='dim')}")
        lines.append("")
        lines.append(style("↑/↓ o numeros · Enter comprar · Esc volver", color="muted"))
        return box_lines(lines, inner_width=62, title="TIENDA", color="amber")

    def graveyard_overlay(self) -> list[str]:
        lines = [style("Cementerio", color="rose", bold=True), ""]
        if not self.engine.state.graveyard:
            lines.append(style("Vacío.", color="muted"))
        else:
            for i, card in enumerate(self.engine.state.graveyard):
                cursor = i == self.graveyard_cursor
                marker = style("▶", color="orange", bold=True) if cursor else " "
                lines.append(f"{marker} {style(str(i + 1), color='orange')} {card.label}  HP {card.value}")
        lines.append("")
        lines.append(style("Enter elegir · Esc volver", color="muted"))
        return box_lines(lines, inner_width=42, title="CEMENTERIO", color="rose")

    def victory_overlay(self, cols: int) -> list[str]:
        state = self.engine.state
        winner = state.winner or "?"
        win = winner == state.players[0].name
        title = "VICTORIA" if win else "FIN DE PARTIDA"
        lines = [
            gradient_text(title, [(255, 255, 255), (245, 158, 11), (244, 63, 94)], bold=True),
            "",
            style(f"Gana {winner}", color="amber", bold=True),
            "",
        ]
        for idx, player in enumerate(state.players):
            stats = state.stats[idx]
            lines.append(
                f"{style(player.name, color='emerald' if idx == 0 else 'rose', bold=True)}  "
                f"daño {stats.damage_dealt} · kills {stats.kills} · compras {stats.shop_purchases}"
            )
        lines.extend(["", style("Q salir · 1 nueva vs Bot · 2 nueva Local", color="muted")])
        return box_lines(lines, inner_width=56, title="RESULTADO", color="amber")

    def overlay_box(self, cols: int, rows: int, base: list[str], overlay: list[str]) -> list[str]:
        out = base[:]
        top = max(2, (rows - len(overlay)) // 2)
        for i, line in enumerate(overlay):
            if top + i >= len(out):
                out.append("")
            left = max(0, (cols - width(line)) // 2)
            under = out[top + i] if top + i < len(out) else ""
            out[top + i] = " " * left + line
        return out

    def with_background(self, lines: list[str], rows: int) -> list[str]:
        bg_lines = []
        for i in range(rows):
            line = lines[i] if i < len(lines) else ""
            bg_lines.append(line)
        return bg_lines

    def handle_key(self, key: str, term: Terminal) -> None:
        if key == "q":
            self.running = False
            return
        if key == "?":
            self.screen = "help" if self.screen != "help" else "play"
            return
        if self.screen == "help":
            self.screen = "play" if self.engine.state.players else "menu"
            return
        if self.engine.state.winner:
            if key == "1":
                self.start("bot")
            elif key == "2":
                self.start("local")
            return
        if self.screen == "menu":
            self.handle_menu_key(key)
            return
        if self.screen == "shop":
            self.handle_shop_key(key, term)
            return
        if self.screen == "graveyard":
            self.handle_graveyard_key(key, term)
            return
        self.handle_play_key(key, term)

    def handle_menu_key(self, key: str) -> None:
        if key == "1":
            self.start("bot")
        elif key == "2":
            self.start("local")
        elif key == "4":
            self.initial_lives = 4 if self.initial_lives == 6 else 6
            self.message = f"Vidas iniciales: {self.initial_lives}"
        elif key == "j":
            self.include_jokers = not self.include_jokers
            self.message = f"Jokers: {'SI' if self.include_jokers else 'NO'}"
        elif key == "f":
            self.quick_mode = not self.quick_mode
            self.message = f"Modo rápido: {'SI' if self.quick_mode else 'NO'}"
        elif key == "d":
            order = ["easy", "normal", "hard"]
            self.bot_difficulty = order[(order.index(self.bot_difficulty) + 1) % len(order)]
            self.message = f"Dificultad bot: {self.bot_difficulty}"

    def handle_play_key(self, key: str, term: Terminal) -> None:
        state = self.engine.state
        if not state.players:
            return
        if self.mode == "bot" and state.turn == 1:
            return
        current = self.engine.current_player()
        if key == "ESC":
            self.cancel_modes()
            return
        if self.target_mode or state.espionage_mode:
            self.handle_target_key(key, term)
            return
        if key == "LEFT":
            self.hand_cursor = max(0, self.hand_cursor - 1)
        elif key == "RIGHT":
            self.hand_cursor = min(max(0, len(current.hand) - 1), self.hand_cursor + 1)
        elif key == "SPACE":
            self.toggle_card(current)
        elif key == "m":
            self.screen = "shop"
            self.shop_cursor = 0
        elif key == "p":
            self.engine.next_turn()
            self.selected_cards.clear()
            self.message = "Turno pasado."
        elif key == "a":
            self.begin_attack()
        elif key == "g":
            self.do_bank(term)
        elif key == "l":
            self.do_place_life(term)
        elif key == "s":
            self.begin_target("shield")
        elif key == "h":
            self.begin_target("heal")
        elif key == "t":
            self.begin_target("trap")
        elif key == "r":
            self.begin_revive(term)

    def handle_target_key(self, key: str, term: Terminal) -> None:
        state = self.engine.state
        mode = self.target_mode
        if key == "ESC":
            self.cancel_modes()
            return
        target_player_idx = self.target_player_index()
        player = state.players[target_player_idx]
        if key == "LEFT":
            self.life_cursor = max(0, self.life_cursor - 1)
        elif key == "RIGHT":
            self.life_cursor = min(max(0, len(player.lives) - 1), self.life_cursor + 1)
        elif key == "c" and mode == "attack" and self.selected_targets:
            self.finish_attack(term)
        elif key == "ENTER":
            if state.espionage_mode:
                if self.engine.espionage_reveal(self.life_cursor):
                    self.message = "Vida revelada."
                    if not self.engine.state.espionage_mode:
                        self.target_mode = None
                else:
                    self.message = "No se puede revelar esa vida."
                return
            if mode == "attack":
                target = (target_player_idx, self.life_cursor)
                if target not in self.selected_targets:
                    self.selected_targets.append(target)
                if len(self.selected_targets) >= self.max_attack_targets():
                    self.finish_attack(term)
                else:
                    self.message = "Elige otro objetivo o pulsa C para confirmar."
            elif mode == "shield":
                self.finish_own_life_action(term, "shield")
            elif mode == "heal":
                self.finish_own_life_action(term, "heal")
            elif mode == "trap":
                self.finish_own_life_action(term, "trap")
            elif mode == "hide":
                if self.engine.buy_luck_item("hide", self.life_cursor):
                    self.engine.consume_actions(1)
                    self.after_action(term, "Vida ocultada.")
                else:
                    self.message = "No se puede ocultar esa vida."
            elif mode == "sabotage":
                if self.engine.buy_luck_item("sabotage", self.life_cursor):
                    self.engine.consume_actions(1)
                    self.after_action(term, "Escudo saboteado.")
                else:
                    self.message = "Ese objetivo no tiene escudo."

    def handle_shop_key(self, key: str, term: Terminal) -> None:
        items = self.shop_items()
        if key == "ESC" or key == "m":
            self.screen = "play"
            return
        if key == "UP":
            self.shop_cursor = max(0, self.shop_cursor - 1)
            return
        if key == "DOWN":
            self.shop_cursor = min(len(items) - 1, self.shop_cursor + 1)
            return
        if key.isdigit() and 1 <= int(key) <= len(items):
            self.shop_cursor = int(key) - 1
            self.buy_shop_item(items[self.shop_cursor], term)
            return
        if key == "ENTER":
            self.buy_shop_item(items[self.shop_cursor], term)

    def handle_graveyard_key(self, key: str, term: Terminal) -> None:
        graveyard = self.engine.state.graveyard
        if key == "ESC":
            self.screen = "play"
            self.target_mode = None
            return
        if key == "UP":
            self.graveyard_cursor = max(0, self.graveyard_cursor - 1)
        elif key == "DOWN":
            self.graveyard_cursor = min(max(0, len(graveyard) - 1), self.graveyard_cursor + 1)
        elif key == "ENTER" and graveyard and self.target_mode == "revive":
            idx = self.only_selected_card()
            if idx is not None and self.engine.revive_joker(self.engine.state.turn, idx, self.graveyard_cursor):
                self.engine.consume_actions(1)
                self.after_action(term, "Vida revivida.")
            else:
                self.message = "No se pudo revivir."
            self.screen = "play"
            self.target_mode = None

    def maybe_bot_step(self, term: Terminal) -> None:
        state = self.engine.state
        if self.screen != "play" or self.mode != "bot" or state.winner or not state.players:
            return
        if state.turn != 1:
            return
        now = time.monotonic()
        if now - self._last_bot_step < {"easy": 1.0, "normal": 0.75, "hard": 0.45}.get(self.bot_difficulty, 0.75):
            return
        self._last_bot_step = now
        execute_bot_step(self.engine, self.bot_difficulty)
        self.after_action(term, "El bot actuó.", bot=True)

    def start(self, mode: str) -> None:
        self.mode = mode
        names = ("Tú", "Bot") if mode == "bot" else ("Jugador 1", "Jugador 2")
        self.engine = GameEngine(random.Random())
        self.engine.start_game(
            initial_lives=self.initial_lives,
            include_jokers=self.include_jokers,
            quick_mode=self.quick_mode,
            names=names,
        )
        self.screen = "play"
        self.message = "Partida iniciada."
        self.hand_cursor = 0
        self.selected_cards.clear()
        self.cancel_modes(quiet=True)

    def toggle_card(self, player) -> None:
        if not player.hand:
            return
        idx = min(self.hand_cursor, len(player.hand) - 1)
        card = player.hand[idx]
        if idx in self.selected_cards:
            self.selected_cards.remove(idx)
            return
        if not self.selected_cards:
            self.selected_cards.add(idx)
            return
        selected = [player.hand[i] for i in sorted(self.selected_cards)]
        if compatible_selection(selected[0], card):
            self.selected_cards.add(idx)
        else:
            self.selected_cards = {idx}

    def begin_attack(self) -> None:
        cards = self.selected_hand_cards()
        if not cards:
            self.message = "Selecciona picas o Joker Negro."
            return
        if not is_attack_card(cards[0]):
            self.message = "Esa carta no ataca."
            return
        if len(cards) > self.engine.state.actions_left:
            self.message = "No tienes acciones suficientes."
            return
        self.target_mode = "attack"
        self.selected_targets = []
        self.life_cursor = 0
        self.message = "Elige objetivo enemigo."

    def do_bank(self, term: Terminal) -> None:
        indices = sorted(self.selected_cards)
        if not indices:
            self.message = "Selecciona tréboles o diamantes."
            return
        if len(indices) > self.engine.state.actions_left:
            self.message = "No tienes acciones suficientes."
            return
        if self.engine.bank_resources(self.engine.state.turn, indices):
            self.engine.consume_actions(len(indices))
            self.after_action(term, "Recursos guardados.")
        else:
            self.message = "Solo puedes guardar ♣ o ♦."

    def do_place_life(self, term: Terminal) -> None:
        idx = self.only_selected_card()
        if idx is None:
            self.message = "Selecciona un corazón."
            return
        if self.engine.place_life(self.engine.state.turn, idx):
            self.engine.consume_actions(1)
            self.after_action(term, "Vida colocada.")
        else:
            self.message = "No se puede colocar esa vida."

    def begin_target(self, mode: str) -> None:
        idx = self.only_selected_card()
        if idx is None:
            self.message = "Selecciona una sola carta."
            return
        card = self.engine.current_player().hand[idx]
        if mode == "shield" and card.suit != CLUBS:
            self.message = "Escudo necesita un ♣."
            return
        if mode == "heal" and card.suit != DIAMONDS:
            self.message = "Curar necesita un ♦."
            return
        if mode == "trap" and (card.suit != SPADES or card.is_joker):
            self.message = "Trampa necesita una ♠ normal."
            return
        if self.engine.state.actions_left < 1:
            self.message = "No tienes acciones."
            return
        self.target_mode = mode
        self.life_cursor = 0
        self.message = self.target_prompt()

    def begin_revive(self, term: Terminal) -> None:
        idx = self.only_selected_card()
        if idx is None:
            self.message = "Selecciona Joker Rojo."
            return
        card = self.engine.current_player().hand[idx]
        if not card.is_red_joker:
            self.message = "Necesitas Joker Rojo."
            return
        if not self.engine.state.graveyard:
            self.message = "Cementerio vacío."
            return
        self.target_mode = "revive"
        self.graveyard_cursor = 0
        self.screen = "graveyard"

    def finish_attack(self, term: Terminal) -> None:
        indices = sorted(self.selected_cards)
        if self.engine.execute_attack(self.selected_targets, indices):
            self.engine.consume_actions(len(indices))
            self.after_action(term, "Ataque ejecutado.")
        else:
            self.message = "Ataque inválido."
        self.cancel_modes(quiet=True)

    def finish_own_life_action(self, term: Terminal, kind: str) -> None:
        idx = self.only_selected_card()
        ok = False
        if idx is None:
            self.message = "Selecciona una carta."
            return
        if kind == "shield":
            ok = self.engine.place_shield(self.engine.state.turn, idx, self.life_cursor)
        elif kind == "heal":
            ok = self.engine.heal_life(self.engine.state.turn, idx, self.life_cursor)
        elif kind == "trap":
            ok = self.engine.place_trap(self.engine.state.turn, idx, self.life_cursor)
        if ok:
            self.engine.consume_actions(1)
            self.after_action(term, f"{kind} ejecutado.")
        else:
            self.message = "Objetivo inválido."
        self.cancel_modes(quiet=True)

    def buy_shop_item(self, item: dict, term: Terminal) -> None:
        if not item["enabled"]():
            self.message = "No puedes comprar eso ahora."
            return
        action = item["action"]
        if action == "draw3":
            ok, _ = self.engine.buy_money_item("draw3")
        elif action == "discard":
            ok, _ = self.engine.buy_money_item("discard", sorted(self.selected_cards))
            self.selected_cards.clear()
        elif action == "roulette":
            ok, segment = self.engine.buy_money_item("roulette")
            if ok and segment is not None:
                self.message = f"Ruleta: {ROULETTE_LABELS[segment]}"
        elif action == "revive":
            ok, _ = self.engine.buy_money_item("revive")
        elif action == "shuffle":
            ok = self.engine.buy_luck_item("shuffle")
        elif action == "ambush":
            ok = self.engine.buy_luck_item("ambush")
        elif action == "espionage":
            ok = self.engine.buy_luck_item("espionage")
            if ok:
                self.target_mode = "espionage"
                self.life_cursor = 0
        elif action == "hide":
            self.target_mode = "hide"
            self.life_cursor = 0
            self.screen = "play"
            self.message = "Elige una vida propia revelada."
            return
        elif action == "sabotage":
            self.target_mode = "sabotage"
            self.life_cursor = 0
            self.screen = "play"
            self.message = "Elige una vida enemiga con escudo."
            return
        else:
            ok = False
        if ok:
            self.engine.consume_actions(1)
            self.screen = "play"
            self.after_action(term, "Compra realizada.")
        else:
            self.message = "Compra inválida."

    def after_action(self, term: Terminal, message: str, *, bot: bool = False) -> None:
        self.message = message
        if self.engine.has_dying_lives():
            term.draw(self.render(term))
            time.sleep(0.7)
            self.engine.cleanup_dead_lives()
        self.selected_cards.clear()
        self.selected_targets.clear()
        self.target_mode = None
        self.screen = "play"
        if self.engine.state.winner:
            return
        if self.engine.state.actions_left <= 0:
            term.draw(self.render(term))
            time.sleep(0.45)
            self.engine.next_turn()
            self.hand_cursor = 0

    def cancel_modes(self, *, quiet: bool = False) -> None:
        self.target_mode = None
        self.selected_targets.clear()
        if self.screen in ("shop", "graveyard"):
            self.screen = "play"
        if not quiet:
            self.message = "Acción cancelada."

    def selected_hand_cards(self) -> list[Card]:
        hand = self.engine.current_player().hand
        return [hand[i] for i in sorted(self.selected_cards) if 0 <= i < len(hand)]

    def only_selected_card(self) -> int | None:
        return next(iter(self.selected_cards)) if len(self.selected_cards) == 1 else None

    def target_player_index(self) -> int:
        if self.target_mode in ("attack", "sabotage", "espionage") or self.engine.state.espionage_mode:
            return self.engine.opponent_idx()
        return self.engine.state.turn

    def max_attack_targets(self) -> int:
        cards = self.selected_hand_cards()
        if any(card.is_black_joker for card in cards):
            return 2
        if any(card.rank == "K" and card.suit == SPADES for card in cards):
            return 2
        return 1

    def target_prompt(self) -> str:
        prompts = {
            "attack": f"Elige objetivo enemigo ({len(self.selected_targets)}/{self.max_attack_targets()}) · Enter · C confirmar",
            "shield": "Elige vida propia para escudo · Enter",
            "heal": "Elige vida propia para curar · Enter",
            "trap": "Elige vida propia para trampa · Enter",
            "hide": "Elige vida propia revelada para ocultar · Enter",
            "sabotage": "Elige escudo enemigo para sabotear · Enter",
            "espionage": "Elige vida enemiga oculta para revelar · Enter",
            "revive": "Elige vida del cementerio",
        }
        return prompts.get(self.target_mode or "", "")

    def selected_prompt(self) -> str:
        cards = self.selected_hand_cards()
        cost = len(cards)
        labels = " ".join(card.label for card in cards)
        damage = attack_preview(cards, self.engine.current_player().attack_buff)
        parts = [style(f"Seleccionado: {labels}", color="white", bold=True), style(f"coste {cost}", color="muted")]
        if damage:
            parts.append(style(f"daño {damage}", color="rose", bold=True))
        return "  ".join(parts)

    def shop_items(self) -> list[dict]:
        state = self.engine.state
        player = self.engine.current_player() if state.players else None
        opponent = state.players[self.engine.opponent_idx()] if state.players else None
        return [
            {"label": "Descarte", "cost": "$8", "desc": "Descarta hasta 2 seleccionadas, roba igual.", "color": "amber", "action": "discard", "enabled": lambda: player and player.money >= 8 and player.hand and state.actions_left >= 1},
            {"label": "Robar 3", "cost": "$10", "desc": "Roba hasta 3 cartas sin pasar de 8.", "color": "amber", "action": "draw3", "enabled": lambda: player and player.money >= 10 and len(player.hand) < 8 and state.actions_left >= 1},
            {"label": "Ruleta", "cost": "$15", "desc": "Buff o nerf para el próximo ataque.", "color": "amber", "action": "roulette", "enabled": lambda: player and player.money >= 15 and state.actions_left >= 1},
            {"label": "Revivir vida", "cost": "$25", "desc": "Trae la última vida del cementerio.", "color": "amber", "action": "revive", "enabled": lambda: player and player.money >= 25 and state.graveyard and state.actions_left >= 1},
            {"label": "Reorganizar", "cost": "8♣", "desc": "Mezcla posiciones de tus vidas.", "color": "emerald", "action": "shuffle", "enabled": lambda: player and player.luck >= 8 and state.actions_left >= 1},
            {"label": "Ocultar", "cost": "10♣", "desc": "Voltea una vida propia revelada.", "color": "emerald", "action": "hide", "enabled": lambda: player and player.luck >= 10 and any(l.face_up for l in player.lives) and state.actions_left >= 1},
            {"label": "Espionaje", "cost": "12♣", "desc": "Revela hasta 2 vidas enemigas.", "color": "emerald", "action": "espionage", "enabled": lambda: player and opponent and player.luck >= 12 and any(not l.face_up for l in opponent.lives) and state.actions_left >= 1},
            {"label": "Sabotaje", "cost": "15♣", "desc": "Destruye un escudo enemigo.", "color": "emerald", "action": "sabotage", "enabled": lambda: player and opponent and player.luck >= 15 and any(l.shield for l in opponent.lives) and state.actions_left >= 1},
            {"label": "Emboscada", "cost": "20♣", "desc": "Tu próximo ataque ignora escudos.", "color": "emerald", "action": "ambush", "enabled": lambda: player and player.luck >= 20 and not player.ambush and state.actions_left >= 1},
        ]


def card_block(
    card: Card,
    *,
    hidden: bool = False,
    selected: bool = False,
    cursor: bool = False,
    target: bool = False,
    own_life: bool = False,
    caption: str = "",
) -> list[str]:
    base_color = "orange" if card.is_red_joker else "purple" if card.is_black_joker else SUIT_COLOR.get(card.suit, "slate")
    border_color = "amber" if selected or cursor else "rose" if target else base_color
    b = lambda text: style(text, color=border_color, bold=selected or cursor or target)
    inner = 9
    if hidden and not own_life:
        body = [
            "░░░░░░░░░",
            "░ ╳ ╳ ╳ ░",
            "░ STRAT ░",
            "░ ╳ ╳ ╳ ░",
            "░░░░░░░░░",
        ]
        rank_top = "??"
        rank_bottom = "??"
        color = "dim"
    else:
        label = card.label
        color = base_color
        rank_top = label
        rank_bottom = label
        center_symbol = card.symbol if not card.is_joker else ("☠" if card.is_black_joker else "✚")
        status = f"HP {card.hp_left:>2}" if card.is_life else f"{card.value:>2} DMG"
        if card.is_black_joker:
            status = "KO x2"
        elif card.is_red_joker:
            status = "REVIVE"
        body = [
            pad(style(rank_top, color=color, bold=True), inner),
            " " * inner,
            center(style(center_symbol, color=color, bold=True), inner),
            center(style(status, color="muted"), inner),
            pad(style(rank_bottom, color=color, bold=True), inner),
        ]
    if card.is_dying:
        body[2] = center(style("KILL", color="rose", bold=True), inner)
    top = b("╭" + "─" * inner + "╮")
    bottom = b("╰" + "─" * inner + "╯")
    lines = [top]
    for raw in body:
        lines.append(b("│") + pad(raw, inner) + b("│"))
    lines.append(bottom)
    if card.is_life:
        extra = hp_bar(card, reveal=not hidden or own_life)
        if own_life and card.trap:
            extra = style("⚑", color="purple", bold=True) + extra[1:]
        if own_life and not card.face_up:
            extra = center(style("oculta", color="dim"), 11)
    else:
        extra = center(style(caption or "", color="amber" if selected else "dim", bold=selected), 11)
    if card.shield and (own_life or not hidden):
        extra = center(style(f"SH {card.shield.value}", color="emerald", bold=True), 11)
    return [*lines, pad(extra, 11)]


def hp_bar(card: Card, *, reveal: bool) -> str:
    if not reveal:
        return style("───────────", color="dim")
    total = max(1, card.value)
    filled = round((card.hp_left / total) * 7)
    color = "emerald" if card.hp_left / total > 0.5 else "amber" if card.hp_left / total > 0.25 else "rose"
    bar = style("█" * filled, color=color) + style("░" * (7 - filled), color="dim")
    return f"{bar}{style(str(card.hp_left).rjust(2), color=color, bold=True)}"


def join_blocks(blocks: list[list[str]], gap: int = 1) -> list[str]:
    if not blocks:
        return []
    height = max(len(block) for block in blocks)
    out = []
    for row in range(height):
        parts = []
        for block in blocks:
            parts.append(block[row] if row < len(block) else " " * 11)
        out.append((" " * gap).join(parts))
    return out


def mini_stack(title: str, count: int, color: str, top: Card | None = None) -> list[str]:
    if top:
        label = top.label
        symbol = top.symbol
    else:
        label = "##"
        symbol = "◆"
    return [
        style("╭───────╮", color=color),
        style("│", color=color) + center(style(label, color=color, bold=True), 7) + style("│", color=color),
        style("│", color=color) + center(style(symbol, color=color, bold=True), 7) + style("│", color=color),
        style("│", color=color) + center(str(count), 7) + style("│", color=color),
        style("╰───────╯", color=color),
        center(style(title, color="dim"), 9),
    ]


def compatible_selection(first: Card, new: Card) -> bool:
    return (is_attack_card(first) and is_attack_card(new)) or (is_resource_card(first) and is_resource_card(new))


def is_attack_card(card: Card) -> bool:
    return card.suit == SPADES or card.is_black_joker


def is_resource_card(card: Card) -> bool:
    return card.suit in (CLUBS, DIAMONDS)


def attack_preview(cards: list[Card], buff: float = 1) -> int:
    if not cards or not is_attack_card(cards[0]):
        return 0
    if any(card.is_black_joker for card in cards):
        return 0
    spades = sum(1 for card in cards if card.suit == SPADES)
    combo = 3 if spades == 2 else 7 if spades >= 3 else 0
    return round((sum(card.value for card in cards) + combo) * buff)


def main() -> int:
    return App().run()
