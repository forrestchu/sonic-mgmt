import os
import pytest
from spytest import st

import matplotlib
matplotlib.use('Agg')

from utilities.utils import retry_api

from esr_vars import * #all the variables used for vrf testcase
from esr_vars import data
from esr_lib import *
from ixia_vars import *
from ixia_helper import *

dut1 = 'MC-56'
dut2 = 'MC-57'
data.my_dut_list = [dut1, dut2]
data.load_locator_endx_ecmp_conf_done = False
data.load_locator_endx_ecmp_hash_conf_done = False


@pytest.fixture(scope="module", autouse=True)
def esr_locator_endx_ecmp_module_hooks(request):
    try:
        ixia_controller_init()
        yield
    except Exception as e:
        st.log("Exception occurred: {}".format(e))
    finally:
        ixia_stop_all_protocols()
        ixia_controller_deinit()


@pytest.fixture(scope="function", autouse=True)
def esr_locator_endx_ecmp_func_hooks(request):
    func_name = st.get_func_name(request)
    st.log("esr_locator_endx_ecmp_func_hooks enter {}".format(func_name))
   
    if func_name == 'test_locator_128_endx_ecmp':
        if data.load_locator_endx_ecmp_conf_done == False:
            double_dut_load_config('128_endx_ecmp', '128_endx_ecmp')
            data.load_locator_endx_ecmp_conf_done = True
    else:
        if data.load_locator_endx_ecmp_hash_conf_done == False:
            double_dut_load_config('endx_ecmp_hash', 'endx_ecmp_hash')
            data.load_locator_endx_ecmp_hash_conf_done = True 

    yield
    pass


def load_config(duts, filesuffix1, filesuffix2):
    curr_path = os.getcwd()
    method="replace_configdb"
    for dut in duts:
        if (dut == "MC-56"):
            json_file = "{}/routing/SRv6/esr_locator_dut1_{}.json".format(curr_path, filesuffix1)
        else:
            json_file = "{}/routing/SRv6/esr_locator_dut2_{}.json".format(curr_path, filesuffix2)
        try:
            st.apply_files(dut, [json_file], method=method)
        except Exception as e:
            print("Error applying config file {} to {}: {}".format(json_file, dut, e))
            return

        st.wait(10)

    try:
        st.reboot(duts)
    except Exception as e:
        print("Error rebooting {}: {}".format(duts, e))
        return
    st.banner("{} json config loaded completed for {}".format(filesuffix1, duts))


def double_dut_load_config(filesuffix1, filesuffix2):
    load_config([dut1, dut2], filesuffix1, filesuffix2)

def load_ixia_config(config_name, traffic_name):
    ixia_load_config(config_name)
    ixia_start_all_protocols()
    ixia_disable_traffic(traffic_name)
    ixia_enable_traffic(traffic_name)

'''
1. Dut1/Dut2 config 1k vrfs and 1k policy 
2. Each policy has 4 different priority cpaths
3. Each policy has a sbfd to detect
4. Shutdown/no shutdown interface on Dut1, sbfd flap
5. Check traffic
'''
@pytest.mark.community
@pytest.mark.community_pass
def test_locator_128_endx_ecmp():
    st.log("Enter test_locator_128_endx_ecmp.")

    # check subport
    if not retry_api(check_ip_intf_state, dut1, 'Eth1', retry_count= 6, delay= 10):
        st.report_fail("Step0.0: {} Check ip interface Eth1 state failed".format(dut1))

    if not retry_api(check_ip_intf_state, dut1, 'Eth2', retry_count= 6, delay= 10):
        st.report_fail("Step0.1: {} Check ip interface Eth2 state failed".format(dut1))

    if not retry_api(check_ip_intf_state, dut2, 'Eth1', retry_count= 6, delay= 10):
        st.report_fail("Step0.2: {} Check ip interface Eth1 state failed".format(dut2))

    if not retry_api(check_ip_intf_state, dut2, 'Eth2', retry_count= 6, delay= 10):
        st.report_fail("Step0.3: {} Check ip interface Eth2 state failed".format(dut2))

    st.wait(5)

    # arp/nd learn
    for i in range(1,129):
        st.config(dut1, 'ping -c 1 101.0.{}.57'.format(i))
        st.config(dut1, 'ping -c 1 101:0:{}::57'.format(hex(i)[2:]))
        st.config(dut1, 'ping -c 1 202.0.{}.57'.format(i))
        st.config(dut1, 'ping -c 1 202:0:{}::57'.format(hex(i)[2:]))

    # check arp/nd
    if not retry_api(check_arp_state, dut1, 'Eth1', retry_count=1, delay= 10):
        st.report_fail("Step0.4: {} Check arp state failed".format(dut1))

    if not retry_api(check_arp_state, dut1, 'Eth2', retry_count=1, delay= 10):
        st.report_fail("Step0.5: {} Check arp state failed".format(dut1))

    if not retry_api(check_ndp_state, dut2, 'Eth1', retry_count=1, delay= 10):
        st.report_fail("Step0.6: {} Check ndp state failed".format(dut2))

    if not retry_api(check_ndp_state, dut2, 'Eth1', retry_count=1, delay= 10):
        st.report_fail("Step0.7: {} Check ndp state failed".format(dut2))

    # check appdb
    # unua v4
    key = 'SRV6_MY_SID_TABLE:fd00:101:2022:12::/64'
    checkpoint_msg = "check appdb key {} check failed.".format(key)
    appdb_onefield_checkpoint(dut2, key, "block_len", data.compress_endx_ecmp_unua_sid["block_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "node_len", data.compress_endx_ecmp_unua_sid["node_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "func_len", data.compress_endx_ecmp_unua_sid["func_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "argu_len", data.compress_endx_ecmp_unua_sid["argu_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "action", "end.x", expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "vrf", "Default", expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "ifname", data.compress_endx_ecmp_sid_ifname, expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "nexthop", data.compress_endx_ecmp_sid_nexthop_v4, expect = True, checkpoint = checkpoint_msg)

    # ua v4
    key = "SRV6_MY_SID_TABLE:fd00:101:12::/48"
    checkpoint_msg = "check appdb key {} check failed.".format(key)
    appdb_onefield_checkpoint(dut2, key, "block_len", data.compress_endx_ecmp_ua_sid["block_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "node_len", data.compress_endx_ecmp_ua_sid["node_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "func_len", data.compress_endx_ecmp_ua_sid["func_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "argu_len", data.compress_endx_ecmp_ua_sid["argu_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "action", "end.x", expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "vrf", "Default", expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "ifname", data.compress_endx_ecmp_sid_ifname, expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "nexthop", data.compress_endx_ecmp_sid_nexthop_v4, expect = True, checkpoint = checkpoint_msg)

    # unua v6
    key = 'SRV6_MY_SID_TABLE:fd00:202:2022:13::/64'
    checkpoint_msg = "check appdb key {} check failed.".format(key)
    appdb_onefield_checkpoint(dut2, key, "block_len", data.compress_endx_ecmp_unua_sid["block_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "node_len", data.compress_endx_ecmp_unua_sid["node_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "func_len", data.compress_endx_ecmp_unua_sid["func_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "argu_len", data.compress_endx_ecmp_unua_sid["argu_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "action", "end.x", expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "vrf", "Default", expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "ifname", data.compress_endx_ecmp_sid_ifname, expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "nexthop", data.compress_endx_ecmp_sid_nexthop_v6, expect = True, checkpoint = checkpoint_msg)

    # ua v6
    key = 'SRV6_MY_SID_TABLE:fd00:202:13::/48'
    checkpoint_msg = "check appdb key {} check failed.".format(key)
    appdb_onefield_checkpoint(dut2, key, "block_len", data.compress_endx_ecmp_ua_sid["block_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "node_len", data.compress_endx_ecmp_ua_sid["node_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "func_len", data.compress_endx_ecmp_ua_sid["func_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "argu_len", data.compress_endx_ecmp_ua_sid["argu_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "action", "end.x", expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "vrf", "Default", expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "ifname", data.compress_endx_ecmp_sid_ifname, expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "nexthop", data.compress_endx_ecmp_sid_nexthop_v6, expect = True, checkpoint = checkpoint_msg)

    # endx v4
    key = 'SRV6_MY_SID_TABLE:fd00:101:3033:fff1:12::/80'
    checkpoint_msg = "check appdb key {} check failed.".format(key)
    appdb_onefield_checkpoint(dut2, key, "block_len", data.noncompress_endx_ecmp_sid["block_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "node_len", data.noncompress_endx_ecmp_sid["node_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "func_len", data.noncompress_endx_ecmp_sid["func_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "argu_len", data.noncompress_endx_ecmp_sid["argu_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "action", "end.x", expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "vrf", "Default", expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "ifname", data.noncompress_endx_ecmp_sid_ifname, expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "nexthop", data.noncompress_endx_ecmp_sid_nexthop_v4, expect = True, checkpoint = checkpoint_msg)

    # endx v6
    key = 'SRV6_MY_SID_TABLE:fd00:101:3033:fff1:13::/80'
    checkpoint_msg = "check appdb key {} check failed.".format(key)
    appdb_onefield_checkpoint(dut2, key, "block_len", data.noncompress_endx_ecmp_sid["block_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "node_len", data.noncompress_endx_ecmp_sid["node_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "func_len", data.noncompress_endx_ecmp_sid["func_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "argu_len", data.noncompress_endx_ecmp_sid["argu_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "action", "end.x", expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "vrf", "Default", expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "ifname", data.noncompress_endx_ecmp_sid_ifname, expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "nexthop", data.noncompress_endx_ecmp_sid_nexthop_v6, expect = True, checkpoint = checkpoint_msg)

    # check asicdb
    ret = retry_api(check_asicdb_member, dut2, retry_count= 3, delay= 5)
    if not ret:
        st.report_fail("Step0.8: Check dut2 cdb asicdb member failed")
    
    # unua v4
    load_ixia_config(ESR_LOCATOR_ENDX_ECMP_UNUA_V4_CONFIG,TRAFFIC_ENDX_ECMP)

    ret = ixia_start_traffic(TRAFFIC_ENDX_ECMP)
    if not ret:
        st.report_fail("Step1.1: Start traffic item {} ixia_config {} frame failed".format(TRAFFIC_ENDX_ECMP,ESR_LOCATOR_ENDX_ECMP_UNUA_V4_CONFIG))
    st.wait(30)
    #check traffic on interface Ethernet1
    ret = retry_api(check_dut_intf_tx_traffic_counters, dut2, ["Ethernet1"], 51, retry_count= 3, delay= 5)
    if not ret:
        st.report_fail("Step1.2: Check dut interface counters failed")

    ret = ixia_stop_traffic(TRAFFIC_ENDX_ECMP)
    if not ret:
        st.report_fail("Step1.3: Stop traffic item {} ixia_config {} frame failed".format(TRAFFIC_ENDX_ECMP,ESR_LOCATOR_ENDX_ECMP_UNUA_V4_CONFIG))

    # ua v4
    load_ixia_config(ESR_LOCATOR_ENDX_ECMP_UA_V4_CONFIG,TRAFFIC_ENDX_ECMP)

    ret = ixia_start_traffic(TRAFFIC_ENDX_ECMP)
    if not ret:
        st.report_fail("Step2.1: Start traffic item {} ixia_config {} frame failed".format(TRAFFIC_ENDX_ECMP,ESR_LOCATOR_ENDX_ECMP_UA_V4_CONFIG))
    st.wait(30)
    #check traffic on interface Ethernet1
    ret = retry_api(check_dut_intf_tx_traffic_counters, dut2, ["Ethernet1"], 51, retry_count= 3, delay= 5)
    if not ret:
        st.report_fail("Step2.2: Check dut interface counters failed")

    ret = ixia_stop_traffic(TRAFFIC_ENDX_ECMP)
    if not ret:
        st.report_fail("Step2.3: Stop traffic item {} ixia_config {} frame failed".format(TRAFFIC_ENDX_ECMP,ESR_LOCATOR_ENDX_ECMP_UA_V4_CONFIG))    

    # unua v6
    load_ixia_config(ESR_LOCATOR_ENDX_ECMP_UNUA_V6_CONFIG,TRAFFIC_ENDX_ECMP)

    ret = ixia_start_traffic(TRAFFIC_ENDX_ECMP)
    if not ret:
        st.report_fail("Step3.1: Start traffic item {} ixia_config {} frame failed".format(TRAFFIC_ENDX_ECMP,ESR_LOCATOR_ENDX_ECMP_UNUA_V6_CONFIG))
    st.wait(30)
    #check traffic on interface Ethernet1
    ret = retry_api(check_dut_intf_tx_traffic_counters, dut2, ["Ethernet1"], 51, retry_count= 3, delay= 5)
    if not ret:
        st.report_fail("Step3.2: Check dut interface counters failed")

    ret = ixia_stop_traffic(TRAFFIC_ENDX_ECMP)
    if not ret:
        st.report_fail("Step3.3: Stop traffic item {} ixia_config {} frame failed".format(TRAFFIC_ENDX_ECMP,ESR_LOCATOR_ENDX_ECMP_UNUA_V6_CONFIG))  

    # ua v6
    load_ixia_config(ESR_LOCATOR_ENDX_ECMP_UA_V6_CONFIG,TRAFFIC_ENDX_ECMP)

    ret = ixia_start_traffic(TRAFFIC_ENDX_ECMP)
    if not ret:
        st.report_fail("Step4.1: Start traffic item {} ixia_config {} frame failed".format(TRAFFIC_ENDX_ECMP,ESR_LOCATOR_ENDX_ECMP_UA_V6_CONFIG))
    st.wait(30)
    #check traffic on interface Ethernet1
    ret = retry_api(check_dut_intf_tx_traffic_counters, dut2, ["Ethernet1"], 51, retry_count= 3, delay= 5)
    if not ret:
        st.report_fail("Step4.2: Check dut interface counters failed")

    ret = ixia_stop_traffic(TRAFFIC_ENDX_ECMP)
    if not ret:
        st.report_fail("Step4.3: Stop traffic item {} ixia_config {} frame failed".format(TRAFFIC_ENDX_ECMP,ESR_LOCATOR_ENDX_ECMP_UA_V6_CONFIG))   

    # endx ecmp v4
    load_ixia_config(ESR_LOCATOR_ENDX_ECMP_V4_CONFIG,TRAFFIC_ENDX_ECMP)

    ret = ixia_start_traffic(TRAFFIC_ENDX_ECMP)
    if not ret:
        st.report_fail("Step5.1: Start traffic item {} ixia_config {} frame failed".format(TRAFFIC_ENDX_ECMP,ESR_LOCATOR_ENDX_ECMP_V4_CONFIG))
    st.wait(30)
    #check traffic on interface Ethernet2
    ret = retry_api(check_dut_intf_tx_traffic_counters, dut2, ["Ethernet2"], 51, retry_count= 3, delay= 5)
    if not ret:
        st.report_fail("Step5.2: Check dut interface counters failed")

    ret = ixia_stop_traffic(TRAFFIC_ENDX_ECMP)
    if not ret:
        st.report_fail("Step5.3: Stop traffic item {} ixia_config {} frame failed".format(TRAFFIC_ENDX_ECMP,ESR_LOCATOR_ENDX_ECMP_V4_CONFIG))   

    # endx ecmp v6
    load_ixia_config(ESR_LOCATOR_ENDX_ECMP_V6_CONFIG,TRAFFIC_ENDX_ECMP)

    ret = ixia_start_traffic(TRAFFIC_ENDX_ECMP)
    if not ret:
        st.report_fail("Step6.1: Start traffic item {} ixia_config {} frame failed".format(TRAFFIC_ENDX_ECMP,ESR_LOCATOR_ENDX_ECMP_V6_CONFIG))
    st.wait(30)
    #check traffic on interface Ethernet2
    ret = retry_api(check_dut_intf_tx_traffic_counters, dut2, ["Ethernet2"], 51, retry_count= 3, delay= 5)
    if not ret:
        st.report_fail("Step6.2: Check dut interface counters failed")

    ret = ixia_stop_traffic(TRAFFIC_ENDX_ECMP)
    if not ret:
        st.report_fail("Step6.3: Stop traffic item {} ixia_config {} frame failed".format(TRAFFIC_ENDX_ECMP,ESR_LOCATOR_ENDX_ECMP_V6_CONFIG))  
                
    st.report_pass("test_case_passed")


@pytest.mark.community
@pytest.mark.community_pass
def test_locator_endx_ecmp_hash():
    st.log("Enter test_locator_endx_ecmp_hash.")

    # check ip interface
    if not retry_api(check_ip_interface_state, dut1, 'Ethernet1,Ethernet2,Ethernet3,Ethernet4', retry_count= 6, delay= 10):
        st.report_fail("Step0.0: {} Check ip interface  state failed".format(dut1))


    if not retry_api(check_ip_interface_state, dut2, 'Ethernet1,Ethernet2,Ethernet3,Ethernet4', retry_count= 6, delay= 10):
        st.report_fail("Step0.1: {} Check ip interface  state failed".format(dut2))


    st.wait(5)

    # nd learn
    st.config(dut1, 'ping -c 1  2044::179')
    st.config(dut1, 'ping -c 1  2055::179')
    st.config(dut1, 'ping -c 1  2066::179')
    st.config(dut1, 'ping -c 1  2077::179')

    # check appdb
    # noncompress-v6
    key = 'SRV6_MY_SID_TABLE:fd00:501:501:fff1:31::/80'
    checkpoint_msg = "check appdb key {} check failed.".format(key)
    appdb_onefield_checkpoint(dut2, key, "block_len", data.noncompress_endx_ecmp_v6_sid["block_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "node_len", data.noncompress_endx_ecmp_v6_sid["node_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "func_len", data.noncompress_endx_ecmp_v6_sid["func_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "argu_len", data.noncompress_endx_ecmp_v6_sid["argu_len"], expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "action", "end.x", expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "vrf", "Default", expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "ifname", data.noncompress_endx_ecmp_v6_sid_ifname, expect = True, checkpoint = checkpoint_msg)
    appdb_onefield_checkpoint(dut2, key, "nexthop", data.noncompress_endx_ecmp_v6_sid_nexthop, expect = True, checkpoint = checkpoint_msg)

    # check asicdb
    ret = retry_api(check_asicdb_member_hash, dut2, retry_count= 3, delay= 5)
    if not ret:
        st.report_fail("Step0.2: Check dut2 cdb asicdb member failed")
    
    # endx ecmp v6 hash
    load_ixia_config(ESR_LOCATOR_ENDX_ECMP_V6_HASH_CONFIG,TRAFFIC_ENDX_ECMP)

    ret = ixia_start_traffic(TRAFFIC_ENDX_ECMP)
    if not ret:
        st.report_fail("Step1.1: Start traffic item {} ixia_config {} frame failed".format(TRAFFIC_ENDX_ECMP,ESR_LOCATOR_ENDX_ECMP_V6_HASH_CONFIG))
    st.wait(30)
    #check traffic on interface Ethernet1,Ethernet2,Ethernet3,Ethernet4
    ret = retry_api(check_dut_intf_tx_traffic_counters, dut2, ["Ethernet1","Ethernet2","Ethernet3","Ethernet4"], 1270, retry_count= 3, delay= 5)
    if not ret:
        st.report_fail("Step1.2: Check dut interface counters failed")

    ret = ixia_stop_traffic(TRAFFIC_ENDX_ECMP)
    if not ret:
        st.report_fail("Step1.3: Stop traffic item {} ixia_config {} frame failed".format(TRAFFIC_ENDX_ECMP,ESR_LOCATOR_ENDX_ECMP_V6_HASH_CONFIG))
             
    st.report_pass("test_case_passed")





