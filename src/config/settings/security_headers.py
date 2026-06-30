"""
Заголовки и настройки безопасности HTTP.

Используются SecurityMiddleware и XFrameOptionsMiddleware (уже в MIDDLEWARE).
Для CSP, Referrer-Policy, Permissions-Policy — SecurityHeadersMiddleware.
"""

# Запрет MIME-sniffing (X-Content-Type-Options: nosniff)
SECURE_CONTENT_TYPE_NOSNIFF = True

# Запрет встраивания в iframe (X-Frame-Options). DENY — максимальная защита от clickjacking
X_FRAME_OPTIONS = "DENY"

# Редирект на HTTPS и HSTS включаются только в production (см. patterns/production.py)
