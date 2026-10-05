from django.test import TestCase


class UnroutedTestCase(TestCase):
    """Andamiaje que se sacó de la superficie pública.

    /payments/ exponía facturas de cualquiera y tenía un POST que marcaba la
    factura como pagada sin verificar nada. /accounts/register/ dejaba elegir
    programa y nivel, que es lo que filtra la matriculación. Los dos están
    comentados en config/urls.py y accounts/urls.py; estos tests los pinan para
    que nadie los vuelva a montar sin acordarse de por qué.
    """

    def test_payments_are_not_routed(self):
        self.assertEqual(self.client.get("/es/payments/").status_code, 404)

    def test_public_registration_is_not_routed(self):
        self.assertEqual(self.client.get("/es/accounts/register/").status_code, 404)
