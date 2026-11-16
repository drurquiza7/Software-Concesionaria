from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.http import ip_cliente
from apps.core.ratelimit import registrar_intento

from . import selectors
from .decorators import URL_SELECTOR, requiere_sesion, vista_publica
from .forms import LoginForm
from .session import activar_concesionaria

ERROR_CREDENCIALES = "El email o la contraseña no son correctos. Revisalos y probá de nuevo."
ERROR_DEMASIADOS_INTENTOS = "Hiciste demasiados intentos. Esperá un minuto y volvé a probar."


def _intento_permitido(request: HttpRequest, email: str) -> bool:
    """RS-16. Se evalúan los dos contadores siempre, para que ambos registren el intento."""
    limite = settings.LOGIN_INTENTOS_MAXIMOS
    ventana = settings.LOGIN_VENTANA_SEGUNDOS
    por_ip = registrar_intento("login-ip", ip_cliente(request), limite, ventana)
    por_email = registrar_intento("login-email", email.strip().lower(), limite, ventana)
    return por_ip and por_email


def _destino_seguro(request: HttpRequest) -> str | None:
    destino = request.POST.get("next") or request.GET.get("next")
    if destino and url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return destino
    return None


@vista_publica
@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect(URL_SELECTOR)
    form = LoginForm(request.POST or None)
    contexto = {"form": form, "next": _destino_seguro(request) or ""}
    if request.method != "POST":
        return render(request, "accounts/login.html", contexto)
    if not _intento_permitido(request, request.POST.get("email", "")):
        contexto["error"] = ERROR_DEMASIADOS_INTENTOS
        respuesta = render(request, "accounts/login.html", contexto, status=429)
        respuesta["Retry-After"] = str(settings.LOGIN_VENTANA_SEGUNDOS)
        return respuesta
    usuario = None
    if form.is_valid():
        usuario = authenticate(
            request, email=form.cleaned_data["email"], password=form.cleaned_data["password"]
        )
    if usuario is None:
        # Mismo mensaje para email inexistente, clave incorrecta o usuario inactivo.
        contexto["error"] = ERROR_CREDENCIALES
        return render(request, "accounts/login.html", contexto, status=401)
    login(request, usuario)
    membresias = selectors.membresias_de_usuario(usuario)
    if len(membresias) == 1:
        activar_concesionaria(request, membresias[0])
    return redirect(contexto["next"] or URL_SELECTOR)


@requiere_sesion
@require_POST
def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect(settings.LOGIN_URL)


@requiere_sesion
@require_http_methods(["GET", "POST"])
def seleccionar_concesionaria(request: HttpRequest) -> HttpResponse:
    membresias = selectors.membresias_de_usuario(request.user)
    if request.method == "POST":
        # El valor del formulario solo elige entre las membresías propias, nunca un tenant libre.
        pedida = request.POST.get("membresia", "")
        elegida = next((m for m in membresias if str(m.pk) == pedida), None)
        if elegida is None:
            raise Http404
        activar_concesionaria(request, elegida)
        return redirect(URL_SELECTOR)
    return render(
        request,
        "accounts/seleccionar_concesionaria.html",
        {"membresias": membresias, "tenant_activo": request.tenant},
    )
