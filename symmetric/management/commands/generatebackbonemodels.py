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
from django.utils.encoding import force_unicode

import symmetric.management.overrides
from symmetric.functions import camel_case_to_underscore, underscore_to_camel_case
from symmetric.management.codeemitter import CodeEmitter
from symmetric.management.functions import get_base_classes, get_resource_type, get_subclass_filter, format_regex_stack, is_readonly
from symmetric.management.functions import get_model_name, get_model_name_plural, get_collection_name, get_collection_name_plural
from symmetric.management.translate import translate_code
from symmetric.models import get_related_model
from symmetric.views import ApiAction, ApiRequirement, BasicApiView, api_view

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
			make_option('--es6',
				action='store_true',
				dest='es6',
				default=False,
				help='Output the code as es6 code. If module-type is not given also implies esm module-type.'),
			make_option('--defaults',
				action='store_true',
				dest='defaults',
				default=False,
				help='Add in available default values into the models.'),
			make_option('--descriptions',
				action='store_true',
				dest='descriptions',
				default=False,
				help='Add the help_text for each field under a descriptions object.'),
			make_option('--titles',
				action='store_true',
				dest='titles',
				default=False,
				help='Add the verbose name for each field under a titles object.'),
			make_option('--choices',
				action='store_true',
				dest='choices',
				default=False,
				help='Add the choices for each field under a choices object.'),
			make_option('--cord',
				action='store_true',
				dest='cord',
				default=False,
				help='Use cord functionality for defining properties, validation, and submodels.'),
			make_option('--validation',
				action='store_true',
				dest='validation',
				default=False,
				help='Add a validation method to each model.'),
			make_option('--validation-method',
				dest='validation_method',
				type='string',
				default='validate',
				help='Validation method to call, defaults to the global validate method. If --cord is given this default will become Backbone.Cord.validate'),
			make_option('--models-code',
				dest='models-code',
				type='string',
				help='Raw code to mixin with the models code.'),
			make_option('--collections-code',
				dest='collections-code',
				type='string',
				help='Raw code to mixin with the collections code.'),
			make_option('--indent',
				dest='indent',
				type='int',
				default=0,
				help='Each tab should instead indent with this number of spaces.')
		)

	def add_choices(self, model):
		choices = {}
		for field in model._meta.fields:
			if hasattr(field, 'choices') and field.choices:
				field_choices = {}
				for choice in field.choices:
					field_choices[choice[0]] = choice[1]
				key = field.name
				if self.camelcase:
					key = underscore_to_camel_case(key)
				choices[key] = field_choices
		if choices:
			self.models[get_model_name(model)]['choices'] = choices

	def add_defaults(self, model):
		name = get_model_name(model)
		for field in model._meta.fields:
			if is_readonly(model, field.name):
				continue
			default = field.default
			if isinstance(default, type):
				default = default()
			if default is not NOT_PROVIDED and not callable(default):
				if not self.models[name].has_key('defaults'):
					self.models[name]['defaults'] = {}
				key = field.name
				if self.camelcase:
					key = underscore_to_camel_case(key)
				self.models[name]['defaults'][key] = default

	def add_descriptions(self, model):
		descriptions = {}
		for field in model._meta.fields:
			if hasattr(field, 'help_text') and field.help_text:
				key = field.name
				if self.camelcase:
					key = underscore_to_camel_case(key)
				descriptions[key] = force_unicode(field.help_text)
		if descriptions:
			self.models[get_model_name(model)]['descriptions'] = descriptions

	def add_titles(self, model):
		titles = {}
		for field in model._meta.fields:
			key = field.name
			if self.camelcase:
				key = underscore_to_camel_case(key)
			titles[key] = field.verbose_name.title()
		if titles:
			self.models[get_model_name(model)]['titles'] = titles

	def add_validation(self, model):
		rules = {}
		if rules:
			self.models[get_model_name(model)]['rules'] = rules
			self.models[get_model_name(model)]['validate'] = 'validate'

	def add_parse(self, model):
		fields = []
		for field in model._meta.fields:
			# Parse DateField and DateTimeFields, but not TimeFields
			if isinstance(field, DateField):
				if self.camelcase:
					fields.append("'%s'" % underscore_to_camel_case(field.name))
				else:
					fields.append("'%s'" % field.name)
		if fields:
			self.models[get_model_name(model)]['parse'] = ', '.join(fields)

	def translate_properties(self, model):
		lang = 'es6' if self.es6 else 'js'
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
			self.add_parse(model)
			if self.choices:
				self.add_choices(model)
			if self.defaults:
				self.add_defaults(model)
			if self.descriptions:
				self.add_descriptions(model)
			if  self.titles:
				self.add_titles(model)
			if self.validation:
				self.add_validation(model)
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
			models = ['if (attrs.hasOwnProperty(models.%s.prototype.idAttribute)) {\nreturn new models.%s(attrs, options);\n}\n' % (model, model) for model in models if self.models.has_key(model)]
			if len(models) < count:
				models.append('return new Backbone.Model(attrs, options);\n')
			return '%s {\n%s}' % (self.get_anon_func('attrs, options'), 'else '.join(models))
		else:
			return 'models.' + models[0]

	def get_anon_func(self, args=''):
		if self.es6:
			return '(%s) =>' % args
		else:
			return 'function(%s)' % args

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
		# Module definition start
		if self.module_type == 'amd':
			self.emit("define(['backbone', 'underscore'], %s {" % self.get_anon_func('Backbone, _'))
		elif self.module_type != 'esm':
			self.emit('(%s {' % self.get_anon_func())
		if self.module_type != 'esm':
			self.emit('"use strict";', '')
		if self.module_type == 'cjs':
			self.emit(
				"%s Backbone = require('backbone');" % self.const,
				"%s _ = require('underscore');" % self.const,
				''
			)
		elif self.module_type == 'esm':
			self.emit(
				"import Backbone from 'backbone';",
				"import _ from 'underscore';",
				''
			)

	def print_module_footer(self, f=sys.stdout):
		# Module definition end
		if self.module_type == 'amd':
			self.emit('return { models: models, collections: collections, singletons: singletons}; });')
		elif self.module_type == 'cjs':
			self.emit(
				'exports.models = models;',
				'exports.collections = collections;',
				'exports.singletons = singletons;'
			)
		elif self.module_type == 'esm':
			self.emit('export { models, collections, singletons };')
		else:
			self.emit(
				'window.models = models;',
				'window.collections = collections;',
				'window.singletons = singletons;'
			)
		if self.module_type != 'amd' and self.module_type != 'esm':
			self.emit('})();')

	def handle(self, *args, **options):
		self.defaults = options['defaults']
		self.choices = options['choices']
		self.descriptions = options['descriptions']
		self.titles = options['titles']
		self.cord = options['cord']
		self.es6 = options['es6']
		self.module_type = options['module_type']
		self.validation = options['validation']
		self.validation_method = options['validation_method']
		if self.cord:
			if '--validation-method' not in sys.argv:
				self.validation_method = 'Backbone.Cord.validate'
		if self.es6:
			if '--module-type' not in sys.argv:
				self.module_type = 'esm'
			self.const = 'const'
			self.local = 'let'
		else:
			self.const = 'var'
			self.local = 'var'
		self.emit = CodeEmitter(sys.stdout, options['indent'])
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
			return re.sub(r'"([a-zA-Z][^"]*)":', r'\1:', jsn)

		separators = (',', ': ')

		self.print_module_header()

		# Add newUrl attributes to the models so they can be created outside of collections.
		# Matching models and collections will share the same name
		for name in self.models:
			if self.models[name].has_key('urlRoot') and self.collections.has_key(name):
				self.models[name]['newUrl'] = self.collections[name]['url']

		# Output the code
		model_js = unjson(json.dumps(self.models, separators=separators, indent=True, sort_keys=True))
		# Convert all urlRoot attributes into functions.
		# The collection's url should be overridden when the object already exists with an id (!isNew) because it may be part of a heterogeneous subclass collection or related collection that does not have an endpoint for updating the object
		# A newUrl is also defined/undefined when the model is created outside of a collection it can still use its collection's url for creating a new instance
		model_js = re.sub(r'urlRoot: "([^"]*)"',
			r"""urlRoot: %s {
				if (!this.isNew()) {
					return "\1";
				} else if (!this.collection) {
					return this.newUrl;
				}
			}""" % self.get_anon_func(), model_js)
		# Convert all parse attributes into a function
		model_js = re.sub(r'parse: "([^"]*)"',
			r"""parse: %s {
				if (response) {
					_.each([\1], %s {
						if (response[attribute]) {
							response[attribute] = new Date(response[attribute]);
						}
					});
				}
				if (this._parse) {
					response = this._parse(response);
				}
				return response;
			}""" % (self.get_anon_func('response'), self.get_anon_func('attribute')), model_js)
		model_js = re.sub(r'validate: "(validate)"',
			"""validate: %s {
				%s name, rule, expanded, ret, errors = [];
				for (name in attributes) {
					if (attributes.hasOwnProperty(name)) {
						rule = this.rules[name];
						ret = %s(attributes[name], expanded = {
							type: rule[0],
							equals: rule[1] || (this.choices && this.choices[name]),
							min: rule[2],
							max: rule[3],
							format: rule[4],
							required: rule[5]
						});
						if (ret !== true) {
							errors.push({error: ret, rule: expanded, attr: name});
						}
					}
					if (this._validate) {
						this._validate(errors);
					}
					if (errors.length) {
						return errors;
					}
				}
			}
			""" % (self.get_anon_func('attributes'), self.local, self.validation_method), model_js)

		self.emit(*('%s models = %s;\n' % (self.const, model_js)).split('\n'))
		if options['models-code']:
			with open(options['models-code'], 'r') as f:
				self.emit(*f.read().split('\n'))
		self.emit(
			'_.each(models, %s {' % self.get_anon_func('value, key'),
				'models[key] = Backbone.Model.extend(value);',
			'});',
			''
		)
		for name in self.related_collections:
			self.emit('Object.defineProperties(models.%s.prototype, {' % name)
			for i, related in enumerate(self.related_collections[name]):
				comma = ',' if i < (len(self.related_collections[name]) - 1) else ''
				self.emit(
					'%sCollection: {' % related['collection'],
						'get: function() {',
							'return Backbone.Collection.extend({')
				self.emit(		*('model: %s,' % self.get_model_unreplacement(related['model'])).split('\n'))
				self.emit(		'url: "%s"' % related['url'],
							'});',
						'}',
					'}%s' % comma
				)
			self.emit('});', '')
		collections_js = unjson(json.dumps(self.collections, separators=separators, indent=4))
		# Convert the special model###modelName code into a models.Class or a function for a heterogeneous collection
		collections_js = re.sub(r'"model###(.*)"', self.get_model_unreplacement, collections_js)
		self.emit(*('%s collections = %s;\n' % (self.const, collections_js)).split('\n'))
		if options['collections-code']:
			with open(options['collections-code'], 'r') as f:
				self.emit(*f.read().split('\n'))
		self.emit(
			'_.each(collections, %s {' % self.get_anon_func('value, key'),
				'collections[key] = Backbone.Collection.extend(value);',
			'});',
			''
		)

		if self.cord:
			# Add related models and any api properties
			for name in self.model_properties:
				self.emit('models.%s.prototype.computed = {' % name)
				for i, prop_name in enumerate(self.model_properties[name]):
					comma = '' if i == len(self.model_properties[name]) - 1 else ','
					self.emit(
						'%s: %s {' % (prop_name, self.get_anon_func(', '.join(self.model_properties_args[name][prop_name]))),
							'return %s;' % self.model_properties[name][prop_name],
						'}%s' % comma
					)
				self.emit('};', '')
		else:
			# Add properties to get related nested models
			if self.include_related:
				for name in self.include_related:
					self.emit('Object.defineProperties(models.%s.prototype, {' % name)
					for i, field_name in enumerate(self.include_related[name]):
						comma = '' if i == len(self.include_related[name]) - 1 else ','
						self.emit(
							'%s: {' % field_name,
								'get: %s {' % self.get_anon_func(),
									'return this.attributes.%s && new models.%s(this.attributes.%s);' % (field_name, self.include_related[name][field_name], field_name),
								'}',
							'}%s' % comma
						)
					self.emit('});', '')
			# Add on any api properties
			for name in self.model_properties:
				self.emit('Object.defineProperties(models.%s.prototype, {' % name)
				for i, prop_name in enumerate(self.model_properties[name]):
					comma = '' if i == len(self.model_properties[name]) - 1 else ','
					self.emit(
						'%s: {' % prop_name,
							'get: %s {' % self.get_anon_func(),
								'return %s;' % self.model_properties[name][prop_name],
							'}',
						'}%s' % comma
					)
				self.emit('});', '')
		# Singleton objects
		if self.singletons:
			self.emit('%s singletons = {' % self.const)
			for i, name in enumerate(self.singletons):
				comma = ',' if i < (len(self.singletons) - 1) else ''
				self.emit('%s: models.%s.extend({ url: "%s" })%s' % (name, name, self.singletons[name], comma))
			self.emit('};')
		else:
			self.emit('%s singletons = {};' % self.const)
		self.emit('')
		self.print_module_footer()
