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
from sbfd_vars import data

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


def check_bcmcmd_route_count(dut, loopCnt, ipType, defcount, expcount):
    flag = 0
    iter = 1
    while iter <= loopCnt:
        if ipType == "ipv4":
            curr_count = asicapi.get_ipv4_route_count(dut)
        elif ipType == "ipv6":
            curr_count = asicapi.get_ipv6_route_count(dut)

        route_cnt = int(curr_count) - int(defcount)

        st.log("Learnt route count after iteration {} : {}".format(iter,route_cnt))

        if int(route_cnt) == int(expcount):
            flag = 1
            break
        iter = iter+1
        time.sleep(1)

    if flag:
        return True
    else:
        return False

def verify_bgp_route_count(dut,family='ipv4',shell="sonic",**kwargs):
    if family.lower() == 'ipv4':
        output = bgpfeature.show_bgp_ipv4_summary(dut)
    if family.lower() == 'ipv6':
        output = bgpfeature.show_bgp_ipv6_summary(dut)
    st.debug(output)
    if 'neighbor' in kwargs and 'state' in kwargs:
        match = {'neighbor': kwargs['neighbor']}
        try:
            entries = filter_and_select(output, None, match)[0]
        except Exception:
            st.log("ERROR 1")
        if entries['state']:
            if kwargs['state'] == 'Established':
                if entries['state'].isdigit():
                    return entries['state']
                else:
                    return 0
            else:
                return 0
        else:
            return 0
    return 0

def verify_ping(src_obj,port_handle,dev_handle,dst_ip,ping_count=5,exp_count=5):
    ping_count,exp_count = int(ping_count),int(exp_count)
    if src_obj.tg_type == 'stc':
        result = src_obj.tg_emulation_ping(handle=dev_handle,host=dst_ip,count=ping_count)
        print("ping output: %s" % (result))
        return True if int(result['tx']) == ping_count and  int(result['rx']) == exp_count else False
    return True

def check_end_to_end_intf_traffic_counters(dut, port):

    DUT_tx_value = papi.get_interface_counters(dut, port, "tx_ok")
    for i in DUT_tx_value:
        p1_tx = i['tx_ok']
        p1_tx = p1_tx.replace(",","")
    st.log("tx_ok xounter value on DUT Inress port : {}".format(p1_tx))
    if (abs(int(float(p1_tx))) > 0):
        output = papi.get_interface_counters_all(dut)
        entry1 = filter_and_select(output, ["tx_bps"], {'iface': port})
        for i in entry1:
            p1_txmt = i['tx_bps']
            p1_txmt = p1_txmt.replace(" Gb/s","")
            p1_txmt = p1_txmt.replace(" Mb/s","")
            p1_txmt = p1_txmt.replace(" Kb/s","")
            p1_txmt = p1_txmt.replace(" b/s","")
        if (abs(int(float(p1_txmt))) == 0):
            st.show(dut, "show arp")
            st.error("End to End traffic is Zero")
            return False
        else:
            st.log("End to End traffic is fine")
            return True
    else:
        st.error("End to End traffic is not fine")
        return False

def intf_traffic_stats(entry_tx):
    for i in entry_tx:
        p_txmt = i['tx_bps']
        p_txmt = p_txmt.replace(" Gb/s","")
        p_txmt = p_txmt.replace(" Mb/s","")
        p_txmt = p_txmt.replace(" Kb/s","")
        p_txmt = p_txmt.replace(" b/s","")

    p_tx = abs(int(float(p_txmt)))
    return p_tx

def check_dut_intf_tx_traffic_counters(dut, portlist, expect_val):
    papi.clear_interface_counters(dut)
    st.wait(5)
    output = papi.get_interface_counters_all(dut)
    retry = 0
    while len(output) == 0 and retry < 10:
        output = papi.get_interface_counters_all(dut)
        retry += 1
        st.wait(2)
    if retry == 10:
        st.error("Error: Dut port stats")
        return False

    tx_bps_list = []
    for port in portlist:
        tx_bps = intf_traffic_stats(filter_and_select(output, ["tx_bps"], {'iface': port}))
        tx_bps_list.append(tx_bps)

    st.log("Inter Dut port stats  tx_ok xounter value on DUT Egress ports : {} expect: {}".format(tx_bps_list,expect_val))

    for tx_bps in tx_bps_list:
        if tx_bps == 0:
            st.error("Error:Inter Dut port stats tx_ok xounter value on DUT Egress port: {}".format(tx_bps))
            return False
        else:
            deviation = abs(expect_val - tx_bps)
            percent = (float(deviation)/expect_val)*100
            if percent > 10:
                st.log("Inter Dut port stats tx_ok xounter value on DUT Egress ports {}".format(tx_bps))
                return False

    st.log("All ECMP paths are utilized")
    return True

def get_handles():
    tg1, tg_ph_1 = tgapi.get_handle_byname("T1D1P1") # ixia - 179 Eth109
    tg2, tg_ph_2 = tgapi.get_handle_byname("T1D1P2") # ixia - 179 Eth110
    tg3, tg_ph_3 = tgapi.get_handle_byname("T1D1P3") # ixia - 179 Eth111
    tg4, tg_ph_4 = tgapi.get_handle_byname("T1D1P4") # ixia - 179 Eth112
    tg5, tg_ph_5 = tgapi.get_handle_byname("T1D2P1") # ixia - 178 Eth109
    tg6, tg_ph_6 = tgapi.get_handle_byname("T1D2P2") # ixia - 178 Eth110
    tg7, tg_ph_7 = tgapi.get_handle_byname("T1D1P5") # ixia - 179 Eth50
    tg8, tg_ph_8 = tgapi.get_handle_byname("T1D1P6") # ixia - 179 Eth51
    tg_list = [tg1, tg2, tg3, tg4, tg5, tg6, tg7, tg8]
    tg_ph_list = [tg_ph_1, tg_ph_2, tg_ph_3, tg_ph_4, tg_ph_5, tg_ph_6, tg_ph_7, tg_ph_8]
    return (tg_list, tg_ph_list)

def get_dut_ip():
    data.my_dut_list = st.get_dut_names()

    cmd = "cli -c 'no page' -c 'show ip interface brief'"
    output1 = st.show(dut1, cmd)
    output2 = st.show(dut2, cmd)

    data.dut1_all_ip_addr = copy.deepcopy(output1)
    data.dut2_all_ip_addr = copy.deepcopy(output2)

@pytest.fixture(scope="module", autouse=True)
def sbfd_module_hooks(request):
    #add things at the start of this module
    yield

@pytest.fixture(scope="function", autouse=True)
def sbfd_func_hooks(request):
    # add things at the start every test case
    yield

def duts_base_config():
    curr_path = os.getcwd()
    json_file_dut1 = curr_path+"/routing/SRv6/esr_dut1_config.json"
    json_file_dut2 = curr_path+"/routing/SRv6/esr_dut2_config.json"
    st.apply_files(dut1, [json_file_dut1])
    st.apply_files(dut2, [json_file_dut2])

    reboot.config_save_reboot(data.my_dut_list)


def l3_base_unconfig():

    st.log("remove l3 base config.")
    ipfeature.clear_ip_configuration(st.get_dut_names())
    vapi.clear_vlan_configuration(st.get_dut_names())
    #command = "show arp"
    #st.show(dut1, command)

def load_static_router_sbfd_config():
    curr_path = os.getcwd()
    filesuffix = "static_router_sbfd_config"

    json_file1 = curr_path+"/routing/SBFD/dut1_"+filesuffix+".json"
    st.apply_files(dut1, [json_file1])

    json_file2 = curr_path+"/routing/SBFD/dut2_"+filesuffix+".json"
    st.apply_files(dut2, [json_file2])

    st.wait(10)

    reboot.config_reload_reboot(dut1, "/etc/spytest/SBFD/dut1_"+filesuffix+".json")
    reboot.config_reload_reboot(dut2, "/etc/spytest/SBFD/dut2_"+filesuffix+".json")

    st.banner("load_static_router_sbfd_config completed")


def load_bgp_router_ms_sbfd_config():
    curr_path = os.getcwd()
    filesuffix = "bgp_router_ms_sbfd_config"

    json_file1 = curr_path+"/routing/SBFD/dut1_"+filesuffix+".json"
    st.apply_files(dut1, [json_file1])

    json_file2 = curr_path+"/routing/SBFD/dut2_"+filesuffix+".json"
    st.apply_files(dut2, [json_file2])

    st.wait(10)

    reboot.config_reload_reboot(dut1, "/etc/spytest/SBFD/dut1_"+filesuffix+".json")
    reboot.config_reload_reboot(dut2, "/etc/spytest/SBFD/dut2_"+filesuffix+".json")

    st.banner("load_bgp_router_ms_sbfd_config completed")

def load_bgp_router_multi_sidlist_ecmp_sbfd_config():
    curr_path = os.getcwd()
    filesuffix = "bgp_router_multisidlist_sbfd_config"

    json_file1 = curr_path+"/routing/SBFD/dut1_"+filesuffix+".json"
    st.apply_files(dut1, [json_file1])

    json_file2 = curr_path+"/routing/SBFD/dut2_"+filesuffix+".json"
    st.apply_files(dut2, [json_file2])

    st.wait(10)

    reboot.config_reload_reboot(dut1, "/etc/spytest/SBFD/dut1_"+filesuffix+".json")
    reboot.config_reload_reboot(dut2, "/etc/spytest/SBFD/dut2_"+filesuffix+".json")

    st.banner("load_bgp_router_multi_sidlist_ecmp_sbfd_config completed")

@pytest.mark.community
@pytest.mark.community_pass
def test_sbfd_base_case1():

    load_static_router_sbfd_config()

    st.banner("test_sbfd_base_case1 begin")
    st.wait(30)

    # step 1 : ping each other , learn each nd
    st.config(dut1, 'ping -c2 2023::59')
    st.config(dut2, 'ping -c2 2023::58')
    st.config(dut1, 'ping -c2 2000::59')
    st.config(dut2, 'ping -c2 2000::58')

    # step 2 : check dut1 bfdd end-x and nd infos


    # step 3 : dut2 config sbfd reflector


    # step 4 : dut1 config sidlist and policy and  check policy

    # check sidlist ASCIDB
    # fwd  
# 127.0.0.1:6381[1]> keys *RESTORE_ATTR2OID_SRV6_SID_LIST_FWD_sl2*
# 1) "RESTORE_ATTR2OID_SRV6_SID_LIST_FWD_sl2SAI_SRV6_SIDLIST_ATTR_SEGMENT_LIST=1:fd00:301:2021:fff1:1::|SAI_SRV6_SIDLIST_ATTR_TYPE=SAI_SRV6_SIDLIST_TYPE_ENCAPS_RED"
# 127.0.0.1:6381[1]> hgetall RESTORE_ATTR2OID_SRV6_SID_LIST_FWD_sl2SAI_SRV6_SIDLIST_ATTR_SEGMENT_LIST=1:fd00:301:2021:fff1:1::|SAI_SRV6_SIDLIST_ATTR_TYPE=SAI_SRV6_SIDLIST_TYPE_ENCAPS_RED
# 1) "SAI_OBJECT_TYPE_SRV6_SIDLIST:oid:0x3d000000000edf"
# 2) "NULL"
# 127.0.0.1:6381[1]> hgetall ASIC_STATE:SAI_OBJECT_TYPE_SRV6_SIDLIST:oid:0x3d000000000edf
# 1) "SAI_SRV6_SIDLIST_ATTR_SEGMENT_LIST"
# 2) "1:fd00:301:2021:fff1:1::"
# 3) "SAI_SRV6_SIDLIST_ATTR_TYPE"
# 4) "SAI_SRV6_SIDLIST_TYPE_ENCAPS_RED"
# 127.0.0.1:6381[1]>  
   
    # sbfd
# 127.0.0.1:6381[1]> keys *RESTORE_ATTR2OID_SRV6_SID_LIST_BFD_sl2*
# 1) "RESTORE_ATTR2OID_SRV6_SID_LIST_BFD_sl2SAI_SRV6_SIDLIST_ATTR_SEGMENT_LIST=2:fd00:301:2021:fff1:1::,fd00:201:2021:fff1:eee::|SAI_SRV6_SIDLIST_ATTR_TYPE=SAI_SRV6_SIDLIST_TYPE_ENCAPS_RED"
# 127.0.0.1:6381[1]> hgetall RESTORE_ATTR2OID_SRV6_SID_LIST_BFD_sl2SAI_SRV6_SIDLIST_ATTR_SEGMENT_LIST=2:fd00:301:2021:fff1:1::,fd00:201:2021:fff1:eee::|SAI_SRV6_SIDLIST_ATTR_TYPE=SAI_SRV6_SIDLIST_TYPE_ENCAPS_RED
# 1) "SAI_OBJECT_TYPE_SRV6_SIDLIST:oid:0x3d000000000ee0"
# 2) "NULL"
# 127.0.0.1:6381[1]> hgetall ASIC_STATE:SAI_OBJECT_TYPE_SRV6_SIDLIST:oid:0x3d000000000ee0
# 1) "SAI_SRV6_SIDLIST_ATTR_SEGMENT_LIST"
# 2) "2:fd00:301:2021:fff1:1::,fd00:201:2021:fff1:eee::"
# 3) "SAI_SRV6_SIDLIST_ATTR_TYPE"
# 4) "SAI_SRV6_SIDLIST_TYPE_ENCAPS_RED"
# 127.0.0.1:6381[1]> 


    # step 5 : dut1 config sbfd and check sbfd
    

    # step 6 : dut1 dut2 reboot check config recover

    st.report_pass("test_case_passed")


@pytest.mark.community
@pytest.mark.community_pass
def test_sbfd_ms_sidlist_case2():

    load_bgp_router_ms_sbfd_config()
    st.banner("test_sbfd_ms_sidlist_case2 begin")

    #step1: 
    
    st.report_pass("test_case_passed")


@pytest.mark.community
@pytest.mark.community_pass
def test_sbfd_multi_sidlist_ecmp_case3():

    load_bgp_router_ms_sbfd_config()
    st.banner("test_sbfd_multi_sidlist_ecmp_case3 begin")


    # step1 

    st.report_pass("test_case_passed")
