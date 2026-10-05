import threading
from datetime import datetime
from django.contrib.auth import get_user_model
from django.conf import settings
from core.utils import send_html_email


def generate_password():
    return get_user_model().objects.make_random_password()


def _next_numbered_id(prefix):
    """Siguiente id libre del tipo <prefijo>-<año>-<n>.

    Va por el máximo existente, no por la cuenta: si se borra a alguien del
    medio, la cuenta baja y el siguiente recibiría un número ya ocupado. El
    espacio de ids es el de los usernames, así que no se filtra por rol.
    """
    year = datetime.now().strftime("%Y")
    start = f"{prefix}-{year}-"
    taken = [
        int(name[len(start) :])
        for name in get_user_model()
        .objects.filter(username__startswith=start)
        .values_list("username", flat=True)
        if name[len(start) :].isdigit()
    ]
    # ponytail: dos altas simultáneas pueden pedir el mismo número y el UNIQUE
    # de la BD hace fallar una de las dos. Con altas simultáneas, reintentar.
    return f"{start}{max(taken, default=0) + 1}"


def generate_student_id():
    return _next_numbered_id(settings.STUDENT_ID_PREFIX)


def generate_lecturer_id():
    return _next_numbered_id(settings.LECTURER_ID_PREFIX)


def generate_student_credentials():
    return generate_student_id(), generate_password()


def generate_lecturer_credentials():
    return generate_lecturer_id(), generate_password()


class EmailThread(threading.Thread):
    def __init__(self, subject, recipient_list, template_name, context):
        self.subject = subject
        self.recipient_list = recipient_list
        self.template_name = template_name
        self.context = context
        threading.Thread.__init__(self)

    def run(self):
        send_html_email(
            subject=self.subject,
            recipient_list=self.recipient_list,
            template=self.template_name,
            context=self.context,
        )


def send_new_account_email(user, password):
    if user.is_student:
        template_name = "accounts/email/new_student_account_confirmation.html"
    else:
        template_name = "accounts/email/new_lecturer_account_confirmation.html"
    email = {
        "subject": "Your SkyLearn account confirmation and credentials",
        "recipient_list": [user.email],
        "template_name": template_name,
        "context": {
            "user": user,
            "password": password,
            # datos de protección de datos, para el aviso que va en el correo
            "responsable": settings.DATA_CONTROLLER,
            "email_dpo": settings.DATA_PROTECTION_EMAIL,
            "retencion": settings.DATA_RETENTION,
            "site_url": settings.SITE_URL,
        },
    }
    EmailThread(**email).start()


def client_ip(request):
    """La IP de quien hace la petición, mirando detrás del proxy.

    El servidor va con nginx delante de gunicorn, así que REMOTE_ADDR es el del
    proxy. La primera dirección de X-Forwarded-For es la del cliente.
    """
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def record_consent(user, request, recorded_by=None):
    """Deja la prueba del consentimiento informado (RGPD, art. 7.1).

    Se guarda la versión del texto que estaba publicado, la fecha, la IP y el
    navegador. Si el texto cambia, se sube PRIVACY_VERSION y las pruebas
    anteriores siguen diciendo con qué versión se consintió.
    """
    from .models import ConsentRecord

    return ConsentRecord.objects.create(
        user=user,
        version=settings.PRIVACY_VERSION,
        ip=client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:255],
        recorded_by=recorded_by,
    )
