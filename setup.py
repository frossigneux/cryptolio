from distutils.core import setup

setup(
    name='cryptolio',
    packages=['cryptolio'],
    version='0.0.1',
    description='Cryptocurrency portfolio rebalancing',
    author='François Rossigneux',
    author_email='francois.rossigneux@gmail.com',
    keywords=['cryptocurrency', 'portfolio', 'rebalancing'],
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Financial and Insurance Industry',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: OS Independent',
        'Topic :: Office/Business :: Financial :: Investment',
    ],
    install_requires=[
        'click',
        'python-coinmarketcap',
        'ccxt',
        'lxml',
        'matplotlib',
        'semidbm',
    ],
    entry_points={
        'console_scripts': [
            'cryptolio-rebalancing = cryptolio.rebalancing:main',
            'cryptolio-backtest = cryptolio.backtest:main'
        ]
    },
    long_description="""\
Cryptocurrency portfolio rebalancing
------------------------------------

The rebalancing strategy is based on the Crypto20 whitepaper:
https://cdn.crypto20.com/pdf/c20-whitepaper.pdf
"""
)
