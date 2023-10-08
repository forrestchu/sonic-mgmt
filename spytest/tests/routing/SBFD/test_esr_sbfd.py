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
from sbfd_vars import data
from SRv6.ixia_vars import *
from SRv6.ixia_helper import *

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
data.load_base_config_done = False

def load_json_config(filesuffix=''):
    curr_path = os.getcwd()

    json_file_dut1_multi_vrf = curr_path+"/routing/SRv6/dut1_"+filesuffix+".json"
    json_file_dut2_multi_vrf = curr_path+"/routing/SRv6/dut2_"+filesuffix+".json"

    st.apply_files(dut1, [json_file_dut1_multi_vrf], method="replace_configdb")
    st.apply_files(dut2, [json_file_dut2_multi_vrf], method="replace_configdb")

    st.wait(10)
    st.reboot([dut1, dut2])
    st.banner("%s json config loaded completed" % (filesuffix))

def show_appdb_tbale_info(dut, table):
    command = redis.build(dut, redis.APPL_DB, 'keys "{}"'.format(table))
    output = st.show(dut, command, skip_tmpl=True)
    if output is '':
        st.report_fail("{} app DB has no {}".format(dut, table))
    st.log(output)

def config_sbfd(dut, policy, sbfd_cli):
    st.config(dut, "cli -c 'configure terminal' \
              -c 'segment-routing' \
              -c 'traffic-eng' \
              -c '{}' \
              -c '{}'".format(policy, sbfd_cli))

def double_check_sbfd(dut, sbfd_key, sbfd_check_filed, offload=True, delete=False):
    # show bfd peers | grep 'peer 20.20.20.58 (endpoint 20.20.20.58 color 1 sidlist sl1_ipv4) local-address 20.20.20.58' -A 20
    cmd = "show bfd peers | grep '{}' -A 20".format(sbfd_key)
    output = st.show(dut, cmd, type='vtysh')
    st.log (output)

    st.wait(10)
    output = st.show(dut, cmd, type='vtysh')
    st.log (output)

    # show bfd peers counters | grep 'peer 20.20.20.58 (endpoint 20.20.20.58 color 1 sidlist sl1_ipv4) local-address 20.20.20.58' -A 7
    count_cmd = "show bfd peers counters | grep '{}' -A 7".format(sbfd_key)
    output = st.show(dut, count_cmd, type='vtysh')
    st.log (output)

    if offload:
        # check appdb ,check hardware flag
        pass
    
    return True

def save_config_and_reboot(dut):
    cmd = "cli -c 'config t' -c 'copy running-config startup-config'"
    st.config(dut, cmd)
    st.log("start reboot")
    st.reboot(dut)
    st.wait(5) 
    st.log("finish reboot")

@pytest.fixture(scope="module", autouse=True)
def sbfd_module_hooks(request):
    #add things at the start of this module
    ixia_controller_init()
    yield
    ixia_stop_all_protocols()
    ixia_controller_deinit()

@pytest.fixture(scope="function", autouse=True)
def sbfd_func_hooks(request):
    # add things at the start every test case

    if st.get_func_name(request) in  ["test_sbfd_echo_single_endx_case1","test_sbfd_echo_two_endx_case2",
                                      "test_sbfd_echo_ms_path_case3"]:
        st.log("sbfd_base_config case enter ")
        if data.load_base_config_done == False:
            load_json_config('sbfd_base_config')
            st.wait(30)
            data.load_base_config_done = True
        
        # ping each other to learn nd and arp 
        st.config(dut1, 'ping -c2 2000::59')
        st.config(dut2, 'ping -c2 2000::58')
        st.config(dut1, 'ping -c2 20.20.20.59')
        st.config(dut2, 'ping -c2 20.20.20.58')
        
        st.show(dut1, "vtysh -c 'show bfd nd infos'", skip_tmpl=True)
        # check
        st.show(dut1, "vtysh -c 'show bfd sr endx infos'", skip_tmpl=True)
        # check
        st.show(dut1, "vtysh -c 'show sr-te policy detail'", skip_tmpl=True)
        # check
        st.show(dut1, 'ip neigh show', skip_tmpl=True)

        show_appdb_tbale_info(dut1, 'SRV6_MY_SID_TABLE')
        show_appdb_tbale_info(dut2, 'SRV6_MY_SID_TABLE')
        
    #load TG config

    yield
    pass


@pytest.mark.community
@pytest.mark.community_pass
def test_sbfd_echo_single_endx_case1():

    st.banner("test_sbfd_echo_single_endx_case1 begin")
    
    police_v4 = 'policy color 1 endpoint 2000::59'
    police_v6 = 'policy color 2 endpoint 2000::59'
    # step 1 : config sbfd echo
    config_sbfd(dut1, police_v4, 'sbfd echo source-address 20.20.20.58')

    # step 2 : check sbfd echo    
    check_filed = {
        'Status':'up',
        'Peer Type' : 'echo',
        'Detect-multiplier': '3',
        'Echo transmission interval' : '300' 
    }
    for key in data['policy_sbfd'][police_v4]:
        ret = double_check_sbfd(dut1, key, check_filed, False, False)
        if not ret:
            st.report_fail("step 2 test_sbfd_echo_single_endx_case1 failed")

    # step 3 : check configdb , single endx ipv4 cannot offload ,so has no bfd appdb
#127.0.0.1:6379[4]> hgetall SRV6_POLICY|1|2000::59
#  1) "cpath@"
#  2) "100|cp1_ipv4|sl1_ipv4|1"
#  3) "NULL"
#  4) "NULL"
#  5) "sbfd_type"
#  6) "echo"
#  7) "sbfd_update_source"
#  8) "20.20.20.58"
#  9) "sbfd_detect_multiplier"
# 10) "3"
# 11) "sbfd_rx_timer"
# 12) "100"
# 13) "sbfd_tx_timer"
# 14) "100"
# 127.0.0.1:6379[4]>

    # step 4 : modify interval
    config_sbfd(dut1, police_v4, 'sbfd echo source-address 20.20.20.58 3 100 100')   
    check_filed = {
        'Status':'up',
        'Peer Type' : 'echo',
        'Detect-multiplier': '3',
        'Echo transmission interval' : '100' 
    }
    for key in data['policy_sbfd'][police_v4]:
        ret = double_check_sbfd(dut1, key, check_filed, False, False) 
        if not ret:
            st.report_fail("step 4 test_sbfd_echo_single_endx_case1 failed")

    # step 5 : check del sbfd echo 
    config_sbfd(dut1, police_v4, 'no sbfd echo')
    check_filed = {}
    for key in data['policy_sbfd'][police_v4]:
        ret = double_check_sbfd(dut1, key, check_filed, False, True) 
        if not ret:
            st.report_fail("step 5 test_sbfd_echo_single_endx_case1 failed")


    # step 6 : config ipv6 single endx sbfd echo
    config_sbfd(dut1, police_v6, 'sbfd echo source-address 2000::58')

    # step 7 : check sbfd echo
    check_filed = {
        'Status':'up',
        'Peer Type' : 'echo',
        'Detect-multiplier': '3',
        'Echo transmission interval' : '300' 
    }
    for key in data['policy_sbfd'][police_v6]:
        ret = double_check_sbfd(dut1, key, check_filed, True, False)
        if not ret:
            st.report_fail("step 7 test_sbfd_echo_single_endx_case1 failed")

    # step 8 : check configdb and appdb
    
#127.0.0.1:6379[4]> hgetall SRV6_POLICY|1|2000::59
#  1) "cpath@"
#  2) "100|cp1_ipv6|sl2_ipv6|1"
#  3) "NULL"
#  4) "NULL"
#  5) "sbfd_type"
#  6) "echo"
#  7) "sbfd_update_source"
#  8) "2000::58"
#  9) "sbfd_detect_multiplier"
# 10) "3"
# 11) "sbfd_rx_timer"
# 12) "100"
# 13) "sbfd_tx_timer"
# 14) "100"
# 127.0.0.1:6379[4]>

# 127.0.0.1:6380> hgetall BFD_PEER:2000::56|73631234|4
#  1) "type"
#  2) "SBFD_ECHO"
#  3) "ttl"
#  4) "255"
#  5) "iphdr"
#  6) "6"
#  7) "detection-multiplier"
#  8) "3"
#  9) "udp-src-port"
# 10) "3784"
# 11) "udp-dst-port"
# 12) "3785"
# 13) "local-discriminator"
# 14) "73631234"
# 15) "remote-discriminator"
# 16) "73631234"
# 17) "min-receive"
# 18) "300000"
# 19) "min-tx-interval"
# 20) "300000"
# 21) "vrf"
# 22) "Default"
# 23) "src-ip"
# 24) "2000::56"
# 25) "dst-ip"
# 26) "2000::56"
# 27) "segment"
# 28) "sl5"

    # step 9 : modify interval
    config_sbfd(dut1, police_v6, 'sbfd echo source-address 2000::58 3 100 100')   
    check_filed = {
        'Status':'up',
        'Peer Type' : 'echo',
        'Detect-multiplier': '3',
        'Echo transmission interval' : '100' 
    }
    for key in data['policy_sbfd'][police_v6]:
        ret = double_check_sbfd(dut1, key, check_filed, True, False) 
        if not ret:
            st.report_fail("step 9 test_sbfd_echo_single_endx_case1 failed")

    
    st.show(dut1, "vtysh -c 'show sr-te policy detail'", skip_tmpl=True)

    # step 10 : check del sbfd echo 
    config_sbfd(dut1, police_v6, 'no sbfd echo')
    check_filed = {}
    for key in data['policy_sbfd'][police_v6]:
        ret = double_check_sbfd(dut1, key, check_filed, True, True) 
        if not ret:
            st.report_fail("step 10 test_sbfd_echo_single_endx_case1 failed")
        
    # step 11 : check appdb is clear

    st.report_pass("test_case_passed")


@pytest.mark.community
@pytest.mark.community_pass
def test_sbfd_echo_two_endx_case2():

    st.banner("test_sbfd_echo_two_endx_case2 begin")

    policy = 'policy color 8 endpoint 2000::59'

    # step 1 : config sbfd echo
    config_sbfd(dut1, policy, 'sbfd echo source-address 20.20.20.58')

    # step 2 : check sbfd echo
    check_filed = {
        'Status':'up',
        'Peer Type' : 'echo',
        'Detect-multiplier': '3',
        'Echo transmission interval' : '300' 
    }
    for key in data['policy_sbfd'][policy]:
        ret = double_check_sbfd(dut1, key, check_filed, True, False)
        if not ret:
            st.report_fail("step 2  test_sbfd_echo_two_endx_case2 failed")        

    # step 3 : check configdb and appdn, need offload
    st.show(dut1, "vtysh -c 'show sr-te policy detail'", skip_tmpl=True)

    # step 4 : modify interval
    config_sbfd(dut1, policy, 'sbfd echo source-address 20.20.20.58 3 100 100')   
    check_filed = {
        'Status':'up',
        'Peer Type' : 'echo',
        'Detect-multiplier': '3',
        'Echo transmission interval' : '100' 
    }
    for key in data['policy_sbfd'][policy]:
        ret = double_check_sbfd(dut1, key, check_filed, True, False)
        if not ret:
            st.report_fail("step 4 test_sbfd_echo_two_endx_case2 failed")   

    # step 5 : simulate fault
    
    st.show(dut1, "vtysh -c 'show sr-te policy detail'", skip_tmpl=True)

    # step 6 : check del sbfd echo 
    config_sbfd(dut1, policy, 'no sbfd echo')
    check_filed = {}
    for key in data['policy_sbfd'][policy]:
        ret = double_check_sbfd(dut1, key, check_filed, True, True)
        if not ret:
            st.report_fail("step 5 test_sbfd_echo_two_endx_case2 failed")   

    # step 7 : check appdb is clear

    st.report_pass("test_case_passed")


@pytest.mark.community
@pytest.mark.community_pass
def test_sbfd_echo_mspath_case3():

    st.banner("test_sbfd_echo_ms_path_case3 begin")

    policy_v4 = 'policy color 6 endpoint 2000::59'
    policy_v6 = 'policy color 7 endpoint 2000::59'

    # step 1 : config sbfd echo
    config_sbfd(dut1, policy_v4, 'sbfd echo source-address 20.20.20.58')
    config_sbfd(dut1, policy_v6, 'sbfd echo source-address 2000::58')

    # step 2 : check sbfd echo
    check_filed = {
        'Status':'up',
        'Peer Type' : 'echo',
        'Detect-multiplier': '3',
        'Echo transmission interval' : '300' 
    }

    for key in data['policy_sbfd'][policy_v4] + data['policy_sbfd'][policy_v6] :
        ret = double_check_sbfd(dut1, key, check_filed, True, False)
        if not ret:
            st.report_fail("step 2 test_sbfd_echo_mspath_case3 failed")

    # step 3 : simulate fault
    
    st.show(dut1, "vtysh -c 'show sr-te policy detail'", skip_tmpl=True)

    # step 4 : check del sbfd echo 
    config_sbfd(dut1, policy_v4, 'no sbfd echo')
    config_sbfd(dut1, policy_v6, 'no sbfd echo')
    check_filed = {}
    for key in data['policy_sbfd'][policy_v4] + data['policy_sbfd'][policy_v6] :
        ret = double_check_sbfd(dut1, key, check_filed, True, True)
        if not ret:
            st.report_fail("step 4 test_sbfd_echo_mspath_case3 failed")   

    # step 5 : check appdb is clear

    st.report_pass("test_case_passed")

@pytest.mark.community
@pytest.mark.community_pass
def test_sbfd_echo_loadbalancing_case4():

    st.banner("test_sbfd_loadbalancing_case4 begin")

    policy_v4 = 'policy color 3 endpoint 2000::59'
    policy_v6 = 'policy color 4 endpoint 2000::59'

    # step 1 : config sbfd echo
    config_sbfd(dut1, policy_v4, 'sbfd echo source-address 20.20.20.58')
    config_sbfd(dut1, policy_v6, 'sbfd echo source-address 2000::58')

    # step 2 : check sbfd echo
    check_filed = {
        'Status':'up',
        'Peer Type' : 'echo',
        'Detect-multiplier': '3',
        'Echo transmission interval' : '300' 
    }
    for key in data['policy_sbfd'][policy_v4] + data['policy_sbfd'][policy_v6] :
        ret = double_check_sbfd(dut1, key, check_filed, True, False)
        if not ret:
            st.report_fail("step 2 test_sbfd_loadbalancing_case4 failed")


    # step 3 : simulate fault
    
    st.show(dut1, "vtysh -c 'show sr-te policy detail'", skip_tmpl=True)

    # step 4 : check del sbfd echo 
    config_sbfd(dut1, policy_v4, 'no sbfd echo')
    config_sbfd(dut1, policy_v6, 'no sbfd echo')
    check_filed = {}
    for key in data['policy_sbfd'][policy_v4] + data['policy_sbfd'][policy_v6] :
        ret = double_check_sbfd(dut1, key, check_filed, True, True)
        if not ret:
            st.report_fail("step 4 test_sbfd_loadbalancing_case4 failed")   

    # step 5 : check appdb is clear

    st.report_pass("test_case_passed")

@pytest.mark.community
@pytest.mark.community_pass
def test_sbfd_mspath_case5():

    st.banner("test_sbfd_mspath_case5 begin")

    policy = 'policy color 9 endpoint 2000::59'

    # step 1 : config sbfd
    config_sbfd(dut1, policy, 'sbfd enable source-address 2000::58')

    # step 2 : check sbfd
    check_filed = {
        'Status':'up',
        'Peer Type' : 'sbfd initiator',
        'Detect-multiplier': '3',
        'Receive interval': '300ms',
        'Transmission interval': '300ms'
    }
    for key in data['policy_sbfd'][policy] :
        ret = double_check_sbfd(dut1, key, check_filed, True, False)
        if not ret:
            st.report_fail("step 2 test_sbfd_mspath_case5 failed")

    st.wait(30)
    check_filed = {
        'Status':'up',
        'Peer Type' : 'sbfd initiator',
        'Uptime:': 30  #need > 20s
    }
    for key in data['policy_sbfd'][policy] :
        ret = double_check_sbfd(dut1, key, check_filed, True, False)
        if not ret:
            st.report_fail("step 2 wait 20s test_sbfd_mspath_case5 failed")


    # step 3 : simulate fault
    
    st.show(dut1, "vtysh -c 'show sr-te policy detail'", skip_tmpl=True)

    # step 4 : check del sbfd echo 
    config_sbfd(dut1, policy, 'no sbfd enable')
    check_filed = {}
    for key in data['policy_sbfd'][policy] :
        ret = double_check_sbfd(dut1, key, check_filed, True, True)
        if not ret:
            st.report_fail("step 4 test_sbfd_mspath_case5 failed")   

    # step 5 : check appdb is clear

    st.report_pass("test_case_passed")

@pytest.mark.community
@pytest.mark.community_pass
def test_sbfd_reboot_recover_case6():

    st.banner("test_sbfd_reboot_recover_case6 begin")
    
    policy_1 = 'policy color 1 endpoint 2000::59'
    policy_2 = 'policy color 3 endpoint 2000::59'
    policy_3 = 'policy color 4 endpoint 2000::59'
    policy_4 = 'policy color 7 endpoint 2000::59'
    policy_5 = 'policy color 8 endpoint 2000::59'
    policy_6 = 'policy color 9 endpoint 2000::59'
    # step 1 : config sbfd
    config_sbfd(dut1, policy_1, 'sbfd echo source-address 20.20.20.58')
    config_sbfd(dut1, policy_2, 'sbfd echo source-address 20.20.20.58')
    config_sbfd(dut1, policy_3, 'sbfd echo source-address 2000::58')
    config_sbfd(dut1, policy_4, 'sbfd echo source-address 2000::58')
    config_sbfd(dut1, policy_5, 'sbfd echo source-address 20.20.20.58')
    config_sbfd(dut1, policy_6, 'sbfd enable source-address 2000::58')

    # step 2 : check sbfd 
  
    check_filed = {
        'Status':'up'
    }
    combined_list = data['policy_sbfd'][policy_1] \
                + data['policy_sbfd'][policy_2] \
                + data['policy_sbfd'][policy_3] \
                + data['policy_sbfd'][policy_4] \
                + data['policy_sbfd'][policy_5] \
                + data['policy_sbfd'][policy_6] 

    for key in combined_list:
        ret = double_check_sbfd(dut1, key, check_filed, True, False)
        if not ret:
            st.report_fail("step 2 test_sbfd_mspath_case5 failed")

    save_config_and_reboot(dut1)
    
    # step 3 : check sbfd status
    for key in combined_list:
        ret = double_check_sbfd(dut1, key, check_filed, True, False)
        if not ret:
            st.report_fail("step 2 test_sbfd_mspath_case5 failed")

    # step 4 : clear sbfd config
    config_sbfd(dut1, policy_1, 'no sbfd echo')
    config_sbfd(dut1, policy_2, 'no sbfd echo')
    config_sbfd(dut1, policy_3, 'no sbfd echo')
    config_sbfd(dut1, policy_4, 'no sbfd echo')
    config_sbfd(dut1, policy_5, 'no sbfd echo')
    config_sbfd(dut1, policy_6, 'no sbfd enable')    

    st.report_pass("test_case_passed")

@pytest.mark.community
@pytest.mark.community_pass
def test_sbfd_flapping_case7():

    st.banner("test_sbfd_flapping_case7 begin")

    policy_1 = 'policy color 2 endpoint 2000::59'
    policy_2 = 'policy color 6 endpoint 2000::59'
    policy_3 = 'policy color 7 endpoint 2000::59'
    policy_4 = 'policy color 8 endpoint 2000::59'
    policy_5 = 'policy color 9 endpoint 2000::59'
    # step 1 : config sbfd
    config_sbfd(dut1, policy_1, 'sbfd echo source-address 2000::58')
    config_sbfd(dut1, policy_2, 'sbfd echo source-address 20.20.20.58')
    config_sbfd(dut1, policy_3, 'sbfd echo source-address 2000::58')
    config_sbfd(dut1, policy_4, 'sbfd echo source-address 20.20.20.58')
    config_sbfd(dut1, policy_5, 'sbfd enable source-address 2000::58')

    # step 2 : check sbfd status
    check_filed = {
        'Status':'up'
    }

    combined_list = data['policy_sbfd'][policy_1] \
                + data['policy_sbfd'][policy_2] \
                + data['policy_sbfd'][policy_3] \
                + data['policy_sbfd'][policy_4] \
                + data['policy_sbfd'][policy_5]

    for key in combined_list:
        ret = double_check_sbfd(dut1, key, check_filed, True, False)
        if not ret:
            st.report_fail("step 2 test_sbfd_mspath_case5 failed")


    # step 3: interface flap 
    intf_list = ['Ethernet1', 'Ethernet2', 'Ethernet3', 'Ethernet4']
    
    for i in range(10):
        for intf in intf_list:
            st.config(dut2, 'cli -c "config t" -c "interface {}" -c "shutdown"')
            st.wait(5)
            st.config(dut2, 'cli -c "config t" -c "interface {}" -c "no shutdown"')
            st.wait(5)
    
    # step 4: check dependency
    # ping each other to learn nd and arp 
    st.config(dut1, 'ping -c2 2000::59')
    st.config(dut2, 'ping -c2 2000::58')
    st.config(dut1, 'ping -c2 20.20.20.59')
    st.config(dut2, 'ping -c2 20.20.20.58')
    
    st.show(dut1, "vtysh -c 'show bfd nd infos'", skip_tmpl=True)
    # check
    st.show(dut1, "vtysh -c 'show bfd sr endx infos'", skip_tmpl=True)
    # check
    st.show(dut1, "vtysh -c 'show sr-te policy detail'", skip_tmpl=True)
    # check
    st.show(dut1, 'ip neigh show', skip_tmpl=True)

    show_appdb_tbale_info(dut1, 'SRV6_MY_SID_TABLE')
    show_appdb_tbale_info(dut2, 'SRV6_MY_SID_TABLE')

    # step 5: check sbfd status
    for key in combined_list:
        ret = double_check_sbfd(dut1, key, check_filed, True, False)
        if not ret:
            st.report_fail("step 5 test_sbfd_mspath_case5 failed")

    st.wait(20)
    check_filed = {
        'Status':'up',
        'Uptime:': 20  #need > 20s
    }    
    for key in combined_list:
        ret = double_check_sbfd(dut1, key, check_filed, True, False)
        if not ret:
            st.report_fail("step 5 wait 20s test_sbfd_mspath_case5 failed")


    # step 6 : clear sbfd config
    config_sbfd(dut1, policy_1, 'no sbfd echo')
    config_sbfd(dut1, policy_2, 'no sbfd echo')
    config_sbfd(dut1, policy_3, 'no sbfd echo')
    config_sbfd(dut1, policy_4, 'no sbfd echo')
    config_sbfd(dut1, policy_5, 'no sbfd enable')

    st.report_pass("test_case_passed")

