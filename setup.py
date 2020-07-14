import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="example-pkg-YOUR-USERNAME-HERE", # Replace with your own username
    version="1.0.0",
    author="Goheeca",
    author_email="goheeca@gmail.com",
    description="Python library for speech to text using NanoTrix cloud",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/tzolkincz/ntx-python",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)