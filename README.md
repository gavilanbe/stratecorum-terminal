# 🃏 Stratecorum Terminal

¡Stratecorum convertido en un juego de cartas y estrategia para la terminal, a todo color y sin dependencias externas! 🎨 Hecho en Python, pensado para iTerm con truecolor.

## ✨ Características

- 🃏 Juego de cartas estratégico con vidas, escudos, trampas, curaciones y el Joker rojo.
- 🛒 Tienda para gastar recursos durante la partida.
- 🤖 Dos modos de juego: **local pass-and-play** y **contra un bot**.
- 🎨 Interfaz a todo color (truecolor) optimizada para iTerm.
- 🪶 Cero dependencias externas: solo Python estándar.
- ✅ Incluye tests con `pytest`.

## 🚀 Cómo jugar / ejecutar

```bash
python3 play.py
```

O instalándolo como paquete:

```bash
pip install -e .
stratecorum-terminal
```

Ejecutar los tests:

```bash
pytest
```

> Recomendado: iTerm en una ventana de al menos `110x38`, fuente con símbolos Unicode y color truecolor.

## 🎮 Controles

- `1` / `2`: elegir modo en el menú.
- `←` / `→`: moverte por la mano, vidas o tienda.
- `Space`: seleccionar/deseleccionar carta de la mano.
- `A`: atacar · `G`: guardar recursos · `L`: colocar vida.
- `S`: escudo · `H`: curar · `T`: trampa.
- `R`: Joker rojo / revivir · `M`: tienda · `P`: pasar turno.
- `Enter`: confirmar objetivo · `C`: confirmar ataque multiobjetivo.
- `Esc`: cancelar modo actual · `Q`: salir.

## 🛠️ Tecnología

- **Python 3** (>=3.11), solo librería estándar.
- Empaquetado con `pyproject.toml` y tests con **pytest**.
- Motor, bot, render de terminal y app separados en `src/stratecorum_terminal/`.

## 📦 Parte de mi colección de juegos

Mi juego de estrategia por cartas dentro de la colección de juegos de terminal. 🕹️
