"""
Middleware: добавляет заголовки безопасности к каждому ответу.

- Referrer-Policy: ограничивает передачу Referer
- Content-Security-Policy: ограничивает источники скриптов, стилей и т.д.
- Permissions-Policy: отключает неиспользуемые браузерные API
"""


class SecurityHeadersMiddleware:
    """
    Добавляет к ответу заголовки Referrer-Policy, Content-Security-Policy, Permissions-Policy.
    Должен идти после SecurityMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not hasattr(response, "headers"):
            return response

        if "Referrer-Policy" not in response.headers:
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        if "Content-Security-Policy" not in response.headers:
            # Яндекс.Карты + OSM/MapLibre: домены тайлов; unsafe-eval — требование JS API Яндекса.
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-eval' https://api-maps.yandex.ru "
                "https://*.api-maps.yandex.ru https://yastatic.net https://suggest-maps.yandex.ru; "
                "style-src 'self' 'unsafe-inline' https://api-maps.yandex.ru "
                "https://*.api-maps.yandex.ru https://yastatic.net; "
                "img-src 'self' data: blob: https:; "
                "font-src 'self' data:; "
                "connect-src 'self' https://api-maps.yandex.ru https://*.api-maps.yandex.ru "
                "https://*.maps.yandex.net https://suggest-maps.yandex.ru https://yastatic.net "
                "https://tile.openstreetmap.org https://*.tile.openstreetmap.org; "
                "worker-src 'self' blob: data: https://api-maps.yandex.ru "
                "https://*.api-maps.yandex.ru https://yastatic.net; "
                "child-src blob: https://api-maps.yandex.ru; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )

        if "Permissions-Policy" not in response.headers:
            response.headers["Permissions-Policy"] = (
                "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
                "magnetometer=(), microphone=(), payment=(), usb=()"
            )

        return response
