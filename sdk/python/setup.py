from setuptools import find_packages, setup

setup(
    name="aetherdesk",
    version="0.1.0",
    description="AetherDesk Call Center Platform SDK",
    packages=find_packages(),
    install_requires=["httpx>=0.24.0"],
    python_requires=">=3.9",
)
