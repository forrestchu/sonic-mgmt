import os
import copy
import pytest
import json
import difflib
import string
import random
from utilities import parallel

from spytest import st, tgapi, SpyTestDict
from spytest.utils import filter_and_select
from utilities.utils import retry_api

import apis.common.asic as asicapi
import apis.switching.vlan as vapi
import apis.routing.ip as ipfeature
import apis.switching.mac as macapi
import apis.system.reboot as reboot
import apis.system.port as papi
import apis.system.interface as intfapi
import apis.routing.bgp as bgp_api
import apis.routing.arp as arp_obj
import apis.routing.bfd as bfdapi
import apis.routing.ip_bgp as ip_bgp
from apis.common import redis

from sbfd_vars import data

## check config db 
def configdb_onefield_checkpoint(dut, key, checkfield, checkval, expect = True, checkpoint = ''):
    command = redis.build(dut, redis.CONFIG_DB, 'hget "{}" "{}"'.format(key, checkfield))
    output = st.show(dut, command, skip_tmpl=True)
    if output is '':
        st.report_fail("{} confg DB has no right filed {}".format(checkpoint, checkfield))

    output = output.strip('"')
    last_pos = output.rfind('"')
    output = output[:last_pos]
    st.log(output)
    st.log(checkval)
    check = (checkval == output)
    st.log(check)

    if expect is not check:
        st.report_fail("{} confg DB has no right {} config".format(checkpoint, checkfield))

## check config db
def configdb_checkarray(dut, key, checkfield, checkval, expect = True, checkpoint = ''):
    command = redis.build(dut, redis.CONFIG_DB, 'hgetall "{}"'.format(key))
    output = st.show(dut, command)
    st.log(output)

    redis_cfg_checkpoint = False
    exist = False
    for i in range(len(output)):
        if output[i].get('donor_intf') == checkfield:
            exist = True
            if i+1 < len(output):
                vals = output[i+1].get('donor_intf').split(",")
                if checkval in vals:
                    redis_cfg_checkpoint = True

    if redis_cfg_checkpoint != expect:
        st.report_fail("{} confg DB has no right {} config".format(checkpoint, checkfield))

def appdb_checkpoint(dut, key, checkfield, checkval, expect = True, checkpoint = ''):
    command = redis.build(dut, redis.APPL_DB, 'hgetall "{}"'.format(key))
    output = st.show(dut, command)
    st.log(output)

    redis_cfg_checkpoint = False
    exist = False
    redis_cfg_exist_checkpoint = False if exist else True
    for i in range(len(output)):
        if output[i].get('donor_intf') == checkfield:
            exist = True
            if i+1 < len(output):
                if output[i+1].get('donor_intf') == checkval:
                    redis_cfg_checkpoint = True
            
    if checkval == 'null':
        redis_cfg_exist_checkpoint = False if exist else True
        if redis_cfg_exist_checkpoint != expect:
            st.report_fail("{} confg DB has {} config".format(checkpoint, checkfield))  
    else:
        if redis_cfg_checkpoint != expect:
            st.report_fail("{} confg DB has no right {} config".format(checkpoint, checkfield))

def appdb_onefield_checkpoint(dut, key, checkfield, checkval, expect = True, checkpoint = ''):
    command = redis.build(dut, redis.APPL_DB, 'hget "{}" "{}"'.format(key, checkfield))
    output = st.show(dut, command, skip_tmpl=True)
    if output is '':
        st.report_fail("{} app DB has no right filed {}".format(checkpoint, checkfield))

    output = output.strip('"')
    last_pos = output.rfind('"')
    output = output[:last_pos]
    st.log(output)
    st.log(checkval)
    check = (checkval == output)
    st.log(check)

    if expect is not check:
        st.report_fail("{} app DB has no right {} config".format(checkpoint, checkfield))

def appdb_get_onefield(dut, key, field):
    command = redis.build(dut, redis.APPL_DB, 'hget "{}" "{}"'.format(key, field))
    output = st.show(dut, command, skip_tmpl=True)
    if output is '':
        return None

    output = output.strip('"')
    last_pos = output.rfind('"')
    output = output[:last_pos]
    st.log(output)
    return output

def show_hw_route_count(dut):
    def_v4_route_count = asicapi.get_ipv4_route_count(dut)
    st.log("{} v4 route : {}".format(dut, def_v4_route_count))
    def_v6_route_count = asicapi.get_ipv6_route_count(dut)
    st.log("{} v6 route : {}".format(dut, def_v6_route_count))