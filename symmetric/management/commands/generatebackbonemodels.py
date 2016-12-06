import ast
import json
import re
import sys
from functools import partial
from importlib import import_module
from optparse import make_option

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models.fields import NOT_PROVIDED, DateField

import api.management.overrides
from api.functions import camel_case_to_underscore, underscore_to_camel_case
from api.management.functions import get_base_classes, get_resource_type, get_subclass_filter, format_regex_stack
from api.management.functions import get_model_name, get_model_name_plural, get_collection_name, get_collection_name_plural
from api.management.translate import translate_code
from api.models import get_related_model
from api.views import ApiAction, ApiRequirement, BasicApiView, api_view

class BackboneAttributeTransformer(ast.NodeTransformer):
	"""Any access to self.property_name should be converted to self.attributes.property_name if it is a field."""
	def __init__(self, model):
		self.model = model

	def visit_Attribute(self, node):
		if type(node.value) is ast.Name and node.value.id == 'self':
			if type(node.attr) is str and node.attr != 'id':
				try:
					self.model._meta.get_field(node.attr)
					node.attr = 'get("%s")' % node.attr
				except:
					pass
		else:
			self.visit(node.value)
		return node

class Command(BaseCommand):
	help = 'Generate backbone models for API endpoints.'
	option_list = BaseCommand.option_list + (
			make_option('--module-type',
				dest='module_type',
				type='string',
				default='global',
				help='Output the models inside the specified module type. Options are: global, amd, cjs, esm.'),
			make_option('--defaults',
				action='store_true',
				dest='defaults',
				default=False,
				help='Add in available default values into the models.'),
			make_option('--cord',
				action='store_true',
				dest='cord',
				default=False,
				help='Use cord functionality for defining properties and submobels.'),
			make_option('--schema',
				action='store_true',
				dest='schema',
				default=False,
				help='Add JSON Schema to each model under a variable schema.'),
			make_option('--models-code',
				dest='models-code',
				type='string',
				help='Raw code to mixin with the models code.'),
			make_option('--collections-code',
				dest='collections-code',
				type='string',
				help='Raw code to mixin with the collections code.')
		)

	def add_choices(self, model):
		for field in model._meta.fields:
			if hasattr(field, 'choices') and field.choices:
				choices = {}
				for choice in field.choices:
					choices[choice[0]] = choice[1]
				key = '%s_choices' % field.name
				if self.camelcase:
					key = underscore_to_camel_case(key)
				self.models[get_model_name(model)][key] = choices

	def add_parse(self, model):
		fields = []
		for field in model._meta.fields:
			# Parse DateField and DateTimeFields, but not TimeFields
			if isinstance(field, DateField):
				if self.camelcase:
					fields.append("'%s'" % underscore_to_camel_case(field.name))
				else:
					fields.append("'%s'" % field.name)
		if field:
			self.models[get_model_name(model)]['parse'] = ','.join(fields)

	def add_defaults(self, model):
		name = get_model_name(model)
		for field in model._meta.fields:
			if field.default is not NOT_PROVIDED:
				if not self.models[name].has_key('defaults'):
					self.models[name]['defaults'] = {}
				key = field.name
				if self.camelcase:
					key = underscore_to_camel_case(key)
				self.models[name]['defaults'][key] = field.default

	def translate_properties(self, model):
		lang = 'js'
		model_properties = {}
		model_properties_args = {}
		for cls in [model] + get_base_classes(model):
			for name in cls.__dict__:
				attr = cls.__dict__[name]
				if type(attr) is property and attr.fget and hasattr(attr.fget, 'api_code'):
					if self.camelcase:
						name = underscore_to_camel_case(name)
					if getattr(attr.fget, 'api_translations', None) and attr.fget.api_translations.has_key(lang):
						model_properties[name] = attr.fget.api_translations[lang]
					else:
						model_properties[name] = translate_code(attr.fget.api_code, lang, BackboneAttributeTransformer(model))
		# If using Cord, then convert all references to other api properties to a get model call then to just arguments passed into the getter instead
		if self.cord:
			def replace_properties(m):
				prop = m.group(1)
				if prop in model_properties:
					return 'this.get("%s")' % prop
				return m.group(0)
			def replace_attributes(args, m):
				attr = m.group(1)
				args.add(attr)
				return attr
			for name, code in model_properties.items():
				model_properties_args[name] = set()
				code = re.sub(r'this.([0-9a-zA-Z_]*)', replace_properties, code)
				model_properties[name] = re.sub(r'this.get\("([0-9a-zA-Z_]*)"\)', partial(replace_attributes, model_properties_args[name]), code)
		if model_properties:
			self.model_properties[get_model_name(model)] = model_properties
		if model_properties_args:
			self.model_properties_args[get_model_name(model)] = model_properties_args

	def get_include_related(self, model):
		related_models = {}
		name = get_model_name(model)
		if hasattr(model, 'API') and hasattr(model.API, 'include_related'):
			include_related = model.API.include_related
			for field in model._meta.fields:
				if field.name in include_related:
					if self.camelcase:
						field_name = underscore_to_camel_case(field.name)
					else:
						field_name = field.name
					related_models[field_name] = get_model_name(get_related_model(field))
		if related_models:
			self.include_related[name] = related_models

	def add_model(self, model, extra):
		# Add the model for any resource type
		name = get_model_name(model)
		if not self.models.has_key(name):
			self.models[name] = {}
			if self.renameid:
				self.models[name]['idAttribute'] = camel_case_to_underscore(name) + '_id'
				if self.camelcase:
					self.models[name]['idAttribute'] = underscore_to_camel_case(self.models[name]['idAttribute'])
			self.add_choices(model)
			self.add_parse(model)
			if self.defaults:
				self.add_defaults(model)
			self.translate_properties(model)
			self.get_include_related(model)
		self.models[name].update(extra)

	def get_model_replacement(self, view):
		subclass_filter = get_subclass_filter(view)
		if subclass_filter:
			model_str = '|'.join([get_model_name(model) for model in subclass_filter.subclasses])
		else:
			model_str = get_model_name(view.model)
		return model_str

	def get_model_unreplacement(self, match):
		models = match if isinstance(match, (str, unicode)) else match.group(1)
		models = models.split('|')
		count = len(models)
		if count > 1:
			models = ['if(attrs.hasOwnProperty(models.{0}.prototype.idAttribute)) return new models.{0}(attrs, options);'.format(model) for model in models if self.models.has_key(model)]
			if len(models) < count:
				models.append('return new Backbone.Model(attrs, options);')
			return 'function(attrs, options) { %s }' % ' else '.join(models)
		else:
			return 'models.' + models[0]

	def enum_patterns(self, patterns):
		for pattern in patterns:
			if pattern.callback:
				if isinstance(pattern.callback, (api_view, BasicApiView)):
					self.regex_stack.append(pattern._regex)
					view = pattern.callback
					url = format_regex_stack(self.regex_stack)
					resource_type = get_resource_type(self.regex_stack, pattern)
					model_extra = {}
					if resource_type == 'Collection':
						collection_name = get_collection_name(view)
						if url.find('<object_id>') == -1 and url.find('<slug>') == -1:
							# Unrelated
							self.collections[collection_name] = {'url': url, 'model': 'model###' + self.get_model_replacement(view)}
						else:
							# Related
							parent_name = get_model_name(view.parent_model)
							if url.find('<object_id>') != -1:
								if not self.related_collections.has_key(parent_name):
									self.related_collections[parent_name] = []
								self.related_collections[parent_name].append({'collection': collection_name, 'model': self.get_model_replacement(view), 'url': url.replace('<object_id>', '" + this.id + "')})
					elif resource_type == 'Object':
						if url.find('<object_id>') != -1:
							# Remove the last piece of the url path, should be <object_id>, don't look for <slug> because the idAttribute above only allows the object id
							model_extra['urlRoot'] = '/' + '/'.join(url.strip('/').split('/')[:-1])
					elif resource_type == 'Single Object':
						self.singletons[get_model_name(view.model)] = '/' + url.strip('/')
					# Add the model for any view without a subclass filter
					if not get_subclass_filter(view):
						self.add_model(view.model, model_extra)
					self.regex_stack.pop()
			else:
				self.regex_stack.append(pattern._regex)
				self.enum_patterns(pattern.url_patterns)
		if self.regex_stack:
			self.regex_stack.pop()

	def print_module_header(self, f=sys.stdout):
		print >> f, ";/* jslint indent: false */"
		# Module definition start
		if self.module_type == 'amd':
			print >> f, "define(['backbone', 'underscore'], function(Backbone, _) {"
		else:
			print >> f, '(function() {'
		print >> f, '"use strict";'
		print >> f, ''
		print >> f, 'function parseDates(response, attributes) {\n\t_.each(attributes, function(attribute) {\n\t\tif(response[attribute])\n\t\t\tresponse[attribute] = new Date(response[attribute]);\n\t});\n}'
		print >> f, ''
		if self.module_type == 'cjs':
			print >> f, "var Backbone = require('backbone');"
			print >> f, "var Underscore = require('underscore');"
		elif self.module_type == 'ems':
			print >> f, "var Backbone = require('backbone');"
			print >> f, "var Underscore = require('underscore');"

	def print_module_footer(self, f=sys.stdout):
		# Module definition end
		if self.module_type == 'amd':
			print >> f, 'return { models: models, collections: collections, singletons: singletons}; });'
		elif self.module_type == 'cjs':
			print >> f, 'exports.models = models;'
			print >> f, 'exports.collections = collections;'
			print >> f, 'exports.singletons = singletons;'
		elif self.module_type == 'ems':
			print >> f, 'export { models, collections, singletons };'
		else:
			print >> f, 'window.models = models;'
			print >> f, 'window.collections = collections;'
			print >> f, 'window.singletons = singletons;'
		if self.module_type != 'amd':
			print >> f, '})();'

	def handle(self, *args, **options):
		self.defaults = options['defaults']
		self.cord = options['cord']
		self.module_type = options['module_type']
		self.regex_stack = []
		self.models = {}
		self.model_properties = {}
		self.model_properties_args = {}
		self.collections = {}
		self.related_collections = {}
		self.singletons = {}
		self.include_related = {}
		self.camelcase = getattr(settings, 'API_CAMELCASE', True)
		self.renameid = getattr(settings, 'API_RENAME_ID', True)
		module = import_module(settings.ROOT_URLCONF)
		self.enum_patterns(module.urlpatterns)

		def unjson(jsn):
			# Convert spaces to tabs and json keys to unquoted javascript attributes
			return re.sub(r'"([a-zA-Z][^"]*)":', r'\1:', jsn.replace('    ','\t'))

		separators = (',', ': ')

		self.print_module_header()

		# Add newUrl attributes to the models so they can be created outside of collections.
		# Matching models and collections will share the same name
		for name in self.models:
			if self.models[name].has_key('urlRoot') and self.collections.has_key(name):
				self.models[name]['newUrl'] = self.collections[name]['url']

		# Output the code
		model_js = unjson(json.dumps(self.models, separators=separators, indent=4))
		# Convert all urlRoot attributes into functions.
		# The collection's url should be overridden when the object already exists with an id (!isNew) because it may be part of a heterogeneous subclass collection or related collection that does not have an endpoint for updating the object
		# A newUrl is also defined/undefined when the model is created outside of a collection it can still use its collection's url for creating a new instance
		model_js = re.sub(r'urlRoot: "([^"]*)"', r'urlRoot: function() { if(!this.isNew()) return "\1"; else if(!this.collection) return this.newUrl; }', model_js)
		# Convert all parse attributes into a function
		model_js = re.sub(r'parse: "([^"]*)"', r'parse: function(response) { if(response) parseDates(response, [\1]); return response; }', model_js)

		print 'var models = %s;' % model_js
		print ''
		if options['models-code']:
			with open(options['models-code'], 'r') as f:
				print f.read()
		print "_.each(models, function(value, key) { models[key] = Backbone.Model.extend(value); });"
		print ''
		for name in self.related_collections:
			print 'Object.defineProperties(models.%s.prototype, {' % name
			for i, related in enumerate(self.related_collections[name]):
				comma = ',' if i < (len(self.related_collections[name]) - 1) else ''
				print '\t%sCollection: { get: function() { return Backbone.Collection.extend({ model: %s, url: "%s" }); } }%s' % (related['collection'], self.get_model_unreplacement(related['model']), related['url'], comma)
			print '});\n'
		collections_js = unjson(json.dumps(self.collections, separators=separators, indent=4))
		# Convert the special model###modelName code into a models.Class or a function for a heterogeneous collection
		collections_js = re.sub(r'"model###(.*)"', self.get_model_unreplacement, collections_js)
		print 'var collections = %s;' % collections_js
		print ''
		if options['collections-code']:
			with open(options['collections-code'], 'r') as f:
				print f.read()
		print "_.each(collections, function(value, key) { collections[key] = Backbone.Collection.extend(value); });"
		print ''

		if self.cord:
			# Add related models and any api properties
			for name in self.model_properties:
				print 'models.%s.prototype.computed = {' % name
				for i, prop_name in enumerate(self.model_properties[name]):
					print '\t%s: function(%s) { return %s; });' % (prop_name, ', '.join(self.model_properties_args[name][prop_name]), self.model_properties[name][prop_name])
				print '};'
				print ''
		else:
			# Add properties to get related nested models
			if self.include_related:
				for name in self.include_related:
					print 'Object.defineProperties(models.%s.prototype, {' % name
					for i, field_name in enumerate(self.include_related[name]):
						comma = '' if i == len(self.include_related[name]) - 1 else ','
						print '\t%s: { get: function() { return this.attributes.%s && new models.%s(this.attributes.%s); } }%s' % (field_name, field_name, self.include_related[name][field_name], field_name, comma)
					print '});'
					print ''
			# Add on any api properties
			for name in self.model_properties:
				print 'Object.defineProperties(models.%s.prototype, {' % name
				for i, prop_name in enumerate(self.model_properties[name]):
					comma = '' if i == len(self.model_properties[name]) - 1 else ','
					print '\t%s: { get: function() { return %s; } }%s' % (prop_name, self.model_properties[name][prop_name], comma)
				print '});'
				print ''
		# Singleton objects
		if self.singletons:
			print 'var singletons = {'
			for i, name in enumerate(self.singletons):
				comma = ',' if i < (len(self.singletons) - 1) else ''
				print '\t%s: models.%s.extend({ url: "%s" })%s' % (name, name, self.singletons[name], comma)
			print '};'
		else:
			print 'var singletons = {};'
		print ''
		self.print_module_footer()
