import ast
import json
import os
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
from symmetric.management.functions import get_base_classes, get_resource_type, get_subclass_filter, format_regex_stack, is_readonly, is_excluded, is_included
from symmetric.management.functions import get_model_name, get_model_name_plural, get_collection_name, get_collection_name_plural
from symmetric.management.rules import ApiFieldRule
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

def unjson(jsn):
	# Convert spaces to tabs and json keys to unquoted javascript attributes
	return re.sub(r'"([a-zA-Z0-9][^"]*)":', r'\1:', jsn)

separators = (',', ': ')

class Command(BaseCommand):
	help = 'Generate backbone models for API endpoints.'
	option_list = BaseCommand.option_list + (
			make_option('--dest',
				dest='dest',
				type='string',
				default='.',
				help='Output the models and colllections into models/ and collections/ inside the path given.'),
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
			make_option('--formats',
				action='store_true',
				dest='formats',
				default=False,
				help='Add all field format messages used as errors when a field is invalid.'),
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
			if is_excluded(model, field.name):
				continue
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
			if is_excluded(model, field.name) or is_readonly(model, field.name):
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
		subtitles = {}
		for field in model._meta.fields:
			if is_excluded(model, field.name):
				continue
			if hasattr(field, 'help_text') and field.help_text:
				key = field.name
				if self.camelcase:
					key = underscore_to_camel_case(key)
				subtitles[key] = force_unicode(field.help_text)
		if subtitles:
			self.models[get_model_name(model)]['subtitles'] = subtitles

	def add_titles(self, model):
		titles = {}
		for field in model._meta.fields:
			if is_excluded(model, field.name):
				continue
			key = field.name
			if self.camelcase:
				key = underscore_to_camel_case(key)
			titles[key] = field.verbose_name.title()
		if titles:
			self.models[get_model_name(model)]['titles'] = titles

	def add_instructions(self, model):
		instructions = {}
		for field in model._meta.fields:
			if is_excluded(model, field.name):
				continue
			key = field.name
			if self.camelcase:
				key = underscore_to_camel_case(key)
			message = force_unicode(field.error_messages.get('invalid', field.error_messages.get('invalid_choice', '')))
			default_invalid = default_invalid_choice = None
			for cls in reversed([field.__class__] + get_base_classes(field.__class__)):
				if not hasattr(cls, 'default_error_messages'):
					continue
				default_invalid = cls.default_error_messages.get('invalid', default_invalid)
				default_invalid_choice = cls.default_error_messages.get('invalid_choice', default_invalid_choice)
			if message and message != default_invalid and message != default_invalid_choice:
				instructions[key] = message
		if instructions:
			self.models[get_model_name(model)]['instructions'] = instructions

	def add_validation(self, model):
		rules = {}
		for field in model._meta.fields:
			if is_excluded(model, field.name) or is_readonly(model, field.name):
				continue
			key = field.name
			if self.camelcase:
				key = underscore_to_camel_case(key)
			rules[key] = ApiFieldRule(field).rule
		if rules:
			self.models[get_model_name(model)]['rules'] = rules
			if not self.cord:
				self.models[get_model_name(model)]['validate'] = 'validate'

	def add_parse(self, model):
		fields = []
		for field in model._meta.fields:
			if is_excluded(model, field.name):
				continue
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
		model_name = get_model_name(model)
		if model_properties:
			self.model_properties[model_name] = model_properties
		if model_properties_args:
			self.model_properties_args[model_name] = model_properties_args

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

	def get_readonly_fields(self, model):
		fields = []
		included_fields = []
		name = get_model_name(model)
		for field in model._meta.fields:
			if is_excluded(model, field.name):
				continue
			if is_readonly(model, field.name):
				key = field.name
				if self.camelcase:
					key = underscore_to_camel_case(key)
				if is_included(model, field.name):
					included_fields.append(key)
				fields.append(key)
		if field:
			self.readonly_fields[name] = fields
		if included_fields:
			self.readonly_included_fields[name] = included_fields

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
			if self.formats:
				self.add_instructions(model)
			if  self.titles:
				self.add_titles(model)
			if self.validation:
				self.add_validation(model)
			self.translate_properties(model)
			self.get_include_related(model)
			self.get_readonly_fields(model)
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
			models = ['if (attrs.hasOwnProperty(%s.prototype.idAttribute)) {\nreturn new %s(attrs, options);\n}\n' % (model, model) for model in models if self.models.has_key(model)]
			if len(models) < count:
				models.append('return new Backbone.Model(attrs, options);\n')
			return '%s {\n%s}' % (self.get_anon_func('attrs, options'), 'else '.join(models))
		else:
			return models[0]

	def get_anon_func(self, args=''):
		if self.es6:
			return '(%s) =>' % args
		else:
			return 'function(%s)' % args

	def get_proto_func(self, name, args=''):
		if self.es6:
			return '%s(%s)' % (name, args)
		else:
			return '%s: function(%s)' % (name, args)

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

	def print_module_header(self, f=sys.stdout, dependencies=[]):
		# Module definition start
		if self.module_type == 'amd':
			define_deps = ['backbone', 'underscore'] + dependencies
			define_deps = ["'%s'" % dd for dd in define_deps]
			define_deps = ', '.join(define_deps)
			define_args = ['Backbone', '_'] + [dep.split('/')[-1] for dep in dependencies]
			define_args = ', '.join(define_args)
			self.emit("define([%s], %s {" % (define_deps, self.get_anon_func(define_args)))
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
			if dependencies:
				self.emit(*["%s %s = require('%s');" % (self.const, dep.split('/')[-1], dep) for dep in dependencies])
				self.emit('')
		elif self.module_type == 'esm':
			self.emit(
				"import Backbone from 'backbone';",
				"import _ from 'underscore';",
				''
			)
			if dependencies:
				self.emit(*["import %s from '%s';" % (dep.split('/')[-1], dep) for dep in dependencies])
				self.emit('')

	def print_module_footer(self, f=sys.stdout, name=None):
		# Module definition end
		if self.module_type == 'amd':
			if name:
				self.emit('return %s; });' % name)
			else:
				self.emit('return { models: models, collections: collections, singletons: singletons}; });')
		elif self.module_type == 'cjs':
			if name:
				self.emit('module.exports = %s;' % name)
			self.emit(
				'exports.models = models;',
				'exports.collections = collections;',
				'exports.singletons = singletons;'
			)
		elif self.module_type == 'esm':
			if name:
				self.emit('export default %s;' % name)
			else:
				self.emit('export default { models, collections, singletons };')
		else:
			if name:
				self.emit('window.%s = %s' % (name, name))
			else:
				self.emit(
					'window.models = models;',
					'window.collections = collections;',
					'window.singletons = singletons;'
				)
		if self.module_type != 'amd' and self.module_type != 'esm':
			self.emit('})();')

	def output_model(self, name, model):
		path = os.path.join(self.dest_models, '%s.js' % name)

		dependencies = []
		include_related = self.include_related.get(name)
		if include_related:
			dependencies += ['models/%s' % ir for ir in include_related.values()]
		model_properties = self.model_properties.get(name)
		if model_properties and self.cord:
			model['computed'] = 'computed'
		related_collections = self.related_collections.get(name)
		if related_collections:
			model['related'] = 'related'
			dependencies += ['./%s' % r['model'] for r in related_collections]
			dependencies += ['../collections/%s' % r['collection'] for r in related_collections]
		readonly_fields = self.readonly_fields.get(name, [])
		readonly_included_fields = self.readonly_included_fields.get(name, [])
		if readonly_fields:
			model['toJSON'] = 'toJSON'

		with open(path, 'w') as f:
			self.emit = CodeEmitter(f, self.indent)
			self.print_module_header(f, dependencies)
			model_js = unjson(json.dumps(model, separators=separators, indent=True, sort_keys=True))

			# Convert all urlRoot attributes into functions.
			# The collection's url should be overridden when the object already exists with an id (!isNew) because it may be part of a heterogeneous subclass collection or related collection that does not have an endpoint for updating the object
			# A newUrl is also defined/undefined when the model is created outside of a collection it can still use its collection's url for creating a new instance
			model_js = re.sub(r'urlRoot: "([^"]*)"',
				r"""%s {
					if (!this.isNew()) {
						return "\1";
					} else if (!this.collection) {
						return this.newUrl;
					}
				}""" % self.get_proto_func('urlRoot'), model_js)

			# Convert all parse attributes into a function
			parse_related = []
			if include_related:
				for i, field_name in enumerate(include_related):
					parse_related.append('if (response.%s) {\nresponse.%s = new %s(response.%s);\n}' % (field_name, field_name, include_related[field_name], field_name))
			parse_related = '\n'.join(parse_related)
			model_js = re.sub(r'parse: "([^"]*)"',
				r"""%s {
					if (response) {
						_.each([\1], %s {
							if (response[attr]) {
								response[attr] = new Date(response[attr]);
							}
						});
						%s
					}
					// Custom parse function can also process response
					if (this.extendedParse) {
						response = this.extendedParse(response);
					}
					return response;
				}""" % (self.get_proto_func('parse', 'response'), self.get_anon_func('attr'), parse_related), model_js)

			# Add to the toJSON function to exclude readonly fields
			readonly_fields = '\n'.join(['delete data.%s;' % ro for ro in readonly_fields])
			id_suffix = 'Id' if self.camelcase else '_id'
			readonly_included_fields = '\n'.join(["data.%s%s = this.get('%s').id;" % (included, id_suffix, included) for included in readonly_included_fields])
			if readonly_included_fields:
				readonly_included_fields = '\n' + readonly_included_fields
			model_js = re.sub(r'toJSON: "toJSON"',
				"""%s {
					%s data = Backbone.Model.prototype.toJSON.call(this);
					%s%s
					return data;
				}""" % (self.get_proto_func('toJSON'), self.const, readonly_fields, readonly_included_fields), model_js)

			# Convert all validate entries to functions
			model_js = re.sub(r'validate: "validate"',
				"""%s {
					%s attr, rule, ret, errors = {};
					for (attr in attributes) {
						if (attributes.hasOwnProperty(attr)) {
							rule = this.rules[attr];
							if (rule) {
								if (rule.equals === null && rule.equals === void(0)) {
									rule.equals = this.choices && this.choices[attr];
								}
								ret = %s(attributes[attr], rule);
								if (ret !== true) {
									errors[attr] = ret;
								}
							}
						}
					}
					// Custom validation can also add to the errors object
					if (this.extendedValidate) {
						this.extendedValidate(errors);
					}
					if (Object.keys(errors).length) {
						return errors;
					}
				}""" % (self.get_proto_func('validate', 'attributes'), self.local, self.validation_method), model_js)

			# Add on any computed api properties
			computed = []
			if model_properties:
				if self.cord:
					computed.append('computed: {')
					for i, prop_name in enumerate(model_properties):
						comma = '' if i == len(model_properties) - 1 else ','
						computed.extend((
							'%s: %s {' % (prop_name, self.get_anon_func(', '.join(self.model_properties_args[name][prop_name]))),
								'return %s;' % model_properties[prop_name],
							'}%s' % comma
						))
					computed.append('}')
					model_js = re.sub(r'computed: "computed"', '\n'.join(computed), model_js)
					computed = None
				else:
					computed.extend(('Object.defineProperties(%s.prototype, {' % name))
					for i, prop_name in enumerate(model_properties):
						comma = '' if i == len(model_properties) - 1 else ','
						computed.extend((
							'%s: {' % prop_name,
								'get: %s {' % self.get_anon_func(),
									'return %s;' % model_properties[prop_name],
								'}',
							'}%s' % comma
						))
					computed.extend(('});', ''))

			get_related = []
			if related_collections:
				get_related.append('Object.defineProperties(%s.prototype, {' % name)
				for i, related in enumerate(related_collections):
					comma = '' if i == len(related_collections) - 1 else ','
					get_related.extend((
						'%s {' % self.get_proto_func('get%sCollection' % related['collection']),
							'return Backbone.Collection.extend({'))
					get_related.extend(('model: %s,' % self.get_model_unreplacement(related['model'])).split('\n'))
					get_related.extend(('url: "%s"' % related['url'],
							'});',
						'}' + comma
					))
				model_js = re.sub(r'related: "related"', '\n'.join(get_related), model_js)

			self.emit(*('%s %s = Backbone.Model.extend(%s);\n' % (self.const, name, model_js)).split('\n'))

			# Non-cord computed properties
			if computed:
				self.emit(*model_properties)

			# If this model also has a singleton instance add a function to get it
			if self.singletons.has_key(name):
				model_js = self.emit(
					'%s sharedInstance;' % self.local,
						'%s.prototype.getShared%s: %s {' % (name, name, self.get_anon_func()),
						'if(!sharedInstance) {',
							'sharedInstance = new %s();' % name,
							'sharedInstance.url = "%s";' % self.singletons[name],
						'}',
						'return sharedInstance;',
					'}', '')

			self.print_module_footer(f, name)

	def output_collection(self, name, collection):
		path = os.path.join(self.dest_collections, '%s.js' % name)
		with open(path, 'w') as f:
			self.emit = CodeEmitter(f, self.indent)

			collection_js = unjson(json.dumps(collection, separators=separators, indent=4))
			# Convert the special model###modelName code into a models.Class or a function for a heterogeneous collection
			dependencies = ['../models/' + model for model in re.findall(r'"model###(.*)"', collection_js)[0].split('|')]
			collection_js = re.sub(r'"model###(.*)"', self.get_model_unreplacement, collection_js)
			name = name + 'Collection'
			self.print_module_header(f, dependencies)
			self.emit(*('%s %s = Backbone.Collection.extend(%s);\n' % (self.const, name, collection_js)).split('\n'))
			self.print_module_footer(f, name)

	def handle(self, *args, **options):
		self.dest = os.path.abspath(options['dest'])
		self.defaults = options['defaults']
		self.choices = options['choices']
		self.descriptions = options['descriptions']
		self.titles = options['titles']
		self.formats = options['formats']
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
		self.indent = options['indent']
		self.emit = CodeEmitter(sys.stdout, self.indent)
		self.regex_stack = []
		self.models = {}
		self.model_properties = {}
		self.model_properties_args = {}
		self.collections = {}
		self.related_collections = {}
		self.singletons = {}
		self.include_related = {}
		self.readonly_fields = {}
		self.readonly_included_fields = {}
		self.camelcase = getattr(settings, 'API_CAMELCASE', True)
		self.renameid = getattr(settings, 'API_RENAME_ID', True)

		module = import_module(settings.ROOT_URLCONF)
		self.enum_patterns(module.urlpatterns)
		# Add newUrl attributes to the models so they can be created outside of collections.
		# Matching models and collections will share the same name
		for name in self.models:
			if self.models[name].has_key('urlRoot') and self.collections.has_key(name):
				self.models[name]['newUrl'] = self.collections[name]['url']

		try:
			os.makedirs(self.dest)
		except:
			print 'Warning: Overwriting any contents in ' + self.dest

		self.dest_models = os.path.join(self.dest, 'models')
		self.dest_collections = os.path.join(self.dest, 'collections')
		try:
			os.mkdir(self.dest_models)
		except:
			pass
		try:
			os.mkdir(self.dest_collections)
		except:
			pass

		for name in self.models:
			self.output_model(name, self.models[name])
		for name in self.collections:
			self.output_collection(name, self.collections[name])
