import os
from setuptools import setup, find_packages

this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="memloop",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "chromadb",
        "sentence-transformers",
        "beautifulsoup4",
        "requests",
        "pypdf",
    ],
    entry_points={
        "console_scripts": [
            "memloop=memloop.cli:main",
        ],
    },
    author="Vansh",
    author_email="vanshgoyal9528@gmail.com",  
    description="A local-first, dual-memory engine for AI Agents.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/vanshcodeworks/memloop",  
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.8",
)
