"""Посимвольная замена ошибочной раскладки клавиатуры EN ↔ RU (qwerty ↔ йцукен)."""

_EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`"
_RU = "йцукенгшщзхъфывапролджэячсмитьбюё"
_EN_UPPER = _EN.upper()
_RU_UPPER = _RU.upper()

_LAYOUT_MAP = str.maketrans(
    _EN + _EN_UPPER + _RU + _RU_UPPER,
    _RU + _RU_UPPER + _EN + _EN_UPPER,
)


def swap_keyboard_layout(text: str) -> str:
    """Заменить символы как при вводе в другой раскладке (EN↔RU)."""
    if not text:
        return text
    return text.translate(_LAYOUT_MAP)


def search_layout_variants(text: str) -> list[str]:
    """Уникальные непустые варианты строки для поиска: исходный и с заменой раскладки."""
    normalized = (text or '').strip()
    if not normalized:
        return []
    variants = [normalized]
    swapped = swap_keyboard_layout(normalized)
    if swapped and swapped != normalized:
        variants.append(swapped)
    return variants
