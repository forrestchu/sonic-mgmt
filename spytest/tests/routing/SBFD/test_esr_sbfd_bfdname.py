import os
import pytest
import sys
import json
import netaddr
import time,datetime
from collections import OrderedDict
from utilities import parallel
import apis.routing.bgp as bgpfeature

from spytest import st, tgapi, SpyTestDict
from spytest.utils import filter_and_select
from utilities.utils import retry_api

import apis.common.asic as asicapi
import apis.routing.ip as ipfeature
import apis.system.reboot as reboot
import apis.system.port as papi
import apis.system.interface as intfapi
import apis.routing.bgp as bgp_api
import apis.routing.arp as arp_obj
import apis.routing.bfd as bfdapi
import apis.routing.ip_bgp as ip_bgp
from apis.common import redis
from sbfd_lib import *
from sbfd_vars import data
from apis.common.ixia_helper import *

#
#            +-------------------+                 +-------------------+
# TG1_1====  |                    |                |                    |
#            |                    |                |                    |
# TG1_2====  |                    |                |                    |=====TG2_1
#            |DUT1(21.135.163.58) | ===========    |DUT2(21.135.163.59) |
#            |                    |                |                    |=====TG2_2
# TG1_3====  |                    |                |                    |
#            |                    |                |                    |
# TG1_4====  |                    |                |                    |
#            +-------------------+                  +-------------------+


#data = SpyTestDict()

data.srv6 = {}

dut1 = 'MC-58'
dut2 = 'MC-59'
data.my_dut_list = [dut1, dut2]
data.load_basic_config_done = False
data.load_static_config_done = False
data.current_discr = 0

def load_json_config(filesuffix=''):
    curr_path = os.getcwd()

    json_file_dut1_multi_vrf = curr_path+"/routing/SBFD/dut1_"+filesuffix+".json"
    json_file_dut2_multi_vrf = curr_path+"/routing/SBFD/dut2_"+filesuffix+".json"

    st.apply_files(dut1, [json_file_dut1_multi_vrf], method="replace_configdb")
    st.apply_files(dut2, [json_file_dut2_multi_vrf], method="replace_configdb")

    st.wait(10)
    st.reboot([dut1, dut2])
    st.banner("%s json config loaded completed" % (filesuffix))

def show_appdb_table_info(dut, table):
    key = 'empty array'
    command = redis.build(dut, redis.APPL_DB, 'keys "{}"'.format(table))
    output = st.show(dut, command, skip_tmpl=True)
    if key in output:
        return
    else:
        st.log(output)
        st.report_fail("{} app DB has {}".format(dut, table))

def get_bfd_uptime_sec(output):
    uptime = 0
    uptime_day = 0
    uptime_hour = 0
    uptime_min = 0
    uptime_sec = 0
    if 'status' in output and output['status'] == 'up':
        uptime_day = 0 if output.get('uptimeday') == '' else int(output.get('uptimeday'))
        uptime_hour= 0 if output.get('uptimehr') == '' else int(output.get('uptimehr'))
        uptime_min= 0 if output.get('uptimemin') == '' else int(output.get('uptimemin'))
        uptime_sec= 0 if output.get('uptimesec') == '' else int(output.get('uptimesec'))
        uptime =  uptime_day * 86400 +  uptime_hour * 3600 + uptime_min * 60 + uptime_sec
    st.log("get bfd uptime {} , day {}, hour {}, min {}, sec {}".format(uptime, uptime_day, uptime_hour, uptime_min, uptime_sec))
    return uptime

def double_check_bfd_session(dut, bfd_session_key, bfd_session_check_field, offload=True, delete=False):
    # show bfd peers | grep 'peer 192.20.1.59 name BFD_SINGLE_V4_VRF mode bfd local-address 192.20.1.58 vrf Test1 interface PortChannel101' -A 20
    create_by_hardware = False
    bfd_status = ''
    cmd = 'cli -c "no page" -c "show bfd peers" | grep {} -A 21'.format('"'+bfd_session_key+'"')
    output = st.show(dut, cmd)
    st.log (output)
    if type(output) != list:
        st.log ("output is not list type")
        return False

    if len(output)>0:
        output = output[0]
    st.log (output)

    if delete:
        if len(output) == 0:
            return True
        if output.get('peer', '') == '':
            return True
        else:
            return False

    uptime1 = get_bfd_uptime_sec(output)
    st.log (bfd_session_check_field)
    for field, val in bfd_session_check_field.items():
        st.log (field)
        st.log (val)
        if field == 'status':
            bfd_status = val
        if field in output :
            if type(output[field]) == list:
                checkval = output[field][0]
            else:
                checkval = output[field]
            if val != checkval:
                st.log("{} 's {} is not match, expect {} actual {}".format(bfd_session_key, field, val, checkval))
                return False

    st.wait(10)

    output = st.show(dut, cmd)
    if type(output) == list and len(output)>0:
        output = output[0]
    st.log (output)
    uptime2 = get_bfd_uptime_sec(output)
    for field, val in bfd_session_check_field.items():
        if field in output :
            if type(output[field]) == list:
                checkval = output[field][0]
            else:
                checkval = output[field]
            if val != checkval:
                st.log("{} 's {} is not match, expect {} actual {}".format(bfd_session_key, field, val, checkval))
                return False
    
    if bfd_status == 'up':
        if uptime2 - uptime1 < 10:
            st.log("{} not up continuously".format(bfd_session_key))
            return False
        
        if 'local_id' in output:
            data.current_discr = output['local_id']
        
        if 'hardware' in output:
            if output['hardware'] == 'hardware':
                create_by_hardware = True
        
        # show bfd peers counters | grep 'peer 20.20.20.58 p(endpoint 20.20.20.58 color 1 sidlist sl1_ipv4) local-address 20.20.20.58' -A 7
        count_cmd = 'cli -c "no page" -c "show bfd peers counters" | grep {} -A 7'.format('"'+bfd_session_key+'"')
        output = st.show(dut, count_cmd)
        if type(output) == list and len(output)>0:
            output = output[0]
        st.log (output)

        if offload:
            # check appdb ,check hardware flag
            if create_by_hardware == False:
                st.log("{} not offload".format(bfd_session_key))
                return False

    return True

def save_config_and_reboot(dut):
    cmd = 'cli -c "config t" -c "copy running-config startup-config"'
    st.config(dut, cmd)
    st.log("start reboot")
    st.reboot(dut)
    st.wait(5) 
    st.log("finish reboot")

def learn_arp_by_ping():
    st.config(dut1, 'ping -c2 192.10.1.59')
    st.config(dut1, 'ping -c2 192.20.1.59 -I PortChannel101')
    st.config(dut1, 'ping -c2 192.30.1.59')
    st.config(dut1, 'ping -c2 192.40.1.59 -I PortChannel103')
    st.config(dut1, 'ping -c2 fd00:100::59')
    st.config(dut1, 'ping -c2 fd00:200::59 -I PortChannel101')
    st.config(dut1, 'ping -c2 fd00:300::59')
    st.config(dut1, 'ping -c2 fd00:400::59 -I PortChannel103')
    st.config(dut1, 'ping -c2 20.20.20.59')
    st.config(dut1, 'ping -c2 2000::59')
    st.config(dut1, 'ping -c2 30.30.30.59 -I PortChannel101')
    st.config(dut1, 'ping -c2 3000::59 -I PortChannel101')

    st.config(dut2, 'ping -c2 192.10.1.58')
    st.config(dut2, 'ping -c2 192.20.1.58 -I PortChannel101')
    st.config(dut2, 'ping -c2 192.30.1.58')
    st.config(dut2, 'ping -c2 192.40.1.58 -I PortChannel103')
    st.config(dut2, 'ping -c2 fd00:100::58')
    st.config(dut2, 'ping -c2 fd00:200::58 -I PortChannel101')
    st.config(dut2, 'ping -c2 fd00:300::58')
    st.config(dut2, 'ping -c2 fd00:400::58 -I PortChannel103')
    st.config(dut2, 'ping -c2 20.20.20.58')
    st.config(dut2, 'ping -c2 2000::58')
    st.config(dut2, 'ping -c2 30.30.30.58 -I PortChannel101')
    st.config(dut2, 'ping -c2 3000::58 -I PortChannel101')

# init api
def check_bfd_session_configdb(bfd_mode, configdb_key, default, checkpoint):
    if bfd_mode == 'bfd-single-v4':
        if configdb_key == 'BFD_PEER|BFD_SINGLE_V4_DEFAULT':
            configdb_onefield_checkpoint(dut1, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "interface", "PortChannel100", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "multihop", "false", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "peer", "192.10.1.59", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "enabled", "true", True, checkpoint)

            configdb_onefield_checkpoint(dut2, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "interface", "PortChannel100", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "multihop", "false", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "peer", "192.10.1.58", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "enabled", "true", True, checkpoint) 
        elif configdb_key == 'BFD_PEER|BFD_SINGLE_V4_VRF':
            configdb_onefield_checkpoint(dut1, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "interface", "PortChannel101", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "multihop", "false", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "peer", "192.20.1.59", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "enabled", "true", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "vrf", "Test1", True, checkpoint)

            configdb_onefield_checkpoint(dut2, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "interface", "PortChannel101", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "multihop", "false", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "peer", "192.20.1.58", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "enabled", "true", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "vrf", "Test1", True, checkpoint)

    elif bfd_mode == 'bfd-single-v6': 
        if configdb_key == 'BFD_PEER|BFD_SINGLE_V6_DEFAULT':
            configdb_onefield_checkpoint(dut1, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "interface", "PortChannel100", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "multihop", "false", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "peer", "fd00:100::59", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "enabled", "true", True, checkpoint)

            configdb_onefield_checkpoint(dut2, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "interface", "PortChannel100", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "multihop", "false", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "peer", "fd00:100::58", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "enabled", "true", True, checkpoint) 

        elif configdb_key == 'BFD_PEER|BFD_SINGLE_V6_VRF':
            configdb_onefield_checkpoint(dut1, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "interface", "PortChannel101", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "multihop", "false", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "peer", "fd00:200::59", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "enabled", "true", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "vrf", "Test1", True, checkpoint)

            configdb_onefield_checkpoint(dut2, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "interface", "PortChannel101", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "multihop", "false", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "peer", "fd00:200::58", True, checkpoint)
            #configdb_onefield_checkpoint(dut2, configdb_key, "enabled", "true", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "vrf", "Test1", True, checkpoint)

    elif bfd_mode == 'bfd-multi-v4': 
        if configdb_key == 'BFD_PEER|BFD_MULTI_V4_DEFAULT':
            configdb_onefield_checkpoint(dut1, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "local-address", "192.30.1.58", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "multihop", "true", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "peer", "192.30.1.59", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "enabled", "true", True, checkpoint)

            configdb_onefield_checkpoint(dut2, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "local-address", "192.30.1.59", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "multihop", "true", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "peer", "192.30.1.58", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "enabled", "true", True, checkpoint)

        elif configdb_key == 'BFD_PEER|BFD_MULTI_V4_VRF':
            configdb_onefield_checkpoint(dut1, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "local-address", "192.40.1.58", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "multihop", "true", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "peer", "192.40.1.59", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "enabled", "true", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "vrf", "Test1", True, checkpoint)  

            configdb_onefield_checkpoint(dut2, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "local-address", "192.40.1.59", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "multihop", "true", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "peer", "192.40.1.58", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "enabled", "true", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "vrf", "Test1", True, checkpoint)  

    elif bfd_mode == 'bfd-multi-v6': 
        if configdb_key == 'BFD_PEER|BFD_MULTI_V6_DEFAULT':
            configdb_onefield_checkpoint(dut1, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "local-address", "fd00:300::58", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "multihop", "true", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "peer", "fd00:300::59", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "enabled", "true", True, checkpoint)

            configdb_onefield_checkpoint(dut2, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "local-address", "fd00:300::59", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "multihop", "true", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "peer", "fd00:300::58", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "enabled", "true", True, checkpoint)

        elif configdb_key == 'BFD_PEER|BFD_MULTI_V6_VRF':
            configdb_onefield_checkpoint(dut1, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "local-address", "fd00:400::58", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "multihop", "true", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "peer", "fd00:400::59", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "enabled", "true", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "vrf", "Test1", True, checkpoint)

            configdb_onefield_checkpoint(dut2, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "local-address", "fd00:400::59", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "multihop", "true", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "peer", "fd00:400::58", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "enabled", "true", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "vrf", "Test1", True, checkpoint)

    elif bfd_mode == 'sbfd-echo-v4':
            configdb_onefield_checkpoint(dut1, configdb_key, "mode", "sbfd-echo", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "segment-list", "fd00:303:2022:fff1:eee::", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "source-ipv6", "2000::58", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "local-address", "20.20.20.58", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "multihop", "false", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "peer", "20.20.20.58", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "enabled", "true", True, checkpoint)
    elif bfd_mode == 'sbfd-echo-v6':
            configdb_onefield_checkpoint(dut1, configdb_key, "mode", "sbfd-echo", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "segment-list", "fd00:303:2022:fff1:eee::", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "source-ipv6", "2000::58", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "local-address", "2000::58", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "multihop", "false", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "peer", "2000::58", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "enabled", "true", True, checkpoint)
    elif bfd_mode == 'sbfd-init-v4':
            configdb_onefield_checkpoint(dut1, configdb_key, "mode", "sbfd", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "segment-list", "fd00:303:2022:fff1:eee::", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "source-ipv6", "2000::58", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "remote-discr", "10086", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "local-address", "20.20.20.58", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "multihop", "false", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "peer", "20.20.20.59", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "enabled", "true", True, checkpoint)
    elif bfd_mode == 'sbfd-init-v6':
            configdb_onefield_checkpoint(dut1, configdb_key, "mode", "sbfd", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "segment-list", "fd00:303:2022:fff1:eee::", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "source-ipv6", "2000::58", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "remote-discr", "10087", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "local-address", "2000::58", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "multihop", "false", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "peer", "2000::59", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "enabled", "true", True, checkpoint)

    if default == False:
        configdb_onefield_checkpoint(dut1, configdb_key, "min-tx-interval", "100", True, checkpoint)
        configdb_onefield_checkpoint(dut1, configdb_key, "min-receive", "100", True, checkpoint)
        configdb_onefield_checkpoint(dut1, configdb_key, "detection-multiplier", "5", True, checkpoint)
        if bfd_mode != 'sbfd-echo-v4' and  bfd_mode != 'sbfd-echo-v6' and bfd_mode != 'sbfd-init-v6' and bfd_mode != 'sbfd-init-v4':
            configdb_onefield_checkpoint(dut2, configdb_key, "min-tx-interval", "100", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "min-receive", "100", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "detection-multiplier", "5", True, checkpoint)     

def check_bfd_session_status(bfd_mode, check_field, offload=True, delete=False):
    if bfd_mode == 'bfd-single-v4':
        key = 'peer 192.20.1.59 name BFD_SINGLE_V4_VRF mode bfd local-address 192.20.1.58 vrf Test1 interface PortChannel101'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut1 {} check_bfd_session_status vrf Test1 failed".format(bfd_mode))

        key = 'peer 192.20.1.58 name BFD_SINGLE_V4_VRF mode bfd local-address 192.20.1.59 vrf Test1 interface PortChannel101'
        ret = double_check_bfd_session(dut2, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut2 {} check_bfd_session_status vrf Test1 failed".format(bfd_mode))

        key = 'peer 192.10.1.59 name BFD_SINGLE_V4_DEFAULT mode bfd local-address 192.10.1.58 vrf Default interface PortChannel100'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut1 {} check_bfd_session_status vrf default failed".format(bfd_mode))

        key = 'peer 192.10.1.58 name BFD_SINGLE_V4_DEFAULT mode bfd local-address 192.10.1.59 vrf Default interface PortChannel100'
        ret = double_check_bfd_session(dut2, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut2 {} check_bfd_session_status vrf default failed".format(bfd_mode))
    elif bfd_mode == 'bfd-single-v6':
        key = 'peer fd00:200::59 name BFD_SINGLE_V6_VRF mode bfd local-address fd00:200::58 vrf Test1 interface PortChannel101'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut1 {} check_bfd_session_status vrf Test1 failed".format(bfd_mode))

        key = 'peer fd00:200::58 name BFD_SINGLE_V6_VRF mode bfd local-address fd00:200::59 vrf Test1 interface PortChannel101'
        ret = double_check_bfd_session(dut2, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut2 {} check_bfd_session_status vrf Test1 failed".format(bfd_mode))

        key = 'peer fd00:100::59 name BFD_SINGLE_V6_DEFAULT mode bfd local-address fd00:100::58 vrf Default interface PortChannel100'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut1 {} check_bfd_session_status vrf default failed".format(bfd_mode))

        key = 'peer fd00:100::58 name BFD_SINGLE_V6_DEFAULT mode bfd local-address fd00:100::59 vrf Default interface PortChannel100'
        ret = double_check_bfd_session(dut2, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut2 {} check_bfd_session_status vrf default failed".format(bfd_mode))
    elif bfd_mode == 'bfd-multi-v4':
        key = 'peer 192.40.1.59 name BFD_MULTI_V4_VRF multihop mode bfd local-address 192.40.1.58 vrf Test1'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut1 {} check_bfd_session_status vrf Test1 failed".format(bfd_mode))

        key = 'peer 192.40.1.58 name BFD_MULTI_V4_VRF multihop mode bfd local-address 192.40.1.59 vrf Test1'
        ret = double_check_bfd_session(dut2, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut2 {} check_bfd_session_status vrf Test1 failed".format(bfd_mode))

        key = 'peer 192.30.1.59 name BFD_MULTI_V4_DEFAULT multihop mode bfd local-address 192.30.1.58 vrf Default'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut1 {} check_bfd_session_status vrf default failed".format(bfd_mode))

        key = 'peer 192.30.1.58 name BFD_MULTI_V4_DEFAULT multihop mode bfd local-address 192.30.1.59 vrf Default'
        ret = double_check_bfd_session(dut2, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut2 {} check_bfd_session_status vrf default failed".format(bfd_mode))
    elif bfd_mode == 'bfd-multi-v6':
        key = 'peer fd00:400::59 name BFD_MULTI_V6_VRF multihop mode bfd local-address fd00:400::58 vrf Test1'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut1 {} check_bfd_session_status vrf Test1 failed".format(bfd_mode))

        key = 'peer fd00:400::58 name BFD_MULTI_V6_VRF multihop mode bfd local-address fd00:400::59 vrf Test1'
        ret = double_check_bfd_session(dut2, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut2 {} check_bfd_session_status vrf Test1 failed".format(bfd_mode))

        key = 'peer fd00:300::59 name BFD_MULTI_V6_DEFAULT multihop mode bfd local-address fd00:300::58 vrf Default'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut1 {} check_bfd_session_status vrf default failed".format(bfd_mode))

        key = 'peer fd00:300::58 name BFD_MULTI_V6_DEFAULT multihop mode bfd local-address fd00:300::59 vrf Default'
        ret = double_check_bfd_session(dut2, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut2 {} check_bfd_session_status vrf default failed".format(bfd_mode))
    elif bfd_mode == 'sbfd-echo-v4':
        key = 'peer 20.20.20.58 name SBFD_ECHO_V4_DEFAULT mode sbfd-echo local-address 20.20.20.58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 vrf Default'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut1 {} check_bfd_session_status vrf Default failed".format(bfd_mode))

    elif bfd_mode == 'sbfd-echo-v6':
        key = 'peer 2000::58 name SBFD_ECHO_V6_DEFAULT mode sbfd-echo local-address 2000::58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 vrf Default'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut1 {} check_bfd_session_status vrf Default failed".format(bfd_mode))

    elif bfd_mode == 'sbfd-init-v4':
        key = 'peer 20.20.20.59 name SBFD_INIT_V4_DEFAULT mode sbfd local-address 20.20.20.58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 remote-discr 10086 vrf Default'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut1 {} check_bfd_session_status vrf Default failed".format(bfd_mode))

    elif bfd_mode == 'sbfd-init-v6':
        key = 'peer 2000::59 name SBFD_INIT_V6_DEFAULT mode sbfd local-address 2000::58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 remote-discr 10087 vrf Default'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("dut1 {} check_bfd_session_status vrf Default failed".format(bfd_mode))
    else:
        st.log("check_bfd_session_status: wrong bfd mode type")

def del_peer_bfd(bfd_mode):
    if bfd_mode == 'bfd-single-v4':
        #default
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c 'no peer 192.10.1.59 name BFD_SINGLE_V4_DEFAULT mode bfd interface PortChannel100'")
        st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c 'no peer 192.10.1.58 name BFD_SINGLE_V4_DEFAULT mode bfd interface PortChannel100'")
        #vrf
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c 'no peer 192.20.1.59 name BFD_SINGLE_V4_VRF mode bfd interface PortChannel101 vrf Test1'")
        st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c 'no peer 192.20.1.58 name BFD_SINGLE_V4_VRF mode bfd interface PortChannel101 vrf Test1'")
    elif bfd_mode == 'bfd-single-v6':
        #default
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c 'no peer fd00:100::59 name BFD_SINGLE_V6_DEFAULT mode bfd interface PortChannel100'")
        st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c 'no peer fd00:100::58 name BFD_SINGLE_V6_DEFAULT mode bfd interface PortChannel100'")
        #vrf
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c 'no peer fd00:200::59 name BFD_SINGLE_V6_VRF mode bfd interface PortChannel101 vrf Test1'")
        st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c 'no peer fd00:200::58 name BFD_SINGLE_V6_VRF mode bfd interface PortChannel101 vrf Test1'")
    elif bfd_mode == 'bfd-multi-v4':
        #default
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c 'no peer 192.30.1.59 name BFD_MULTI_V4_DEFAULT mode bfd local-address 192.30.1.58 multihop'")
        st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c 'no peer 192.30.1.58 name BFD_MULTI_V4_DEFAULT mode bfd local-address 192.30.1.59 multihop'")
        #vrf
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c 'no peer 192.40.1.59 name BFD_MULTI_V4_VRF mode bfd local-address 192.40.1.58 multihop vrf Test1'")
        st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c 'no peer 192.40.1.58 name BFD_MULTI_V4_VRF mode bfd local-address 192.40.1.59 multihop vrf Test1'")
    elif bfd_mode == 'bfd-multi-v6':
        #default
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c 'no peer fd00:300::59 name BFD_MULTI_V6_DEFAULT mode bfd local-address fd00:300::58 multihop'")
        st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c 'no peer fd00:300::58 name BFD_MULTI_V6_DEFAULT mode bfd local-address fd00:300::59 multihop'")
        #vrf
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c 'no peer fd00:400::59 name BFD_MULTI_V6_VRF mode bfd local-address fd00:400::58 multihop vrf Test1'")
        st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c 'no peer fd00:400::58 name BFD_MULTI_V6_VRF mode bfd local-address fd00:400::59 multihop vrf Test1'")
    elif bfd_mode == 'sbfd-echo-v4':
        #sbfd-echo v4
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c 'no peer 20.20.20.58 name SBFD_ECHO_V4_DEFAULT mode sbfd-echo local-address 20.20.20.58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58'")
    elif bfd_mode == 'sbfd-echo-v6':
        #sbfd-echo v6
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c 'no peer 2000::58 name SBFD_ECHO_V6_DEFAULT mode sbfd-echo local-address 2000::58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58'")
    elif bfd_mode == 'sbfd-init-v4':
        #sbfd v4
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c 'no peer 20.20.20.59 name SBFD_INIT_V4_DEFAULT mode sbfd local-address 20.20.20.58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 remote-discr 10086'")
        st.config(dut2, "cli -c 'configure terminal' -c 'no sbfd reflector all'")
    elif bfd_mode == 'sbfd-init-v6':
        #sbfd v6
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c 'no peer 2000::59 name SBFD_INIT_V6_DEFAULT mode sbfd local-address 2000::58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 remote-discr 10087'")
        st.config(dut2, "cli -c 'configure terminal' -c 'no sbfd reflector all'")
    
                
def config_peer_bfd(bfd_mode):
    # sbfd only need test vrf default
    if bfd_mode == 'sbfd-echo-v4':
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer 20.20.20.58 name SBFD_ECHO_V4_DEFAULT mode sbfd-echo\
                  local-address 20.20.20.58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58'")
    elif bfd_mode == 'sbfd-echo-v6':
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer 2000::58 name SBFD_ECHO_V6_DEFAULT mode sbfd-echo \
                  local-address 2000::58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58'")
    elif bfd_mode == 'sbfd-init-v4':
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer 20.20.20.59 name SBFD_INIT_V4_DEFAULT mode sbfd \
                  local-address 20.20.20.58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 remote-discr 10086'")
        st.config(dut2, "cli -c 'configure terminal' -c 'sbfd reflector source-address 20.20.20.59 discriminator 10086'")
    elif bfd_mode == 'sbfd-init-v6':
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer 2000::59 name SBFD_INIT_V6_DEFAULT mode sbfd \
                  local-address 2000::58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 remote-discr 10087'")
        st.config(dut2, "cli -c 'configure terminal' -c 'sbfd reflector source-address 2000::59 discriminator 10087'")
    elif bfd_mode == 'bfd-single-v4':
        #default
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer 192.10.1.59 name BFD_SINGLE_V4_DEFAULT mode bfd interface PortChannel100'")
        st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer 192.10.1.58 name BFD_SINGLE_V4_DEFAULT mode bfd interface PortChannel100'")
        #vrf
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer 192.20.1.59 name BFD_SINGLE_V4_VRF mode bfd interface PortChannel101 vrf Test1'")
        st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer 192.20.1.58 name BFD_SINGLE_V4_VRF mode bfd interface PortChannel101 vrf Test1'")
    elif bfd_mode == 'bfd-single-v6':
        #default
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer fd00:100::59 name BFD_SINGLE_V6_DEFAULT mode bfd interface PortChannel100'")
        st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer fd00:100::58 name BFD_SINGLE_V6_DEFAULT mode bfd interface PortChannel100'")
        #vrf
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer fd00:200::59 name BFD_SINGLE_V6_VRF mode bfd interface PortChannel101 vrf Test1'")
        st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer fd00:200::58 name BFD_SINGLE_V6_VRF mode bfd interface PortChannel101 vrf Test1'")
    elif bfd_mode == 'bfd-multi-v4':
        #default
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer 192.30.1.59 name BFD_MULTI_V4_DEFAULT mode bfd local-address 192.30.1.58 multihop'")
        st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer 192.30.1.58 name BFD_MULTI_V4_DEFAULT mode bfd local-address 192.30.1.59 multihop'")
        #vrf
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer 192.40.1.59 name BFD_MULTI_V4_VRF mode bfd local-address 192.40.1.58 multihop vrf Test1'")
        st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer 192.40.1.58 name BFD_MULTI_V4_VRF mode bfd local-address 192.40.1.59 multihop vrf Test1'")
    elif bfd_mode == 'bfd-multi-v6':
        #default
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer fd00:300::59 name BFD_MULTI_V6_DEFAULT mode bfd local-address fd00:300::58 multihop'")
        st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer fd00:300::58 name BFD_MULTI_V6_DEFAULT mode bfd local-address fd00:300::59 multihop'")
        #vrf
        st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer fd00:400::59 name BFD_MULTI_V6_VRF mode bfd local-address fd00:400::58 multihop vrf Test1'")
        st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c \
                  'peer fd00:400::58 name BFD_MULTI_V6_VRF mode bfd local-address fd00:400::59 multihop vrf Test1'")
    else:
        st.log("config_peer_bfd: wrong bfd mode type")


@pytest.fixture(scope="module", autouse=True)
def sbfd_module_hooks(request):
    #add things at the start of this module
    # ixia_controller_init()
    yield
    # ixia_stop_all_protocols()
    # ixia_controller_deinit()

@pytest.fixture(scope="function", autouse=True)
def sbfd_bfd_func_hooks(request):
    # add things at the start every test case

    if st.get_func_name(request) in  ["test_config_bfd_name_session_case1", "test_config_sbfd_name_session_case2",
                                      "test_exception_bfd_name_session_case3", "test_exception_sbfd_name_session_case4"]:
        st.log("bfd_basic_config case enter ")
        if data.load_basic_config_done == False:
            load_json_config('bfd_basic_config')
            st.wait(120)
            data.load_basic_config_done = True
        
        # ping each other to learn nd and arp 
        learn_arp_by_ping()
    
    yield
    pass

# BFD-BASIC-FUNC-001
# BFD-BASIC-FUNC-002
# BFD-BASIC-FUNC-003
@pytest.mark.community
@pytest.mark.community_pass
def test_config_bfd_name_session_case1():
    st.banner("test_config_bfd_name_session_case1 begin")
    
    # step 1: config bfd single-v4/single-v6/multi-v4/multi-v6
    config_peer_bfd('bfd-single-v4')
    st.wait(2)
    config_peer_bfd('bfd-single-v6')
    st.wait(2)
    config_peer_bfd('bfd-multi-v4')
    st.wait(2)
    config_peer_bfd('bfd-multi-v6')
    st.wait(2)

    # step 2 : check bfd single-v4/single-v6/multi-v4/multi-v6  
    check_field = {
        'status':'up',
        'peer_type' : 'configured',
        'multiplier': '3'
    }   
    mode = 'bfd-single-v4'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-single-v6'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-multi-v4'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-multi-v6'
    check_bfd_session_status(mode, check_field, True, False)

    # step3: check configdb
    mode = 'bfd-single-v4'
    configdb_key = "BFD_PEER|BFD_SINGLE_V4_DEFAULT"
    checkpoint_msg = "test_config_bfd_name_session_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, True, checkpoint_msg)

    configdb_key = "BFD_PEER|BFD_SINGLE_V4_VRF"
    checkpoint_msg = "test_config_bfd_name_session_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, True, checkpoint_msg)

    mode = 'bfd-single-v6'
    configdb_key = "BFD_PEER|BFD_SINGLE_V6_DEFAULT"
    checkpoint_msg = "test_config_bfd_name_session_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, True, checkpoint_msg)

    configdb_key = "BFD_PEER|BFD_SINGLE_V6_VRF"
    checkpoint_msg = "test_config_bfd_name_session_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, True, checkpoint_msg)
    
    mode = 'bfd-multi-v4'
    configdb_key = "BFD_PEER|BFD_MULTI_V4_DEFAULT"
    checkpoint_msg = "test_config_bfd_name_session_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, True, checkpoint_msg)

    configdb_key = "BFD_PEER|BFD_MULTI_V4_VRF"
    checkpoint_msg = "test_config_bfd_name_session_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, True, checkpoint_msg)

    mode = 'bfd-multi-v6'
    configdb_key = "BFD_PEER|BFD_MULTI_V6_DEFAULT"
    checkpoint_msg = "test_config_bfd_name_session_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, True, checkpoint_msg)

    configdb_key = "BFD_PEER|BFD_MULTI_V6_VRF"
    checkpoint_msg = "test_config_bfd_name_session_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, True, checkpoint_msg)

    # step 4 : modify interval and multiplier
    # single v4 default
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.10.1.59 name BFD_SINGLE_V4_DEFAULT mode bfd interface PortChannel100' -c 'detect-multiplier 5'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.10.1.59 name BFD_SINGLE_V4_DEFAULT mode bfd interface PortChannel100' -c 'receive-interval 100'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.10.1.59 name BFD_SINGLE_V4_DEFAULT mode bfd interface PortChannel100' -c 'transmit-interval 100'")

    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.10.1.58 name BFD_SINGLE_V4_DEFAULT mode bfd interface PortChannel100' -c 'detect-multiplier 5'")
    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.10.1.58 name BFD_SINGLE_V4_DEFAULT mode bfd interface PortChannel100' -c 'receive-interval 100'")
    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.10.1.58 name BFD_SINGLE_V4_DEFAULT mode bfd interface PortChannel100' -c 'transmit-interval 100'")

    # single v4 vrf
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.20.1.59 name BFD_SINGLE_V4_VRF mode bfd interface PortChannel101 vrf Test1' -c 'detect-multiplier 5'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.20.1.59 name BFD_SINGLE_V4_VRF mode bfd interface PortChannel101 vrf Test1' -c 'receive-interval 100'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.20.1.59 name BFD_SINGLE_V4_VRF mode bfd interface PortChannel101 vrf Test1' -c 'transmit-interval 100'")

    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.20.1.58 name BFD_SINGLE_V4_VRF mode bfd interface PortChannel101 vrf Test1' -c 'detect-multiplier 5'")
    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.20.1.58 name BFD_SINGLE_V4_VRF mode bfd interface PortChannel101 vrf Test1' -c 'receive-interval 100'")
    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.20.1.58 name BFD_SINGLE_V4_VRF mode bfd interface PortChannel101 vrf Test1' -c 'transmit-interval 100'")

    # single v6 default
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:100::59 name BFD_SINGLE_V6_DEFAULT mode bfd interface PortChannel100' -c 'detect-multiplier 5'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:100::59 name BFD_SINGLE_V6_DEFAULT mode bfd interface PortChannel100' -c 'receive-interval 100'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:100::59 name BFD_SINGLE_V6_DEFAULT mode bfd interface PortChannel100' -c 'transmit-interval 100'")

    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:100::58 name BFD_SINGLE_V6_DEFAULT mode bfd interface PortChannel100' -c 'detect-multiplier 5'")
    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:100::58 name BFD_SINGLE_V6_DEFAULT mode bfd interface PortChannel100' -c 'receive-interval 100'")
    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:100::58 name BFD_SINGLE_V6_DEFAULT mode bfd interface PortChannel100' -c 'transmit-interval 100'")

    # single v6 vrf
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:200::59 name BFD_SINGLE_V6_VRF mode bfd interface PortChannel101 vrf Test1' -c 'detect-multiplier 5'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:200::59 name BFD_SINGLE_V6_VRF mode bfd interface PortChannel101 vrf Test1' -c 'receive-interval 100'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:200::59 name BFD_SINGLE_V6_VRF mode bfd interface PortChannel101 vrf Test1' -c 'transmit-interval 100'")

    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:200::58 name BFD_SINGLE_V6_VRF mode bfd interface PortChannel101 vrf Test1' -c 'detect-multiplier 5'")
    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:200::58 name BFD_SINGLE_V6_VRF mode bfd interface PortChannel101 vrf Test1' -c 'receive-interval 100'")
    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:200::58 name BFD_SINGLE_V6_VRF mode bfd interface PortChannel101 vrf Test1' -c 'transmit-interval 100'")

    # multi v4 default
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.30.1.59 name BFD_MULTI_V4_DEFAULT mode bfd local-address 192.30.1.58 multihop' -c 'detect-multiplier 5'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.30.1.59 name BFD_MULTI_V4_DEFAULT mode bfd local-address 192.30.1.58 multihop' -c 'receive-interval 100'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.30.1.59 name BFD_MULTI_V4_DEFAULT mode bfd local-address 192.30.1.58 multihop' -c 'transmit-interval 100'")

    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.30.1.58 name BFD_MULTI_V4_DEFAULT mode bfd local-address 192.30.1.59 multihop' -c 'detect-multiplier 5'")
    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.30.1.58 name BFD_MULTI_V4_DEFAULT mode bfd local-address 192.30.1.59 multihop' -c 'receive-interval 100'")
    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.30.1.58 name BFD_MULTI_V4_DEFAULT mode bfd local-address 192.30.1.59 multihop' -c 'transmit-interval 100'")

    # multi v4 vrf
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.40.1.59 name BFD_MULTI_V4_VRF mode bfd local-address 192.40.1.58 multihop vrf Test1' -c 'detect-multiplier 5'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.40.1.59 name BFD_MULTI_V4_VRF mode bfd local-address 192.40.1.58 multihop vrf Test1' -c 'receive-interval 100'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.40.1.59 name BFD_MULTI_V4_VRF mode bfd local-address 192.40.1.58 multihop vrf Test1' -c 'transmit-interval 100'")

    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.40.1.58 name BFD_MULTI_V4_VRF mode bfd local-address 192.40.1.59 multihop vrf Test1' -c 'detect-multiplier 5'")
    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.40.1.58 name BFD_MULTI_V4_VRF mode bfd local-address 192.40.1.59 multihop vrf Test1' -c 'receive-interval 100'")
    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 192.40.1.58 name BFD_MULTI_V4_VRF mode bfd local-address 192.40.1.59 multihop vrf Test1' -c 'transmit-interval 100'")
                

    # multi v6 default
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:300::59 name BFD_MULTI_V6_DEFAULT mode bfd local-address fd00:300::58 multihop' -c 'detect-multiplier 5'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:300::59 name BFD_MULTI_V6_DEFAULT mode bfd local-address fd00:300::58 multihop' -c 'receive-interval 100'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:300::59 name BFD_MULTI_V6_DEFAULT mode bfd local-address fd00:300::58 multihop' -c 'transmit-interval 100'")

    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:300::58 name BFD_MULTI_V6_DEFAULT mode bfd local-address fd00:300::59 multihop' -c 'detect-multiplier 5'")
    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:300::58 name BFD_MULTI_V6_DEFAULT mode bfd local-address fd00:300::59 multihop' -c 'receive-interval 100'")
    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:300::58 name BFD_MULTI_V6_DEFAULT mode bfd local-address fd00:300::59 multihop' -c 'transmit-interval 100'")
                
    # multi v6 vrf
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:400::59 name BFD_MULTI_V6_VRF mode bfd local-address fd00:400::58 multihop vrf Test1' -c 'detect-multiplier 5'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:400::59 name BFD_MULTI_V6_VRF mode bfd local-address fd00:400::58 multihop vrf Test1' -c 'receive-interval 100'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:400::59 name BFD_MULTI_V6_VRF mode bfd local-address fd00:400::58 multihop vrf Test1' -c 'transmit-interval 100'")

    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:400::58 name BFD_MULTI_V6_VRF mode bfd local-address fd00:400::59 multihop vrf Test1' -c 'detect-multiplier 5'")
    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:400::58 name BFD_MULTI_V6_VRF mode bfd local-address fd00:400::59 multihop vrf Test1' -c 'receive-interval 100'")
    st.config(dut2, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer fd00:400::58 name BFD_MULTI_V6_VRF mode bfd local-address fd00:400::59 multihop vrf Test1' -c 'transmit-interval 100'")

    check_field = {
        'status':'up',
        'peer_type' : 'configured',
        'multiplier': '5'
    }

    mode = 'bfd-single-v4'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-single-v6'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-multi-v4'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-multi-v6'
    check_bfd_session_status(mode, check_field, True, False)

    # check configdb
    mode = 'bfd-single-v4'
    configdb_key = "BFD_PEER|BFD_SINGLE_V4_DEFAULT"
    checkpoint_msg = "test_config_bfd_name_session_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, False, checkpoint_msg)

    configdb_key = "BFD_PEER|BFD_SINGLE_V4_VRF"
    checkpoint_msg = "test_config_bfd_name_session_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, False, checkpoint_msg)

    mode = 'bfd-single-v6'
    configdb_key = "BFD_PEER|BFD_SINGLE_V6_DEFAULT"
    checkpoint_msg = "test_config_bfd_name_session_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, False, checkpoint_msg)

    configdb_key = "BFD_PEER|BFD_SINGLE_V6_VRF"
    checkpoint_msg = "test_config_bfd_name_session_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, False, checkpoint_msg)
    
    mode = 'bfd-multi-v4'
    configdb_key = "BFD_PEER|BFD_MULTI_V4_DEFAULT"
    checkpoint_msg = "test_config_bfd_name_session_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, False, checkpoint_msg)

    configdb_key = "BFD_PEER|BFD_MULTI_V4_VRF"
    checkpoint_msg = "test_config_bfd_name_session_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, False, checkpoint_msg)

    mode = 'bfd-multi-v6'
    configdb_key = "BFD_PEER|BFD_MULTI_V6_DEFAULT"
    checkpoint_msg = "test_config_bfd_name_session_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, False, checkpoint_msg)

    configdb_key = "BFD_PEER|BFD_MULTI_V6_VRF"
    checkpoint_msg = "test_config_bfd_name_session_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, False, checkpoint_msg)

    # step 5 : check del bfd single-v4/single-v6/multi-v4/multi-v6
    check_field = {}
    mode = 'bfd-single-v4' 
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    mode = 'bfd-single-v6' 
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    mode = 'bfd-multi-v4' 
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    mode = 'bfd-multi-v6' 
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)
        
    # step 6 : check appdb is clear
    show_appdb_table_info(dut1, '*BFD*')
    show_appdb_table_info(dut2, '*BFD*')

    st.report_pass('test_case_passed')


# SBFD-BASIC-FUNC-001
# SBFD-BASIC-FUNC-002
@pytest.mark.community
@pytest.mark.community_pass
def test_config_sbfd_name_session_case2():
    st.banner("test_config_sbfd_name_session_case2 begin")
    # step 1: config sbfd
    mode = 'sbfd-echo-v4'
    config_peer_bfd(mode)
    mode = 'sbfd-echo-v6'
    config_peer_bfd(mode)
    mode = 'sbfd-init-v4'
    config_peer_bfd(mode)
    mode = 'sbfd-init-v6'
    config_peer_bfd(mode)
    st.wait(70)

   # step 2 : check sbfd    
    check_field = {
        'status':'up',
        'peer_type' : 'sbfd initiator',
        'multiplier': '3'
    }
    mode = 'sbfd-init-v4'
    check_bfd_session_status(mode, check_field, True, False)
    mode = 'sbfd-init-v6'
    check_bfd_session_status(mode, check_field, True, False)

    check_field = {
        'status':'up',
        'peer_type' : 'echo',
        'multiplier': '3'
    }
    mode = 'sbfd-echo-v4'
    check_bfd_session_status(mode, check_field, True, False)
    mode = 'sbfd-echo-v6'
    check_bfd_session_status(mode, check_field, True, False)

    # step3: check configdb
    mode = 'sbfd-init-v4'
    configdb_key = "BFD_PEER|SBFD_INIT_V4_DEFAULT"
    checkpoint_msg = "test_config_sbfd_name_session_case2 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, True, checkpoint_msg)

    mode = 'sbfd-init-v6'
    configdb_key = "BFD_PEER|SBFD_INIT_V6_DEFAULT"
    checkpoint_msg = "test_config_sbfd_name_session_case2 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, True, checkpoint_msg)

    mode = 'sbfd-echo-v4'
    configdb_key = "BFD_PEER|SBFD_ECHO_V4_DEFAULT"
    checkpoint_msg = "test_config_sbfd_name_session_case2 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, True, checkpoint_msg)

    mode = 'sbfd-echo-v6'
    configdb_key = "BFD_PEER|SBFD_ECHO_V6_DEFAULT"
    checkpoint_msg = "test_config_sbfd_name_session_case2 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, True, checkpoint_msg)


    # step 4 : modify interval and multiplier
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 2000::59 name SBFD_INIT_V6_DEFAULT mode sbfd local-address 2000::58 \
                 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 remote-discr 10087' -c 'detect-multiplier 5'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 2000::59 name SBFD_INIT_V6_DEFAULT mode sbfd local-address 2000::58 \
                 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 remote-discr 10087' -c 'receive-interval 100'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 2000::59 name SBFD_INIT_V6_DEFAULT mode sbfd local-address 2000::58 \
                 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 remote-discr 10087' -c 'transmit-interval 100'")
    
    check_field = {
        'status':'up',
        'peer_type' : 'sbfd initiator',
        'multiplier': '5'
    }
    mode = 'sbfd-init-v6'
    check_bfd_session_status(mode, check_field, True, False)

    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 20.20.20.59 name SBFD_INIT_V4_DEFAULT mode sbfd local-address 20.20.20.58  \
                 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 remote-discr 10086' -c 'detect-multiplier 5'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 20.20.20.59 name SBFD_INIT_V4_DEFAULT mode sbfd local-address 20.20.20.58  \
                 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 remote-discr 10086' -c 'receive-interval 100'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 20.20.20.59 name SBFD_INIT_V4_DEFAULT mode sbfd local-address 20.20.20.58  \
                 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 remote-discr 10086' -c 'transmit-interval 100'")

    mode = 'sbfd-init-v4'
    check_bfd_session_status(mode, check_field, True, False)

    check_field = {
        'status':'up',
        'peer_type' : 'echo',
        'multiplier': '5'
    }
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 20.20.20.58 name SBFD_ECHO_V4_DEFAULT mode sbfd-echo local-address 20.20.20.58 \
                 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58' -c 'detect-multiplier 5'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 20.20.20.58 name SBFD_ECHO_V4_DEFAULT mode sbfd-echo local-address 20.20.20.58 \
                 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58' -c 'receive-interval 100'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 20.20.20.58 name SBFD_ECHO_V4_DEFAULT mode sbfd-echo local-address 20.20.20.58 \
                 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58' -c 'transmit-interval 100'")
    mode = 'sbfd-echo-v4'
    check_bfd_session_status(mode, check_field, True, False)

    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 2000::58 name SBFD_ECHO_V6_DEFAULT mode sbfd-echo local-address 2000::58 \
                 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58' -c 'detect-multiplier 5'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 2000::58 name SBFD_ECHO_V6_DEFAULT mode sbfd-echo local-address 2000::58 \
                 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58' -c 'receive-interval 100'")
    st.config(dut1, "cli -c 'configure terminal' -c 'bfd' -c  \
                'peer 2000::58 name SBFD_ECHO_V6_DEFAULT mode sbfd-echo local-address 2000::58 \
                 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58' -c 'transmit-interval 100'")
    mode = 'sbfd-echo-v6'
    check_bfd_session_status(mode, check_field, True, False)
 
    # check configdb
    mode = 'sbfd-init-v4'
    configdb_key = "BFD_PEER|SBFD_INIT_V4_DEFAULT"
    checkpoint_msg = "test_config_sbfd_name_session_case2 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, False, checkpoint_msg)

    mode = 'sbfd-init-v6'
    configdb_key = "BFD_PEER|SBFD_INIT_V6_DEFAULT"
    checkpoint_msg = "test_config_sbfd_name_session_case2 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, False, checkpoint_msg)

    mode = 'sbfd-echo-v4'
    configdb_key = "BFD_PEER|SBFD_ECHO_V4_DEFAULT"
    checkpoint_msg = "test_config_sbfd_name_session_case2 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, False, checkpoint_msg)

    mode = 'sbfd-echo-v6'
    configdb_key = "BFD_PEER|SBFD_ECHO_V6_DEFAULT"
    checkpoint_msg = "test_config_sbfd_name_session_case2 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, False, checkpoint_msg)

    # step 5 : check del sbfd
    check_field = {}
    mode = 'sbfd-init-v4'
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    mode = 'sbfd-init-v6'
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)
    
    mode = 'sbfd-echo-v4'
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    mode = 'sbfd-echo-v6'
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    # step 6 : check appdb is clear
    show_appdb_table_info(dut1, '*BFD*')
    show_appdb_table_info(dut2, '*BFD*')   

    st.report_pass('test_case_passed')


# BFD-BASIC-EXCP-001
# BFD-BASIC-EXCP-002
# BFD-BASIC-EXCP-003
@pytest.mark.community
@pytest.mark.community_pass
def test_exception_bfd_name_session_case3():
    st.banner("test_exception_bfd_name_session_case3 begin")

    # BFD-BASIC-EXCP-001
    # step 1: config bfd single-v4/single-v6/multi-v4/multi-v6
    st.log("step 1.1 config bfd single-v4/single-v6/multi-v4/multi-v6:")
    config_peer_bfd('bfd-single-v4')
    st.wait(2)
    config_peer_bfd('bfd-single-v6')
    st.wait(2)
    config_peer_bfd('bfd-multi-v4')
    st.wait(2)
    config_peer_bfd('bfd-multi-v6')
    st.wait(2)

    # step 2 : check bfd single-v4/single-v6/multi-v4/multi-v6  
    st.log("step 1.2 check bfd single-v4/single-v6/multi-v4/multi-v6:")
    check_field = {
        'status':'up',
        'peer_type' : 'configured',
        'multiplier': '3'
    }   
    mode = 'bfd-single-v4'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-single-v6'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-multi-v4'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-multi-v6'
    check_bfd_session_status(mode, check_field, True, False)

    # step 3 : shutdown interface
    st.log("step 1.3 shutdown interface:")
    intf_list = ['Ethernet1', 'Ethernet2', 'Ethernet3', 'Ethernet4']
    for intf in intf_list:
        st.config(dut2, 'cli -c "config t" -c "interface {}" -c "shutdown"'.format(intf))
        st.wait(5)

    # step 4 : check bfd single-v4/single-v6/multi-v4/multi-v6  
    st.log("step 1.4 check bfd single-v4/single-v6/multi-v4/multi-v6:")
    check_field = {
        'status':'down',
        'peer_type' : 'configured',
        'multiplier': '3'
    }   
    mode = 'bfd-single-v4'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-single-v6'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-multi-v4'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-multi-v6'
    check_bfd_session_status(mode, check_field, True, False)

    # step 5 : no shutdown interface
    st.log("step 1.5 no shutdown interface:")
    intf_list = ['Ethernet1', 'Ethernet2', 'Ethernet3', 'Ethernet4']
    for intf in intf_list:
        st.config(dut2, 'cli -c "config t" -c "interface {}" -c "no shutdown"'.format(intf))
        st.wait(5)

    # step 6 : check bfd single-v4/single-v6/multi-v4/multi-v6  
    st.log("step 1.6 check bfd single-v4/single-v6/multi-v4/multi-v6:")
    check_field = {
        'status':'up',
        'peer_type' : 'configured',
        'multiplier': '3'
    }   
    mode = 'bfd-single-v4'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-single-v6'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-multi-v4'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-multi-v6'
    check_bfd_session_status(mode, check_field, True, False)

    # step 7 : check del bfd single-v4/single-v6/multi-v4/multi-v6
    st.log("step 1.7 check del bfd single-v4/single-v6/multi-v4/multi-v6:") 
    check_field = {}
    mode = 'bfd-single-v4' 
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    mode = 'bfd-single-v6' 
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    mode = 'bfd-multi-v4' 
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    mode = 'bfd-multi-v6' 
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)
        
    # step 8 : check appdb is clear
    st.log("step 1.8 check appdb is clear:")
    show_appdb_table_info(dut1, '*BFD*')
    show_appdb_table_info(dut2, '*BFD*')   

    # BFD-BASIC-EXCP-002    
    # step 1 : shutdown interface
    st.log("step 2.1 shutdown interface:")
    intf_list = ['Ethernet1', 'Ethernet2', 'Ethernet3', 'Ethernet4']
    for intf in intf_list:
        st.config(dut2, 'cli -c "config t" -c "interface {}" -c "shutdown"'.format(intf))
        st.wait(5)

    # step 2: config bfd single-v4/single-v6/multi-v4/multi-v6
    st.log("step 2.2 config bfd single-v4/single-v6/multi-v4/multi-v6:")
    config_peer_bfd('bfd-single-v4')
    st.wait(2)
    config_peer_bfd('bfd-single-v6')
    st.wait(2)
    config_peer_bfd('bfd-multi-v4')
    st.wait(2)
    config_peer_bfd('bfd-multi-v6')
    st.wait(2)

    # step 3 : check bfd single-v4/single-v6/multi-v4/multi-v6  
    st.log("step 2.3 check bfd single-v4/single-v6/multi-v4/multi-v6:")
    check_field = {
        'status':'down',
        'peer_type' : 'configured',
        'multiplier': '3'
    }   
    mode = 'bfd-single-v4'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-single-v6'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-multi-v4'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-multi-v6'
    check_bfd_session_status(mode, check_field, True, False)

    # step 4 : no shutdown interface
    st.log("step 2.4 no shutdown interface:")
    intf_list = ['Ethernet1', 'Ethernet2', 'Ethernet3', 'Ethernet4']
    for intf in intf_list:
        st.config(dut2, 'cli -c "config t" -c "interface {}" -c "no shutdown"'.format(intf))
        st.wait(5)

    # step 5 : check bfd single-v4/single-v6/multi-v4/multi-v6  
    st.log("step 2.5 check bfd single-v4/single-v6/multi-v4/multi-v6:")
    check_field = {
        'status':'up',
        'peer_type' : 'configured',
        'multiplier': '3'
    }   
    mode = 'bfd-single-v4'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-single-v6'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-multi-v4'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-multi-v6'
    check_bfd_session_status(mode, check_field, True, False)

    # step 6 : check del sbfd
    st.log("step 2.6 check del sbfd:")
    check_field = {}
    mode = 'bfd-single-v4' 
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    mode = 'bfd-single-v6' 
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    mode = 'bfd-multi-v4' 
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    mode = 'bfd-multi-v6' 
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    # step 7 : check appdb is clear
    st.log("step 2.7 check appdb is clear:")
    show_appdb_table_info(dut1, '*BFD*')
    show_appdb_table_info(dut2, '*BFD*')   

    # BFD-BASIC-EXCP-003 
    # step 1: config bfd single-v4/single-v6/multi-v4/multi-v6
    st.log("step 3.1 config bfd single-v4/single-v6/multi-v4/multi-v6:")
    config_peer_bfd('bfd-single-v4')
    st.wait(2)
    config_peer_bfd('bfd-single-v6')
    st.wait(2)
    config_peer_bfd('bfd-multi-v4')
    st.wait(2)
    config_peer_bfd('bfd-multi-v6')
    st.wait(2)

    # step 2 : check bfd single-v4/single-v6/multi-v4/multi-v6  
    st.log("step 3.2 check bfd single-v4/single-v6/multi-v4/multi-v6:")
    check_field = {
        'status':'up',
        'peer_type' : 'configured',
        'multiplier': '3'
    }   
    mode = 'bfd-single-v4'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-single-v6'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-multi-v4'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-multi-v6'
    check_bfd_session_status(mode, check_field, True, False)

    # step 3 : flapping interface 
    st.log("step 3.3 flapping interface:")
    intf_list = ['Ethernet1', 'Ethernet2', 'Ethernet3', 'Ethernet4']  
    for i in range(10):
        for intf in intf_list:
            st.config(dut2, 'cli -c "config t" -c "interface {}" -c "shutdown"'.format(intf))
            st.wait(5)
            st.config(dut2, 'cli -c "config t" -c "interface {}" -c "no shutdown"'.format(intf))
            st.wait(5)

    # step 4 : check bfd single-v4/single-v6/multi-v4/multi-v6  
    st.log("step 3.4 check bfd single-v4/single-v6/multi-v4/multi-v6:")
    check_field = {
        'status':'up',
        'peer_type' : 'configured',
        'multiplier': '3'
    }   
    mode = 'bfd-single-v4'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-single-v6'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-multi-v4'
    check_bfd_session_status(mode, check_field, True, False)

    mode = 'bfd-multi-v6'
    check_bfd_session_status(mode, check_field, True, False)

    # step 5 : check del bfd single-v4/single-v6/multi-v4/multi-v6
    st.log("step 3.5 check del bfd single-v4/single-v6/multi-v4/multi-v6:")
    check_field = {}
    mode = 'bfd-single-v4' 
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    mode = 'bfd-single-v6' 
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    mode = 'bfd-multi-v4' 
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    mode = 'bfd-multi-v6' 
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)
        
    # step 6 : check appdb is clear
    st.log("step 3.6 check appdb is clear:")
    show_appdb_table_info(dut1, '*BFD*')
    show_appdb_table_info(dut2, '*BFD*')

    st.report_pass('test_case_passed')


# SBFD-BASIC-EXCP-001
# SBFD-BASIC-EXCP-002
@pytest.mark.community
@pytest.mark.community_pass
def test_exception_sbfd_name_session_case4():
    st.banner("test_exception_sbfd_name_session_case4 begin")

    # SBFD-BASIC-EXCP-001
    # step 1: config sbfd sbfd-echo-v4/sbfd-echo-v6/sbfd-init-v6
    st.log("step 1.1 config sbfd sbfd-echo-v4/sbfd-echo-v6/sbfd-init-v6:")
    config_peer_bfd('sbfd-echo-v4')
    st.wait(2)
    config_peer_bfd('sbfd-echo-v6')
    st.wait(2)
    config_peer_bfd('sbfd-init-v4')
    st.wait(2)
    config_peer_bfd('sbfd-init-v6')
    st.wait(70)

    # step 2 : check sbfd sbfd-echo-v4/sbfd-echo-v6/sbfd-init-v4/sbfd-init-v6  
    st.log("step 1.2 check sbfd sbfd-echo-v4/sbfd-echo-v6/sbfd-init-v4/sbfd-init-v6:")
    check_field = {
        'status':'up',
        'peer_type' : 'sbfd initiator',
        'multiplier': '3'
    }
    mode = 'sbfd-init-v4'
    check_bfd_session_status(mode, check_field, True, False)
    mode = 'sbfd-init-v6'
    check_bfd_session_status(mode, check_field, True, False)

    check_field = {
        'status':'up',
        'peer_type' : 'echo',
        'multiplier': '3'
    }
    mode = 'sbfd-echo-v4'
    check_bfd_session_status(mode, check_field, True, False)
    mode = 'sbfd-echo-v6'
    check_bfd_session_status(mode, check_field, True, False)

    # step 3 : Deprecation Routing 
    st.log("step 1.3 Deprecation Routing:")
    st.config(dut1, 'cli -c "config t" -c "no ipv6 route fd00:303:2022::/48 fd00:100::59"')
    st.wait(5)

    # step 4 : check sbfd sbfd-echo-v4/sbfd-echo-v6/sbfd-init-v6  
    st.log("step 1.4 check sbfd sbfd-echo-v4/sbfd-echo-v6/sbfd-init-v4/sbfd-init-v6:")
    check_field = {
        'status':'down',
        'peer_type' : 'sbfd initiator',
        'multiplier': '3'
    }
    mode = 'sbfd-init-v4'
    check_bfd_session_status(mode, check_field, True, False)
    mode = 'sbfd-init-v6'
    check_bfd_session_status(mode, check_field, True, False)

    check_field = {
        'status':'down',
        'peer_type' : 'echo',
        'multiplier': '3'
    }
    mode = 'sbfd-echo-v4'
    check_bfd_session_status(mode, check_field, True, False)
    mode = 'sbfd-echo-v6'
    check_bfd_session_status(mode, check_field, True, False)

    # step 5 : Restoring Routes
    st.log("step 1.5 Restoring Routes:")
    st.config(dut1, 'cli -c "config t" -c "ipv6 route fd00:303:2022::/48 fd00:100::59"')
    st.wait(70)

    # step 6 : check sbfd sbfd-echo-v4/sbfd-echo-v6/sbfd-init-v6 
    st.log("step 1.6 check sbfd sbfd-echo-v4/sbfd-echo-v6/sbfd-init-v4/sbfd-init-v6:")
    check_field = {
        'status':'up',
        'peer_type' : 'sbfd initiator',
        'multiplier': '3'
    }
    mode = 'sbfd-init-v4'
    check_bfd_session_status(mode, check_field, True, False)
    mode = 'sbfd-init-v6'
    check_bfd_session_status(mode, check_field, True, False)

    check_field = {
        'status':'up',
        'peer_type' : 'echo',
        'multiplier': '3'
    }
    mode = 'sbfd-echo-v4'
    check_bfd_session_status(mode, check_field, True, False)
    mode = 'sbfd-echo-v6'
    check_bfd_session_status(mode, check_field, True, False)

    # step 7 : check del sbfd sbfd-echo-v4/sbfd-echo-v6/sbfd-init-v6
    st.log("step 1.7 check del sbfd sbfd-echo-v4/sbfd-echo-v6/sbfd-init-v6:") 
    check_field = {}
    mode = 'sbfd-init-v4'
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    mode = 'sbfd-init-v6'
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)
    
    mode = 'sbfd-echo-v4'
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    mode = 'sbfd-echo-v6'
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    # step 8 : check appdb is clear
    st.log("step 1.8 check appdb is clear:")
    show_appdb_table_info(dut1, '*BFD*')
    show_appdb_table_info(dut2, '*BFD*')   
          

    # SBFD-BASIC-EXCP-002   
    # step 1 : Deprecation Routing
    st.log("step 2.1 Deprecation Routing:")
    st.config(dut1, 'cli -c "config t" -c "no ipv6 route fd00:303:2022::/48 fd00:100::59"')
    st.wait(5)

    # step 2: config sbfd sbfd-echo-v4/sbfd-echo-v6/sbfd-init-v6
    st.log("step 1.1 config sbfd sbfd-echo-v4/sbfd-echo-v6/sbfd-init-v4/sbfd-init-v6:")
    config_peer_bfd('sbfd-echo-v4')
    st.wait(2)
    config_peer_bfd('sbfd-echo-v6')
    st.wait(2)
    config_peer_bfd('sbfd-init-v4')
    st.wait(2)
    config_peer_bfd('sbfd-init-v6')
    st.wait(70)

    st.log("step 2.2 check sbfd sbfd-echo-v4/sbfd-echo-v6/sbfd-init-v4/sbfd-init-v6:")
    check_field = {
        'status':'down',
        'peer_type' : 'sbfd initiator',
        'multiplier': '3'
    }
    mode = 'sbfd-init-v4'
    check_bfd_session_status(mode, check_field, True, False)
    mode = 'sbfd-init-v6'
    check_bfd_session_status(mode, check_field, True, False)

    check_field = {
        'status':'down',
        'peer_type' : 'echo',
        'multiplier': '3'
    }
    mode = 'sbfd-echo-v4'
    check_bfd_session_status(mode, check_field, True, False)
    mode = 'sbfd-echo-v6'
    check_bfd_session_status(mode, check_field, True, False)

    # step 3 : Restoring Routes
    st.log("step 2.3 Restoring Routes:")
    st.config(dut1, 'cli -c "config t" -c "ipv6 route fd00:303:2022::/48 fd00:100::59"')
    st.wait(70)

    # step 4 : check sbfd sbfd-echo-v4/sbfd-echo-v6/sbfd-init-v4/sbfd-init-v6 
    st.log("step 2.4 check sbfd sbfd-echo-v4/sbfd-echo-v6/sbfd-init-v4/sbfd-init-v6:")
    check_field = {
        'status':'up',
        'peer_type' : 'sbfd initiator',
        'multiplier': '3'
    }
    mode = 'sbfd-init-v4'
    check_bfd_session_status(mode, check_field, True, False)
    mode = 'sbfd-init-v6'
    check_bfd_session_status(mode, check_field, True, False)

    check_field = {
        'status':'up',
        'peer_type' : 'echo',
        'multiplier': '3'
    }
    mode = 'sbfd-echo-v4'
    check_bfd_session_status(mode, check_field, True, False)
    mode = 'sbfd-echo-v6'
    check_bfd_session_status(mode, check_field, True, False)

    # step 5 : check del sbfd sbfd-echo-v4/sbfd-echo-v6/sbfd-init-v4/sbfd-init-v6
    st.log("step 2.5 check del sbfd sbfd-echo-v4/sbfd-echo-v6/sbfd-init-v4/sbfd-init-v6:") 
    check_field = {}
    mode = 'sbfd-init-v4'
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    mode = 'sbfd-init-v6'
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)
    
    mode = 'sbfd-echo-v4'
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    mode = 'sbfd-echo-v6'
    del_peer_bfd(mode)
    check_bfd_session_status(mode, check_field, True, True)

    # step 6 : check appdb is clear
    st.log("step 2.6 check appdb is clear:")
    show_appdb_table_info(dut1, '*BFD*')
    show_appdb_table_info(dut2, '*BFD*')   

    st.report_pass('test_case_passed')