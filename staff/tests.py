from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import StaffProfile, Task


class StaffPanelTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.manager_user = User.objects.create_user('manager', password='test-pass-123')
        self.employee_user = User.objects.create_user('employee', password='test-pass-123')
        self.manager = StaffProfile.objects.create(user=self.manager_user, role=StaffProfile.Role.COORDINATOR,
                                                   is_approved=True)
        self.employee = StaffProfile.objects.create(user=self.employee_user, role=StaffProfile.Role.EMPLOYEE,
                                                    manager=self.manager, is_approved=True)

    def test_staff_dashboard_requires_login(self):
        response = self.client.get(reverse('staff:dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_employee_sees_own_task(self):
        Task.objects.create(title='Test vazifa', description='Tavsif', assignee=self.employee,
                            created_by=self.manager, due_at=timezone.now() + timedelta(days=1))
        self.client.force_login(self.employee_user)
        response = self.client.get(reverse('staff:task_list'))
        self.assertContains(response, 'Test vazifa')

    def test_employee_cannot_create_task(self):
        self.client.force_login(self.employee_user)
        response = self.client.get(reverse('staff:task_create'))
        self.assertEqual(response.status_code, 403)
