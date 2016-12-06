package {{ package }};

import android.util.Log;

import com.symbiotic.api.API;
import com.symbiotic.api.APIRequestParams;
import com.symbiotic.api.APIURLConnection;

import java.util.ArrayList;

import org.json.JSONObject;
import org.json.JSONArray;

public final class {{ name }}Connection
{
	public static final int REQUEST_NONE = 0;{% for request_type in request_types %}
	public static final int {{ request_type }} = {{ forloop.counter }};{% endfor %}
	{% for url in urls %}
	{{ url }}{% endfor %}

	public interface RequestListener
	{% templatetag openbrace %}{% for listener_method_decl in listener_method_decls %}
		{{ listener_method_decl }}{% endfor %}
		public void requestFailed({{ name }}Connection connection, String errorMessage);
	}

	// Base class to make implementing anonymous classes easier
	public static class BasicRequestListener implements RequestListener
	{% templatetag openbrace %}{% for basic_listener_method in basic_listener_methods %}
		{{ basic_listener_method }}{% endfor %}
		public void requestFailed({{ name }}Connection connection, String errorMessage) { Log.e(API.TAG, "{{ name }} connection failed with error: " + errorMessage); }
	}

	private static final String XHEADER_NEW_OBJECT_ID = "X-New-Object-Id";

	private RequestListener listener;
	private APIRequestParams requestParams;
	private JSONObject requestData;
	private int requestType;
	private API.JSONSerializable requestObject;
	private int action;
	private APIURLConnection connection;
	private int statusCode;

	public {{ name }}Connection(RequestListener listener)
	{
		this.listener = listener;
	}

	public void cancel()
	{
		if(this.connection != null)
			this.connection.abort();
		this.requestObject = null;
		this.requestType = REQUEST_NONE;
		this.connection = null;
		this.statusCode = 0;
	}

	public RequestListener getListener()
	{
		return this.listener;
	}

	public APIRequestParams getRequestParams()
	{
		return this.requestParams;
	}

	public JSONObject getRequestData()
	{
		return this.requestData;
	}

	/** Special request data to include. This must be maintained manually it is not set to null upon completion or cancelation. */
	public void setRequestData(JSONObject data)
	{
		this.requestData = data;
	}

	public int getRequestType()
	{
		return this.requestType;
	}

	public int getStatusCode()
	{
		return this.statusCode;
	}

	private void performRequestWithObject(API.JSONSerializable obj, int action, int requestType, String path, boolean https, boolean login, boolean sign)
	{
		byte[] data = null;

		this.cancel();

		if(obj != null)
		{
			try
			{
				JSONObject jsonObject = obj.getJSONObject();
				if(this.requestData != null)
					jsonObject.put("_data", requestData);
				data = jsonObject.toString().getBytes();
			}
			catch(Exception e)
			{
				this.listener.requestFailed(this, e.getMessage());
				return;
			}
		}
		this.connection = new APIURLConnection(action, path, this.requestParams, data, https, login, sign);
		this.requestObject = obj;
		this.action = action;
		this.requestType = requestType;

		Thread thread = new Thread(new Runnable() {
			public void run()
			{
				String response;
				JSONArray jsonArray;
				final Object responseObject;
				final Object[] responseArray;

				try
				{
					response = {{ name }}Connection.this.connection.execute();
					{{ name }}Connection.this.statusCode = {{ name }}Connection.this.connection.getResponseCode();
					if({{ name }}Connection.this.statusCode >= 400)
					{
						final String error = new JSONObject(response).getString("message");
						if({{ name }}Connection.this.listener != null)
							API.runOnUiThread(new Runnable() { public void run() { {{ name }}Connection.this.listener.requestFailed({{ name }}Connection.this, error); } });
					}
					else
					{
						switch({{ name }}Connection.this.requestType)
						{
{% for response_case in response_cases %}{{ response_case }}
{% endfor %}
							default:
								break;
						}
					}
				}
				catch(Exception e)
				{
					if(!{{ name }}Connection.this.connection.isAborted())
					{
						final String error;
						if(!API.isConnected())
							error = API.ERROR_NOINTERNET;
						else
							error = e.getMessage();
						if({{ name }}Connection.this.listener != null)
							API.runOnUiThread(new Runnable() { public void run() { {{ name }}Connection.this.listener.requestFailed({{ name }}Connection.this, error); } });
					}
				}
				{{ name }}Connection.this.requestType = REQUEST_NONE;
				{{ name }}Connection.this.statusCode = 0;
			}
		});
		thread.start();
	}
{% for method in methods %}
{{ method }}{% endfor %}

}
