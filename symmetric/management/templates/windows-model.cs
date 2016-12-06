using System;
using System.Globalization;
using System.IO.IsolatedStorage;
using System.Net;
using System.Reflection;
using System.Runtime.Serialization;
using System.Text;
using System.Windows;
using System.Windows.Threading;

namespace {{ namespace }}
{
    [DataContract]
    class {{ name }}
    {% templatetag openbrace %}{% for property in properties %}
		{{ property }}{% endfor %}
    }
}
