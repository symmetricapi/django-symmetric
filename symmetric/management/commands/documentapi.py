import re
from importlib import import_module
from optparse import make_option

from django.conf import settings
from django.core.management.base import BaseCommand

import api.management.overrides
from api.filters import combine_filters
from api.functions import _ApiModel, get_object_data
from api.management.functions import get_doc_str, get_resource_type, format_regex_stack, is_anonymous, is_auto_now
from api.views import api_view, api_related_view, api_filter_contacts_view
from api.views import api_login_view, api_logout_view, api_create_user_view, api_set_password_view, api_reset_password_view
from api.views import ApiAction, ApiRequirement, BasicApiView

class Command(BaseCommand):
	help = 'Generate documentation for API endpoints.'
	option_list = BaseCommand.option_list + (
			make_option('--compact', '-c',
				action='store_true',
				dest='compact',
				default=False,
				help='Output only callback information info with the url endpoints.'),
			make_option('--urls', '-u',
				action='store_true',
				dest='urls',
				default=False,
				help='Output only the url endpoints.'),
			make_option('--anonymous', '-a',
				action='store_true',
				dest='anonymous',
				default=False,
				help='Output only the endpoints that may be used anonymously without a login session.'),
			make_option('--raml', '-r',
				action='store_true',
				dest='raml',
				default=False,
				help=''),
			make_option('--raml-mixin', '-m',
				type='string',
				dest='raml-mixin',
				help='Mixin/overwrite the raml with following raml file.')
		)
	API_AUTH_VIEWS = (api_login_view, api_logout_view, api_create_user_view, api_set_password_view, api_reset_password_view)

	def format_actions(self, view, resource_type):
		# Mask the actual allowed actions based on the resource type
		masks = {'Single Object': ApiAction.READ | ApiAction.UPDATE, 'Collection': ApiAction.READ | ApiAction.CREATE, 'Object': ApiAction.READ | ApiAction.UPDATE | ApiAction.DELETE}
		actions = view.actions & masks[resource_type]

		actions_str = []
		if actions & ApiAction.READ:
			actions_str.append('READ')
		if actions & ApiAction.UPDATE:
			actions_str.append('UPDATE')
		if actions & ApiAction.CREATE:
			actions_str.append('CREATE')
		if actions & ApiAction.DELETE:
			actions_str.append('DELETE')
		return ', '.join(actions_str)

	def format_requirements(self, view):
		requirements = []
		if view.requirements & ApiRequirement.LOGIN:
			requirements.append('User must be logged in.')
		if view.requirements & ApiRequirement.STAFF:
			requirements.append('User must be staff.')
		if view.requirements & ApiRequirement.SUPERUSER:
			requirements.append('User must be superuser.')
		if view.requirements & ApiRequirement.JSONP:
			requirements.append('JSONP requests allowed.')
		if view.requirements & ApiRequirement.HMAC:
			requirements.append('CREATE and UPDATE requests must include an HMAC.')
		if view.requirements & ApiRequirement.ANONYMOUS_READ:
			requirements.append('READ requests may be anonymous.')
		if view.requirements & ApiRequirement.HTTPS:
			requirements.append('Request must be done over HTTPS.')
		return ' '.join(requirements)

	def help_text(self, field_name, view):
		for field in view.model._meta.fields:
			if field.name == field_name:
				if hasattr(field, 'help_text'):
					return field.help_text.encode('utf-8')
		return ''

	def build_raml(self, view):
		# TODO: support BasicApiView
		if isinstance(view, BasicApiView):
			return
		resource = None
		path = ['/' + c.replace('<','{').replace('>','}') for c in format_regex_stack(self.regex_stack).split('/') if c]
		for component in path[1:]:
			if resource is None:
				resource = self.raml_data
			if not resource.has_key(component):
				resource[component] = {}
			resource = resource[component]
		resource['displayName'] = view.model.__name__
		if view.actions & ApiAction.READ:
			resource['get'] = {'responses': {200: {'body': {'*/*':{}}}}}

	def format_model(self, view):
		if hasattr(view, 'parent_model') and view.parent_model:
			# api_related_view and BasicApiView
			print 'Parent Model: %s' % view.parent_model.__name__
		print 'Model: %s' % view.model.__name__
		if view.model.__dict__.has_key('clean'):
				print 'Clean: %s' % get_doc_str(view.model.clean)
		if view.model.__dict__.has_key('save'):
			print 'Save: %s' % get_doc_str(view.model.save)
		if self.compact:
			return
		model = _ApiModel(view.model)
		print 'Fields: '
		print '%s%s%s%s' % ('name'.center(25), 'list'.center(10), 'readonly'.center(15), 'sub-object'.center(10))
		for name, encoded_name, encode, decode in model.fields:
			list_str = ''
			for name_list, encoded_name_list, encode_list, decode_list in model.list_fields:
				if name == name_list:
					list_str = '*'
					break
			sub_object_str = '*' if encode is get_object_data else ''
			if not model.encoded_fields.has_key(encoded_name):
				if is_auto_now(name, view):
					readonly_str = 'auto'
				else:
					readonly_str = '*'
			else:
				# Find out if it is automatically set from request_user_field or request_ip_field or is a related_field
				if hasattr(view.model, 'API') and hasattr(view.model.API, 'request_user_field') and view.model.API.request_user_field == name:
					readonly_str = 'auto'
				elif hasattr(view.model, 'API') and hasattr(view.model.API, 'request_ip_field') and view.model.API.request_ip_field == name:
					readonly_str = 'auto'
				elif isinstance(view, api_related_view) and view.related_field == name[:-3]:
					readonly_str = 'auto'
				else:
					readonly_str = ''
			help = self.help_text(name, view)
			print '%s%s%s%s   %s' % (encoded_name.ljust(25), list_str.center(10), readonly_str.center(15), sub_object_str.center(10), help)

	def format_view(self, view, resource_type):
		path = format_regex_stack(self.regex_stack)
		if self.docfilter and path.lower().find(self.docfilter) == -1 and (not view.model or view.model.__name__.lower() != self.docfilter):
			return
		if self.urls:
			print path
			return
		print 'Path: %s' % path
		if isinstance(view, BasicApiView) and view.__call__.__doc__:
			print view.__call__.__doc__
		print 'Allowed Actions: [%s]' % self.format_actions(view, resource_type)
		print 'Resource Type: ' + resource_type
		if view.requirements:
			print 'Requirements: %s' % self.format_requirements(view)
		if hasattr(view, 'filter') and view.filter:
			if isinstance(view.filter, combine_filters):
				print 'Filters:'
				print str(view.filter)
			else:
				print 'Filter: %s' % get_doc_str(view.filter)
		if hasattr(view, 'authorization') and view.authorization:
			print 'Authorization: %s' % get_doc_str(view.authorization)
		if hasattr(view, 'verification') and view.verification:
			print 'Verification: %s' % get_doc_str(view.verification)
		if view.model:
			self.format_model(view)
		print '-----------------------------------------------------------------------'

	def format_auth_view(self, view):
		path = format_regex_stack(self.regex_stack)
		if self.docfilter:
			return
		if self.urls:
			print path
			return
		print 'Path: %s' % path
		print get_doc_str(view)
		if hasattr(view, 'requirements') and view.requirements:
			print 'Requirements: %s' % self.format_requirements(view)
		if hasattr(view, 'fields') and view.fields:
			print 'Filter Fields: %s' % ','.join(view.fields)
		if hasattr(view, 'model') and view.model:
			self.format_model(view)
		print '-----------------------------------------------------------------------'

	def enum_patterns(self, patterns):
		for pattern in patterns:
			if pattern.callback:
				if self.anonymous and not is_anonymous(pattern.callback):
					continue
				if isinstance(pattern.callback, (api_view, BasicApiView)):
					self.regex_stack.append(pattern._regex)
					if self.raml:
						self.build_raml(pattern.callback)
					else:
						self.format_view(pattern.callback, get_resource_type(self.regex_stack, pattern))
					self.regex_stack.pop()
				elif pattern.callback in Command.API_AUTH_VIEWS or isinstance(pattern.callback, api_filter_contacts_view):
					self.regex_stack.append(pattern._regex)
					self.format_auth_view(pattern.callback)
					self.regex_stack.pop()
			else:
				self.regex_stack.append(pattern._regex)
				self.enum_patterns(pattern.url_patterns)
		if self.regex_stack:
			self.regex_stack.pop()

	def handle(self, *args, **options):
		if args:
			self.docfilter = args[0].lower()
		else:
			self.docfilter = None
		self.urls = options['urls']
		self.compact = options['compact']
		self.anonymous = options['anonymous']
		self.raml = options['raml']
		self.regex_stack = []
		self.raml_data = {}
		module = import_module(settings.ROOT_URLCONF)
		self.enum_patterns(module.urlpatterns)
		if self.raml:
			try:
				import yaml
				self.raml_data.update({'title': 'API', 'version': 'v1', 'baseUri':'/api/{version}'})
				if options['raml-mixin']:
					with open(options['raml-mixin']) as f:
						self.raml_data.update(yaml.load(f))
				print '#%RAML 0.8'
				print yaml.dump(self.raml_data, default_flow_style=False, allow_unicode=True, encoding=None)
			except ImportError as e:
				print "Please install pyyaml first."
