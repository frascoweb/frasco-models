from setuptools import setup, find_packages


def desc():
    with open("README.md") as f:
        return f.read()

def reqs():
    with open('requirements.txt') as f:
        return f.read().splitlines()

setup(
    name='frasco-models',
    version='0.1',
    url='http://github.com/frascoweb/frasco-models',
    license='MIT',
    author='Maxime Bouroumeau-Fuseau',
    author_email='maxime.bouroumeau@gmail.com',
    description="ORM for Frasco",
    long_description=desc(),
    packages=find_packages(),
    platforms='any',
    install_requires=reqs() + [
        'frasco',
        'persistpy'
    ]
)