from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Student
from course.models import Course, Program
from result.models import TakenCourse


class CourseDropTests(TestCase):
    """Desapuntar es un POST: antes un GET devolvia None y Django petaba."""

    def setUp(self):
        self.program = Program.objects.create(title="Programa de prueba")
        self.course = Course.objects.create(
            title="Curso de prueba",
            code="TEST-1",
            program=self.program,
            level="Bachelor",
            year=1,
            semester="First",
        )
        self.user = get_user_model().objects.create_user(
            username="alumno", email="alumno@example.com", password="password"
        )
        self.user.is_student = True
        self.user.save()
        self.student = Student.objects.create(
            student=self.user, level="Bachelor", program=self.program
        )
        self.enrollment = TakenCourse.objects.create(
            student=self.student, course=self.course
        )
        self.url = reverse("course_drop")

    def test_get_is_rejected(self):
        self.client.login(username="alumno", password="password")

        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_post_drops_the_enrollment(self):
        self.client.login(username="alumno", password="password")

        response = self.client.post(self.url, {"course_ids": [self.course.pk]})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            TakenCourse.objects.filter(
                student=self.student, course=self.course
            ).exists()
        )
