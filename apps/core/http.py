from django.conf import settings
from django.http import HttpRequest


def ip_cliente(request: HttpRequest) -> str:
    """IP del cliente. Solo confía en X-Forwarded-For si hay proxies declarados."""
    proxies = settings.TRUSTED_PROXY_COUNT
    reenviadas = [ip.strip() for ip in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")]
    reenviadas = [ip for ip in reenviadas if ip]
    if proxies > 0 and len(reenviadas) >= proxies:
        return reenviadas[-proxies]
    return request.META.get("REMOTE_ADDR", "")
