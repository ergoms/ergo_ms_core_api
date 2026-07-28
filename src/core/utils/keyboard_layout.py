"""Посимвольная замена ошибочной раскладки клавиатуры EN ↔ RU (qwerty ↔ йцукен).

Используется в поиске: запрос, набранный в «не той» раскладке, даёт те же
результаты (например ``cnfyjr`` → ``станок``).
"""

from __future__ import annotations

# Физические клавиши Windows: unshifted + shifted (`.`/`/` и `ё`/`Ё` — как на ЙЦУКЕН).
_EN_KEYS = r"`qwertyuiop[]asdfghjkl;'zxcvbnm,./" + '~QWERTYUIOP{}ASDFGHJKL:"ZXCVBNM<>?'
_RU_KEYS = 'ёйцукенгшщзхъфывапролджэячсмитьбю.' + 'ЁЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,'

if len(_EN_KEYS) != len(_RU_KEYS):
    raise RuntimeError('keyboard_layout: EN/RU key maps length mismatch')

_LAYOUT_MAP = str.maketrans(_EN_KEYS + _RU_KEYS, _RU_KEYS + _EN_KEYS)
_LATIN_CHARS = frozenset(_EN_KEYS)
_CYRILLIC_CHARS = frozenset(_RU_KEYS)


def swap_keyboard_layout(text: str, *, only: str | None = None) -> str:
    """Заменить символы как при вводе в другой раскладке (EN↔RU).

    ``only``:
      - ``None`` — все символы из карты;
      - ``'latin'`` — только латиница/знаки EN-раскладки (смешанный ввод);
      - ``'cyrillic'`` — только кириллица/знаки RU-раскладки.
    """
    if not text:
        return text
    if only is None:
        return text.translate(_LAYOUT_MAP)
    if only == 'latin':
        charset = _LATIN_CHARS
    elif only == 'cyrillic':
        charset = _CYRILLIC_CHARS
    else:
        raise ValueError("only must be None, 'latin' or 'cyrillic'")
    return ''.join(
        ch.translate(_LAYOUT_MAP) if ch in charset else ch
        for ch in text
    )


def search_layout_variants(text: str) -> list[str]:
    """Уникальные непустые варианты строки для ``icontains``-поиска.

    Порядок: исходный → полная смена раскладки → только латиница → только кириллица.
    Частичные варианты нужны, когда в строке смешаны обе раскладки.
    """
    normalized = ' '.join((text or '').split())
    if not normalized:
        return []

    variants: list[str] = []
    seen: set[str] = set()

    def _add(value: str) -> None:
        if value and value not in seen:
            seen.add(value)
            variants.append(value)

    _add(normalized)
    _add(swap_keyboard_layout(normalized))
    _add(swap_keyboard_layout(normalized, only='latin'))
    _add(swap_keyboard_layout(normalized, only='cyrillic'))
    return variants
