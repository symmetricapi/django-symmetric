package {{ package }};

import android.util.Log;

import com.symbiotic.api.API;
import com.symbiotic.api.APIRequestParams;
import com.symbiotic.api.APIURLConnection;

import java.util.ArrayList;

import org.json.JSONObject;
import org.json.JSONArray;

public final class {{ name }}Connection {
	public static final int REQUEST_NONE = 0;{% for request_type in request_types %}
	public static final int {{ request_type }} = {{ forloop.counter }};{% endfor %}
	{% for url in urls %}
	{{ url }}{% endfor %}

	public interface RequestListener {% templatetag openbrace %}{% for listener_method_decl in listener_method_decls %}
		{{ listener_method_decl }}{% endfor %}
		public void requestFailed({{ name }}Connection connection, String errorMessage);
	}

	// Base class to make implementing anonymous classes easier
	public static class BasicRequestListener implements RequestListener {% templatetag openbrace %}{% for basic_listener_method in basic_listener_methods %}
		{{ basic_listener_method }}{% endfor %}
		public void requestFailed({{ name }}Connection connection, String errorMessage) { Log.e(API.TAG, "{{ name }} connection failed with error: " + errorMessage); }
	}

	private static final String XHEADER_NEW_OBJECT_ID = "X-New-Object-Id";

	private RequestListener mListener;
	private APIRequestParams mRequestParams;
	private JSONObject mRequestData;
	private int mRequestType;
	private API.JSONSerializable mRequestObject;
	private int mAction;
	private APIURLConnection mConnection;
	private int mStatusCode;

	public {{ name }}Connection(RequestListener listener) {
		mListener = listener;
	}

	public void cancel() {
		if (mConnection != null) {
			mConnection.abort();
		}
		mRequestObject = null;
		mRequestType = REQUEST_NONE;
		mConnection = null;
		mStatusCode = 0;
	}

	public RequestListener getListener() {
		return mListener;
	}

	public APIRequestParams getRequestParams() {
		return mRequestParams;
	}

	public JSONObject getRequestData() {
		return mRequestData;
	}

	/** Special request data to include. This must be maintained manually it is not set to null upon completion or cancelation. */
	public void setRequestData(JSONObject data) {
		mRequestData = data;
	}

	public int getRequestType() {
		return mRequestType;
	}

	public int getStatusCode() {
		return mStatusCode;
	}

	private void performRequestWithObject(API.JSONSerializable obj, int action, int requestType, String path, boolean https, boolean login, boolean sign) {
		byte[] data = null;

		cancel();

		if (obj != null) {
			try {
				JSONObject jsonObject = obj.getJSONObject();
				if (mRequestData != null) {
					jsonObject.put("_data", requestData);
				}
				data = jsonObject.toString().getBytes();
			} catch(Exception e) {
				mListener.requestFailed(this, e.getMessage());
				return;
			}
		}
		mConnection = new APIURLConnection(action, path, mRequestParams, data, https, login, sign);
		mRequestObject = obj;
		mAction = action;
		mRequestType = requestType;

		Thread thread = new Thread(new Runnable() {
			public void run() {
				String response;
				JSONArray jsonArray;
				final Object responseObject;
				final Object[] responseArray;

				try {
					response = {{ name }}Connection.this.mConnection.execute();
					{{ name }}Connection.this.mStatusCode = {{ name }}Connection.this.mConnection.getResponseCode();
					if ({{ name }}Connection.this.mStatusCode >= 400) {
						final String error = new JSONObject(response).getString("message");
						if ({{ name }}Connection.this.mListener != null) {
							API.runOnUiThread(new Runnable() {
								public void run() { {{ name }}Connection.this.mListener.requestFailed({{ name }}Connection.this, error); }
							});
						}
					} else {
						switch ({{ name }}Connection.this.mRequestType) {
{% for response_case in response_cases %}{{ response_case }}
{% endfor %}
							default:
								break;
						}
					}
				} catch(Exception e) {
					if (!{{ name }}Connection.this.mConnection.isAborted()) {
						final String error;
						if (!API.isConnected()) {
							error = API.ERROR_NOINTERNET;
						} else {
							error = e.getMessage();
						}
						if ({{ name }}Connection.this.mListener != null) {
							API.runOnUiThread(new Runnable() {
								public void run() { {{ name }}Connection.this.mListener.requestFailed({{ name }}Connection.this, error); }
							});
						}
					}
				}
				{{ name }}Connection.this.mRequestType = REQUEST_NONE;
				{{ name }}Connection.this.mStatusCode = 0;
			}
		});
		thread.start();
	}
{% for method in methods %}
{{ method }}{% endfor %}

}
