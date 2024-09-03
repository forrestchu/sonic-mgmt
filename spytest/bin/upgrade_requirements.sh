#!/bin/sh

dir=$(dirname $0)

# sourde environment
. $dir/env

export CC=gcc
export CPP=cpp
export CXX=c++
export LIBS=
export LDSHARED="gcc -pthread -shared"
export PYMSSQL_BUILD_WITH_BUNDLED_FREETDS=1

$SPYTEST_PYTHON -m pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
$SPYTEST_PYTHON -m pip install -r $dir/requirements0.txt
#$SPYTEST_PYTHON -m pip install -r $dir/requirements1.txt

if [ -d $SCID_PYTHON_BIN ]; then
    $SPYTEST_PYTHON -m compileall $SCID_PYTHON_BIN/..
    chmod -R go+r $SCID_PYTHON_BIN/..
fi

