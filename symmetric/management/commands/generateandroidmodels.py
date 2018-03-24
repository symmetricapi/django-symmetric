import ast
import os
from optparse import make_option

from django.core.management.base import BaseCommand
from django.template import Template

from symmetric.management.functions import get_api_properties
from symmetric.management.generatemodels import GenerateModelsCommand


class ApiPropertyGetMethodTransformer(ast.NodeTransformer):
    """Renames uses of other api properties into get method calls e.g. getProperty()."""

    def __init__(self, model):
        self.api_properties = get_api_properties(model)

    def visit_Attribute(self, node):
        if type(node.value) is ast.Name and node.value.id == 'self' and type(node.attr) is str and node.attr in self.api_properties:
            # underscore here because it will later be converted to camelCase
            node.attr = 'get_%s()' % node.attr
        return node


class Command(BaseCommand, GenerateModelsCommand):
    help = 'Generate Android models for API models or endpoints.'
    option_list = BaseCommand.option_list + GenerateModelsCommand.option_list + (
        make_option(
            '--package',
            action='store',
            dest='package',
            type='string',
            default='com.business.app',
            help='Set the Android package name.',
        ),
    )

    def extra_context(self, model, api_model):
        # first: random.seed()
        # uid = '1' + ''.join([str(random.randint(0,9)) for x in range(18)])
        return {'package': self.package, 'uid': model.__name__.__hash__()}

    def handle(self, *args, **options):
        # Remember options
        self.package = options['package']

        # Create the template
        template_path = os.path.join(os.path.normpath(os.path.dirname(__file__) + '/../templates'), 'android-model.java')
        with open(template_path) as f:
            self.templates = [Template(f.read())]
        self.template_extensions = ['java']

        # Create the mappings
        ivar_base = '{{name}}{% if default %} = {{default}}{% endif %};'
        ivar_base_str = '{{name}}{% if default %} = "{{default}}"{% endif %};'
        ivar_mapping = {
            'AutoField': Template('public int ' + ivar_base),
            'CharField': Template('public String ' + ivar_base_str),
            'IntegerField': Template('public int ' + ivar_base),
            'BigIntegerField': Template('public long ' + ivar_base),
            'DateField': Template('public Date ' + ivar_base),
            'DecimalField': Template('public float ' + ivar_base),
            'BooleanField': Template('public boolean {{name}}{% if default %} = true{% endif %};'),
            'ForeignKey': Template('public {% if included %}{{included_name}}{% else %}int{% endif %} {{name}};'),
            'JSONField': Template('public JSONObject ' + ivar_base),
            'ArrayField': Template('public JSONArray ' + ivar_base),
            'Field': 'public int {name};',
        }
        read_json_base = 'this.{{name}} = jsonObject.opt%s("{{name}}");'
        read_json_mapping = {
            'AutoField': Template(read_json_base % 'Int'),
            'CharField': Template('this.{{name}} = (jsonObject.isNull("{{name}}")) ? null : jsonObject.optString("{{name}}");'),
            'IntegerField': Template(read_json_base % 'Int'),
            'BigIntegerField': Template(read_json_base % 'Long'),
            'DateField': Template('this.{{name}} = (jsonObject.isNull("{{name}}")) ? null : API.parseDate(jsonObject.optString("{{name}}"));'),
            'DecimalField': Template(read_json_base % 'Double'),
            'BooleanField': Template(read_json_base % 'Boolean'),
            'ForeignKey': Template('this.{{name}} = {% if included %}(jsonObject.isNull("{{name}}")) ? null : new {{included_name}}(jsonObject.optJSONObject("{{name}}")){% else %}jsonObject.optInt("{{name}}"){% endif %};'),
            'JSONField': Template(read_json_base % 'JSONObject'),
            'ArrayField': Template(read_json_base % 'JSONArray'),
            'Field': Template(read_json_base % 'Int'),
        }
        write_json_mapping = {
            'DateField': Template('jsonObject.put("{{name}}", {% if null %}(this.{{name}} == null) ? JSONObject.NULL : {% endif %}API.formatDate(this.{{name}}));'),
            'ForeignKey': Template('jsonObject.put("{{name}}", {% if included %}{% if included_readonly %}(this.{{included_obj_name}} != null) ? this.{{included_obj_name}}.getObjectId() : JSONObject.NULL{% else %}(this.{{name}} == null) ? JSONObject.NULL : this.{{name}}.getJSONObject(){% endif %}{% else %}(this.{{name}} == 0) ? JSONObject.NULL : this.{{name}}{% endif %});'),
            'Field': Template('jsonObject.put("{{name}}", {% if null %}(this.{{name}} == null) ? JSONObject.NULL : {% endif %}this.{{name}});'),
            'WriteOnly': True,
        }
        read_parcel_base = 'this.{{name}} = in.read%s();'
        read_parcel_mapping = {
            'AutoField': Template(read_parcel_base % 'Int'),
            'CharField': Template(read_parcel_base % 'String'),
            'IntegerField': Template(read_parcel_base % 'Int'),
            'BigIntegerField': Template(read_parcel_base % 'Long'),
            'DateField': Template('this.{{name}} = (Date)in.readSerializable();'),
            'DecimalField': Template(read_parcel_base % 'Double'),
            'BooleanField': 'boolean[] _{name} = new boolean[1];\nin.readBooleanArray(_{name});\nthis.{name} = _{name}[0];',
            'ForeignKey': Template('this.{{name}} = {% if included %}({{included_name}})in.readSerializable(){% else %}in.readInt(){% endif %};'),
            'JSONField': Template('try { this.{{name}} = new JSONObject(in.readString()); } catch(JSONException e) { }'),
            'ArrayField': Template('try { this.{{name}} = new JSONArray(in.readString()); } catch(JSONException e) { }'),
            'Field': Template(read_parcel_base % 'Int'),
        }
        write_parcel_base = 'dest.write%s(this.{{name}});'
        write_parcel_mapping = {
            'AutoField': Template(write_parcel_base % 'Int'),
            'CharField': Template(write_parcel_base % 'String'),
            'IntegerField': Template(write_parcel_base % 'Int'),
            'BigIntegerField': Template(write_parcel_base % 'Long'),
            'DateField': Template(write_parcel_base % 'Serializable'),
            'DecimalField': Template(write_parcel_base % 'Double'),
            'BooleanField': 'dest.writeBooleanArray(new boolean[] {{ this.{name} }});',
            'ForeignKey': Template(write_parcel_base % '{% if included %}Serializable{% else %}Int{% endif %}'),
            'JSONField': Template('dest.writeString(this.{{name}}.toString());'),
            'ArrayField': Template('dest.writeString(this.{{name}}.toString());'),
            'Field': Template(write_parcel_base % 'Int'),
        }
        read_external_base = 'this.{{name}} = %sinput.read%s();'
        read_external_mapping = {
            'AutoField': Template(read_external_base % ('', 'Int')),
            'CharField': Template(read_external_base % ('(String)', 'Object')),
            'IntegerField': Template(read_external_base % ('', 'Int')),
            'BigIntegerField': Template(read_external_base % ('', 'Long')),
            'DateField': Template(read_external_base % ('(Date)', 'Object')),
            'DecimalField': Template(read_external_base % ('', 'Float')),
            'BooleanField': Template(read_external_base % ('', 'Boolean')),
            'ForeignKey': Template(read_external_base % ('{% if included %}({{included_name}}){% endif %}', '{% if included %}Object{% else %}Int{% endif %}')),
            'JSONField': Template('try { this.{{name}} = new JSONObject((String)input.readObject()); } catch(JSONException e) { }'),
            'ArrayField': Template('try { this.{{name}} = new JSONArray((String)input.readObject()); } catch(JSONException e) { }'),
            'Field': Template(read_external_base % ('', 'Int')),
        }
        write_external_base = 'output.write%s(this.{{name}});'
        write_external_mapping = {
            'AutoField': Template(write_external_base % 'Int'),
            'CharField': Template(write_external_base % 'Object'),
            'IntegerField': Template(write_external_base % 'Int'),
            'BigIntegerField': Template(write_external_base % 'Long'),
            'DateField': Template(write_external_base % 'Object'),
            'DecimalField': Template(write_external_base % 'Float'),
            'BooleanField': Template(write_external_base % 'Boolean'),
            'ForeignKey': Template(write_external_base % '{% if included %}Object{% else %}Int{% endif %}'),
            'JSONField': Template('output.writeObject(this.{{name}}.toString());'),
            'ArrayField': Template('output.writeObject(this.{{name}}.toString());'),
            'Field': Template(write_external_base % 'Int'),
        }
        self.lang = 'java'
        self.property_transformer = ApiPropertyGetMethodTransformer
        self.property_types = {int: 'int', float: 'float', str: 'String', bool: 'boolean'}
        self.property_implementations = '\tpublic {type} get{name_upper}()\n\t{{\n\t\treturn {code};\n\t}}\n'
        self.mappings = {
            'ivars': ivar_mapping,
            'read_json': read_json_mapping,
            'write_json': write_json_mapping,
            'read_parcel': read_parcel_mapping,
            'write_parcel': write_parcel_mapping,
            'read_external': read_external_mapping,
            'write_external': write_external_mapping,
        }
        self.expand_mappings('CharField', 'TextField', 'IPAddressField', 'GenericIPAddressField')
        self.render(*args, **options)
