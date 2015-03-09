from setuptools import setup, find_packages


setup(
    name='frasco-models',
    version='0.1',
    url='http://github.com/frascoweb/frasco-models',
    license='MIT',
    author='Maxime Bouroumeau-Fuseau',
    author_email='maxime.bouroumeau@gmail.com',
    description="ORM for Frasco",
    packages=find_packages(),
    zip_safe=False,
    platforms='any',
    install_requires=[
        'frasco',
        'persistpy',
        'inflection',
        'flask-mongoengine>=0.7'
    ]
)