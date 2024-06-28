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
    command = redis.build(dut, redis.APPL_DB, 'keys "{}"'.format(table))
    output = st.show(dut, command, skip_tmpl=True)
    if output is '':
        st.report_fail("{} app DB has no {}".format(dut, table))
    st.log(output)
    return output

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
    # show bfd peers | grep 'peer 192.20.1.59 bfd-name BFD_SINGLE_V4_VRF bfd-mode bfd local-address 192.20.1.58 vrf Test1 interface PortChannel101' -A 20
    create_by_hardware = False
    cmd = 'cli -c "no page" -c "show bfd peers" | grep {} -A 20'.format('"'+bfd_session_key+'"')
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
    st.config(dut1, 'ping -c2 fd00:100::59')
    st.config(dut1, 'ping -c2 fd00:200::59 -I PortChannel101')
    st.config(dut1, 'ping -c2 20.20.20.59')
    st.config(dut1, 'ping -c2 2000::59')
    st.config(dut1, 'ping -c2 30.30.30.59 -I PortChannel101')
    st.config(dut1, 'ping -c2 3000::59 -I PortChannel101')

    st.config(dut2, 'ping -c2 192.10.1.58')
    st.config(dut2, 'ping -c2 192.20.1.58 -I PortChannel101')
    st.config(dut2, 'ping -c2 fd00:100::58')
    st.config(dut2, 'ping -c2 fd00:200::58 -I PortChannel101')
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
            configdb_onefield_checkpoint(dut1, configdb_key, "peer", "192.10.1.59", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "enabled", "true", True, checkpoint)

        elif configdb_key == 'BFD_PEER|BFD_SINGLE_V6_VRF':
            configdb_onefield_checkpoint(dut2, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "interface", "PortChannel100", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "multihop", "false", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "peer", "192.10.1.58", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "enabled", "true", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "vrf", "Test1", True, checkpoint)
    elif bfd_mode == 'bfd-multi-v4': 
        if configdb_key == 'BFD_PEER|BFD_MULTI_V4_DEFAULT':
            configdb_onefield_checkpoint(dut1, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "interface", "PortChannel100", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "multihop", "True", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "peer", "192.10.1.59", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "enabled", "true", True, checkpoint)

            configdb_onefield_checkpoint(dut2, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "interface", "PortChannel100", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "multihop", "True", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "peer", "192.10.1.58", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "enabled", "true", True, checkpoint)

        elif configdb_key == 'BFD_PEER|BFD_MULTI_V4_VRF':
            configdb_onefield_checkpoint(dut1, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "multihop", "True", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "peer", "192.20.1.59", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "enabled", "true", True, checkpoint)
            configdb_onefield_checkpoint(dut1, configdb_key, "vrf", "Test1", True, checkpoint)  

            configdb_onefield_checkpoint(dut2, configdb_key, "mode", "bfd", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "multihop", "True", True, checkpoint)
            configdb_onefield_checkpoint(dut2, configdb_key, "peer", "192.20.1.58", True, checkpoint)
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
    elif bfd_mode == 'sbfd-init-v6':
            configdb_onefield_checkpoint(dut1, configdb_key, "mode", "sbfd-init", True, checkpoint)
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
        key = 'peer 192.20.1.59 bfd-name BFD_SINGLE_V4_VRF bfd-mode bfd local-address 192.20.1.58 vrf Test1 interface PortChannel101'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("step 2 dut1 test_bfd_ipv4_single_hop_case1 vrf Test1 failed")

        key = 'peer 192.20.1.58 bfd-name BFD_SINGLE_V4_VRF bfd-mode bfd local-address 192.20.1.59 vrf Test1 interface PortChannel101'
        ret = double_check_bfd_session(dut2, key, check_field, offload, delete)
        if not ret:
            st.report_fail("step 2 dut2 test_bfd_ipv4_single_hop_case1 vrf Test1 failed")

        key = 'peer 192.10.1.59 bfd-name BFD_SINGLE_V4_DEFAULT bfd-mode bfd local-address 192.10.1.58 vrf Default interface PortChannel100'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("step 2 dut1 test_bfd_ipv4_single_hop_case1 vrf default failed")

        key = 'peer 192.10.1.58 bfd-name BFD_SINGLE_V4_DEFAULT bfd-mode bfd local-address 192.10.1.59 vrf Default interface PortChannel100'
        ret = double_check_bfd_session(dut2, key, check_field, offload, delete)
        if not ret:
            st.report_fail("step 2 dut2 test_bfd_ipv4_single_hop_case1 vrf default failed")
    elif bfd_mode == 'bfd-single-v6':
        key = 'peer fd00:200::59 bfd-name BFD_SINGLE_V6_VRF bfd-mode bfd local-address fd00:200::58 vrf Test1 interface PortChannel101'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("step 2 dut1 test_bfd_ipv6_single_hop_case1 vrf Test1 failed")

        key = 'peer fd00:200::58 bfd-name BFD_SINGLE_V6_VRF bfd-mode bfd local-address fd00:200::59 vrf Test1 interface PortChannel101'
        ret = double_check_bfd_session(dut2, key, check_field, offload, delete)
        if not ret:
            st.report_fail("step 2 dut2 test_bfd_ipv6_single_hop_case1 vrf Test1 failed")

        key = 'peer fd00:100::59 bfd-name BFD_SINGLE_V6_DEFAULT bfd-mode bfd local-address fd00:100::58 vrf Default interface PortChannel100'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("step 2 dut1 test_bfd_ipv6_single_hop_case1 vrf default failed")

        key = 'peer fd00:100::58 bfd-name BFD_SINGLE_V6_DEFAULT bfd-mode bfd local-address fd00:100::59 vrf Default interface PortChannel100'
        ret = double_check_bfd_session(dut2, key, check_field, offload, delete)
        if not ret:
            st.report_fail("step 2 dut2 test_bfd_ipv6_single_hop_case1 vrf default failed")
    elif bfd_mode == 'bfd-multi-v4':
        key = 'peer 192.20.1.59 bfd-name BFD_MULTI_V4_VRF bfd-mode bfd local-address 192.20.1.58 vrf Test1 interface PortChannel101'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("step 2 dut1 test_bfd_ipv4_multi_hop_case3 vrf Test1 failed")

        key = 'peer 192.20.1.58 bfd-name BFD_MULTI_V4_VRF bfd-mode bfd local-address 192.20.1.59 vrf Test1 interface PortChannel101'
        ret = double_check_bfd_session(dut2, key, check_field, offload, delete)
        if not ret:
            st.report_fail("step 2 dut2 test_bfd_ipv4_multi_hop_case3 vrf Test1 failed")

        key = 'peer 192.10.1.59 bfd-name BFD_MULTI_V4_DEFAULT bfd-mode bfd local-address 192.10.1.58 vrf Default interface PortChannel100'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("step 2 dut1 test_bfd_ipv4_multi_hop_case3 vrf default failed")

        key = 'peer 192.10.1.58 bfd-name BFD_MULTI_V4_DEFAULT bfd-mode bfd local-address 192.10.1.59 vrf Default interface PortChannel100'
        ret = double_check_bfd_session(dut2, key, check_field, offload, delete)
        if not ret:
            st.report_fail("step 2 dut2 test_bfd_ipv4_multi_hop_case3 vrf default failed")
    elif bfd_mode == 'sbfd-echo-v4':
        key = 'peer 20.20.20.58 bfd-name SBFD_ECHO_V4_DEFAULT bfd-mode sbfd-echo local-address 20.20.20.58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 vrf Default'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("step 2 dut1 test_sbfd_echo_v4_case7 vrf Default failed")

    elif bfd_mode == 'sbfd-echo-v6':
        key = 'peer 2000::58 bfd-name SBFD_ECHO_V6_DEFAULT bfd-mode sbfd-echo local-address 2000::58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 vrf Default'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("step 2 dut1 test_sbfd_echo_v6_case8 vrf Default failed")

    elif bfd_mode == 'sbfd-init-v4':
        key = 'peer 20.20.20.59 bfd-name SBFD_INIT_V4_DEFAULT bfd-mode sbfd-init local-address 20.20.20.58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 vrf Default'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("step 2 dut1 test_sbfd_init_v4_case5 vrf Default failed")

    elif bfd_mode == 'sbfd-init-v6':
        key = 'peer 2000::59 bfd-name SBFD_INIT_V6_DEFAULT bfd-mode sbfd-init local-address 2000::58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 remote-discr 10087 vrf Default'
        ret = double_check_bfd_session(dut1, key, check_field, offload, delete)
        if not ret:
            st.report_fail("step 2 dut1 test_sbfd_init_v6_case6 vrf Default failed")
    else:
        st.log("check_bfd_session_status: wrong bfd mode type")

def del_peer_bfd(bfd_mode):
    if bfd_mode == 'bfd-single-v4':
        #default
        st.config(dut1, "cli -c 'configure terminal' -c 'no bfd name BFD_SINGLE_V4_DEFAULT'")
        st.config(dut2, "cli -c 'configure terminal' -c 'no bfd name BFD_SINGLE_V4_DEFAULT'")
        #vrf
        st.config(dut1, "cli -c 'configure terminal' -c 'no bfd name BFD_SINGLE_V4_VRF'")
        st.config(dut2, "cli -c 'configure terminal' -c 'no bfd name BFD_SINGLE_V4_VRF'")
    elif bfd_mode == 'bfd-single-v6':
        #default
        st.config(dut1, "cli -c 'configure terminal' -c 'no bfd name BFD_SINGLE_V6_DEFAULT'")
        st.config(dut2, "cli -c 'configure terminal' -c 'no bfd name BFD_SINGLE_V6_DEFAULT'")
        #vrf
        st.config(dut1, "cli -c 'configure terminal' -c 'no bfd name BFD_SINGLE_V6_VRF'")
        st.config(dut2, "cli -c 'configure terminal' -c 'no bfd name BFD_SINGLE_V6_VRF'")
    elif bfd_mode == 'bfd-multi-v4':
        #default
        st.config(dut1, "cli -c 'configure terminal' -c 'no bfd name BFD_MULTI_V4_DEFAULT'")
        st.config(dut2, "cli -c 'configure terminal' -c 'no bfd name BFD_MULTI_V4_DEFAULT'")
        #vrf
        st.config(dut1, "cli -c 'configure terminal' -c 'no bfd name BFD_MULTI_V4_VRF'")
        st.config(dut2, "cli -c 'configure terminal' -c 'no bfd name BFD_MULTI_V4_VRF'")
    elif bfd_mode == 'sbfd-echo-v4':
        #sbfd-echo v4
        st.config(dut1, "cli -c 'configure terminal' -c 'no bfd name SBFD_ECHO_V4_DEFAULT'")
    elif bfd_mode == 'sbfd-echo-v6':
        #sbfd-echo v6
        st.config(dut1, "cli -c 'configure terminal' -c 'no bfd name SBFD_ECHO_V6_DEFAULT'")
    elif bfd_mode == 'sbfd-init-v4':
        #sbfd-init v4
        st.config(dut1, "cli -c 'configure terminal' -c 'no bfd name SBFD_INIT_V4_DEFAULT'")
    elif bfd_mode == 'sbfd-init-v6':
        #sbfd-init v6
        st.config(dut1, "cli -c 'configure terminal' -c 'no bfd name SBFD_INIT_V6_DEFAULT'")
    
                
def config_peer_bfd(bfd_mode):
    # sbfd only need test vrf default
    if bfd_mode == 'sbfd-echo-v4':
        st.config(dut1, "cli -c 'configure terminal' -c \
                  'bfd peer 20.20.20.58 bfd-name SBFD_ECHO_V4_DEFAULT bfd-mode sbfd-echo status enable \
                  local-address 20.20.20.58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58'")
    elif bfd_mode == 'sbfd-echo-v6':
        st.config(dut1, "cli -c 'configure terminal' -c \
                  'bfd peer 2000::58 bfd-name SBFD_ECHO_V6_DEFAULT bfd-mode sbfd-echo status enable \
                  local-address 2000::58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58'")
    elif bfd_mode == 'sbfd-init-v4':
        st.config(dut1, "cli -c 'configure terminal' -c \
                  'bfd peer 20.20.20.59 bfd-name SBFD_INIT_V4_DEFAULT bfd-mode sbfd-init status enable \
                  local-address 20.20.20.58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 remote-discr 10086'")
        st.config(dut2, "cli -c 'configure terminal' -c 'sbfd reflector source-address 20.20.20.59 discriminator 10086'")
    elif bfd_mode == 'sbfd-init-v6':
        st.config(dut1, "cli -c 'configure terminal' -c \
                  'bfd peer 2000::59 bfd-name SBFD_INIT_V6_DEFAULT bfd-mode sbfd-init status enable \
                  local-address 2000::58 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 remote-discr 10087'")
        st.config(dut2, "cli -c 'configure terminal' -c 'sbfd reflector source-address 2000::59 discriminator 10087'")
    elif bfd_mode == 'bfd-single-v4':
        #default
        st.config(dut1, "cli -c 'configure terminal' -c \
                  'bfd peer 192.10.1.59 bfd-name BFD_SINGLE_V4_DEFAULT bfd-mode bfd status enable interface PortChannel100'")
        st.config(dut2, "cli -c 'configure terminal' -c \
                  'bfd peer 192.10.1.58 bfd-name BFD_SINGLE_V4_DEFAULT bfd-mode bfd status enable interface PortChannel100'")
        #vrf
        st.config(dut1, "cli -c 'configure terminal' -c \
                  'bfd peer 192.20.1.59 bfd-name BFD_SINGLE_V4_VRF bfd-mode bfd status enable interface PortChannel101 vrf Test1'")
        st.config(dut2, "cli -c 'configure terminal' -c \
                  'bfd peer 192.20.1.58 bfd-name BFD_SINGLE_V4_VRF bfd-mode bfd status enable interface PortChannel101 vrf Test1'")
    elif bfd_mode == 'bfd-single-v6':
        #default
        st.config(dut1, "cli -c 'configure terminal' -c \
                  'bfd peer fd00:100::59 bfd-name BFD_SINGLE_V6_DEFAULT bfd-mode bfd status enable interface PortChannel100'")
        st.config(dut2, "cli -c 'configure terminal' -c \
                  'bfd peer fd00:100::58 bfd-name BFD_SINGLE_V6_DEFAULT bfd-mode bfd status enable interface PortChannel100'")
        #vrf
        st.config(dut1, "cli -c 'configure terminal' -c \
                  'bfd peer fd00:200::59 bfd-name BFD_SINGLE_V6_DEFAULT bfd-mode bfd status enable interface PortChannel101 vrf Test1'")
        st.config(dut2, "cli -c 'configure terminal' -c \
                  'bfd peer fd00:200::58 bfd-name BFD_SINGLE_V6_DEFAULT bfd-mode bfd status enable interface PortChannel101 vrf Test1'")
    elif bfd_mode == 'bfd-multi-v4':
        #default
        st.config(dut1, "cli -c 'configure terminal' -c \
                  'bfd peer 192.10.1.59 bfd-name BFD_MULTI_V4_DEFAULT bfd-mode bfd status enable local-address 192.10.1.58'")
        st.config(dut2, "cli -c 'configure terminal' -c \
                  'bfd peer 192.10.1.58 bfd-name BFD_MULTI_V4_DEFAULT bfd-mode bfd status enable local-address 192.10.1.59'")
        #vrf
        st.config(dut1, "cli -c 'configure terminal' -c \
                  'bfd peer 192.20.1.59 bfd-name BFD_MULTI_V4_VRF bfd-mode bfd status enable local-address 192.20.1.58 vrf Test1'")
        st.config(dut2, "cli -c 'configure terminal' -c \
                  'bfd peer 192.20.1.58 bfd-name BFD_MULTI_V4_VRF bfd-mode bfd status enable local-address 192.20.1.59 vrf Test1'")
    elif bfd_mode == 'bfd-multi-v6':
        #default
        st.config(dut1, "cli -c 'configure terminal' -c \
                  'bfd peer fd00:100::59 bfd-name BFD_MULTI_V6_DEFAULT bfd-mode bfd status enable local-address fd00:100::58'")
        st.config(dut2, "cli -c 'configure terminal' -c \
                  'bfd peer fd00:100::58 bfd-name BFD_MULTI_V6_DEFAULT bfd-mode bfd status enable local-address fd00:100::59'")
        #vrf
        st.config(dut1, "cli -c 'configure terminal' -c \
                  'bfd peer fd00:200::59 bfd-name BFD_MULTI_V6_DEFAULT bfd-mode bfd status enable local-address fd00:200::58 vrf Test1'")
        st.config(dut2, "cli -c 'configure terminal' -c \
                  'bfd peer fd00:200::58 bfd-name BFD_MULTI_V6_DEFAULT bfd-mode bfd status enable local-address fd00:200::59 vrf Test1'")
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

    if st.get_func_name(request) in  ["test_bfd_ipv4_single_hop_case1", "test_sbfd_init_v6_case6",
                                      "test_sbfd_echo_v4_case7", "test_sbfd_echo_v6_case8"]:
        st.log("bfd_basic_config case enter ")
        if data.load_basic_config_done == False:
            load_json_config('bfd_basic_config')
            st.wait(120)
            data.load_basic_config_done = True
        
        # ping each other to learn nd and arp 
        learn_arp_by_ping()
    
        # # check
        # st.show(dut1, "vtysh -c 'show sr-te policy detail'", skip_tmpl=True)
        # # check
        # st.show(dut1, 'ip neigh show', skip_tmpl=True)

        # show_appdb_tbale_info(dut1, '*SRV6_MY_SID_TABLE*')
        # show_appdb_tbale_info(dut2, '*SRV6_MY_SID_TABLE*')
    
    # if st.get_func_name(request) in  ["test_bfd_for_static_route_case8"]:
    #     st.log("static_bfd_config case enter ")
    #     if data.load_static_config_done == False:
    #         load_json_config('static_bfd_config')
    #         st.wait(120)
    #         data.load_static_config_done = True
    # #load TG config

    yield
    pass

# BFD-BASIC-FUNC-001
@pytest.mark.community
@pytest.mark.community_pass
def test_bfd_ipv4_single_hop_case1():
    st.banner("test_bfd_ipv4_single_hop_case1 begin")
    # step 1: config bfd ipv4 single hop
    mode = 'bfd-single-v4'
    config_peer_bfd(mode)
    st.wait(5)

   # step 2 : check bfd ipv4 single hop    
    check_field = {
        'status':'up',
        'peer_type' : 'configured',
        'multiplier': '3'
    }

    check_bfd_session_status(mode, check_field, True, False)

    # step3: check configdb
    #  127.0.0.1:6379[4]> hgetall BFD_PEER|BFD_SINGLE_V4_DEFAULT
    #  1) "mode"
    #  2) "bfd"
    #  3) "interface"
    #  4) "PortChannel100"
    #  5) "multihop"
    #  6) "false"
    #  7) "peer"
    #  8) "192.10.1.59"
    #  9) "enabled"
    # 10) "true"
    # 127.0.0.1:6379[4]> hgetall BFD_PEER|BFD_SINGLE_V4_VRF
    #  1) "mode"
    #  2) "bfd"
    #  3) "interface"
    #  4) "PortChannel101"
    #  5) "multihop"
    #  6) "false"
    #  7) "peer"
    #  8) "192.20.1.59"
    #  9) "vrf"
    # 10) "Test1"
    # 11) "enabled"
    # 12) "true"
    # 127.0.0.1:6379[4]> 
    configdb_key = "BFD_PEER|BFD_SINGLE_V4_DEFAULT"
    checkpoint_msg = "test_bfd_ipv4_single_hop_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, True, checkpoint_msg)

    configdb_key = "BFD_PEER|BFD_SINGLE_V4_VRF"
    checkpoint_msg = "test_bfd_ipv4_single_hop_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, True, checkpoint_msg)

    # step 4 : modify interval and multiplier
    #default
    st.config(dut1, "cli -c 'configure terminal' -c \
                'bfd peer 192.10.1.59 bfd-name BFD_SINGLE_V4_DEFAULT bfd-mode bfd status enable interface PortChannel100 detection-multiplier 5 min-receive 100 min-tx-interval 100'")
    st.config(dut2, "cli -c 'configure terminal' -c \
                'bfd peer 192.10.1.58 bfd-name BFD_SINGLE_V4_DEFAULT bfd-mode bfd status enable interface PortChannel100 detection-multiplier 5 min-receive 100 min-tx-interval 100'")
    #vrf
    st.config(dut1, "cli -c 'configure terminal' -c \
                'bfd peer 192.20.1.59 bfd-name BFD_SINGLE_V4_VRF bfd-mode bfd status enable interface PortChannel101 vrf Test1 detection-multiplier 5 min-receive 100 min-tx-interval 100'")
    st.config(dut2, "cli -c 'configure terminal' -c \
                'bfd peer 192.20.1.58 bfd-name BFD_SINGLE_V4_VRF bfd-mode bfd status enable interface PortChannel101 vrf Test1 detection-multiplier 5 min-receive 100 min-tx-interval 100'")  
    check_field = {
        'status':'up',
        'peer_type' : 'configured',
        'multiplier': '5'
    }

    check_bfd_session_status(mode, check_field, True, False)

    # check configdb
    configdb_key = "BFD_PEER|BFD_SINGLE_V4_DEFAULT"
    checkpoint_msg = "test_bfd_ipv4_single_hop_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, False, checkpoint_msg)

    configdb_key = "BFD_PEER|BFD_SINGLE_V4_VRF"
    checkpoint_msg = "test_bfd_ipv4_single_hop_case1 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, False, checkpoint_msg)

    # step 5 : check del bfd ipv4 single 
    del_peer_bfd(mode)
    check_field = {}
    check_bfd_session_status(mode, check_field, True, True)
        
    # step 6 : check appdb is clear

    st.report_pass('test_case_passed')


# BFD-BASIC-FUNC-001
# @pytest.mark.community
# @pytest.mark.community_pass
# def test_bfd_ipv6_single_hop_case2():
#     st.report_pass('test_case_passed')

# # BFD-BASIC-FUNC-002
# @pytest.mark.community
# @pytest.mark.community_pass
# def test_bfd_ipv4_multi_hop_case3():
#     st.report_pass('test_case_passed')

# # BFD-BASIC-FUNC-002
# @pytest.mark.community
# @pytest.mark.community_pass
# def test_bfd_ipv6_multi_hop_case3():
#     st.report_pass('test_case_passed')

# # BFD-BASIC-FUNC-003
# @pytest.mark.community
# @pytest.mark.community_pass
# def test_bfd_mix_case4():
#     st.report_pass('test_case_passed')

# # SBFD-BASIC-FUNC-001
# @pytest.mark.community
# @pytest.mark.community_pass
# def test_sbfd_init_v4_case5():
#     st.report_pass('test_case_passed')

# SBFD-BASIC-FUNC-001
@pytest.mark.community
@pytest.mark.community_pass
def test_sbfd_init_v6_case6():
    st.banner("test_sbfd_init_v6_case6 begin")
    # step 1: config sbfd-init ipv6
    mode = 'sbfd-init-v6'
    config_peer_bfd(mode)
    st.wait(5)

   # step 2 : check sbfd-init ipv6    
    check_field = {
        'status':'up',
        'peer_type' : 'sbfd initiator',
        'multiplier': '3'
    }

    check_bfd_session_status(mode, check_field, True, False)

    # step3: check configdb
    # 127.0.0.1:6379[4]> hgetall "BFD_PEER|SBFD_INIT_V6_DEFAULT"
    #  1) "mode"
    #  2) "sbfd-init"
    #  3) "segment-list"
    #  4) "fd00:303:2022:fff1:eee::"
    #  5) "source-ipv6"
    #  6) "2000::58"
    #  7) "remote-discr"
    #  8) "10087"
    #  9) "local-address"
    # 10) "2000::58"
    # 11) "multihop"
    # 12) "false"
    # 13) "peer"
    # 14) "2000::59"
    # 15) "enabled"
    # 16) "true"
    # 127.0.0.1:6379[4]> 
    configdb_key = "BFD_PEER|SBFD_INIT_V6_DEFAULT"
    checkpoint_msg = "test_sbfd_init_v6_case6 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, True, checkpoint_msg)

    # step 4 : modify interval and multiplier
    st.config(dut1, "cli -c 'configure terminal' -c \
                'bfd peer 2000::59 bfd-name SBFD_INIT_V6_DEFAULT bfd-mode sbfd-init status enable local-address 2000::58 \
                 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 remote-discr 10087 detection-multiplier 5 min-receive 100 min-tx-interval 100'")
    
    check_field = {
        'status':'up',
        'peer_type' : 'sbfd initiator',
        'multiplier': '5'
    }

    check_bfd_session_status(mode, check_field, True, False)

    # check configdb
    configdb_key = "BFD_PEER|SBFD_INIT_V6_DEFAULT"
    checkpoint_msg = "test_sbfd_init_v6_case6 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, False, checkpoint_msg)

    # step 5 : check del sbfd-init ipv6
    del_peer_bfd(mode)
    check_field = {}
    check_bfd_session_status(mode, check_field, True, True)
        
    # step 6 : check appdb is clear
    st.report_pass('test_case_passed')

# SBFD-BASIC-FUNC-002
@pytest.mark.community
@pytest.mark.community_pass
def test_sbfd_echo_v4_case7():
    st.banner("test_sbfd_echo_v4_case7 begin")
    # step 1: config sbfd-echo ipv4
    mode = 'sbfd-echo-v4'
    config_peer_bfd(mode)

    # sbfd echo session offload delay 1min
    st.wait(70)

   # step 2 : check sbfd-echo ipv4    
    check_field = {
        'status':'up',
        'peer_type' : 'echo',
        'multiplier': '3'
    }

    check_bfd_session_status(mode, check_field, True, False)

    # step3: check configdb
    # 127.0.0.1:6379[4]> hgetall "BFD_PEER|SBFD_ECHO_V4_DEFAULT"
    #  1) "mode"
    #  2) "sbfd-echo"
    #  3) "segment-list"
    #  4) "fd00:303:2022:fff1:eee::"
    #  5) "source-ipv6"
    #  6) "2000::58"
    #  7) "local-address"
    #  8) "20.20.20.58"
    #  9) "multihop"
    # 10) "false"
    # 11) "peer"
    # 12) "20.20.20.58"
    # 13) "enabled"
    # 14) "true"
    # 127.0.0.1:6379[4]> 
    configdb_key = "BFD_PEER|SBFD_ECHO_V4_DEFAULT"
    checkpoint_msg = "test_sbfd_echo_v4_case7 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, True, checkpoint_msg)

    # step 4 : modify interval and multiplier
    st.config(dut1, "cli -c 'configure terminal' -c \
                'bfd peer 20.20.20.58 bfd-name SBFD_ECHO_V4_DEFAULT bfd-mode sbfd-echo status enable local-address 20.20.20.58 \
                 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 detection-multiplier 5 min-receive 100 min-tx-interval 100'")

    check_field = {
        'status':'up',
        'peer_type' : 'echo',
        'multiplier': '5'
    }

    check_bfd_session_status(mode, check_field, True, False)

    # check configdb
    configdb_key = "BFD_PEER|SBFD_ECHO_V4_DEFAULT"
    checkpoint_msg = "test_sbfd_echo_v4_case7 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, False, checkpoint_msg)

    # step 5 : check del sbfd-echo ipv4
    del_peer_bfd(mode)
    check_field = {}
    check_bfd_session_status(mode, check_field, True, True)
        
    # step 6 : check appdb is clear

    st.report_pass('test_case_passed')

# SBFD-BASIC-FUNC-002
@pytest.mark.community
@pytest.mark.community_pass
def test_sbfd_echo_v6_case8():
    st.banner("test_sbfd_echo_v6_case8 begin")
    # step 1: config sbfd-echo ipv6
    mode = 'sbfd-echo-v6'
    config_peer_bfd(mode)
    
    # sbfd echo session offload delay 1min
    st.wait(70)

   # step 2 : check sbfd-echo ipv6    
    check_field = {
        'status':'up',
        'peer_type' : 'echo',
        'multiplier': '3'
    }

    check_bfd_session_status(mode, check_field, True, False)

    # step3: check configdb
    # 127.0.0.1:6379[4]> hgetall "BFD_PEER|SBFD_ECHO_V6_DEFAULT"
    #  1) "mode"
    #  2) "sbfd-echo"
    #  3) "segment-list"
    #  4) "fd00:303:2022:fff1:eee::"
    #  5) "source-ipv6"
    #  6) "2000::58"
    #  7) "local-address"
    #  8) "2000::58"
    #  9) "multihop"
    # 10) "false"
    # 11) "peer"
    # 12) "2000::58"
    # 13) "enabled"
    # 14) "true"
    configdb_key = "BFD_PEER|SBFD_ECHO_V6_DEFAULT"
    checkpoint_msg = "test_sbfd_echo_v6_case8 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, True, checkpoint_msg)

    # step 4 : modify interval and multiplier
    st.config(dut1, "cli -c 'configure terminal' -c \
                'bfd peer 2000::58 bfd-name SBFD_ECHO_V6_DEFAULT bfd-mode sbfd-echo status enable local-address 2000::58 \
                 segment-list fd00:303:2022:fff1:eee:: source-ipv6 2000::58 detection-multiplier 5 min-receive 100 min-tx-interval 100'")
    
    check_field = {
        'status':'up',
        'peer_type' : 'echo',
        'multiplier': '5'
    }

    check_bfd_session_status(mode, check_field, True, False)

    # check configdb
    configdb_key = "BFD_PEER|SBFD_ECHO_V6_DEFAULT"
    checkpoint_msg = "test_sbfd_echo_v6_case8 config {} check failed.".format(configdb_key)
    check_bfd_session_configdb(mode, configdb_key, False, checkpoint_msg)

    # step 5 : check del sbfd-echo ipv6
    del_peer_bfd(mode)
    check_field = {}
    check_bfd_session_status(mode, check_field, True, True)
        
    # step 6 : check appdb is clear

    st.report_pass('test_case_passed')
