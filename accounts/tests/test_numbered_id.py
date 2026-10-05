from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class NumberedIdTests(TestCase):
    """El id numerico de las altas no se puede reutilizar.

    Antes iba por `count()`, que baja en cuanto se borra a alguien: al dar de
    alta tras un borrado, el siguiente recibia un numero ya ocupado y el alta
    reventaba con IntegrityError.
    """

    def setUp(self):
        self.prefijo = f"ugr-{datetime.now().strftime('%Y')}-"

    def ids(self):
        return sorted(
            int(u[len(self.prefijo) :])
            for u in User.objects.filter(username__startswith=self.prefijo).values_list(
                "username", flat=True
            )
        )

    def alta(self, tmp):
        User.objects.create_user(username=tmp, password="password", is_student=True)

    def test_el_siguiente_id_no_reutiliza_el_de_un_borrado(self):
        for i in range(3):
            self.alta(f"tmp-{i}")
        self.assertEqual(self.ids(), [1, 2, 3])

        User.objects.get(username=f"{self.prefijo}2").delete()
        self.alta("tmp-4")  # con count() pedia el 3, que ya existia

        self.assertEqual(self.ids(), [1, 3, 4])

    def test_el_id_empieza_por_uno(self):
        self.alta("tmp-1")

        self.assertEqual(self.ids(), [1])
