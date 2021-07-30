from setuptools import setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name='leo-gmi',
    version='1.1.1',
    scripts=['leo'],
    author='shantaram',
    author_email='me@shantaram.xyz',
    license='MIT',
    description='A terminal-based client for the Gemini protocol.',
    long_description=long_description,
    url="https://github.com/xyzshantaram/leo",
    project_urls={
        "Bug Tracker": "https://github.com/xyzshantaram/leo",
        "README": "https://github.com/xyzshantaram/leo#readme"
    },
    long_description_content_type='text/markdown',
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Development Status :: 4 - Beta"
    ],
    keywords='leo gemini gopher http fediverse internet protocol www client',
)