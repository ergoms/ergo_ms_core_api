DEVICE_TYPE_LABELS = {
    'desktop': 'Компьютер',
    'laptop': 'Ноутбук',
    'mobile': 'Смартфон',
    'tablet': 'Планшет',
}

_UNKNOWN_LOCATION = frozenset({'', 'неизвестно', 'unknown', 'n/a'})


def get_client_ip(request) -> str:
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return (request.META.get('REMOTE_ADDR') or '').strip()


def parse_user_agent(user_agent: str) -> dict:
    ua = user_agent or ''
    ua_lower = ua.lower()

    browser = 'Неизвестно'
    if 'edg/' in ua_lower or 'edge/' in ua_lower:
        browser = 'Microsoft Edge'
    elif 'firefox/' in ua_lower:
        browser = 'Firefox'
    elif 'chrome/' in ua_lower and 'chromium' not in ua_lower:
        browser = 'Chrome'
    elif 'safari/' in ua_lower and 'chrome/' not in ua_lower:
        browser = 'Safari'
    elif 'opr/' in ua_lower or 'opera' in ua_lower:
        browser = 'Opera'

    os_name = 'Неизвестно'
    if 'windows' in ua_lower:
        os_name = 'Windows'
    elif 'mac os' in ua_lower or 'macintosh' in ua_lower:
        os_name = 'macOS'
    elif 'android' in ua_lower:
        os_name = 'Android'
    elif 'iphone' in ua_lower or 'ipad' in ua_lower:
        os_name = 'iOS'
    elif 'linux' in ua_lower:
        os_name = 'Linux'

    return {'browser': browser, 'os': os_name}


def format_device_location(city: str | None, country: str | None) -> str:
    parts = []
    for value in (city, country):
        normalized = (value or '').strip()
        if normalized.lower() not in _UNKNOWN_LOCATION:
            parts.append(normalized)
    return ', '.join(parts)


def get_device_type_display(device_type: str) -> str:
    return DEVICE_TYPE_LABELS.get(device_type, device_type or 'Устройство')


def build_device_display_name(user_agent: str, device_type: str) -> str:
    parsed = parse_user_agent(user_agent)
    browser = parsed['browser']
    os_name = parsed['os']
    if browser != 'Неизвестно' and os_name != 'Неизвестно':
        return f'{browser} · {os_name}'
    fallback = {
        'mobile': 'Смартфон',
        'tablet': 'Планшет',
        'laptop': 'Ноутбук',
        'desktop': 'Компьютер',
    }
    return fallback.get(device_type, 'Устройство')
