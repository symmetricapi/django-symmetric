import json

from django.conf import settings
from django.http import HttpRequest, QueryDict
from django.utils.datastructures import MultiValueDict

from .response import render_error
from .views import ApiAction

class ApiMiddleware(object):
	"""
	Api middleware. If this is enabled, each request object will
	get the added attributes:
	api (True/False) - depending on the url request if it starts with /api
	api_action (int) - is api is True, ApiAction determined from the HTTP method
	api_json (True/False/String) - depending on the ?json part of the url request
	api_callback (String) - sets request.api_json = callback and request.api_callback = True and is meant render json wrapped in a callback
	api_version (int) - if api is True, 1 by default, > 1 if /api/#/ is given
	NOTE: request.api_callback is only/always set if request.api_json = True and request.api_json is only/always set if request.api = True
	If requested with AJAX or Accept header wants json, then json is always used.
	"""

	_METHOD_ACTION_DICT = {
		'GET': ApiAction.READ,
		'HEAD': ApiAction.READ,
		'POST': ApiAction.CREATE,
		'PUT': ApiAction.UPDATE,
		'PATCH': ApiAction.UPDATE,
		'DELETE': ApiAction.DELETE
	}
	_API_JSONP = getattr(settings, 'API_JSONP', False)
	_API_CSRF = getattr(settings, 'API_CSRF', True)
	_ERROR_JSONP = 'JSONP requests are not allowed'

	def process_request(self, request):
		if request.path.startswith('/api/'):
			request.api = True
			request.api_version = 1
			request.api_action = ApiMiddleware._METHOD_ACTION_DICT.get(request.method, ApiAction._UNKNOWN)
			if request.is_ajax() or request.META.get('HTTP_ACCEPT', '').startswith('application/json'):
				request.api_json = True
			else:
				callback = request.GET.get('callback', None)
				if callback:
					request.api_callback = True
					request.api_json = callback
				else:
					request_json = request.GET.get('json', None)
					if request_json:
						request.api_callback = False
						if request_json.lower() == 'true':
							request.api_json = True
						else:
							request.api_json = request_json
					else:
						request.api_json = False

			# Check for a restricted JSONP request
			if type(request.api_json) is not bool and not ApiMiddleware._API_JSONP:
				return render_error(request, ApiMiddleware._ERROR_JSONP, 403)

			# Detect the requested API version
			components = request.path.split('/', 3)
			if len(components) >= 3 and components[2].isdigit():
				request.api_version = int(components[2])

			# Process JSON data and PUT requests
			if request.META.get('CONTENT_TYPE', '').startswith('application/json'):
				# Should set either request.POST or request.PUT
				query_dict = QueryDict('', mutable=True)
				query_dict.update(json.loads(request.body))
				setattr(request, request.method, query_dict)
				if request.method == 'PATCH':
					request.PUT = request.PATCH
				request._files = MultiValueDict()
			elif request.method == 'PUT':
				# Process PUT requests
				if hasattr(request, '_post'):
					del request._post
					del request._files
				request.method = 'POST'
				request._load_post_and_files()
				request.method = 'PUT'
				request.PUT = request.POST

			# Skip the csrf check (see Django's CsrfViewMiddleware)
			if not ApiMiddleware._API_CSRF and (request.is_ajax() or request.META.has_key('HTTP_X_NATIVE_APP')):
				request.csrf_processing_done = True
		else:
			request.api = False
