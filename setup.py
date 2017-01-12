from setuptools import setup, find_packages


setup(
    name='frasco-models',
    version='0.5.3',
    url='http://github.com/frascoweb/frasco-models',
    license='MIT',
    author='Maxime Bouroumeau-Fuseau',
    author_email='maxime.bouroumeau@gmail.com',
    description="ORM for Frasco",
    packages=find_packages(),
    package_data={
        'frasco_models': [
            'admin/templates/admin/models_default/*.html',
            '*.html']
    },
    zip_safe=False,
    platforms='any',
    install_requires=[
        'frasco',
        'inflection'
    ]
)
