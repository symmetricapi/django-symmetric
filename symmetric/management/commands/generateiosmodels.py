import os
from optparse import make_option

from django.core.management.base import BaseCommand
from django.template import Template

from symmetric.management.generatemodels import GenerateModelsCommand
from symmetric.management.translate import data_to_objc

included_field_setter = """{% if included %}- (void)set{{ name|title }}:({{ included_name }} *)new{{ name|title }}
{
    if([new{{ name|title }} isKindOfClass:[NSDictionary class]])
    {
        NSDictionary *dictionary = (NSDictionary *)new{{ name|title }};
        new{{ name|title }} = [[[{{ prefix }}{{ included_name }} alloc] init] autorelease];
        [new{{ name|title }} setValuesForKeysWithDictionary:dictionary];
    }
    if(_{{ name }} != new{{ name|title }})
    {
        [_{{ name }} release];
        _{{ name }} = [new{{ name|title }} retain];
    }
}
{% endif %}"""

class Command(BaseCommand, GenerateModelsCommand):
    help = 'Generate iOS models for API models or endpoints.'
    option_list = BaseCommand.option_list + GenerateModelsCommand.option_list

    def handle(self, *args, **options):
        # Create the templates
        self.templates = []
        template_path = os.path.join(os.path.normpath(os.path.dirname(__file__) + '/../templates'), 'ios-model.h')
        with open(template_path) as f:
            self.templates.append(Template(f.read()))
        template_path = os.path.join(os.path.normpath(os.path.dirname(__file__) + '/../templates'), 'ios-model.m')
        with open(template_path) as f:
            self.templates.append(Template(f.read()))
        self.template_extensions = ['h', 'm']

        # Create the mappings
        import_mapping = {
            'ForeignKey': Template('{% if included %}#import "{{prefix}}{{included_name}}.h"{% endif %}'),
            'Field': ''
        }
        property_base = "@property (nonatomic, %s{%% if name == 'hash' or name == 'description' %%}, getter=get{{name|title}}{%% endif %%}) %s{{name}};"
        property_mapping = {
            'CharField': Template(property_base % ('copy', 'NSString *')),
            'IntegerField': Template(property_base % ('assign', 'int32_t ')),
            'PositiveIntegerField': Template(property_base % ('assign', 'uint32_t ')),
            'BigIntegerField': Template(property_base % ('assign', 'int64_t ')),
            'DateField': Template(property_base % ('retain', 'NSDate *')),
            'DecimalField': Template(property_base % ('assign', 'float ')),
            'FloatField': Template(property_base % ('assign', 'float ')),
            'BooleanField': Template(property_base % ('assign', 'BOOL ')),
            'AutoField': Template(property_base % ('assign', 'uint32_t ')),
            'ForeignKey': Template('@property (nonatomic, {% if included %}retain{% else %}assign{% endif %}) {% if included %}{{prefix}}{{included_name}} *{% else %}uint32_t {% endif %}{{name}};'),
            'JSONField': Template(property_base % ('retain', 'NSMutableDictionary *')),
            'ArrayField': Template(property_base % ('retain', 'NSMutableArray *')),
            'Field': '#error "Unsupported field for {name}"'
        }
        synthesizer_mapping = {
            'Field': Template("{% if name == 'hash' or name == 'description' %}@synthesize {{name}} = _{{name}};{% endif %}")
        }
        default_values_data = lambda format_context: '_%s = [%s retain];' % (format_context['name'], data_to_objc(format_context['default'])) if format_context.get('default') else ''
        default_values_mapping = {
            'CharField': default_values_data,
            'JSONField': default_values_data,
            'ArrayField': default_values_data,
            'BooleanField': Template('{% if default %}_{{name}} = YES;{% endif %}'),
            'Field': Template('{% if default %}_{{name}} = {{ default }};{% endif %}')
        }
        dealloc_format = '[_{name} release];'
        dealloc_mapping = {
            'CharField': dealloc_format,
            'DateField': dealloc_format,
            'ForeignKey': Template('{% if included %}[_{{name}} release];{% endif %}'),
            'JSONField': dealloc_format,
            'ArrayField': dealloc_format,
            'Field': ''
        }
        encode_base = '[encoder encode%s:_{{name}} forKey:@"{{name}}"];'
        encode_mapping = {
            'AutoField': Template(encode_base % 'Int32'),
            'CharField': Template(encode_base % 'Object'),
            'IntegerField': Template(encode_base % 'Int32'),
            'BigIntegerField': Template(encode_base % 'Int64'),
            'DateField': Template(encode_base % 'Object'),
            'DecimalField': Template(encode_base % 'Float'),
            'FloatField': Template(encode_base % 'Float'),
            'BooleanField': Template(encode_base % 'Bool'),
            'ForeignKey': Template(encode_base % '{% if included %}Object{% else %}Int32{% endif %}'),
            'JSONField': Template(encode_base % 'Object'),
            'ArrayField': Template(encode_base % 'Object'),
            'Field': ''
        }
        decode_base = '%s{{name}} = [decoder decode%sForKey:@"{{name}}"];'
        decode_mutable_base = '%s{{name}} = [[[decoder decode%sForKey:@"{{name}}"] mutableCopy] autorelease];'
        decode_mapping = {
            'AutoField': Template(decode_base % ('_', 'Int32')),
            'CharField': Template(decode_base % ('self.', 'Object')),
            'IntegerField': Template(decode_base % ('_', 'Int32')),
            'BigIntegerField': Template(decode_base % ('_', 'Int64')),
            'DateField': Template(decode_base % ('self.', 'Object')),
            'DecimalField': Template(decode_base % ('_', 'Float')),
            'FloatField': Template(decode_base % ('_', 'Float')),
            'BooleanField': Template(decode_base % ('_', 'Bool')),
            'ForeignKey': Template(decode_base % ('{% if included %}self.{% else %}_{% endif %}', '{% if included %}Object{% else %}Int32{% endif %}')),
            'JSONField': Template(decode_mutable_base % ('self.', 'Object')),
            'ArrayField': Template(decode_mutable_base % ('self.', 'Object')),
            'Field': ''
        }
        url_encoded_data_string = 'if(_{{name}})\n\t[args addObject:[NSString stringWithFormat:@"{{name}}=%@", [_{{name}} stringByAddingPercentEncodingWithAllowedCharacters:NSCharacterSet.URLQueryAllowedCharacterSet]]];{% if null %}\nelse\n\t[args addObject:@"{{name}}=NULL"];{% endif %}'
        url_encoded_data_date = 'if(_{{name}})\n\t[args addObject:[NSString stringWithFormat:@"{{name}}=%@", [[[API dateFormatter] stringFromDate:_{{name}}] stringByAddingPercentEncodingWithAllowedCharacters:NSCharacterSet.URLQueryAllowedCharacterSet]]];{% if null %}\nelse\n\t[args addObject:@"{{name}}=NULL"];{% endif %}'
        url_encoded_data_number = '[args addObject:[NSString stringWithFormat:@"{{name}}=%s", _{{name}}]];'
        url_encoded_data_json = 'if(_{{name}})\n\t[args addObject:[NSString stringWithFormat:@"{{name}}=%@", [[NSString stringWithJSONObject:_{{name}}] stringByAddingPercentEncodingWithAllowedCharacters:NSCharacterSet.URLQueryAllowedCharacterSet]]];{% if null %}\nelse\n\t[args addObject:@"{{name}}=NULL"];{% endif %}'
        url_encoded_data_json_included =  '[args addObject:@"{{name}}=%@", [[NSString stringWithJSONObject:_{{name}}] stringByAddingPercentEncodingWithAllowedCharacters:NSCharacterSet.URLQueryAllowedCharacterSet]];'
        url_encoded_data_null = '[args addObject:@"{{name}}=NULL"];'
        url_encoded_data_mapping = {
            'CharField': Template(url_encoded_data_string),
            'IntegerField': Template(url_encoded_data_number % '%d'),
            'PositiveIntegerField': Template(url_encoded_data_number % '%u'),
            'BigIntegerField': Template(url_encoded_data_number % '%lld'),
            'DateField': Template(url_encoded_data_date),
            'DecimalField': Template(url_encoded_data_number % '%f'),
            'FloatField': Template(url_encoded_data_number % '%f'),
            'BooleanField': '[args addObject:[NSString stringWithFormat:@"{name}=%@", (_{name}?@"true":@"false")]];',
            'ForeignKey': Template('{% if included %}{% if included_readonly %}if(_{{included_obj_name}}) [args addObject:[NSString stringWithFormat:@"{{name}}=%u", _{{included_obj_name}}.objectId]]; else ' + url_encoded_data_null + ' {% else %}' + url_encoded_data_json_included + '{% endif %}{% else %}if(!_{{name}}) ' + url_encoded_data_null + ' else ' + (url_encoded_data_number % '%u') + '{% endif %}'),
            'JSONField': Template(url_encoded_data_json),
            'ArrayField': Template(url_encoded_data_json),
            'Field': '',
            'WriteOnly': True
        }
        dict_field_mapping = {
            'ForeignKey': Template('{% if not included %}{{name}}{% endif %}'),
            'Field': '{name}',
            'WriteOnly': True
        }
        dict_included_mapping = {
            'ForeignKey': Template('{% if included %}{% if included_readonly %}[dictionary setObject:((_{{included_obj_name}}) ? [NSNumber numberWithUnsignedInteger:_{{included_obj_name}}.objectId] : [NSNull null]) forKey:@"{{name}}"];{% else %}[dictionary setObject:(_{{name}} ? [_{{name}} dictionary] : [NSNull null]) forKey:@"{{name}}"];{% endif %}{% endif %}'),
            'Field': '',
            'WriteOnly': True
        }
        included_field_setter_mapping = {
            'ForeignKey': Template(included_field_setter),
            'Field': ''
        }

        self.lang = 'objc'
        self.property_types = {int: 'NSInteger ', float: 'float ', str: 'NSString *', bool: 'BOOL '}
        self.property_declarations = "@property (nonatomic, readonly) {type}{name};"
        self.property_implementations = Template('- ({{type.strip}}){{name}}\n{\n\treturn {{code}};\n}\n')
        self.mappings = {'imports': import_mapping, 'properties': property_mapping, 'synthesizers': synthesizer_mapping, 'default_values': default_values_mapping, 'dealloc': dealloc_mapping, 'encode': encode_mapping, 'decode': decode_mapping, 'url_encoded_data': url_encoded_data_mapping, 'dict_fields': dict_field_mapping, 'dict_included': dict_included_mapping, 'included_field_setters': included_field_setter_mapping }
        self.expand_mappings('CharField', 'TextField', 'IPAddressField', 'GenericIPAddressField')
        self.render(*args, **options)
