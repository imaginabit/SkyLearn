from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from accounts.decorators import lecturer_required, student_required

User = get_user_model()


class InactiveUserTests(TestCase):
    """Un usuario desactivado no debe pasar los decoradores de rol.

    Sin parentesis, `is_active and is_lecturer or is_superuser` se evaluaba como
    `(is_active and is_lecturer) or is_superuser`, con lo que un superuser
    desactivado entraba igual. Es el caso real de una cuenta desactivada que
    aun tiene la sesion abierta.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.superuser = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="password"
        )
        self.superuser.is_active = False
        self.superuser.save()

    def lecturer_view(self, request):
        return HttpResponse("Lecturer View Content")

    def student_view(self, request):
        return HttpResponse("Student View Content")

    def test_lecturer_required_redirects_inactive_superuser(self):
        request = self.factory.get("/restricted-view")
        request.user = self.superuser

        response = lecturer_required(self.lecturer_view)(request)

        self.assertEqual(response.status_code, 302)

    def test_student_required_redirects_inactive_superuser(self):
        request = self.factory.get("/restricted-view")
        request.user = self.superuser

        response = student_required(self.student_view)(request)

        self.assertEqual(response.status_code, 302)
