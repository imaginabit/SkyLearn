from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class LogoutTests(TestCase):
    """El boton de salir manda un POST: Django 5 ya no cierra sesion por GET."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tmp-logout", password="password"
        )
        self.client.force_login(self.user)

    def test_el_menu_saca_un_formulario_y_no_un_enlace(self):
        html = self.client.get(reverse("profile")).content.decode()

        self.assertIn(f'method="post" action="{reverse("logout")}"', html)
        self.assertNotIn(f'href="{reverse("logout")}"', html)

    def test_el_post_cierra_la_sesion(self):
        response = self.client.post(reverse("logout"))

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)
