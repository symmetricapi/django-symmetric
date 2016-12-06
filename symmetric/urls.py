from importlib import import_module

from django.core.urlresolvers import reverse
from django.conf.urls import include, url

def api_include(urlconf_module, namespace=None, app_name=None):
	"""Include api patterns from a module.

	Similar to include() but extracts a variable called apipatterns from urlconf_module and passes that to include().
	The first argument must be a module name that has apipatterns.
	If apipatterns isn't defined, the module itself will be passed to include().
	"""
	if isinstance(urlconf_module, (str, unicode)):
		urlconf_module = import_module(urlconf_module)
	return include(getattr(urlconf_module, 'apipatterns', urlconf_module), namespace, app_name)

def api_patterns(*args):
	"""Create and add api patterns to urlpatterns.

	Args are a module string or a tuple e.g.
	urlpatterns += api_patterns('game.urls', 'cart.urls')
	or api_patterns('game.urls', ('cart', 'cart.urls'), ('versioned', 'versioned.urls', 3))
	or api_patterns(('versioned', 'versioned.urls', 3))
	The latter examples will create the following versioned urls: /api/versioned/, /api/1/versioned/, ..2, and ..3
	"""
	apipatterns = []
	for pattern in args:
		latest_version = 0
		if isinstance(pattern, (str, unicode)):
			api_path = ''
			url_module = pattern
		elif isinstance(pattern, tuple):
			api_path = pattern[0]
			if api_path:
				api_path += '/'
			url_module = pattern[1]
			if len(pattern) >= 3:
				latest_version = pattern[2]
		else:
			continue
		included = api_include(url_module)
		apipatterns.append(url('^api/' + api_path, included))
		if latest_version:
			for i in range(1, latest_version + 1):
				apipatterns.append(url('^api/%d/%s' % (i, api_path), included))
	return apipatterns

def __api_reverse_suffix(path):
	"""Return the normalized suffix of a url without any api information so that the correct version can be added."""
	if path.startswith('/api/'):
		components = path.split('/', 3)
		if len(components) >= 4 and components[2].isdigit():
			return '/' + components[3]
		else:
			return path[4:]
	else:
		return path

def api_reverse(viewname, version=0, urlconf=None, args=None, kwargs=None, prefix=None, current_app=None):
	path = reverse(viewname, args=args, kwargs=kwargs)
	path = __api_reverse_suffix(path)
	if version > 0:
		return ('/api/%d' % version) + path
	else:
		return '/api' + path
