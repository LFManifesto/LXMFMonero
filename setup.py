#!/usr/bin/env python3
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="reticulumxmr",
    version="0.1.0",
    author="Light Fighter Manifesto L.L.C.",
    author_email="contact@lightfightermanifesto.com",
    description="Monero transactions over Reticulum mesh networks",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/lfmanifesto/reticulumxmr",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Communications",
        "Topic :: Security :: Cryptography",
    ],
    python_requires=">=3.9",
    install_requires=[
        "rns>=0.7.0",
        "msgpack>=1.0.0",
        "requests>=2.25.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "reticulumxmr-hub=reticulumxmr.hub:main",
            "reticulumxmr-client=reticulumxmr.client:main",
            "reticulumxmr-tui=reticulumxmr.tui:main",
        ],
    },
)
