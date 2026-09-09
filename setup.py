# -*- coding:utf-8 -*-
from pathlib import Path

from setuptools import setup

BASE_DIR = Path(__file__).parent
README_PATH = BASE_DIR / "README.md"
INIT_FILE = BASE_DIR / "drissionpage_ai" / "__init__.py"


def read_version():
    namespace = {}
    for line in INIT_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            exec(line, namespace)
            return namespace["__version__"]
    raise RuntimeError("Cannot find __version__ in drissionpage_ai/__init__.py")


long_description = README_PATH.read_text(encoding="utf-8")

setup(
    name="drissionpage-ai",
    version=read_version(),
    author="Night-Master",
    author_email="Night-Master@users.noreply.github.com",
    description="AI-powered web automation based on DrissionPage: locate, extract and act with natural language.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="DrissionPage, AI, web automation, browser, agent, LLM",
    url="https://github.com/Night-Master/drissionpage-ai",
    packages=["drissionpage_ai"],
    zip_safe=False,
    install_requires=[
        'DrissionPage>=4.1.1.0',
        'openai',
        'openai-agents',
        'Pillow',
        'requests',
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
)
