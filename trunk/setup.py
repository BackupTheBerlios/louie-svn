from setuptools import setup, find_packages

version = '1.0b1'

setup(
    name='Louie',

    version=version,

    description="Signal dispatching mechanism",

    long_description="""\
Louie provides Python programmers with a straightforward way to
dispatch signals between objects in a wide variety of contexts. It is
based on PyDispatcher_, which in turn was based on a highly-rated
recipe_ in the Python Cookbook.

.. _PyDispatcher: http://pydispatcher.sf.net/

.. _recipe: http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/87056
""",

    classifiers=[
    'Intended Audience :: Developers',
    'License :: OSI Approved :: BSD License',
    'Programming Language :: Python',
    'Topic :: Software Development :: Libraries :: Python Modules',
    ],

    keywords='',

    author="Patrick K. O'Brien and contributors",

    author_email='louie-users@lists.berlios.de',

    url='http://louie.berlios.de/',

    license='BSD',

    packages=find_packages(exclude=['doc', 'ez_setup', 'examples', 'tests']),

    install_requires=[
    'nose >= 0.7.5',
    ],

    zip_safe=False,

    package_data={
    # -*- package_data: -*-
    },

    test_suite = 'nose.collector',

    )
      
