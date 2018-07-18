package {{ package }};

import android.os.Parcel;
import android.os.Parcelable;
import android.util.Log;

import java.io.Externalizable;
import java.io.IOException;
import java.io.ObjectInput;
import java.io.ObjectOutput;
{% if has_date %}import java.util.Date;
{% endif %}
import org.json.JSONException;
import org.json.JSONObject;
import org.json.JSONArray;

import com.symbiotic.api.API;

public class {{ name }} {% if base_name %}extends {{ base_name }} {% endif %}implements API.JSONSerializable, Parcelable, Externalizable {
	static final long serialVersionUID = {{ uid }}L;
	{% for ivar_stmt in ivars %}
	{{ ivar_stmt }}{% endfor %}

	/** Default empty constructor. */
	public {{ name }}() {}

	/** Constructor to create a {{ name }} from a JSON response. */
	public {{ name }}(JSONObject jsonObject)
	{% templatetag openbrace %}{% if base_name %}
		super(jsonObject);{% endif %}
		if (jsonObject != null) {% templatetag openbrace %}{% for read_json_stmt in read_json %}
			{{ read_json_stmt }}{% endfor %}
		}
	}

	/** Convert this instance to a JSONObject. */
	public JSONObject getJSONObject() {
		JSONObject jsonObject = {% if base_name %}super.getJSONObject();{% else %}new JSONObject();{% endif %}
		try {% templatetag openbrace %}{% for write_json_stmt in write_json %}
			{{ write_json_stmt }}{% empty %}throw new JSONException("Empty");{% endfor %}
		} catch(JSONException e) { }
		return jsonObject;
	}

	/** Constructor to create a {{ name }} from a Parcel */
	@SuppressWarnings("unchecked")
	private {{ name }}(Parcel in) {% templatetag openbrace %}{% if base_name %}
		super(in);{% endif %}
		try {% templatetag openbrace %}{% for read_parcel_stmt in read_parcel %}
			{{ read_parcel_stmt }}{% endfor %}
		}
		catch(Exception e) { Log.e("{{ package }}", Log.getStackTraceString(e)); }
	}
{% if primary_field %}
	public int getObjectId() {
		return {{ primary_field }};
	}

	public void setObjectId(int id) {
		this.{{ primary_field }} = id;
	}

	public boolean equals(Object other) {
		if (this == other) return true;
		if (!(other instanceof {{ name }})) return false;
		{{ name }} other{{ name }} = ({{ name }})other;
		return this.{{ primary_field }} == other{{ name }}.{{ primary_field }};
	}
{% endif %}{% if property_implementations %}{% for property_impl in property_implementations %}
{{ property_impl }}{% endfor %}{% endif %}
	/** Implementation of the Parcelable method describeContents. */
	@Override
	public int describeContents() {
		return 0;
	}

	/** Implementation of the Parcelable method writeToParcel. */
	@Override
	public void writeToParcel(Parcel dest, int flags) {% templatetag openbrace %}{% if base_name %}
		super.writeToParcel(dest, flags);{% endif %}{% for write_parcel_stmt in write_parcel %}
		{{ write_parcel_stmt }}{% endfor %}
	}

	/** Object that is used to regenerate the object. All Parcelables must have a CREATOR that implements these two methods. */
	public static final Parcelable.Creator<{{ name }}> CREATOR = new Parcelable.Creator<{{ name }}>() {
		public {{ name }} createFromParcel(Parcel in) {
			return new {{ name }}(in);
		}

		public {{ name }}[] newArray(int size) {
			return new {{ name }}[size];
		}
	};

	public void readExternal(ObjectInput input) throws IOException, ClassNotFoundException {% templatetag openbrace %}{% if base_name %}
		super.readExternal(input);{% endif %}{% for read_external_stmt in read_external %}
		{{ read_external_stmt }}{% endfor %}
	}

	public void writeExternal(ObjectOutput output) throws IOException {% templatetag openbrace %}{% if base_name %}
		super.writeExternal(output);{% endif %}{% for write_external_stmt in write_external %}
		{{ write_external_stmt }}{% endfor %}
	}
}
