#!/bin/bash
# Local apt sources list
echo "deb http://mirrors.tuna.tsinghua.edu.cn/ubuntu/ xenial main restricted" > /etc/apt/sources.list
echo "deb http://mirrors.tuna.tsinghua.edu.cn/ubuntu/ xenial-updates main restricted" >> /etc/apt/sources.list
echo "deb http://mirrors.tuna.tsinghua.edu.cn/ubuntu/ xenial universe" >> /etc/apt/sources.list
echo "deb http://mirrors.tuna.tsinghua.edu.cn/ubuntu/ xenial-updates universe" >> /etc/apt/sources.list
echo "deb http://mirrors.tuna.tsinghua.edu.cn/ubuntu/ xenial multiverse" >> /etc/apt/sources.list
echo "deb http://mirrors.tuna.tsinghua.edu.cn/ubuntu/ xenial-updates multiverse" >> /etc/apt/sources.list
echo "deb http://mirrors.tuna.tsinghua.edu.cn/ubuntu/ xenial-backports main restricted universe multiverse" >> /etc/apt/sources.list
echo "deb http://mirrors.tuna.tsinghua.edu.cn/ubuntu/ xenial-security main restricted" >> /etc/apt/sources.list
echo "deb http://mirrors.tuna.tsinghua.edu.cn/ubuntu/ xenial-security universe" >> /etc/apt/sources.list
echo "deb http://mirrors.tuna.tsinghua.edu.cn/ubuntu/ xenial-security multiverse" >> /etc/apt/sources.list

apt-get update
apt-get install -y net-tools 
apt-get install -y wget 
apt-get install -y bzip2 
apt-get install -y unzip 
apt-get install -y libz-dev 
apt-get install -y libssh-dev 
apt-get install -y libnl-genl-3-dev 
apt-get install -y libnl-3-dev 
apt-get install -y git 
apt-get install -y libffi-dev 
apt-get install -y libffi6 
apt-get install -y iputils-ping 
apt-get install -y libxss1 
apt-get install -y libxss-dev 
apt-get install -y expect
apt-get install -y vim
apt-get install -y snmp

#BASE_URL="http://30.57.186.117/spytest"
BASE_URL="http://21.135.167.180:8888/spytest"

cd /tmp
# Download packages
wget $BASE_URL/ActivePython-2.7.18.0000-linux-x86_64-glibc-2.12-af4b3624.tar.gz
wget $BASE_URL/ActiveTcl-8.5.19.8519-x86_64-linux-glibc-2.5-403583.tar
wget $BASE_URL/IxNetworkAPI9.10.2007.7Linux64.bin.tgz
wget $BASE_URL/Ixia.tcl-fix.tcl
tar zxvf ActivePython-2.7.18.0000-linux-x86_64-glibc-2.12-af4b3624.tar.gz
tar zxvf ActiveTcl-8.5.19.8519-x86_64-linux-glibc-2.5-403583.tar
tar zxvf IxNetworkAPI9.10.2007.7Linux64.bin.tgz

# get autoexpect scripts to install above packages
wget $BASE_URL/ActivePython.exp
wget $BASE_URL/ActiveTcl.exp
wget $BASE_URL/IxNetworkAPI.exp
chmod +x *.exp

# Install ActivePython to /projects/scid/tools/ActivPython/2.7.18
./ActivePython.exp
cd /projects/scid/tools/ActivPython/ 
ln -s 2.7.18/ current

# Install ActiveTcl to /projects/scid/tools/ActivTcl/8.5.19
cd /tmp/
./ActiveTcl.exp
cd /projects/scid/tools/ActivTcl
ln -s 8.5.19/ current

# Install Ixia network to /projects/scid/tgen/ixia/all/ixia/ixnetwork/9.10.2007.7
cd /tmp/
./IxNetworkAPI.exp
cd /projects/scid/tgen/ixia/all/ixia/hlapi/
ln -s 9.10.2007.43/ 9.10
cd /projects/scid/tgen/ixia/all/ixia/ixnetwork/
ln -s 9.10.2007.7 9.10
cd /projects/scid/tgen/ixia/all/ixia/ixos-api/
ln -s 9.10.16.6/ 9.10

# Replace Ixia.tcl
cd /tmp/
mv Ixia.tcl-fix.tcl /projects/scid/tgen/ixia/all/ixia/hlapi/9.10.2007.43/Ixia.tcl

ln -s /usr/lib/x86_64-linux-gnu/libffi.so.6 /usr/lib/x86_64-linux-gnu/libffi.so.5

# https://github.com/HypothesisWorks/hypothesis/pull/2015/files
wget $BASE_URL/compat.patch
cd /projects/scid/tools/ActivPython/current/lib/python2.7/site-packages/hypothesis/internal/
patch -p1 < /tmp/compat.patch

cd /tmp/
rm *.gz *.tar *.tgz
