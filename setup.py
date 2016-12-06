from setuptools import setup, find_packages

setup(
	name='django-symmetric',
	version='0.0.1',
	description='RESTful Django API views to ease automation of creating symmetric client-side code.',
	url='https://github.com/symmetricapi/django-symmetric',
	author='mvx24',
	author_email='cram2400@gmail.com',
	license='MIT',
	classifiers=[
		'Development Status :: 3 - Alpha',
		'Environment :: Console',
		'Framework :: Django',
		'License :: OSI Approved :: MIT License',
		'Operating System :: MacOS :: MacOS X',
		'Operating System :: POSIX',
		'Operating System :: Unix',
		'Programming Language :: Python :: 2.7',
		'Programming Language :: Python :: 2 :: Only',
		'Topic :: Database',
		'Topic :: Software Development :: Code Generators',
		'Topic :: Software Development :: Libraries :: Python Modules'
	],
	keywords='django restful api views backbone java android ios',
	packages=find_packages(exclude=['tests']),
	install_requires=['django'],
	package_data={
		'': ['management/templates/*']
	}
)
