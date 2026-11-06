from django.test.client import Client
from django.test.runner import DiscoverRunner


class ProjectTestRunner(DiscoverRunner):
    """Marks test logins as location-verified, so staff tests reach the page
    they are testing instead of /panel/location-required/. Only tests are
    affected; test_staff_panel_requires_location removes the mark to cover
    the real check."""

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._client_login = original = Client._login

        def login(client, user, backend=None):
            original(client, user, backend)
            session = client.session
            session['staff_location_verified'] = True
            session.save()

        Client._login = login

    def teardown_test_environment(self, **kwargs):
        Client._login = self._client_login
        super().teardown_test_environment(**kwargs)
