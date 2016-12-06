import os
import re
from importlib import import_module
from optparse import make_option

from django.conf import settings
from django.core.management.base import CommandError
from django.template import Template, Context

import api.management.overrides
from api.functions import _ApiModel
from api.management.functions import format_regex_stack, get_app_url_prefix, is_sublist, get_subclass_filter, get_model_name
from api.views import ApiAction, ApiRequirement, BasicApiView, api_view

"""
	Connection actions are mapped in the following way:
	api_view or ApiView
		with missing URL params - READ_LIST, CREATE
			for a BasicApiView single_object = True or an api_view with default_args for id or slug - READ_OBJECT, UPDATE
		with <object_id> - READ_OBJECT, UPDATE, DELETE
		with <slug> - READ_OBJECT, no update or delete because the object needs to be passed to the method and only the id is used
	api_related_view or ApiRelatedView
		regardless missing or provided URL params if single_object = True for a BasicApiView - READ_RELATED_OBJECT, UPDATE_RELATED
		with missing URL params - not possible for api_related_view
		with <object_id> or <slug> - READ_RELATED_LIST, CREATE_RELATED
	BasicApiViews, including subclasses ApiCurrentUserView, ApiCurrentUserRelatedView
		treated as api_view when parent_model is None
		treated as api_related_view when parent_model is not None

	Current user and collections:
	userinfo - /me - ApiCurrentUserView (BasicApiView single_object=True)
	collection - /me/posts - ApiCurrentUserRelatedView (BasicApiView single_object=False)
	Related single objects can only be done with a BasicApiView e.g.:
	object - /me/currentpost - needs to be implemented by the user as a BasicApiView and parent_model set to user, model set to post and .single_object True

	NOTE: api auth views are not supported

	Generated method signatures should be similar to the following
	READ_OBJECT - readObject
	READ_LIST - readObjects
	CREATE - createObject(object)
	UPDATE - updateObject(object)
	DELETE - deleteObject(object)
	READ_RELATED_LIST - readChildrenForParent
	CREATE_RELATED - createChildForParent(childObject)
	READ_RELATED_OBJECT - readObjectForParent
	UPDATE_RELATED - updateObjectForParent(childObject)

	The ACTIONS needing param info:
	object id/slug: READ_OBJECT, UPDATE
	parent id/slug: READ_RELATED_LIST, CREATE_RELATED, READ_RELATED_OBJECT, UPDATE_RELATED:
		{ param: '' or 'id' or 'slug'}
	UPDATE only needs param info for deciding how to create it's URL, the method signature doesn't change, it always takes an object (not id or slug)
	when param is set add withSlug or withId to the method signatures above and additional id or slug argument
"""

class GenerateConnectionsCommand(object):
	option_list = (
			make_option('--dest',
				type='string',
				dest='dest',
				help='Output all connections for the detected apps with api endpoints and render them into this destination directory.'),
		)
	ALL_ACTIONS = ('READ_OBJECT', 'READ_LIST', 'CREATE', 'UPDATE', 'DELETE', 'READ_RELATED_OBJECT', 'UPDATE_RELATED', 'READ_RELATED_LIST', 'CREATE_RELATED')

	def post_render(self, output):
		return output

	def perform_mapping(self, mapping, format_context):
		if callable(mapping):
			# callable method
			return mapping(format_context)
		elif isinstance(mapping, Template):
			# django template
			return mapping.render(Context(format_context, autoescape=False))
		else:
			# normal python string formatting
			return mapping.format(**format_context)

	def get_view_actions(self, url, view):
		actions = []
		single_object = False
		if hasattr(view, 'parent_model') and view.parent_model:
			# For api_related_view, ApiRelatedView, or BasicApiView
			if isinstance(view, BasicApiView) and view.single_object:
				if view.actions & ApiAction.READ:
					actions.append('READ_RELATED_OBJECT')
				if view.actions & ApiAction.UPDATE:
					actions.append('UPDATE_RELATED')
			else:
				if view.actions & ApiAction.READ:
					actions.append('READ_RELATED_LIST')
				if view.actions & ApiAction.CREATE:
					actions.append('CREATE_RELATED')
		else:
			# For api_view, ApiView, or BasicApiView (without a parent_model)
			if (url.find('<object_id>') == -1 and url.find('<slug>') == -1):
				if (isinstance(view, BasicApiView) and view.single_object) or (url in self.single_object_urls):
					if view.actions & ApiAction.READ:
						actions.append('READ_OBJECT')
					if view.actions & ApiAction.UPDATE:
						actions.append('UPDATE')
				else:
					if view.actions & ApiAction.READ:
						actions.append('READ_LIST')
					if view.actions & ApiAction.CREATE:
						actions.append('CREATE')
			elif url.find('<object_id>') != -1:
				if view.actions & ApiAction.READ:
					actions.append('READ_OBJECT')
				if view.actions & ApiAction.UPDATE:
					actions.append('UPDATE')
				if view.actions & ApiAction.DELETE:
					actions.append('DELETE')
			elif url.find('<slug>') != -1:
				if view.actions & ApiAction.READ:
					actions.append('READ_OBJECT')
		return actions

	def get_param_context(self, url, action):
		context = {'param': '', 'param_lower': '', 'param_type': ''}
		if action in ('READ_OBJECT', 'UPDATE', 'READ_RELATED_OBJECT', 'UPDATE_RELATED', 'READ_RELATED_LIST', 'CREATE_RELATED'):
			if url.find('<object_id>') != -1:
				context['param'] = 'Id'
				context['param_lower'] = 'id'
				context['param_type'] = self.object_id_type
			if url.find('<slug>') != -1:
				context['param'] = 'Slug'
				context['param_lower'] = 'slug'
				context['param_type'] = self.slug_type
		return context

	def get_context(self, app_label):
		context = {'name': app_label, 'name_lower': app_label[0].lower() + app_label[1:] }
		if hasattr(self, 'extra_context'):
			context.update(self.extra_context())

		# Loop over the view mappings
		for mapping_name in self.mappings:
			mapping = self.mappings[mapping_name]
			lines = []
			for url_format, view in self.views.iteritems():
				for action in self.get_view_actions(self.urls[url_format], view):
					line = None
					if mapping.has_key(action):
						format_context = {
							'url': self.urls[url_format],
							'url_format': url_format,
							'view': view,
							'app_name': app_label,
							'app_name_lower': app_label[0].lower() + app_label[1:],
							'model_name': view.model.__name__,
							'name': view.model.__name__,
							'name_lower': view.model.__name__[0].lower() + view.model.__name__[1:],
							'name_plural': view.model._meta.verbose_name_plural.title().replace(' ', ''),
							'name_plural_lower': view.model._meta.verbose_name_plural[0].lower() + view.model._meta.verbose_name_plural.title().replace(' ', '')[1:],
							'login': ((view.requirements & ApiRequirement.LOGIN) and not (action.startswith('READ') and (view.requirements & ApiRequirement.ANONYMOUS_READ))),
							'https': (view.requirements & ApiRequirement.HTTPS),
							'hmac': (view.requirements & ApiRequirement.HMAC)
						}
						subclass_filter = get_subclass_filter(view)
						if subclass_filter:
							format_context['subclasses'] = [(_ApiModel(model).id_field[1], get_model_name(model)) for model in subclass_filter.subclasses]
						format_context.update(self.get_param_context(self.urls[url_format], action))
						if hasattr(view, 'parent_model') and view.parent_model:
							# Related and basic api views
							format_context['parent_name'] = view.parent_model.__name__
							format_context['parent_name_lower'] = view.parent_model.__name__[0].lower() + view.parent_model.__name__[1:]
							format_context['parent_name_plural'] = view.parent_model._meta.verbose_name_plural.title().replace(' ', '')
							format_context['parent_name_plural_lower'] = view.parent_model._meta.verbose_name_plural[0].lower() + view.parent_model._meta.verbose_name_plural.title().replace(' ', '')[1:]
						line = self.perform_mapping(mapping[action], format_context)
					if line is None:
						raise CommandError("No such mapping for %s in %s." % (action, mapping_name))
					elif line:
						line = line.split('\n')
						if not mapping.get('RemoveDuplicates', False) or not is_sublist(lines, line):
							lines.extend(line)
			context[mapping_name] = lines
			if mapping.get('Sort', False):
				context[mapping_name].sort()

		return context

	def make_url_format(self, url_pattern):
		url_pattern = url_pattern.replace('<object_id>', self.object_id_format)
		url_pattern = url_pattern.replace('<slug>', self.slug_format)
		return url_pattern

	def enum_patterns(self, patterns):
		for pattern in patterns:
			if pattern.callback:
				self.regex_stack.append(pattern._regex)
				if isinstance(pattern.callback, (api_view, BasicApiView)):
					url = format_regex_stack(self.regex_stack)
					url_format = self.make_url_format(url)
					self.urls[url_format] = url
					if hasattr(pattern, 'default_args') and (pattern.default_args.has_key('object_id') or pattern.default_args.has_key('slug')):
						self.single_object_urls.add(url)
					self.views[url_format] = pattern.callback
				self.regex_stack.pop()
			else:
				self.regex_stack.append(pattern._regex)
				self.enum_patterns(pattern.url_patterns)
		if self.regex_stack:
			self.regex_stack.pop()

	def render(self, *args, **options):
		if not hasattr(self, 'templates'):
			raise CommandError('No templates set!')
		app_renames = {arg.split('=')[0]:arg.split('=')[1] for arg in args if arg.find('=') != -1}
		if options and options['dest']:
			try:
				os.makedirs(options['dest'])
			except:
				print 'Warning: Overwriting any contents in %s' % options['dest']
			for app_name in settings.INSTALLED_APPS:
				try:
					module = import_module(app_name + '.urls')
					patterns = getattr(module, 'apipatterns', getattr(module, 'urlpatterns', []))
				except:
					continue
				app_label = app_name.split('.')[-1]
				app_rename = app_renames.get(app_label, app_label)
				app_rename = app_rename[0].upper() + app_rename[1:]
				self.views = {}
				self.urls = {}
				self.single_object_urls = set()
				self.regex_stack = [get_app_url_prefix(app_name, patterns)]
				self.enum_patterns(patterns)
				if self.views:
					context = self.get_context(app_rename)
					for i in range(len(self.templates)):
						template = self.templates[i]
						template_extension = self.template_extensions[i]
						path = os.path.join(options['dest'], '%sConnection.%s' % (app_rename, template_extension))
						print 'Rendering %s' % path
						with open(path, 'w') as f:
							f.write(self.post_render(template.render(Context(context, autoescape=False))))
		elif args:
			for app_name in args:
				try:
					module = import_module(app_name + '.urls')
					patterns = getattr(module, 'apipatterns', getattr(module, 'urlpatterns', []))
				except:
					continue
				app_label = app_name.split('.')[-1]
				app_rename = app_renames.get(app_label, app_label)
				app_rename = app_rename[0].upper() + app_rename[1:]
				self.views = {}
				self.urls = {}
				self.single_object_urls = set()
				self.regex_stack = [get_app_url_prefix(app_name, patterns)]
				self.enum_patterns(patterns)
				context = self.get_context(app_rename)
				for template in self.templates:
					print self.post_render(template.render(Context(context, autoescape=False)))
		else:
			raise CommandError("No app or destination directory specified.")
