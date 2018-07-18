from importlib import import_module
from optparse import make_option
import os

from django.apps import apps
from django.conf import settings
from django.core.management.base import CommandError
from django.db.models.fields import NOT_PROVIDED, TimeField, DateField
from django.db.models.fields.related import ForeignKey
from django.template import Template, Context

import symmetric.management.overrides
from symmetric.functions import _ApiModel, underscore_to_camel_case
from symmetric.management.functions import get_base_classes, get_base_models, get_base_model, get_field, has_field
from symmetric.management.translate import translate_code
from symmetric.models import get_related_model
from symmetric.views import ApiAction, ApiRequirement, BasicApiView, api_view


get_model = apps.get_model


class GenerateModelsCommand(object):
    option_list = (
        make_option(
            '--prefix',
            type='string',
            dest='prefix',
            default='',
            help='Prefix to add to each class name and file name.',
        ),
        make_option(
            '--dest',
            type='string',
            dest='dest',
            help='Output the all detected models from api endpoints and render them into this destination directory.',
        ),
        make_option(
            '--exclude',
            type='string',
            dest='exclude',
            action='append',
            help='Do not output anything for the models specified.',
        ),
        make_option(
            '--indent',
            dest='indent',
            type='int',
            default=2,
            help='Each tab should instead indent with this number of spaces or 0 for hard tabs.',
        ),
    )

    def get_include_related_models(self, model):
        related_models = set()
        if hasattr(model, 'API') and hasattr(model.API, 'include_related'):
            include_related = model.API.include_related
            for field in model._meta.fields:
                if field.name in include_related:
                    related_models.add(get_related_model(field))
                    related_models |= self.get_include_related_models(get_related_model(field))
        return related_models

    def post_render(self, output):
        if self.indent:
            return output.replace('\t', ' ' * self.indent)
        return output

    def base_extra_context(self, model, api_model):
        has_date = False
        has_bool = False
        datetime_fields = []
        primary_field = None
        if api_model.id_field:
            primary_field = api_model.id_field[1]
        base = get_base_model(model)
        base_name = None
        if base:
            base_name = base.__name__
        for decoded_name, encoded_name, encode, decode in api_model.fields:
            if has_field(base, decoded_name):
                continue
            field = get_field(model, decoded_name)
            field_type = field.__class__.__name__
            if field_type == 'DateTimeField' or field_type == 'DateField':
                has_date = True
                datetime_fields.append((encoded_name, encoded_name[0].upper() + encoded_name[1:]))
            elif field_type == 'BooleanField':
                has_bool = True
            if not primary_field and field.primary_key:
                primary_field = encoded_name
        return {'prefix': self.prefix, 'base_name': base_name, 'name': model.__name__, 'name_lower': model.__name__[0].lower() + model.__name__[1:], 'has_date': has_date, 'has_bool': has_bool, 'primary_field': primary_field, 'datetime_fields': datetime_fields}

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

    def get_context(self, model):
        api_model = _ApiModel(model)
        context = self.base_extra_context(model, api_model)

        if hasattr(self, 'extra_context'):
            context.update(self.extra_context(model, api_model))

        # Loop over the mappings
        for mapping_name in self.mappings:
            mapping = self.mappings[mapping_name]
            write_only = False
            if isinstance(mapping, dict):
                write_only = mapping.get('WriteOnly', False)
            lines = []
            for decoded_name, encoded_name, encode, decode in api_model.fields:
                field = get_field(model, decoded_name)
                # Skip any field that is not directly on model and is not the primary id field (which could be on the base too)
                if field.model is not model and encoded_name != context['primary_field']:
                    continue
                # Skip any ptr field to base models
                if decoded_name.endswith('_ptr_id'):
                    continue
                include_related = hasattr(model, 'API') and hasattr(model.API, 'include_related') and field.name in model.API.include_related
                included_readonly = False
                included_obj_name = ''
                if write_only and encoded_name not in api_model.encoded_fields:
                    # Skip readonly fields, but make an exception for included foreign keys, see Included Objects in the documentation
                    if isinstance(field, ForeignKey) and include_related:
                        included_obj_name = encoded_name
                        encoded_name += 'Id' if self.camelcase else '_id'
                        included_readonly = True
                    else:
                        continue
                line = None
                classes = [field.__class__] + get_base_classes(field.__class__)
                for cls in classes:
                    field_type = cls.__name__
                    if callable(mapping):
                        line = mapping(model, encoded_name, field)
                    elif mapping.has_key(field_type):
                        format_context = {'name': encoded_name, 'null': field.null}
                        if field.default is not NOT_PROVIDED and not isinstance(field, (TimeField, DateField)):
                            # Only supply default values for non-date/time fields, it will be easier to just add these after manually
                            format_context['default'] = field.default
                        if include_related:
                            format_context['included'] = True
                            format_context['included_readonly'] = included_readonly
                            format_context['included_obj_name'] = included_obj_name
                            format_context['included_name'] = get_related_model(field).__name__
                        line = self.perform_mapping(mapping[field_type], format_context)
                    if line is not None:
                        break
                if line is None:
                    raise CommandError("No such mapping for %s in %s." % (field_type, mapping_name))
                elif line:
                    lines += line.split('\n')
            context[mapping_name] = lines

        # Translate the api properties
        if hasattr(self, 'property_declarations') or hasattr(self, 'property_implementations'):
            decl_lines = []
            impl_lines = []
            property_transformer = getattr(self, 'property_transformer', None)
            for name in model.__dict__:
                attr = model.__dict__[name]
                if type(attr) is property and attr.fget and hasattr(attr.fget, 'api_code'):
                    if getattr(attr.fget, 'api_translations', None) and attr.fget.api_translations.has_key(self.lang):
                        code = attr.fget.api_translations[self.lang]
                    else:
                        code = translate_code(attr.fget.api_code, self.lang, (property_transformer(model) if property_transformer else None))
                    format_context = {'name': name if not self.camelcase else underscore_to_camel_case(name), 'type': self.property_types[attr.fget.api_type], 'code': code}
                    format_context['name_upper'] = format_context['name'][0].upper() + format_context['name'][1:]
                    if hasattr(self, 'property_declarations'):
                        line = self.perform_mapping(self.property_declarations, format_context)
                        decl_lines += line.split('\n')
                    if hasattr(self, 'property_implementations'):
                        line = self.perform_mapping(self.property_implementations, format_context)
                        impl_lines += line.split('\n')
            if decl_lines:
                context['property_declarations'] = decl_lines
            if impl_lines:
                context['property_implementations'] = impl_lines

        return context

    def enum_patterns(self, patterns):
        for pattern in patterns:
            if pattern.callback:
                if isinstance(pattern.callback, (api_view, BasicApiView)) and pattern.callback.model:
                    self.models.add(pattern.callback.model)
                    self.models |= self.get_include_related_models(pattern.callback.model)
            else:
                self.enum_patterns(pattern.url_patterns)

    def expand_mappings(self, field, *expanded_fields):
        for mapping in self.mappings.values():
            for key, value in mapping.items():
                if key == field:
                    for expanded_field in expanded_fields:
                        if not mapping.has_key(expanded_field):
                            mapping[expanded_field] = mapping[field]
                    break

    def render(self, *args, **options):
        self.camelcase = getattr(settings, 'API_CAMELCASE', True)
        self.prefix = options['prefix']
        self.indent = options['indent']
        if not hasattr(self, 'templates'):
            raise CommandError('No templates set!')
        if options and options['dest']:
            try:
                os.makedirs(options['dest'])
            except:
                print 'Warning: Overwriting any contents in %s' % options['dest']
            self.models = set()
            module = import_module(settings.ROOT_URLCONF)
            self.enum_patterns(module.urlpatterns)
            # Add any base models to the set
            base_models = set()
            for model in self.models:
                base_models |= set(get_base_models(model))
            self.models |= base_models
            for model in self.models:
                if options['exclude'] and model.__name__ in options['exclude']:
                    continue
                context = self.get_context(model)
                for i in range(len(self.templates)):
                    template = self.templates[i]
                    template_extension = self.template_extensions[i]
                    path = os.path.join(options['dest'], '%s%s.%s' % (self.prefix, model.__name__, template_extension))
                    print 'Rendering %s' % path
                    with open(path, 'w') as f:
                        f.write(self.post_render(template.render(Context(context, autoescape=False))))
        elif args:
            for model_name in args:
                model = model_name.split('.')
                model = get_model(model[0], model[1])
                context = self.get_context(model)
                for template in self.templates:
                    print self.post_render(template.render(Context(context, autoescape=False)))
        else:
            raise CommandError("No model or destination directory specified.")
