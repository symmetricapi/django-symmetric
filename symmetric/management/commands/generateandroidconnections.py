import os
from optparse import make_option

from django.core.management.base import BaseCommand
from django.template import Template

from api.management.generateconnections import GenerateConnectionsCommand

READ_OBJECT_METHOD = """
	public void read{{ name }}{% if param %}With{{ param }}({{ param_type }} {{ name_lower }}{{ param }}){% else %}(){% endif %}
	{
		String path = {% if param %}String.format(URL_{{ name|upper }}_WITH_{{ param|upper }}, {{ name_lower }}{{ param }}){% else %}URL_{{ name|upper }}{% endif %};
		performRequestWithObject(null, API.ACTION_READ, REQUEST_READ_{{ name|upper }}, path, {% if https %}true{% else %}false{% endif %}, {% if login %}true{% else %}false{% endif %}, false);
	}

	public static void read{{ name }}{% if param %}With{{ param }}({{ param_type }} {{ name_lower }}{{ param }}, {% else %}({% endif %}RequestListener listener)
	{
		{{ app_name }}Connection connection = new {{ app_name }}Connection(listener);
		connection.read{{ name }}{% if param %}With{{ param }}({{ name_lower }}{{ param }}){% else %}(){% endif %};
	}"""

READ_LIST_METHOD = """
	public void read{{ name_plural }}()
	{
		performRequestWithObject(null, API.ACTION_LIST, REQUEST_READ_{{ name_plural|upper }}, URL_{{ name_plural|upper }}, {% if https %}true{% else %}false{% endif %}, {% if login %}true{% else %}false{% endif %}, false);
	}

	public void read{{ name_plural }}(APIRequestParams params)
	{
		this.requestParams = params;
		read{{ name_plural }}();
	}

	public static void read{{ name_plural }}(APIRequestParams params, RequestListener listener)
	{
		{{ app_name }}Connection connection = new {{ app_name }}Connection(listener);
		connection.requestParams = params;
		connection.read{{ name_plural }}();
	}"""

CREATE_METHOD = """
	public void create{{ name }}({{ name }} {{ name_lower }})
	{
		performRequestWithObject({{ name_lower }}, API.ACTION_CREATE, REQUEST_CREATE_{{ name|upper }}, URL_{{ name_plural|upper }}, {% if https %}true{% else %}false{% endif %}, {% if login %}true{% else %}false{% endif %}, {% if hmac %}true{% else %}false{% endif %});
	}

	public static void create{{ name }}({{ name }} {{ name_lower }}, RequestListener listener)
	{
		{{ app_name }}Connection connection = new {{ app_name }}Connection(listener);
		connection.create{{ name }}({{ name_lower }});
	}"""

UPDATE_METHOD = """
	public void update{{ name }}({{ name }} {{ name_lower }})
	{
		String path = {% if param %}String.format(URL_{{ name|upper }}, {{ name_lower }}.getObjectId()){% else %}URL_{{ name|upper }}{% endif %};
		performRequestWithObject({{ name_lower }}, API.ACTION_UPDATE, REQUEST_UPDATE_{{ name|upper }}, path, {% if https %}true{% else %}false{% endif %}, {% if login %}true{% else %}false{% endif %}, {% if hmac %}true{% else %}false{% endif %});
	}

	public static void update{{ name }}({{ name }} {{ name_lower }}, RequestListener listener)
	{
		{{ app_name }}Connection connection = new {{ app_name }}Connection(listener);
		connection.update{{ name }}({{ name_lower }});
	}"""

DELETE_METHOD = """
	public void delete{{ name }}({{ name }} {{ name_lower }})
	{
		performRequestWithObject(null, API.ACTION_DELETE, REQUEST_DELETE_{{ name|upper }}, String.format(URL_{{ name|upper }}, {{ name_lower }}.getObjectId()), {% if https %}true{% else %}false{% endif %}, {% if login %}true{% else %}false{% endif %}, false);
	}

	public static void delete{{ name }}({{ name }} {{ name_lower }}, RequestListener listener)
	{
		{{ app_name }}Connection connection = new {{ app_name }}Connection(listener);
		connection.delete{{ name }}({{ name_lower }});
	}"""

READ_RELATED_LIST_METHOD = """
	public void read{{ name_plural }}For{{ parent_name }}{% if param %}With{{ param }}({{ param_type }} {{ parent_name_lower }}{{ param }}){% else %}(){% endif %}
	{
		String path = {% if param %}String.format(URL_{{ parent_name|upper }}_{{ name_plural|upper }}_WITH_{{ param|upper }}, {{ parent_name_lower }}{{ param }}){% else %}URL_{{ parent_name|upper }}_{{ name_plural|upper }}{% endif %};
		performRequestWithObject(null, API.ACTION_LIST, REQUEST_READ_{{ parent_name|upper }}_{{ name_plural|upper }}, path, {% if https %}true{% else %}false{% endif %}, {% if login %}true{% else %}false{% endif %}, false);
	}

	public void read{{ name_plural }}For{{ parent_name }}{% if param %}With{{ param }}({{ param_type }} {{ parent_name_lower }}{{ param }}, {% else %}({% endif %}APIRequestParams params)
	{
		this.requestParams = params;
		read{{ name_plural }}For{{ parent_name }}{% if param %}With{{ param }}({{ parent_name_lower }}{{ param }}){% else %}(){% endif %};
	}

	public static void read{{ name_plural }}For{{ parent_name }}{% if param %}With{{ param }}({{ param_type }} {{ parent_name_lower }}{{ param }}, {% else %}({% endif %}APIRequestParams params, RequestListener listener)
	{
		{{ app_name }}Connection connection = new {{ app_name }}Connection(listener);
		connection.requestParams = params;
		connection.read{{ name_plural }}For{{ parent_name }}{% if param %}With{{ param }}({{ parent_name_lower }}{{ param }}){% else %}(){% endif %};
	}"""

CREATE_RELATED_METHOD = """
	public void create{{ name }}For{{ parent_name }}{% if param %}With{{ param }}{% endif %}({{ name }} {{ name_lower }}{% if param %}, {{ param_type }} {{ parent_name_lower }}{{ param }}{% endif %})
	{
		String path = {% if param %}String.format(URL_{{ parent_name|upper }}_{{ name_plural|upper }}_WITH_{{ param|upper }}, {{ parent_name_lower }}{{ param }}){% else %}URL_{{ parent_name|upper }}_{{ name_plural|upper }}{% endif %};
		performRequestWithObject({{ name_lower }}, API.ACTION_CREATE, REQUEST_CREATE_{{ parent_name|upper }}_{{ name|upper }}, path, {% if https %}true{% else %}false{% endif %}, {% if login %}true{% else %}false{% endif %}, {% if hmac %}true{% else %}false{% endif %});
	}

	public static void create{{ name }}For{{ parent_name }}{% if param %}With{{ param }}{% endif %}({{ name }} {{ name_lower }}{% if param %}, {{ param_type }} {{ parent_name_lower }}{{ param }}{% endif %}, RequestListener listener)
	{
		{{ app_name }}Connection connection = new {{ app_name }}Connection(listener);
		connection.create{{ name }}For{{ parent_name }}{% if param %}With{{ param }}({{ name_lower }}, {{ parent_name_lower }}{{ param }}){% else %}({{ name_lower }}){% endif %};
	}"""

READ_RELATED_OBJECT_METHOD = """
	public void read{{ name }}For{{ parent_name }}{% if param %}With{{ param }}({{ param_type }} {{ parent_name_lower }}{{ param }}){% else %}(){% endif %}
	{
		String path = {% if param %}String.format(URL_{{ parent_name|upper }}_{{ name|upper }}_WITH_{{ param|upper }}, {{ parent_name_lower }}{{ param }}){% else %}URL_{{ parent_name|upper }}_{{ name|upper }}{% endif %};
		performRequestWithObject(null, API.ACTION_READ, REQUEST_READ_{{ parent_name|upper }}_{{ name|upper }}, path, {% if https %}true{% else %}false{% endif %}, {% if login %}true{% else %}false{% endif %}, false);
	}

	public void read{{ name }}For{{ parent_name }}{% if param %}With{{ param }}({{ param_type }} {{ parent_name_lower }}{{ param }}, RequestListener listener){% else %}(RequestListener listener){% endif %}
	{
		{{ app_name }}Connection connection = new {{ app_name }}Connection(listener);
		connection.read{{ name }}For{{ parent_name }}{% if param %}With{{ param }}({{ parent_name_lower }}{{ param }}){% else %}(){% endif %});
	}"""

UPDATE_RELATED_METHOD = """
	public void update{{ name }}For{{ parent_name }}{% if param %}With{{ param }}{% endif %}({{ name }} {{ name_lower }}{% if param %}, ({{ param_type }} {{ parent_name_lower }}{{ param }}{% endif %})
	{
		String path = {% if param %}String.format(URL_{{ parent_name|upper }}_{{ name|upper }}_WITH_{{ param|upper }}, {{ parent_name_lower }}{{ param }}){% else %}URL_{{ parent_name|upper }}_{{ name|upper }}{% endif %};
		performRequestWithObject({{ name_lower }}, API.ACTION_UPDATE, REQUEST_UPDATE_{{ parent_name|upper }}_{{ name|upper }}, path, {% if https %}true{% else %}false{% endif %}, {% if login %}true{% else %}false{% endif %}, {% if hmac %}true{% else %}false{% endif %});
	}

	public static void update{{ name }}For{{ parent_name }}{% if param %}With{{ param }}{% endif %}({{ name }} {{ name_lower }}{% if param %}, ({{ param_type }} {{ parent_name_lower }}{{ param }}{% endif %}, RequestListener listener)
	{
		{{ app_name }}Connection connection = new {{ app_name }}Connection(listener);
		connection.update{{ name }}For{{ parent_name }}{% if param %}With{{ param }}({{ name_lower }}, {{ parent_name_lower }}{{ param }}){% else %}({{ name_lower }}){% endif %};
	}"""

def indent(s, indentation):
	return '\n'.join([indentation + line for line in s.splitlines()])

READ_OBJECT_RESPONSE = indent("""
case REQUEST_READ_{{ name|upper }}:
	responseObject = new {{ name }}(new JSONObject(response));
	if({{ app_name }}Connection.this.listener != null)
		API.runOnUiThread(new Runnable() { public void run() { {{ app_name }}Connection.this.listener.{{ app_name_lower }}ConnectionDidRead{{ name }}({{ app_name }}Connection.this, ({{ name }})responseObject); } });
	break;""", '\t' * 7)

READ_LIST_RESPONSE = indent("""
case REQUEST_READ_{{ name_plural|upper }}:
	jsonArray = new JSONArray(response);
	responseArray = new {{ name }}[jsonArray.length()];
	for(int i = 0; i < jsonArray.length(); ++i) {% templatetag openbrace %}{% if subclasses %}
		JSONObject jsonObject = jsonArray.getJSONObject(i);{% for subclass in subclasses %}
		{% if forloop.counter0 %}else {% endif %}if(jsonObject.has("{{ subclass.0 }}"))
			responseArray[i] = new {{ subclass.1 }}(jsonObject);{% endfor %}{% else %}
		responseArray[i] = new {{ name }}(jsonArray.getJSONObject(i));{% endif %}
	}
	if({{ app_name }}Connection.this.listener != null)
		API.runOnUiThread(new Runnable() { public void run() { {{ app_name }}Connection.this.listener.{{ app_name_lower }}ConnectionDidRead{{ name_plural }}({{ app_name }}Connection.this, ({{ name }}[])responseArray); } });
	break;""", '\t' * 7)

CREATE_RESPONSE = indent("""
case REQUEST_CREATE_{{ name|upper }}:
	(({{ name }}){{ app_name }}Connection.this.requestObject).setObjectId(API.parseInt({{ app_name }}Connection.this.connection.getHeaderField(XHEADER_NEW_OBJECT_ID)));
	if({{ app_name }}Connection.this.listener != null)
		API.runOnUiThread(new Runnable() { public void run() { {{ app_name }}Connection.this.listener.{{ app_name_lower }}ConnectionDidCreate{{ name }}({{ app_name }}Connection.this, ({{ name }}){{ app_name }}Connection.this.requestObject); } });
	break;""", '\t' * 7)

UPDATE_RESPONSE = indent("""
case REQUEST_UPDATE_{{ name|upper }}:
	if({{ app_name }}Connection.this.listener != null)
		API.runOnUiThread(new Runnable() { public void run() { {{ app_name }}Connection.this.listener.{{ app_name_lower }}ConnectionDidUpdate{{ name }}({{ app_name }}Connection.this, ({{ name }}){{ app_name }}Connection.this.requestObject); } });
	break;""", '\t' * 7)

DELETE_RESPONSE = indent("""
case REQUEST_DELETE_{{ name|upper }}:
	if({{ app_name }}Connection.this.listener != null)
		API.runOnUiThread(new Runnable() { public void run() { {{ app_name }}Connection.this.listener.{{ app_name_lower }}ConnectionDidDelete{{ name }}({{ app_name }}Connection.this, ({{ name }}){{ app_name }}Connection.this.requestObject); } });
	break;""", '\t' * 7)

READ_RELATED_LIST_RESPONSE = indent("""
case REQUEST_READ_{{ parent_name|upper }}_{{ name_plural|upper }}:
	jsonArray = new JSONArray(response);
	responseArray = new {{ name }}[jsonArray.length()];
	for(int i = 0; i < jsonArray.length(); ++i) {% templatetag openbrace %}{% if subclasses %}
		JSONObject jsonObject = jsonArray.getJSONObject(i);{% for subclass in subclasses %}
		{% if forloop.counter0 %}else {% endif %}if(jsonObject.has("{{ subclass.0 }}"))
			responseArray[i] = new {{ subclass.1 }}(jsonObject);{% endfor %}{% else %}
		responseArray[i] = new {{ name }}(jsonArray.getJSONObject(i));{% endif %}
	}
	if({{ app_name }}Connection.this.listener != null)
		API.runOnUiThread(new Runnable() { public void run() { {{ app_name }}Connection.this.listener.{{ app_name_lower }}ConnectionDidRead{{ name_plural }}For{{ parent_name }}({{ app_name }}Connection.this, ({{ name }}[])responseArray); } });
	break;""", '\t' * 7)

CREATE_RELATED_RESPONSE = indent("""
case REQUEST_CREATE_{{ parent_name|upper }}_{{ name|upper }}:
	(({{ name }}){{ app_name }}Connection.this.requestObject).setObjectId(API.parseInt({{ app_name }}Connection.this.connection.getHeaderField(XHEADER_NEW_OBJECT_ID)));
	if({{ app_name }}Connection.this.listener != null)
		API.runOnUiThread(new Runnable() { public void run() { {{ app_name }}Connection.this.listener.{{ app_name_lower }}ConnectionDidCreate{{ name }}For{{ parent_name }}({{ app_name }}Connection.this, ({{ name }}){{ app_name }}Connection.this.requestObject); } });
	break;""", '\t' * 7)

READ_RELATED_OBJECT_RESPONSE = indent("""
case REQUEST_READ_{{ parent_name|upper }}_{{ name|upper }}:
	responseObject = new {{ name }}(new JSONObject(response));
	if({{ app_name }}Connection.this.listener != null)
		API.runOnUiThread(new Runnable() { public void run() { {{ app_name }}Connection.this.listener.{{ app_name_lower }}ConnectionDidRead{{ name }}For{{ parent_name }}({{ app_name }}Connection.this, ({{ name }})responseObject); } });
	break;""", '\t' * 7)

UPDATE_RELATED_RESPONSE = indent("""
case REQUEST_UPDATE_{{ parent_name|upper }}_{{ name|upper }}:
	if({{ app_name }}Connection.this.listener != null)
		API.runOnUiThread(new Runnable() { public void run() { {{ app_name }}Connection.this.listener.{{ app_name_lower }}ConnectionDidUpdate{{ name }}For{{ parent_name }}({{ app_name }}Connection.this, ({{ name }}){{ app_name }}Connection.this.requestObject); } });
	break;""", '\t' * 7)

class Command(BaseCommand, GenerateConnectionsCommand):
	help = 'Generate Android connections for API endpoints.'
	option_list = BaseCommand.option_list + GenerateConnectionsCommand.option_list + (
		make_option('--connection',
			type='string',
			dest='connection',
			default='APIURLConnection',
			help='Connection class to use that should have the same interface as ???.'),
		make_option('--package',
			action='store',
			dest='package',
			type='string',
			default='com.business.app',
			help='Set the Android package name.'),
	)

	def extra_context(self):
		return {'package': self.package, 'connection': self.connection}

	def handle(self, *args, **options):
		# Remember options
		self.package = options['package']
		self.connection = options['connection']

		# Create the templates
		self.templates = []
		template_path = os.path.join(os.path.normpath(os.path.dirname(__file__) + '/../templates'), 'android-connection.java')
		with open(template_path) as f:
			self.templates.append(Template(f.read()))
		self.template_extensions = ['java']

		# Create the mappings
		request_types_base = 'REQUEST_%s_%s'
		request_types_mapping = {
			'READ_OBJECT': Template(request_types_base % ('READ', '{{ name|upper }}')),
			'READ_LIST': Template(request_types_base % ('READ', '{{ name_plural|upper }}')),
			'CREATE': Template(request_types_base % ('CREATE', '{{ name|upper }}')),
			'UPDATE': Template(request_types_base % ('UPDATE', '{{ name|upper }}')),
			'DELETE': Template(request_types_base % ('DELETE', '{{ name|upper }}')),
			'READ_RELATED_LIST': Template(request_types_base % ('READ', '{{ parent_name|upper }}_{{ name_plural|upper }}')),
			'CREATE_RELATED': Template(request_types_base % ('CREATE', '{{ parent_name|upper }}_{{ name|upper }}')),
			'READ_RELATED_OBJECT': Template(request_types_base % ('READ', '{{ parent_name|upper }}_{{ name|upper }}')),
			'UPDATE_RELATED': Template(request_types_base % ('UPDATE', '{{ parent_name|upper }}_{{ name|upper }}')),
			'RemoveDuplicates': True,
			'Sort': True
		}

		urls_mapping = {}
		urls_mapping['READ_OBJECT'] = Template('public static final String URL_{{ name|upper }}{% if param %}_WITH_{{ param|upper }}{% endif %} = "{{ url_format }}";')
		urls_mapping['READ_LIST'] = urls_mapping['CREATE'] = Template('public static final String URL_{{ name_plural|upper }} = "{{ url_format }}";')
		urls_mapping['UPDATE'] = urls_mapping['DELETE'] = Template('public static final String URL_{{ name|upper }} = "{{ url_format }}";')
		urls_mapping['READ_RELATED_LIST'] = urls_mapping['CREATE_RELATED'] = Template('public static final String URL_{{ parent_name|upper }}_{{ name_plural|upper }}{% if param %}_WITH_{{ param|upper }}{% endif %} = "{{ url_format }}";')
		urls_mapping['READ_RELATED_OBJECT'] = urls_mapping['UPDATE_RELATED'] = Template('public static final String URL_{{ parent_name|upper }}_{{ name|upper }}{% if param %}_WITH_{{ param|upper }}{% endif %}  = "{{ url_format }}";')
		urls_mapping['RemoveDuplicates'] = True

		listener_method_decls_base = 'public void {{ app_name_lower }}ConnectionDid%s({{ app_name }}Connection connection, %s);'
		listener_method_decls_mapping = {
			'READ_OBJECT': Template(listener_method_decls_base % ('Read{{ name }}', '{{ name }} {{ name_lower }}')),
			'READ_LIST': Template(listener_method_decls_base % ('Read{{ name_plural }}', '{{ name }}[] {{ name_plural_lower }}')),
			'CREATE': Template(listener_method_decls_base % ('Create{{ name }}', '{{ name }} {{ name_lower }}')),
			'UPDATE': Template(listener_method_decls_base % ('Update{{ name }}', '{{ name }} {{ name_lower }}')),
			'DELETE': Template(listener_method_decls_base % ('Delete{{ name }}', '{{ name }} {{ name_lower }}')),
			'READ_RELATED_LIST': Template(listener_method_decls_base % ('Read{{ name_plural }}For{{ parent_name }}', '{{ name }}[] {{ name_plural_lower }}')),
			'CREATE_RELATED': Template(listener_method_decls_base % ('Create{{ name }}For{{ parent_name }}', '{{ name }} {{ name_lower }}')),
			'READ_RELATED_OBJECT': Template(listener_method_decls_base % ('Read{{ name }}For{{ parent_name }}', '{{ name }} {{ name_lower }}')),
			'UPDATE_RELATED': Template(listener_method_decls_base % ('Update{{ name }}For{{ parent_name }}', '{{ name }} {{ name_lower }}')),
			'RemoveDuplicates': True,
			'Sort': True
		}

		basic_listener_methods_base = 'public void {{ app_name_lower }}ConnectionDid%s({{ app_name }}Connection connection, %s) { Log.i(API.TAG, "{{ app_name }} did %s."); }'
		basic_listener_methods_mapping = {
			'READ_OBJECT': Template(basic_listener_methods_base % ('Read{{ name }}', '{{ name }} {{ name_lower }}', 'read {{ name_lower }}')),
			'READ_LIST': Template(basic_listener_methods_base % ('Read{{ name_plural }}', '{{ name }}[] {{ name_plural_lower }}', 'read " + Integer.toString({{ name_plural_lower }}.length) + " {{ name_plural_lower }}')),
			'CREATE': Template(basic_listener_methods_base % ('Create{{ name }}', '{{ name }} {{ name_lower }}', 'create {{ name_lower }}')),
			'UPDATE': Template(basic_listener_methods_base % ('Update{{ name }}', '{{ name }} {{ name_lower }}', 'update {{ name_lower }}')),
			'DELETE': Template(basic_listener_methods_base % ('Delete{{ name }}', '{{ name }} {{ name_lower }}', 'delete {{ name_lower }}')),
			'READ_RELATED_LIST': Template(basic_listener_methods_base % ('Read{{ name_plural }}For{{ parent_name }}', '{{ name }}[] {{ name_plural_lower }}', 'read " + Integer.toString({{ name_plural_lower }}.length) + " {{ name_plural_lower }} for {{ parent_name_lower }}')),
			'CREATE_RELATED': Template(basic_listener_methods_base % ('Create{{ name }}For{{ parent_name }}', '{{ name }} {{ name_lower }}', 'create {{ name_lower }} for {{ parent_name_lower }}')),
			'READ_RELATED_OBJECT': Template(basic_listener_methods_base % ('Read{{ name }}For{{ parent_name }}', '{{ name }} {{ name_lower }}', 'read {{ name_lower }} for {{ parent_name_lower }}')),
			'UPDATE_RELATED': Template(basic_listener_methods_base % ('Update{{ name }}For{{ parent_name }}', '{{ name }} {{ name_lower }}', 'update {{ name_lower }} for {{ parent_name_lower }}')),
			'RemoveDuplicates': True,
			'Sort': True
		}

		methods_mapping = {
			'READ_OBJECT': Template(READ_OBJECT_METHOD),
			'READ_LIST': Template(READ_LIST_METHOD),
			'CREATE': Template(CREATE_METHOD),
			'UPDATE': Template(UPDATE_METHOD),
			'DELETE': Template(DELETE_METHOD),
			'READ_RELATED_LIST': Template(READ_RELATED_LIST_METHOD),
			'CREATE_RELATED': Template(CREATE_RELATED_METHOD),
			'READ_RELATED_OBJECT': Template(READ_RELATED_OBJECT_METHOD),
			'UPDATE_RELATED': Template(UPDATE_RELATED_METHOD)
		}

		response_cases_mapping = {
			'READ_OBJECT': Template(READ_OBJECT_RESPONSE),
			'READ_LIST': Template(READ_LIST_RESPONSE),
			'CREATE': Template(CREATE_RESPONSE),
			'UPDATE': Template(UPDATE_RESPONSE),
			'DELETE': Template(DELETE_RESPONSE),
			'READ_RELATED_LIST': Template(READ_RELATED_LIST_RESPONSE),
			'CREATE_RELATED': Template(CREATE_RELATED_RESPONSE),
			'READ_RELATED_OBJECT': Template(READ_RELATED_OBJECT_RESPONSE),
			'UPDATE_RELATED': Template(UPDATE_RELATED_RESPONSE),
			'RemoveDuplicates': True
		}

		# Set the configuration options and render
		self.mappings = {'urls': urls_mapping, 'request_types': request_types_mapping, 'listener_method_decls': listener_method_decls_mapping, 'basic_listener_methods': basic_listener_methods_mapping, 'methods': methods_mapping, 'response_cases': response_cases_mapping}
		self.object_id_format = "%d"
		self.slug_format = "%s"
		self.object_id_type = "int"
		self.slug_type = "String"
		self.render(*args, **options)
