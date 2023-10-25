import os
import pytest
import sys
import json
import netaddr
import re
import time,datetime
from collections import OrderedDict
from utilities import parallel
import apis.routing.bgp as bgpfeature

from spytest import st, tgapi, SpyTestDict
from spytest.utils import filter_and_select
import spytest.env as env

from utilities.utils import retry_api
import pandas as pd
import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt

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
from esr_lib import cli_show_json, json_cmp, configdb_checkarray, configdb_onefield_checkpoint,appdb_onefield_checkpoint,check_vrf_route_nums, get_random_array, check_vpn_route_nums, check_bgp_vrf_ipv4_uni_sid,appdb_get_onefield,get_vrf_realname,compare_redistribute_vrf_route, flap_lag_member,show_hw_route_count
import esr_lib as loc_lib
from esr_vars import * #all the variables used for vrf testcase
from esr_vars import data
from ixia_vars import *
from ixia_helper import *
#
#            +-------------------+                 +-------------------+
# TG1_1====  |                    |                |                    |
#            |                    |                |                    |
# TG1_2====  |                    |                |                    |=====TG2_1
#            | DUT1(192.0.0.179)  | ===========    |  DUT2(192.0.0.178) |
#            |                    |                |                    |=====TG2_2
# TG1_3====  |                    |                |                    |
#            |                    |                |                    |
# TG1_4====  |                    |                |                    |
#            +-------------------+                  +-------------------+
#                                                     ||
#                                                     ||
#                                                     ||
#                                                +-----------+
#                                                |           |
#                                                |    RJ     |
#                                                |           |
#                                                |           |
#                                                +-----------+
#                                                     ||
#                                                     ||
#                                                     ||
#                                                     TG3_1#

#data = SpyTestDict()

data.srv6 = {}

dut1 = 'MC-58'
dut2 = 'MC-59'
data.my_dut_list = [dut1, dut2]
data.load_multi_vrf_config_done = False
data.load_mirror_config_done = False
data.load_mirror_ixia_conf_done = False

@pytest.fixture(scope="module", autouse=True)
def esr_sr_te_module_hooks(request):
    #add things at the start of this module
    # add bmp
    ixia_controller_init()
    yield
    ixia_stop_all_protocols()
    ixia_controller_deinit()
    # tgapi.set_reconnect_tgen(True)
    # del bmp log

def duts_base_config():
    curr_path = os.getcwd()
    json_file_dut1 = curr_path+"/routing/SRv6/esr_te_dut1_config.json"
    json_file_dut2 = curr_path+"/routing/SRv6/esr_te_dut2_config.json"
    st.apply_files(dut1, [json_file_dut1], method="replace_configdb")
    st.apply_files(dut2, [json_file_dut2], method="replace_configdb")
    st.reboot([dut1, dut2])

@pytest.mark.community
@pytest.mark.community_pass
def test_base_config_sr_te_config_check_01():

    duts_base_config()

    result = 0

    st.banner("test_base_config_sr_te_config_check_01 begin")
    st.wait(30)

    # step 1 : check ipv6 static route
    route_entries = cli_show_json(dut1, "show ipv6 route json", type="vtysh")
    # expected json
    cwd = os.getcwd()
    expected_route_path = cwd+"/routing/SRv6/locator_static_route_expected_01.json"
    expected_route_json = json.loads(open(expected_route_path).read())
    result = json_cmp(route_entries, expected_route_json)
    if result and result.has_errors():
        st.report_fail("step 1 test_base_config_sr_te_config_check_01_failed")
        for e in result.errors:
            st.log(e)

    # step 2 : check bgp state
    def check_bgp_state():
        output=st.show(dut1,'show bgp neighbors {}'.format('2000::178'), type='vtysh')
        bgp_state = output[0]['state']
        if bgp_state != 'Established':
            return False
        else:    
            return True

    if not retry_api(check_bgp_state, retry_count= 10, delay= 10):
        st.report_fail("step2 pre check bgp state failed")

    # step 3 :check te-policy
    output = st.show(dut1, "show sr-te policy detail", type='vtysh')
    if len(output) == 0:
        st.error("Output is Empty")
        return False
    for a in output:
        for key in a:
            output[output.index(a)][key]=output[output.index(a)][key].lstrip()
            output[output.index(a)][key]=output[output.index(a)][key].rstrip()
            if key in data.te_policy_key:
                if (output[output.index(a)][key] != data.dut1_policy[output.index(a)][key]):
                    print("output:{} != data:{}".format(output[output.index(a)][key],data.dut1_policy[output.index(a)][key]))
                    st.report_fail("step3 check te-policy failed")

    # step 4 : add vpn route
    vrf = 'PUBLIC-TC11'
    check_fields = ['rdroute', 'sid', 'color', 'peerv6', 'secetced', 'policy']
    bgp_as = 100
    st.config(dut1, 'vtysh -c "config t" -c "vrf {}" -c "ip route 192.100.1.0/24 blackhole"'.format(vrf))
    st.config(dut1, 'vtysh -c "config t" -c "router bgp {} vrf {}" -c "address-family ipv4 unicast" -c "redistribute static"'.format(bgp_as, vrf))
    st.config(dut1, 'vtysh -c "config t" -c "vrf {}" -c "ip route 192:100:1::0/64 blackhole"'.format(vrf))
    st.config(dut1, 'vtysh -c "config t" -c "router bgp {} vrf {}" -c "address-family ipv6 unicast" -c "redistribute static"'.format(bgp_as, vrf))

    cmd = "cli -c 'no page' -c 'show bgp ipv4 vpn 192.100.1.0/24'"
    records = st.show(dut2, cmd)
    st.log(records)

    expected_vpn = {
        'rdroute':'2:2:192.100.1.0/24',
        'sid':'fd00:201:201:fff1:11::',
        'color':'1',
        'peerv6':'',
        'policy':'2000::179|1',
        'secetced':'1 available, best #1',
    }

    if not records or len(records)==0:
        st.report_fail("step 4 test_base_config_sr_te_config_check_01_failed")

    check = False
    for re in records:
        match_cnt = 0
        st.log(re)
        for it in check_fields:
            st.log(re[it])
            if re[it] ==  expected_vpn[it]:
                match_cnt +=1

        if match_cnt == len(check_fields):
            check = True
            break

    if not check:
        st.log(records)
        st.report_fail("step 4 test_base_config_sr_te_config_check_01_failed")

    cmd = "cli -c 'no page' -c 'show bgp ipv6 vpn 192:100:1::/64'"
    records = st.show(dut2, cmd)
    st.log(records)

    expected_vpn = {
        'rdroute':'2:2:192:100:1::/64',
        'sid':'fd00:201:201:fff1:11::',
        'color':'2',
        'peerv6':'',
        'policy':'2000::179|2',
        'secetced':'1 available, best #1',
    }

    if not records or len(records)==0:
        st.report_fail("step 4 test_base_config_sr_te_config_check_01_ipv6_failed")

    check = False
    for re in records:
        match_cnt = 0
        st.log(re)
        for it in check_fields:
            st.log(re[it])
            if re[it] ==  expected_vpn[it]:
                match_cnt +=1

        if match_cnt == len(check_fields):
            check = True
            break

    if not check:
        st.log(records)
        st.report_fail("step 4 test_base_config_sr_te_config_check_01_ipv6_failed")

    # step 5 : check vpn route
    show_cmd = "cli -c 'show ip route vrf PUBLIC-TC11 192.100.1.0/24'"
    result = st.show(dut2, show_cmd, skip_tmpl=True)
    if 'seg6 fd00:201:201:fff1:11::' not in result:
        st.report_fail("step 5 test_base_config_sr_te_config_check_01_failed, check sid")

    if 'srv6tunnel(endpoint|color):2000::179|1' not in result:
        st.report_fail("step 5 test_base_config_sr_te_config_check_01_failed, check policy")

    show_cmd = "cli -c 'show ipv6 route vrf PUBLIC-TC11 192:100:1::/64'"
    result = st.show(dut2, show_cmd, skip_tmpl=True)
    if 'seg6 fd00:201:201:fff1:11::' not in result:
        st.report_fail("step 5 test_base_config_sr_te_config_check_01_ipv6_failed, check sid")

    if 'srv6tunnel(endpoint|color):2000::179|2' not in result:
        st.report_fail("step 5 test_base_config_sr_te_config_check_01_ipv6_failed, check policy")

    # step 6 : check app db
    key = 'ROUTE_TABLE:' + 'Vrf10000' + ':192.100.1.0/24'
    nexthop_val = appdb_get_onefield(dut2, key, "nexthop")
    if nexthop_val != "2000::179":
        st.report_fail("step 6 test_base_config_sr_te_config_check_01_failed, check nexthop")

    vpn_sid_val = appdb_get_onefield(dut2, key, "vpn_sid")
    if vpn_sid_val != "fd00:201:201:fff1:11::":
        st.report_fail("step 6 test_base_config_sr_te_config_check_01_failed, check vpn sid")

    seg_src_val = appdb_get_onefield(dut2, key, "seg_src")
    if seg_src_val != "2000::178":
        st.report_fail("step 6 test_base_config_sr_te_config_check_01_failed, check seg")

    policy_val = appdb_get_onefield(dut2, key, "policy")
    if policy_val != "2000::179_1":
        st.report_fail("step 6 test_base_config_sr_te_config_check_01_failed, check policy")

    key = 'ROUTE_TABLE:' + 'Vrf10000' + ':192:100:1::/64'
    nexthop_val = appdb_get_onefield(dut2, key, "nexthop")
    if nexthop_val != "2000::179":
        st.report_fail("step 6 test_base_config_sr_te_config_check_01_ipv6_failed, check nexthop")

    vpn_sid_val = appdb_get_onefield(dut2, key, "vpn_sid")
    if vpn_sid_val != "fd00:201:201:fff1:11::":
        st.report_fail("step 6 test_base_config_sr_te_config_check_01_ipv6_failed, check vpn sid")

    seg_src_val = appdb_get_onefield(dut2, key, "seg_src")
    if seg_src_val != "2000::178":
        st.report_fail("step 6 test_base_config_sr_te_config_check_01_ipv6_failed, check seg")

    policy_val = appdb_get_onefield(dut2, key, "policy")
    if policy_val != "2000::179_2":
        st.report_fail("step 6 test_base_config_sr_te_config_check_01_ipv6_failed, check policy")

    # step 7 : check app db
    vrf_name = 'PUBLIC-TC11'
    st.config(dut1, 'cli -c "config t" -c "router bgp {} vrf {}" -c "address-family ipv4 unicast" -c "no route-map vpn export sr1"'.format(bgp_as, vrf_name))
    st.config(dut1, 'cli -c "config t" -c "router bgp {} vrf {}" -c "address-family ipv6 unicast" -c "no route-map vpn export sr2"'.format(bgp_as, vrf_name))
    st.wait(10)
    cmd = "cli -c 'no page' -c 'show bgp ipv4 vpn 192.100.1.0/24'"
    records = st.show(dut2, cmd)
    st.log(records)

    expected_vpn = {
        'rdroute':'2:2:192.100.1.0/24',
        'sid':'fd00:201:201:fff1:11::',
        'color':'',
        'peerv6':'',
        'policy':'',
        'secetced':'1 available, best #1',
    }

    if not records or len(records)==0:
        st.report_fail("step 7 test_base_config_sr_te_config_check_01_failed, len = 0")

    check = False
    for re in records:
        match_cnt = 0
        st.log(re)
        for it in check_fields:
            st.log(re[it])
            if re[it] ==  expected_vpn[it]:
                match_cnt +=1

        if match_cnt == len(check_fields):
            check = True
            break

    if not check:
        st.log(records)
        st.report_fail("step 7 test_base_config_sr_te_config_check_01_failed, check failed")

    cmd = "cli -c 'no page' -c 'show bgp ipv6 vpn 192:100:1::0/64'"
    records = st.show(dut2, cmd)
    st.log(records)

    expected_vpn = {
        'rdroute':'2:2:192:100:1::/64',
        'sid':'fd00:201:201:fff1:11::',
        'color':'',
        'peerv6':'',
        'policy':'',
        'secetced':'1 available, best #1',
    }

    if not records or len(records)==0:
        st.report_fail("step 7 test_base_config_sr_te_config_check_01_ipv6_failed, len = 0")

    check = False
    for re in records:
        match_cnt = 0
        st.log(re)
        for it in check_fields:
            st.log(re[it])
            if re[it] ==  expected_vpn[it]:
                match_cnt +=1

        if match_cnt == len(check_fields):
            check = True
            break

    if not check:
        st.log(records)
        st.report_fail("step 7 test_base_config_sr_te_config_check_01_ipv6_failed, check failed")

    # step 8 : check app db
    key = 'ROUTE_TABLE:' + 'Vrf10000' + ':192.100.1.0/24'
    policy_val = appdb_get_onefield(dut2, key, "policy")
    if policy_val != "na":
        st.report_fail("step 8 test_base_config_sr_te_config_check_01_failed, check policy")

    key = 'ROUTE_TABLE:' + 'Vrf10000' + ':192:100:1::/64'
    policy_val = appdb_get_onefield(dut2, key, "policy")
    if policy_val != "na":
        st.report_fail("step 8 test_base_config_sr_te_config_check_01_ipv6_failed, check policy")

    # step 9 : recover srv6 config
    st.config(dut1, 'cli -c "config t" -c "router bgp {} vrf {}" -c "address-family ipv4 unicast" -c "route-map vpn export sr1"'.format(bgp_as, vrf_name))
    st.config(dut1, 'cli -c "config t" -c "router bgp {} vrf {}" -c "address-family ipv6 unicast" -c "route-map vpn export sr2"'.format(bgp_as, vrf_name))
    st.wait(10)
    key = 'ROUTE_TABLE:' + 'Vrf10000' + ':192.100.1.0/24'
    policy_val = appdb_get_onefield(dut2, key, "policy")
    if policy_val != "2000::179_1":
        st.report_fail("step 9 test_base_config_sr_te_config_check_01_failed, check policy")

    key = 'ROUTE_TABLE:' + 'Vrf10000' + ':192:100:1::/64'
    policy_val = appdb_get_onefield(dut2, key, "policy")
    if policy_val != "2000::179_2":
        st.report_fail("step 9 test_base_config_sr_te_config_check_01_ipv6_failed, check policy")

    st.report_pass("test_base_config_sr_te_config_check_01 after")

def load_json_config(filesuffix='te_multi_vrf_full'):
    curr_path = os.getcwd()

    json_file_dut1_multi_vrf = curr_path+"/routing/SRv6/dut1_"+filesuffix+".json"
    st.apply_files(dut1, [json_file_dut1_multi_vrf], method="replace_configdb")

    json_file_dut2_multi_vrf = curr_path+"/routing/SRv6/dut2_"+filesuffix+".json"
    st.apply_files(dut2, [json_file_dut2_multi_vrf], method="replace_configdb")

    st.wait(10)

    st.reboot([dut1, dut2])

    st.banner("%s json config loaded completed" % (filesuffix))

def get_kernel_ip_route(dut, number):
    command = "ip route show vrf Vrf{}| wc -l".format(number)
    output = st.show(dut, command, skip_tmpl=True, skip_error_check=True)
    x = re.findall(r"\d+", output)
    if x:
        return int(x[0])
    else:
        return 0

def get_kernel_ipv6_route(dut, number):
    command = "ip -6 route show vrf Vrf{}| wc -l".format(number)
    output = st.show(dut, command, skip_tmpl=True, skip_error_check=True)
    x = re.findall(r"\d+", output)
    if x:
        return int(x[0])
    else:
        return 0

@pytest.mark.community
@pytest.mark.community_pass
def test_base_config_sr_te_2kl_route_learn_02():
    st.banner("test_base_config_sr_te_2kl_route_learn_02 begin")

    # load full config
    if data.load_multi_vrf_config_done == False:
        load_json_config()
        data.load_multi_vrf_config_done = True

    # load ixia config
    ixia_load_config(ESR_MULTI_VRF_CONFIG)
    ixia_start_all_protocols()

    # check redis db , check route
    finish_v4_egress = False
    finish_v6_egress = True
    finish_v4_ingress = False
    finish_v6_ingress = True

    str_start_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    end_timev4_ingress = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    end_timev6_ingress = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    end_timev4_egress = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    end_timev6_egress = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    str_end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    def get_time_diff(start, end):
        start_sec = time.mktime(time.strptime(start, "%Y-%m-%d %X"))
        end_sec = time.mktime(time.strptime(end, "%Y-%m-%d %X"))
        return end_sec-start_sec

    # 5 min check route count
    while get_time_diff(str_start_time, str_end_time) < (5*60):
        # egress
        def_v4_route_count_d2 = asicapi.get_ipv4_route_count(dut2)
        if int(def_v4_route_count_d2) >= 500000 and not finish_v4_egress:
            end_timev4_egress = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            finish_v4_egress = True
            st.log("dut2 v4 learn 50w time cost "+str(get_time_diff(str_start_time, end_timev4_egress)))

        def_v4_route_count_d1 = asicapi.get_ipv4_route_count(dut1)
        if int(def_v4_route_count_d1) >= 500000 and not finish_v4_ingress:
            end_timev4_ingress = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            finish_v4_ingress = True
            st.log("dut1 v4 learn 50w time cost "+str(get_time_diff(str_start_time, end_timev4_ingress)))

        if finish_v4_egress and finish_v6_egress and finish_v4_ingress and finish_v6_ingress:
            break

        st.wait(1)
        str_end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


    if not finish_v4_egress:
        st.report_fail("dut2 v4 learn 50w route slower than 5 min")

    if not finish_v6_egress:
        st.report_fail("dut2 v6 learn 5w route slower than 5 min")

    if not finish_v4_ingress:
        st.report_fail("dut1 v6 learn 5w route slower than 5 min")

    if not finish_v6_ingress:
        st.report_fail("dut1 v6 learn 5w route slower than 5 min")

    st.log("dut2 v4 learn 50w time cost "+str(get_time_diff(str_start_time, end_timev4_egress)))
    st.log("dut2 v6 learn 5w time cost "+str(get_time_diff(str_start_time, end_timev6_egress)))
    st.log("dut1 v4 learn 50w time cost "+str(get_time_diff(str_start_time, end_timev4_ingress)))
    st.log("dut1 v6 learn 5w time cost "+str(get_time_diff(str_start_time, end_timev6_ingress)))
    
    for num in range(1, 100):
        vrf_name = data.vrf_list[num]
        prefix = data.vrf_prefix[vrf_name]
        key = "ROUTE_TABLE:Vrf{}:{}".format(10000+num, prefix)
        policy_val = appdb_get_onefield(dut2, key, "policy")
        if policy_val == "na":
            cmd ='cli -c "no page" -c "show ip route vrf {} {}"'.format(vrf_name, prefix)
            st.show(dut2, cmd, skip_tmpl=True, skip_error_check=True)
            st.report_fail("test_base_config_sr_te_2kl_route_learn_02_failed, vrf {} prefix {}".format(vrf_name, prefix))

    st.report_pass("test_base_config_sr_te_2kl_route_learn_02 after")

def duts_load_config(dut1_config, dut2_config):
    dut_list = st.get_dut_names()
    st.log("===== GET DUT LIST {}".format(dut_list))

    dut1_config_file_path = os.path.join(os.getcwd(), "routing/SRv6/{}".format(dut1_config))
    dut2_config_file_path = os.path.join(os.getcwd(), "routing/SRv6/{}".format(dut2_config))
    st.apply_files(dut_list[0], [dut1_config_file_path], method="replace_configdb")
    st.apply_files(dut_list[1], [dut2_config_file_path], method="replace_configdb")

    st.wait(10)

    st.reboot([dut1, dut2])

    st.banner("config loaded %s and %s completed" % (dut1_config, dut2_config))


def duts_get_memory(dut, progress):
    cmd = "cat /proc/`pidof {}`/status | grep VmRSS".format(progress)
    memory = st.show(dut, cmd, skip_tmpl=True, skip_error_check=True).split("\n")
    return memory

def plot_perf(csv_file, jpg_file):

    data_df = pd.read_csv(csv_file)

    for col in data_df.columns:
        if col == u"~ElapsedTime":
            x = data_df[col]
        elif col == u"21.135.163.53/Card01/Port33:Valid Frames Rx. Rate":
            y = data_df[col]

    plt.clf()
    plt.style.use('seaborn-colorblind')
    plt.xlabel("timestamp", fontsize=11)
    plt.ylabel("Frames Rx. Rate", fontsize=11)
    plt.ylim(ymin=0, ymax=max(y)+100000)
    plt.plot(x, y, color='blue')
    plt.savefig(jpg_file, dpi=1200)
    #plt.show()

def get_route_load_time(cursor, csv_file):
    data_df = pd.read_csv(csv_file)

    for col in data_df.columns:
        if col == u"~ElapsedTime":
            x = data_df[col]
        elif col == u"21.135.163.53/Card01/Port33:Valid Frames Rx. Rate":
            y = data_df[col]

    start_time = cursor
    stop_time = cursor
    max_rx_rate = max(y) + 1
    for i in range(0, len(x) - 1):
        if y[i] != 0 and start_time == cursor:
            start_time = x[i]
        if y[i] * 100 / max_rx_rate > 98 and stop_time == cursor:
            stop_time = x[i]
            break
    st.log("get_route_load_time start = {}, stop = {}, i = {}".format(start_time, stop_time, i))
    return stop_time - start_time, i


def get_route_convergence_time(cursor, csv_file):
    data_df = pd.read_csv(csv_file)

    for col in data_df.columns:
        if col == u"~ElapsedTime":
            x = data_df[col]
        elif col == u"21.135.163.53/Card01/Port33:Valid Frames Rx. Rate":
            y = data_df[col]

    start_time = cursor
    stop_time = cursor
    max_rx_rate = max(y) + 1
    for i in range(cursor - 1, len(x) + 1):
        if y[i] * 100 / max_rx_rate < 98 and start_time == cursor:
            start_time = x[i]

        if y[i] == 0 and stop_time == cursor:
            stop_time = x[i]
            break
    st.log("get_route_convergence_time start = {}, stop = {}, i = {}".format(start_time, stop_time, i))
    if (stop_time == start_time):
        return 1;
    return stop_time - start_time


def get_log_dir_path():
    user_root = env.get("SPYTEST_USER_ROOT", os.getcwd())
    logs_path = env.get("SPYTEST_LOGS_PATH", user_root)
    return logs_path

@pytest.mark.community
@pytest.mark.community_pass
def test_sr_te_performance_2M():
    st.banner("test_sr_te_performance_2M begin")
    dut_list = st.get_dut_names()
    dut1 = dut_list[0]
    dut2 = dut_list[1]

    route_count = 2000000

    # 1. load DUT config
    dut1_config = "performance/dut1_te_one_vrf.json"
    dut2_config = "performance/dut2_te_one_vrf.json"
    duts_load_config(dut1_config, dut2_config)

    # 2. load TG config
    ixia_config = os.path.join(os.getcwd(), "routing/SRv6/performance/ixia_one_vrf_2M.json")
    ixia_load_config(ixia_config)

    # 3. start traffic
    ixia_start_all_traffic()
    ixia_start_logging_port_view()

    # 4. start protocol
    ixia_start_all_protocols()
    st.wait(400)
    if not retry_api(check_vpn_route_nums, dut=dut2, expected_num=route_count, compare=0, retry_count=3, delay=400):
        st.report_fail("check vpn route_nums failed")

    # 5. get memory info for DUT1 bgpd,zebra,orchagent,syncd
    st.log("====== DUT1 ======")
    memory = duts_get_memory(dut1, 'bgpd')
    st.log("====== Memory bgpd ======")
    st.log(memory)
    memory = duts_get_memory(dut1, 'zebra')
    st.log("====== Memory zebra ======")
    st.log(memory)
    memory = duts_get_memory(dut1, 'orchagent')
    st.log("====== Memory orchagent ======")
    st.log(memory)
    memory = duts_get_memory(dut1, 'syncd')
    st.log("====== Memory syncd ======")
    st.log(memory)

    # 6. get memory info for DUT2 bgpd,zebra,orchagent,syncd
    st.log("====== DUT2 ======")
    memory = duts_get_memory(dut2, 'bgpd')
    st.log("====== Memory bgpd ======")
    st.log(memory)
    memory = duts_get_memory(dut2, 'zebra')
    st.log("====== Memory zebra ======")
    st.log(memory)
    memory = duts_get_memory(dut2, 'orchagent')
    st.log("====== Memory orchagent ======")
    st.log(memory)
    memory = duts_get_memory(dut2, 'syncd')
    st.log("====== Memory syncd ======")
    st.log(memory)

    # 7. stop protocol
    ixia_stop_all_protocols()
    st.wait(400)
    # 8. get perform data
    ixia_stop_logging_port_view()
    local_file = "port_statictics_{}.csv".format(route_count)
    local_file = os.path.join(os.getcwd(), "../", get_log_dir_path(), local_file)

    perf_jpg_file = 'eSR_Performance_{}.jpg'.format(route_count)
    perf_jpg_file = os.path.join(os.getcwd(), "../", get_log_dir_path(), perf_jpg_file)

    st.log(local_file)
    st.log(perf_jpg_file)

    ixia_get_port_view_data(local_file)
    plot_perf(local_file, perf_jpg_file)

    load_t, cursor = get_route_load_time(0, local_file)
    covergen_t = get_route_convergence_time(cursor, local_file)

    st.log("======== {} Route Load Time {} =======".format(route_count, load_t))
    st.log("Load Time: {} s, Rate: {} rps".format(load_t, route_count / load_t))

    st.log("======== {} Route Convergence Time {} =======".format(route_count, covergen_t))
    st.log("Convergence Time: {} s, Rate: {} rps".format(covergen_t, route_count / covergen_t))

    # 9. stop traffic
    ixia_stop_all_traffic()
    st.report_pass("msg", "LoadPerf: {} rps, CovergePerf: {} rps".format(route_count / load_t, route_count / covergen_t))
    