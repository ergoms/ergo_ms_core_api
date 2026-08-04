"""System theme catalog and palette helpers."""

DEFAULT_THEME_COLORS = {
    'light': {
        'headerBackground': 'rgba(255, 255, 255, 0.85)',
        'authBackground': 'rgba(255, 255, 255, 0.7)',
        'background': '#f2f2f2',
        'border': '#e0e0e0',
        'primaryText': '#101223',
        'secondaryText': '#6e6e6e',
        'primaryBackground': '#ffffff',
        'secondaryBackground': '#f1f1f1',
        'hoverBackground': '#e1e1e1',
        'accent': '#d0322d',
    },
    'dark': {
        'headerBackground': 'rgba(30, 30, 30, 0.85)',
        'authBackground': 'rgba(30, 30, 30, 0.7)',
        'background': '#111112',
        'border': '#555555',
        'primaryText': '#c9cccf',
        'secondaryText': '#6e6e6e',
        'primaryBackground': '#18181a',
        'secondaryBackground': '#2a2a2c',
        'hoverBackground': '#3d3d3f',
        'accent': '#f14336',
    },
}


def _hex_to_rgb(value):
    raw = (value or '').strip().lstrip('#')
    if len(raw) != 6:
        return None
    try:
        return tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def _mix_hex(base_hex, accent_hex, ratio):
    """Смешивает hex-цвета: ratio — доля accent (0..1)."""
    base = _hex_to_rgb(base_hex)
    accent = _hex_to_rgb(accent_hex)
    if base is None or accent is None:
        return base_hex
    ratio = max(0.0, min(1.0, float(ratio)))
    mixed = tuple(round(b * (1 - ratio) + a * ratio) for b, a in zip(base, accent))
    return '#{:02x}{:02x}{:02x}'.format(*mixed)


def _rgba(hex_color, alpha):
    rgb = _hex_to_rgb(hex_color)
    if rgb is None:
        return f'rgba(255, 255, 255, {alpha})'
    return f'rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {alpha})'


def _palette(base, accent, *, tint=0.06):
    """Базовая палитра light/dark + accent и лёгкий tint поверхностей."""
    colors = dict(DEFAULT_THEME_COLORS[base])
    colors['accent'] = accent
    colors['background'] = _mix_hex(colors['background'], accent, tint)
    colors['secondaryBackground'] = _mix_hex(colors['secondaryBackground'], accent, tint * 0.85)
    colors['hoverBackground'] = _mix_hex(colors['hoverBackground'], accent, tint * 1.15)
    colors['border'] = _mix_hex(colors['border'], accent, tint * 1.4)
    return colors


def _rich_light(*, background, card, muted, border, foreground, muted_fg, accent):
    """Полная светлая палитра (ui-ux-pro-max → ключи ERGO)."""
    return {
        'headerBackground': _rgba(card, 0.9),
        'authBackground': _rgba(card, 0.78),
        'background': background,
        'border': border,
        'primaryText': foreground,
        'secondaryText': muted_fg,
        'primaryBackground': card,
        'secondaryBackground': muted,
        'hoverBackground': _mix_hex(muted, accent, 0.12),
        'accent': accent,
    }


def _rich_dark(*, background, card, muted, border, foreground, muted_fg, accent):
    """Полная тёмная палитра под ту же смысловую тему."""
    return {
        'headerBackground': _rgba(card, 0.92),
        'authBackground': _rgba(background, 0.88),
        'background': background,
        'border': border,
        'primaryText': foreground,
        'secondaryText': muted_fg,
        'primaryBackground': card,
        'secondaryBackground': muted,
        'hoverBackground': _mix_hex(muted, accent, 0.18),
        'accent': accent,
    }


# Карта старых имён → новых (для миграций без дубликатов).
SYSTEM_THEME_RENAME_MAP = {
    'Светлая': 'Стандарт · светлая',
    'Тёмная': 'Стандарт · тёмная',
    'Изумрудная': 'Изумруд',
    'Изумрудная (тёмная)': 'Изумруд · тёмная',
    'Синяя': 'Лазурь',
    'Синяя (тёмная)': 'Лазурь · тёмная',
    'Янтарная': 'Янтарь',
    'Янтарная (тёмная)': 'Янтарь · тёмная',
    'Морской доверие': 'Корпоративный',
    'Морской доверие (тёмная)': 'Корпоративный · тёмная',
    # Исторические имена тем в БД (до переименования), не привязка к модулю CRM
    'CRM синий': 'Деловой синий',
    'CRM синий (тёмная)': 'Деловой синий · тёмная',
    'Бирюзовый фокус': 'Бирюза',
    'Бирюзовый фокус (тёмная)': 'Бирюза · тёмная',
    'Спокойный циан': 'Циан',
    'Спокойный циан (тёмная)': 'Циан · тёмная',
    'Деловой индиго': 'Индиго',
    'Деловой индиго (тёмная)': 'Индиго · тёмная',
}


SYSTEM_THEMES = (
    {
        'name': 'Стандарт · светлая',
        'description': 'Базовая светлая тема интерфейса',
        'base_theme': 'light',
        'is_default': True,
        'colors': DEFAULT_THEME_COLORS['light'],
    },
    {
        'name': 'Стандарт · тёмная',
        'description': 'Базовая тёмная тема интерфейса',
        'base_theme': 'dark',
        'is_default': False,
        'colors': DEFAULT_THEME_COLORS['dark'],
    },
    {
        'name': 'Изумруд',
        'description': 'Светлая тема с изумрудным акцентом',
        'base_theme': 'light',
        'is_default': False,
        'colors': _palette('light', '#059669'),
    },
    {
        'name': 'Изумруд · тёмная',
        'description': 'Тёмная тема с изумрудным акцентом',
        'base_theme': 'dark',
        'is_default': False,
        'colors': _palette('dark', '#34d399', tint=0.08),
    },
    {
        'name': 'Лазурь',
        'description': 'Светлая тема с синим акцентом',
        'base_theme': 'light',
        'is_default': False,
        'colors': _palette('light', '#2563eb'),
    },
    {
        'name': 'Лазурь · тёмная',
        'description': 'Тёмная тема с синим акцентом',
        'base_theme': 'dark',
        'is_default': False,
        'colors': _palette('dark', '#60a5fa', tint=0.08),
    },
    {
        'name': 'Янтарь',
        'description': 'Светлая тема с янтарным акцентом',
        'base_theme': 'light',
        'is_default': False,
        'colors': _palette('light', '#d97706'),
    },
    {
        'name': 'Янтарь · тёмная',
        'description': 'Тёмная тема с янтарным акцентом',
        'base_theme': 'dark',
        'is_default': False,
        'colors': _palette('dark', '#fbbf24', tint=0.08),
    },
    {
        'name': 'Корпоративный',
        'description': 'Строгая корпоративная палитра с синим акцентом',
        'base_theme': 'light',
        'is_default': False,
        'colors': _rich_light(
            background='#F8FAFC',
            card='#FFFFFF',
            muted='#E8ECF1',
            border='#E2E8F0',
            foreground='#020617',
            muted_fg='#64748B',
            accent='#0369A1',
        ),
    },
    {
        'name': 'Корпоративный · тёмная',
        'description': 'Тёмный вариант корпоративной палитры',
        'base_theme': 'dark',
        'is_default': False,
        'colors': _rich_dark(
            background='#0B1220',
            card='#111827',
            muted='#1E293B',
            border='#334155',
            foreground='#F8FAFC',
            muted_fg='#94A3B8',
            accent='#38BDF8',
        ),
    },
    {
        'name': 'Деловой синий',
        'description': 'Спокойный синий для повседневной работы',
        'base_theme': 'light',
        'is_default': False,
        'colors': _rich_light(
            background='#F8FAFC',
            card='#FFFFFF',
            muted='#F1F5FD',
            border='#E4ECFC',
            foreground='#0F172A',
            muted_fg='#64748B',
            accent='#2563EB',
        ),
    },
    {
        'name': 'Деловой синий · тёмная',
        'description': 'Тёмный вариант делового синего',
        'base_theme': 'dark',
        'is_default': False,
        'colors': _rich_dark(
            background='#0B1224',
            card='#111C33',
            muted='#1A2744',
            border='#2A3B5C',
            foreground='#E8EEF9',
            muted_fg='#94A3B8',
            accent='#60A5FA',
        ),
    },
    {
        'name': 'Бирюза',
        'description': 'Бирюзовый акцент для длительной работы с данными',
        'base_theme': 'light',
        'is_default': False,
        'colors': _rich_light(
            background='#F0FDFA',
            card='#FFFFFF',
            muted='#E8F1F4',
            border='#99F6E4',
            foreground='#134E4A',
            muted_fg='#64748B',
            accent='#0D9488',
        ),
    },
    {
        'name': 'Бирюза · тёмная',
        'description': 'Тёмный вариант бирюзовой палитры',
        'base_theme': 'dark',
        'is_default': False,
        'colors': _rich_dark(
            background='#042F2E',
            card='#0B3B39',
            muted='#134E4A',
            border='#2A6A64',
            foreground='#ECFDF5',
            muted_fg='#99F6E4',
            accent='#2DD4BF',
        ),
    },
    {
        'name': 'Циан',
        'description': 'Мягкий циан для спокойных экранов',
        'base_theme': 'light',
        'is_default': False,
        'colors': _rich_light(
            background='#ECFEFF',
            card='#FFFFFF',
            muted='#E8F1F6',
            border='#A5F3FC',
            foreground='#164E63',
            muted_fg='#64748B',
            accent='#0891B2',
        ),
    },
    {
        'name': 'Циан · тёмная',
        'description': 'Тёмный вариант циан-палитры',
        'base_theme': 'dark',
        'is_default': False,
        'colors': _rich_dark(
            background='#083344',
            card='#0E4A5C',
            muted='#155E75',
            border='#1E7490',
            foreground='#ECFEFF',
            muted_fg='#A5F3FC',
            accent='#22D3EE',
        ),
    },
    {
        'name': 'Индиго',
        'description': 'Современный индиго для панелей управления',
        'base_theme': 'light',
        'is_default': False,
        'colors': _rich_light(
            background='#F5F3FF',
            card='#FFFFFF',
            muted='#EBEFF9',
            border='#E0E7FF',
            foreground='#1E1B4B',
            muted_fg='#64748B',
            accent='#6366F1',
        ),
    },
    {
        'name': 'Индиго · тёмная',
        'description': 'Тёмный вариант индиго-палитры',
        'base_theme': 'dark',
        'is_default': False,
        'colors': _rich_dark(
            background='#11131F',
            card='#1A1D2E',
            muted='#252A40',
            border='#373E5C',
            foreground='#EEF2FF',
            muted_fg='#A5B4FC',
            accent='#818CF8',
        ),
    },
    {
        'name': 'Финансовый',
        'description': 'Строгая палитра для счетов и финансовых экранов',
        'base_theme': 'light',
        'is_default': False,
        'colors': _rich_light(
            background='#F8FAFC',
            card='#FFFFFF',
            muted='#EEF2F6',
            border='#E2E8F0',
            foreground='#1E3A5F',
            muted_fg='#64748B',
            accent='#059669',
        ),
    },
    {
        'name': 'Финансовый · тёмная',
        'description': 'Тёмный вариант финансовой палитры',
        'base_theme': 'dark',
        'is_default': False,
        'colors': _rich_dark(
            background='#0B1520',
            card='#122033',
            muted='#1A2F45',
            border='#2A4560',
            foreground='#F1F5F9',
            muted_fg='#94A3B8',
            accent='#34D399',
        ),
    },
    {
        'name': 'Служебный',
        'description': 'Официальная сине-зелёная палитра для служебных разделов',
        'base_theme': 'light',
        'is_default': False,
        'colors': _rich_light(
            background='#F8FAFC',
            card='#FFFFFF',
            muted='#EEF2FF',
            border='#E0E7FF',
            foreground='#1E40AF',
            muted_fg='#64748B',
            accent='#16A34A',
        ),
    },
    {
        'name': 'Служебный · тёмная',
        'description': 'Тёмный вариант служебной палитры',
        'base_theme': 'dark',
        'is_default': False,
        'colors': _rich_dark(
            background='#0B1224',
            card='#121A33',
            muted='#1A2744',
            border='#2A3B5C',
            foreground='#F1F5F9',
            muted_fg='#94A3B8',
            accent='#4ADE80',
        ),
    },
    {
        'name': 'Небесный',
        'description': 'Светлая небесно-синяя палитра для открытых экранов',
        'base_theme': 'light',
        'is_default': False,
        'colors': _rich_light(
            background='#F0F9FF',
            card='#FFFFFF',
            muted='#E0F2FE',
            border='#BAE6FD',
            foreground='#0369A1',
            muted_fg='#64748B',
            accent='#0EA5E9',
        ),
    },
    {
        'name': 'Небесный · тёмная',
        'description': 'Тёмный вариант небесной палитры',
        'base_theme': 'dark',
        'is_default': False,
        'colors': _rich_dark(
            background='#082F49',
            card='#0C3D5C',
            muted='#0E4A6E',
            border='#1A5F85',
            foreground='#F0F9FF',
            muted_fg='#7DD3FC',
            accent='#38BDF8',
        ),
    },
    {
        'name': 'Контрастный',
        'description': 'Синий с оранжевым акцентом для выразительных экранов',
        'base_theme': 'light',
        'is_default': False,
        'colors': _rich_light(
            background='#F8FAFC',
            card='#FFFFFF',
            muted='#EFF3FF',
            border='#DBEAFE',
            foreground='#1E293B',
            muted_fg='#64748B',
            accent='#EA580C',
        ),
    },
    {
        'name': 'Контрастный · тёмная',
        'description': 'Тёмный вариант контрастной палитры',
        'base_theme': 'dark',
        'is_default': False,
        'colors': _rich_dark(
            background='#0B1224',
            card='#111C33',
            muted='#1A2744',
            border='#2A3B5C',
            foreground='#F1F5F9',
            muted_fg='#94A3B8',
            accent='#FB923C',
        ),
    },
    # --- Инклюзивные палитры (синхрон имён с themeCategories.js на клиенте) ---
    {
        'name': 'Высокий контраст',
        'description': 'Максимальная читаемость текста и элементов управления',
        'base_theme': 'light',
        'is_default': False,
        'colors': _rich_light(
            background='#FFFFFF',
            card='#FFFFFF',
            muted='#F0F0F0',
            border='#1A1A1A',
            foreground='#0A0A0A',
            muted_fg='#333333',
            accent='#0000EE',
        ),
    },
    {
        'name': 'Высокий контраст · тёмная',
        'description': 'Тёмный вариант с максимальной читаемостью',
        'base_theme': 'dark',
        'is_default': False,
        'colors': _rich_dark(
            background='#000000',
            card='#121212',
            muted='#1E1E1E',
            border='#FFFFFF',
            foreground='#FFFFFF',
            muted_fg='#E0E0E0',
            accent='#66B2FF',
        ),
    },
    {
        'name': 'Тёплый свет',
        'description': 'Кремовые тона с меньшим синим — комфортнее вечером',
        'base_theme': 'light',
        'is_default': False,
        'colors': _rich_light(
            background='#FFF8F0',
            card='#FFFCF8',
            muted='#F5EDE3',
            border='#E8D9C8',
            foreground='#3D2E1F',
            muted_fg='#7A6550',
            accent='#C2410C',
        ),
    },
    {
        'name': 'Тёплый свет · тёмная',
        'description': 'Тёплый тёмный вариант с приглушённым синим',
        'base_theme': 'dark',
        'is_default': False,
        'colors': _rich_dark(
            background='#1A1410',
            card='#241C16',
            muted='#322820',
            border='#4A3B2F',
            foreground='#F5EDE3',
            muted_fg='#C4B5A5',
            accent='#FB923C',
        ),
    },
    {
        'name': 'Ясные · RG',
        'description': 'Палитра, в которой легче различать красный и зелёный',
        'base_theme': 'light',
        'is_default': False,
        'colors': _rich_light(
            background='#F7F9FC',
            card='#FFFFFF',
            muted='#EEF3F8',
            border='#D0DCE8',
            foreground='#1A1A1A',
            muted_fg='#5A6A7A',
            accent='#0077BB',
        ),
    },
    {
        'name': 'Ясные · RG · тёмная',
        'description': 'Тёмный вариант палитры с удобным различением красного и зелёного',
        'base_theme': 'dark',
        'is_default': False,
        'colors': _rich_dark(
            background='#0D1520',
            card='#152030',
            muted='#1E2E42',
            border='#334A63',
            foreground='#F0F4F8',
            muted_fg='#A8B8C8',
            accent='#EE7733',
        ),
    },
    {
        'name': 'Мягкие · BY',
        'description': 'Палитра, в которой легче различать синий и жёлтый',
        'base_theme': 'light',
        'is_default': False,
        'colors': _rich_light(
            background='#FAF8FB',
            card='#FFFFFF',
            muted='#F3EEF5',
            border='#E0D4E6',
            foreground='#1F1224',
            muted_fg='#6B5A70',
            accent='#CC3377',
        ),
    },
    {
        'name': 'Мягкие · BY · тёмная',
        'description': 'Тёмный вариант палитры с удобным различением синего и жёлтого',
        'base_theme': 'dark',
        'is_default': False,
        'colors': _rich_dark(
            background='#140F18',
            card='#1E1624',
            muted='#2A2034',
            border='#443550',
            foreground='#F8F4FA',
            muted_fg='#C8B8D0',
            accent='#33BBAA',
        ),
    },
    {
        'name': 'Монохром',
        'description': 'Без цветовых акцентов — смысл передаётся яркостью',
        'base_theme': 'light',
        'is_default': False,
        'colors': _rich_light(
            background='#F5F5F5',
            card='#FFFFFF',
            muted='#EBEBEB',
            border='#C8C8C8',
            foreground='#111111',
            muted_fg='#666666',
            accent='#1A1A1A',
        ),
    },
    {
        'name': 'Монохром · тёмная',
        'description': 'Тёмный монохром без цветовых акцентов',
        'base_theme': 'dark',
        'is_default': False,
        'colors': _rich_dark(
            background='#0D0D0D',
            card='#1A1A1A',
            muted='#262626',
            border='#404040',
            foreground='#F5F5F5',
            muted_fg='#A3A3A3',
            accent='#E5E5E5',
        ),
    },
)

# Базовые имена инклюзивных тем (без суффикса « · тёмная»). Синхрон с themeCategories.js.
ACCESSIBILITY_THEME_BASE_NAMES = frozenset({
    'Высокий контраст',
    'Тёплый свет',
    'Ясные · RG',
    'Мягкие · BY',
    'Монохром',
})

# Старые имена → новые (миграции без дубликатов).
ACCESSIBILITY_THEME_RENAME_MAP = {
    'Дальтонизм · RG': 'Ясные · RG',
    'Дальтонизм · RG · тёмная': 'Ясные · RG · тёмная',
    'Дальтонизм · BY': 'Мягкие · BY',
    'Дальтонизм · BY · тёмная': 'Мягкие · BY · тёмная',
    'Ясные цвета': 'Ясные · RG',
    'Ясные цвета · тёмная': 'Ясные · RG · тёмная',
    'Мягкие оттенки': 'Мягкие · BY',
    'Мягкие оттенки · тёмная': 'Мягкие · BY · тёмная',
}

_DARK_SUFFIX = ' · тёмная'
_LIGHT_SUFFIX = ' · светлая'


def derive_site_theme_pair_key(name):
    """Ключ группировки light/dark вариантов темы сайта — базовое имя без суффикса варианта."""
    raw = (name or '').strip()
    if raw.endswith(_DARK_SUFFIX):
        return raw[: -len(_DARK_SUFFIX)].strip()
    if raw.endswith(_LIGHT_SUFFIX):
        return raw[: -len(_LIGHT_SUFFIX)].strip()
    return raw


def is_accessibility_theme(name):
    """True, если тема относится к инклюзивным палитрам."""
    raw = (name or '').strip()
    if not raw:
        return False
    if raw in ACCESSIBILITY_THEME_BASE_NAMES:
        return True
    if raw.endswith(_DARK_SUFFIX):
        return raw[: -len(_DARK_SUFFIX)] in ACCESSIBILITY_THEME_BASE_NAMES
    return False


