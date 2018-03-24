from importlib import import_module

from django.conf import settings
from django.conf.urls import url
from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.test import TestCase
from django.test.client import Client

from symmetric.urls import api_reverse

def api_test(request):
    if hasattr(request, 'api') and request.api:
        return HttpResponse()
    else:
        return HttpResponse(status=400)

def api_json_test(request):
    if hasattr(request, 'api_json') and request.api_json:
        return HttpResponse()
    else:
        return HttpResponse(status=400)

def api_version_test(request):
    version = int(request.GET.get('version', '1'))
    if hasattr(request, 'api_version') and request.api_version == version:
        return HttpResponse()
    else:
        return HttpResponse(status=400)

class ApiTest(TestCase):

    def setUp(self):
        module = import_module(settings.ROOT_URLCONF)
        module.urlpatterns += [
            url(r'^api/test/$', api_test),
            url(r'^api/jsontest/$', api_json_test),
            url(r'^api/versiontest/$', api_version_test),
            url(r'^api/1/versiontest/$', api_version_test),
            url(r'^api/2/versiontest/$', api_version_test)
        ]

    def test_middleware(self):
        """Tests the middleware request manipulation."""
        c = Client()
        response = c.get(api_reverse(api_test))
        self.assertEqual(response.status_code, 200)

        # Test json
        response = c.get(api_reverse(api_json_test) + '?json=true')
        self.assertEqual(response.status_code, 200)

        # Test versioning
        response = c.get(api_reverse(api_version_test) + '?version=1')
        self.assertEqual(response.status_code, 200)

        response = c.get(api_reverse(api_version_test, 1) + '?version=1')
        self.assertEqual(response.status_code, 200)

        response = c.get(api_reverse(api_version_test, 2) + '?version=2')
        self.assertEqual(response.status_code, 200)

        response = c.get(api_reverse(api_version_test, 1) + '?version=2')
        self.assertNotEqual(response.status_code, 200)
