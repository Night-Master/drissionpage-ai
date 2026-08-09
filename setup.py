# -*- coding:utf-8 -*-
from pathlib import Path

from setuptools import setup, find_packages

BASE_DIR = Path(__file__).parent
README_PATH = BASE_DIR / "README.md"
VERSION_FILE = BASE_DIR / "DrissionPage" / "version.py"


def read_version():
    namespace = {}
    exec(VERSION_FILE.read_text(encoding="utf-8"), namespace)
    return namespace["__version__"]


long_description = README_PATH.read_text(encoding="utf-8")

setup(
    name="drissionpage-ai",
    version=read_version(),
    author="Night-Master",
    author_email="you@example.com",  # TODO: 改成你的邮箱
    description="AI-powered web automation based on DrissionPage: locate, extract and act with natural language.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="DrissionPage, AI, web automation, browser, agent, LLM",
    url="https://github.com/Night-Master/drissionpage-ai",
    include_package_data=True,
    packages=find_packages(),
    package_data={
        "DrissionPage": ["*.pyi"],
        "DrissionPage._ai": ["*.pyi"],
        "DrissionPage._base": ["*.pyi"],
        "DrissionPage._configs": ["*.pyi", "configs.ini"],
        "DrissionPage._elements": ["*.pyi"],
        "DrissionPage._functions": ["*.pyi", "suffixes.dat"],
        "DrissionPage._pages": ["*.pyi"],
        "DrissionPage._units": ["*.pyi"],
    },
    zip_safe=False,
    install_requires=[
        'lxml',
        'requests',
        'openai',
        'openai-agents',
        'Pillow',
        'cssselect',
        'DownloadKit>=2.0.7',
        'websocket-client',
        'click',
        'tldextract>=3.4.4',
        'psutil'
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Development Status :: 4 - Beta",
        "Topic :: Utilities",
        "Topic :: Software Development :: Testing",
    ],
    python_requires='>=3.10',
    entry_points={
        'console_scripts': [
            'dp = DrissionPage._functions.cli:main',
        ],
    },
)
