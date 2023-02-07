#!/bin/bash

BUILD_DIR=$(cd "$(dirname "$0")"; pwd)
BUILD_IMAGE=spytest-$USER
DOCKFILE=$BUILD_DIR/Dockerfile.spytest

# Check BUILD_IMAGE
docker inspect --type image $BUILD_IMAGE &> /dev/null

if [ $? -ne 0 ]; then
    echo "Build docker image $BUILD_IMAGE"
    echo "Docker build file is $DOCKFILE"
    docker build --force-rm --no-cache -t $BUILD_IMAGE -f $DOCKFILE $BUILD_DIR
    docker inspect --type image $BUILD_IMAGE &> /dev/null
    if [ $? -ne 0 ]; then
        echo "Build docker image $BUILD_IMAGE fail!"
        exit 1
    fi
fi

if [ -n "$TERM" ]; then
    TERMINAL=t
fi

docker run --rm=true --privileged \
           --net=host \
           -v $BUILD_DIR:/var/$USER/ \
           -v /var/spytest:/var/spytest \
           -w /var/$USER/ \
           -ti $BUILD_IMAGE:latest \
           bash
