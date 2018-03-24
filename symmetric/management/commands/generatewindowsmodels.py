import os
from optparse import make_option

from django.core.management.base import BaseCommand
from django.template import Template

from symmetric.management.generatemodels import GenerateModelsCommand

class Command(BaseCommand, GenerateModelsCommand):
    help = 'Generate Windows Phone models for API models or endpoints.'
    option_list = BaseCommand.option_list + GenerateModelsCommand.option_list + (
            make_option('--namespace',
                action='store',
                dest='namespace',
                type='string',
                default='com.business.app',
                help='Set the Windows namespace.'),
        )

    def extra_context(self, model, api_model):
        return {'namespace': self.namespace }

    def handle(self, *args, **options):
        # Remember options
        self.namespace = options['namespace']

        # Create the templates
        template_path = os.path.join(os.path.normpath(os.path.dirname(__file__) + '/../templates'), 'windows-model.cs')
        with open(template_path) as f:
            self.templates = [Template(f.read())]
        self.template_extensions = ['cs']

        # Create the mappings
        property_base = '[DataMember(Name = "{{ name }}")]\ninternal %s {{ name|title }} {%% templatetag openbrace %%} get; set; {%% templatetag closebrace %%}'
        property_mapping = {
            'CharField': Template(property_base % 'string'),
            'IntegerField': Template(property_base % 'int'),
            'PositiveIntegerField': Template(property_base % 'uint'),
            'BigIntegerField': Template(property_base % 'long'),
            'DateField': Template(property_base % 'DateTime'),
            'DecimalField': Template(property_base % 'float'),
            'BooleanField': Template(property_base % 'bool'),
            'Field': ';'
        }
        self.mappings = {'properties': property_mapping }
        self.render(*args, **options)
