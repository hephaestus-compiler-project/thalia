from setuptools import setup

setup(
    name='doc2json',
    version='1.0',
    scripts=['doc2json.py'],
    packages=['docparser'],
    install_requires=[
        # Add any dependencies required by your script
    ],
    entry_points={
        'console_scripts': [
            'doc2json=doc2json:main'
        ]
    },
)
