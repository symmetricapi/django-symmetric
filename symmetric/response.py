import json

from django.db.models.query import QuerySet
from django.http import HttpResponse, Http404
from django.utils.html import escape

from functions import get_object_data, get_object_list_data
from symmetric import xml

__NO_CACHE = 'max-age=0, no-cache, no-store, must-revalidate'


def __default_dumps(obj):
	if isinstance(obj, QuerySet):
		# Dumping a QuerySet with this function shouldn't happen, but just in case
		return tuple(obj)
	else:
		data = get_object_data(obj)
		if data:
			return data
		else:
			raise TypeError(repr(obj) + " is not serializable")


def __default_list_dumps(obj):
	if isinstance(obj, QuerySet):
		return tuple(obj)
	else:
		data = get_object_list_data(obj)
		if data:
			return data
		else:
			raise TypeError(repr(obj) + " is not serializable")


def set_response_headers(request, **kwargs):
	if not hasattr(request, 'api_response_headers'):
		request.api_response_headers = kwargs.copy()
	else:
		request.api_response_headers.update(kwargs)


def apply_response_headers(request, response):
	if hasattr(request, 'api_response_headers'):
		for header, value in request.api_response_headers.iteritems():
			response[header] = value
	# Django never automatically adds Content-Length to a response unless ConditionalGetMiddleware is used, so do it
	# here in case the middleware isn't being used
	response['Content-Length'] = str(len(response.content))
	response['Cache-Control'] = __NO_CACHE


def render_data(request, data, status=200):
	"""Render data as xml or json based on the request."""
	if request.api:
		default = __default_list_dumps if isinstance(data, (tuple, list, set, QuerySet)) else __default_dumps
		if not request.api_json:
			response = HttpResponse(content_type='application/xml', status=status)
			xml.dumps(data, response, default=default)
		elif request.api_json is not True:
			response = HttpResponse(content_type='text/javascript', status=status)
			if request.api_callback:
				response.write(request.api_json + '(')
				response.write(json.dumps(data, default=default))
				response.write(');')
			else:
				response.write(request.api_json + ' = ')
				response.write(json.dumps(data, default=default))
				response.write(';')
		else:
			response = HttpResponse(json.dumps(data, default=default), content_type='application/json', status=status)
		apply_response_headers(request, response)
		return response
	else:
		raise Http404


def render_error(request, message, status, code=None):
	"""Render and error message and code."""
	if code is None:
		code = status
	if request.api:
		if not request.api_json:
			response = HttpResponse(
				'<?xml version="1.0" encoding="UTF-8" ?><error><code>%d</code><message>%s</message></error>' % (code, escape(message)),
				status=status,
				content_type='application/xml'
			)
		elif request.api_json is not True:
			if request.api_callback:
				response = HttpResponse(
					'%s({"code":%d,"message":%s});' % (request.api_json, code, json.dumps(message)),
					status=200,
					content_type='text/javascript'
				)
			else:
				response = HttpResponse(
					'%s={"code":%d,"message":%s};' % (request.api_json, code, json.dumps(message)),
					status=200,
					content_type='text/javascript'
				)
		else:
			response = HttpResponse(
				'{"code":%d,"message":%s}' % (code, json.dumps(message)),
				status=status,
				content_type='application/json'
			)
		apply_response_headers(request, response)
		return response
	else:
		if code == 404:
			raise Http404
		else:
			return HttpResponse(
				'<html><head><title>Error %d</title></head><body><b>Error %d</b> - %s</body></html>' % (status, code, message),
				status=status,
				content_type='text/html'
			)


def render_empty(request):
	"""Render an appropriate empty response."""
	# jQuery will report an error if the empty response isn't given as {} or null
	# see dataType "json" here https://api.jquery.com/jQuery.ajax/
	# 204 No Content requires that nothing be in the body, so cannot be used for a json response,
	# see https://tools.ietf.org/html/rfc2616#section-10.2.5
	if request.api_json:
		response = HttpResponse('null', content_type='application/json')
	else:
		response = HttpResponse(status=204)
	apply_response_headers(request, response)
	return response
