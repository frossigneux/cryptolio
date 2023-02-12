#! /bin/sh

BASEDIR=$( dirname `readlink -f $0` )
cd $BASEDIR/..

autoflake --remove-all-unused-imports --remove-unused-variables --remove-duplicate-keys \
  --recursive --in-place cryptolio

isort cryptolio

flake8 --ignore E203,E501,W503 cryptolio

black --line-length=100 \
  cryptolio \
  $@
