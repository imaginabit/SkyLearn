from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.translation import gettext

User = get_user_model()


class GetUserRoleTests(TestCase):
    """`get_user_role` se usa en el sidebar y en los PDF.

    Antes, si la cuenta no era superuser, alumno, docente ni padre (un jefe de
    departamento, o una cuenta dada de alta a pelo), la variable `role` se
    quedaba sin asignar y la pagina petaba con UnboundLocalError.
    """

    def test_una_cuenta_sin_ningun_rol_no_revienta(self):
        suelto = User.objects.create_user(username="suelto", password="password")

        self.assertTrue(suelto.get_user_role)

    def test_cada_rol_devuelve_el_suyo(self):
        # se compara contra gettext y no contra el literal: el idioma por
        # defecto es el castellano y sale "Estudiante", no "Student"
        casos = {
            "is_superuser": gettext("Admin"),
            "is_student": gettext("Student"),
            "is_lecturer": gettext("Lecturer"),
            "is_parent": gettext("Parent"),
        }
        for flag, esperado in casos.items():
            with self.subTest(flag=flag):
                user = User.objects.create_user(
                    username=f"u-{flag}", password="password", **{flag: True}
                )
                self.assertEqual(str(user.get_user_role), esperado)
