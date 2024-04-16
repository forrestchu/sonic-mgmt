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

dut1 = 'MC-58'
dut2 = 'MC-59'
data.my_dut_list = [dut1, dut2]
data.load_1k_policy_ixia_conf_done = False
data.dut1_load_2k_policy_config_done = False
data.load_2k_policy_ixia_conf_done = False
data.test_func_name = ['test_srte_policy_2k_vrf_2k_policy_03', 'test_srte_policy_2k_vrf_2k_policy_color_only_04',
                       'test_srte_policy_2k_vrf_4k_policy_05', 'test_srte_policy_2k_vrf_4k_policy_color_only_06']


@pytest.fixture(scope="module", autouse=True)
def esr_srte_policy_module_hooks(request):
    try:
        ixia_controller_init()
        yield
    except Exception as e:
        st.log("Exception occurred: {}".format(e))
    finally:
        ixia_stop_all_protocols()
        ixia_controller_deinit()

@pytest.fixture(scope="function", autouse=True)
def esr_srte_policy_func_hooks(request):
    func_name = st.get_func_name(request)
    st.log("esr_srte_policy_func_hooks enter {}".format(func_name))
    if func_name in data.test_func_name:
        st.log("esr_srte_policy_func_hooks enter {}".format(func_name))
        if data.dut1_load_2k_policy_config_done == False:
            double_dut_load_config("2k_config", data.dut2_config[func_name])
            data.dut1_load_2k_policy_config_done = True
        else:
            one_dut_load_config(dut2, data.dut2_config[func_name])

        if data.load_2k_policy_ixia_conf_done == False:
            ixia_load_config(ESR_2K_POLICY_CONFIG)
            ixia_start_all_protocols()
            st.wait(60)
            data.load_2k_policy_ixia_conf_done = True
    else:
        if func_name == "test_srte_policy_2k_vrf_1k_policy_01":
            double_dut_load_config("1k_config", "1k_config")
        else:
            double_dut_load_config("1k_config", "1k_config_only")

        if data.load_1k_policy_ixia_conf_done == False:
            ixia_load_config(ESR_1K_POLICY_CONFIG)
            ixia_start_all_protocols()
            st.wait(60)
            data.load_1k_policy_ixia_conf_done = True

    yield
    pass

def load_config(duts, filesuffix1, filesuffix2):
    curr_path = os.getcwd()
    method="replace_configdb"
    for dut in duts:
        if (dut == "MC-58"):
            json_file = "{}/routing/SRv6/esr_te_dut1_{}.json".format(curr_path, filesuffix1)
        else:
            json_file = "{}/routing/SRv6/esr_te_dut2_{}.json".format(curr_path, filesuffix2)
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

def one_dut_load_config(dut, filesuffix):
    load_config([dut], filesuffix)

@pytest.mark.community
@pytest.mark.community_pass
def test_srte_policy_2k_vrf_1k_policy_01():
    ret = ixia_start_traffic(TRAFFIC_1K_TE_POLICY)
    if not ret:
        st.report_fail("Step1: Start traffic item {} rx frame failed".format(TRAFFIC_1K_TE_POLICY))
 
    st.wait(30)
    #check traffic cpath d, on interface Ethernet4
    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet4"], 150)
    if not ret:
        st.report_fail("Step2: Check dut interface counters failed")

    #shutdown Ethernet4
    cmd = "interface {}\n shutdown\n".format("Ethernet4")
    st.config(dut1, cmd, type="alicli", skip_error_check = True)
    st.wait(10)

    #check bfd state
    check_filed = {
        'status':'down',
        'peer_type' : 'echo',
        'multiplier': '3'
    }
    key = "bfd-name d"

    if not retry_api(check_bfd_state, dut2, key, check_filed, retry_count= 5, delay= 10):
        st.report_fail("Step3: The cpath d: bfd-name d not down")

    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet3"], 150)
    if not ret:
        st.report_fail("Step4: Check dut interface counters failed")

    #shutdown Ethernet4
    cmd = "interface {}\n no shutdown\n".format("Ethernet4")
    st.config(dut1, cmd, type="alicli", skip_error_check = True)
    st.wait(10)

    #check bfd state
    check_filed = {
        'status':'up',
        'peer_type' : 'echo',
        'multiplier': '3'
    }
    key = "bfd-name d"

    if not retry_api(check_bfd_state, dut2, key, check_filed, retry_count= 5, delay= 10):
        st.report_fail("Step5: The cpath d: bfd-name d not up")

    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet4"], 150)
    if not ret:
        st.report_fail("Step6: Check dut interface counters failed")

    ret = ixia_stop_traffic(TRAFFIC_1K_TE_POLICY)
    if not ret:
        st.report_fail("Step7: Stop traffic item {} rx frame failed".format(TRAFFIC_1K_TE_POLICY))

    #check Tx Frame Rate
    ret = ixia_check_traffic(TRAFFIC_1K_TE_POLICY, key="Rx Frame Rate", value=100000)
    if not ret:
        st.report_fail("Step8: Check traffic item {} rx frame failed".format(TRAFFIC_1K_TE_POLICY))

    st.report_pass("test_case_passed")

@pytest.mark.community
@pytest.mark.community_pass
def test_srte_policy_2k_vrf_1k_policy_color_only_02():
    ret = ixia_start_traffic(TRAFFIC_1K_TE_POLICY)
    if not ret:
        st.report_fail("Step1: Start traffic item {} rx frame failed".format(TRAFFIC_1K_TE_POLICY))
    st.wait(30)
    #check traffic cpath d, on interface Ethernet4
    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet4"], 150)
    if not ret:
        st.report_fail("Step2: Check dut interface counters failed")

    #shutdown Ethernet4
    cmd = "interface {}\n shutdown\n".format("Ethernet4")
    st.config(dut1, cmd, type="alicli", skip_error_check = True)
    st.wait(10)

    #check bfd state
    check_filed = {
        'status':'down',
        'peer_type' : 'echo',
        'multiplier': '3'
    }
    key = "bfd-name d"

    if not retry_api(check_bfd_state, dut2, key, check_filed, retry_count= 5, delay= 10):
        st.report_fail("Step4: The cpath d: bfd-name d not down")

    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet3"], 150)
    if not ret:
        st.report_fail("Step5: Check dut interface counters failed")

    #shutdown Ethernet3
    cmd = "interface {}\n shutdown\n".format("Ethernet3")
    st.config(dut1, cmd, type="alicli", skip_error_check = True)
    st.wait(10)

    #check bfd state
    check_filed = {
        'status':'down',
        'peer_type' : 'echo',
        'multiplier': '3'
    }
    key = "bfd-name c"

    if not retry_api(check_bfd_state, dut2, key, check_filed, retry_count= 5, delay= 10):
        st.report_fail("Step6: The cpath c: bfd-name c not down")

    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet2"], 150)
    if not ret:
        st.report_fail("Step7: Check dut interface counters failed")

    #shutdown Ethernet2
    cmd = "interface {}\n shutdown\n".format("Ethernet2")
    st.config(dut1, cmd, type="alicli", skip_error_check = True)
    st.wait(10)

    #check bfd state
    check_filed = {
        'status':'down',
        'peer_type' : 'echo',
        'multiplier': '3'
    }
    key = "bfd-name b"

    if not retry_api(check_bfd_state, dut2, key, check_filed, retry_count= 5, delay= 10):
        st.report_fail("Step8: The cpath b: bfd-name b not down")

    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet1"], 150)
    if not ret:
        st.report_fail("Step9: Check dut interface counters failed")

    #no shutdown Ethernet2
    cmd = "interface {}\n no shutdown\n".format("Ethernet2")
    st.config(dut1, cmd, type="alicli", skip_error_check = True)
    st.wait(10)

    #check bfd state
    check_filed = {
        'status':'up',
        'peer_type' : 'echo',
        'multiplier': '3'
    }
    key = "bfd-name b"

    if not retry_api(check_bfd_state, dut2, key, check_filed, retry_count= 5, delay= 10):
        st.report_fail("Step10: The cpath b: bfd-name b not up")

    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet2"], 150)
    if not ret:
        st.report_fail("Step11: Check dut interface counters failed")

    #no shutdown Ethernet3
    cmd = "interface {}\n no shutdown\n".format("Ethernet3")
    st.config(dut1, cmd, type="alicli", skip_error_check = True)
    st.wait(10)

    #check bfd state
    check_filed = {
        'status':'up',
        'peer_type' : 'echo',
        'multiplier': '3'
    }
    key = "bfd-name c"

    if not retry_api(check_bfd_state, dut2, key, check_filed, retry_count= 5, delay= 10):
        st.report_fail("Step12: The cpath c: bfd-name c not down")

    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet3"], 150)
    if not ret:
        st.report_fail("Step13: Check dut interface counters failed")

    #no shutdown Ethernet4
    cmd = "interface {}\n no shutdown\n".format("Ethernet4")
    st.config(dut1, cmd, type="alicli", skip_error_check = True)
    st.wait(10)

    #check bfd state
    check_filed = {
        'status':'up',
        'peer_type' : 'echo',
        'multiplier': '3'
    }
    key = "bfd-name d"

    if not retry_api(check_bfd_state, dut2, key, check_filed, retry_count= 5, delay= 10):
        st.report_fail("Step14: The cpath d: bfd-name d not down")

    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet4"], 150)
    if not ret:
        st.report_fail("Step15: Check dut interface counters failed")
    
    ret = ixia_stop_traffic(TRAFFIC_2K_TE_POLICY)
    if not ret:
        st.report_fail("Step16: Stop traffic item {} rx frame failed".format(TRAFFIC_2K_TE_POLICY))

    #check Tx Frame Rate
    ret = ixia_check_traffic(TRAFFIC_1K_TE_POLICY, key="Rx Frame Rate", value=100000)
    if not ret:
        st.report_fail("Step17: Check traffic item {} rx frame failed".format(TRAFFIC_1K_TE_POLICY))
    st.report_pass("test_case_passed")

@pytest.mark.community
@pytest.mark.community_pass
def test_srte_policy_2k_vrf_2k_policy_03():

    ret = ixia_start_traffic(TRAFFIC_2K_TE_POLICY)
    if not ret:
        st.report_fail("Step1: Start traffic item {} rx frame failed".format(TRAFFIC_2K_TE_POLICY))

    #check traffic cpath d, on interface Ethernet4
    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet4"], 300)
    if not ret:
        st.report_fail("Step2: Check dut interface counters failed")

    #shutdown Ethernet4
    cmd = "interface {}\n shutdown\n".format("Ethernet4")
    st.config(dut1, cmd, type="alicli", skip_error_check = True)
    st.wait(10)

    #sbfd down, cpath change to c
    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet3"], 300)
    if not ret:
        st.report_fail("Step3: Check dut interface counters failed")

    #no shutdown inteface ,sbfd up, cpath change to d
    cmd = "interface {}\n no shutdown\n".format("Ethernet4")
    st.config(dut1, cmd, type="alicli", skip_error_check = True)
    st.wait(10)

    #check bgp state
    if not retry_api(check_bgp_state, dut2, "2000::179", retry_count= 6, delay= 10):
        st.report_fail("Step4: Check bgp state failed")
    st.wait(10)

    #check bfd state
    check_filed = {
        'status':'up',
        'peer_type' : 'echo',
        'multiplier': '3'
    }
    key = "bfd-name d"

    if not retry_api(check_bfd_state, dut2, key, check_filed, retry_count= 5, delay= 10):
        st.report_fail("Step5: The cpath d: bfd-name a not up")

    #check traffic back to Ethernet4
    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet4"], 300)
    if not ret:
        st.report_fail("Step6: Check dut interface counters failed")

    ret = ixia_stop_traffic(TRAFFIC_2K_TE_POLICY)
    if not ret:
        st.report_fail("Step7: Stop traffic item {} rx frame failed".format(TRAFFIC_2K_TE_POLICY))

    #check Tx Frame Rate
    ret = ixia_check_traffic(TRAFFIC_2K_TE_POLICY, key="Rx Frame Rate", value=100000)
    if not ret:
        st.report_fail("Step8: Check traffic item {} rx frame failed".format(TRAFFIC_2K_TE_POLICY))

    st.report_pass("test_case_passed")

@pytest.mark.community
@pytest.mark.community_pass
def test_srte_policy_2k_vrf_2k_policy_color_only_04():

    ret = ixia_start_traffic(TRAFFIC_2K_TE_POLICY)
    if not ret:
        st.report_fail("Step1: Start traffic item {} rx frame failed".format(TRAFFIC_2K_TE_POLICY))

    #check traffic cpath d, on interface Ethernet4
    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet4"], 300)
    if not ret:
        st.report_fail("Step2: Check dut interface counters failed")

    #shutdown Ethernet4
    cmd = "interface {}\n shutdown\n".format("Ethernet4")
    st.config(dut1, cmd, type="alicli", skip_error_check = True)
    st.wait(10)

    #sbfd down, cpath change to c
    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet3"], 300)
    if not ret:
        st.report_fail("Step3: Check dut interface counters failed")

    #no shutdown inteface ,sbfd up, cpath change to d
    cmd = "interface {}\n no shutdown\n".format("Ethernet4")
    st.config(dut1, cmd, type="alicli", skip_error_check = True)
    st.wait(10)

    #check bgp state
    if not retry_api(check_bgp_state, dut2, "2000::179", retry_count= 6, delay= 10):
        st.report_fail("Step4: Check bgp state failed")
    st.wait(10)

    #check bfd state
    check_filed = {
        'status':'up',
        'peer_type' : 'echo',
        'multiplier': '3'
    }
    key = "bfd-name d"

    if not retry_api(check_bfd_state, dut2, key, check_filed, retry_count= 5, delay= 10):
        st.report_fail("Step5: The cpath d: bfd-name a not up")

    #check traffic back to Ethernet4
    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet4"], 300)
    if not ret:
        st.report_fail("Step6: Check dut interface counters failed")

    ret = ixia_stop_traffic(TRAFFIC_2K_TE_POLICY)
    if not ret:
        st.report_fail("Step7: Stop traffic item {} rx frame failed".format(TRAFFIC_2K_TE_POLICY))

    #check Tx Frame Rate
    ret = ixia_check_traffic(TRAFFIC_2K_TE_POLICY, key="Tx Frame Rate", value=100000)
    if not ret:
        st.report_fail("Step8: Check traffic item {} rx frame failed".format(TRAFFIC_2K_TE_POLICY))

    st.report_pass("test_case_passed")

@pytest.mark.community
@pytest.mark.community_pass
def test_srte_policy_2k_vrf_4k_policy_05():

    ret = ixia_start_traffic(TRAFFIC_2K_TE_POLICY)
    if not ret:
        st.report_fail("Step1: Start traffic item {} rx frame failed".format(TRAFFIC_2K_TE_POLICY))

    #check traffic cpath d, on interface Ethernet4
    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet3"], 300)
    if not ret:
        st.report_fail("Step2: Check dut interface counters failed")
    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet4"], 300)
    if not ret:
        st.report_fail("Step3: Check dut interface counters failed")

    #shutdown Ethernet4
    cmd = "interface {}\n shutdown\n".format("Ethernet4")
    st.config(dut1, cmd, type="alicli", skip_error_check = True)
    st.wait(10)

    #sbfd down, cpath change to c
    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet3"], 300)
    if not ret:
        st.report_fail("Step4: Check dut interface counters failed")

    #no shutdown inteface ,sbfd up, cpath change to d
    cmd = "interface {}\n no shutdown\n".format("Ethernet4")
    st.config(dut1, cmd, type="alicli", skip_error_check = True)
    st.wait(10)

    cmd = 'vtysh -c "config t" -c "router bgp 100" -c "neighbor 1000::179 shutdown"'
    st.config(dut1, cmd, type="alicli", skip_error_check = True)
    st.wait(10)

    #check traffic back to Ethernet4
    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet3"], 300)
    if not ret:
        st.report_fail("Step8: Check dut interface Ethernet3 counters failed")
    #check traffic back to Ethernet4
    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet4"], 300)
    if not ret:
        st.report_fail("Step9: Check dut interface Ethernet4 counters failed")

    cmd = 'vtysh -c "config t" -c "router bgp 100" -c "no neighbor 1000::179 shutdown"'
    st.config(dut1, cmd, type="alicli", skip_error_check = True)
    st.wait(10)

   #check bgp state
    if not retry_api(check_bgp_state, dut2, "1000::178", retry_count= 6, delay= 10):
        st.report_fail("Step7: Check bgp state failed")
    st.wait(30)

    #check traffic back to Ethernet3
    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet3"], 300)
    if not ret:
        st.report_fail("Step8: Check dut interface Ethernet3 counters failed")
    #check traffic back to Ethernet4
    ret = check_dut_intf_tx_traffic_counters(dut2, ["Ethernet4"], 300)
    if not ret:
        st.report_fail("Step9: Check dut interface Ethernet4 counters failed")


    ret = ixia_stop_traffic(TRAFFIC_2K_TE_POLICY)
    if not ret:
        st.report_fail("Step5: Stop traffic item {} rx frame failed".format(TRAFFIC_2K_TE_POLICY))

    #check Tx Frame Rate
    ret = ixia_check_traffic(TRAFFIC_2K_TE_POLICY, key="Tx Frame Rate", value=100000)
    if not ret:
        st.report_fail("Step6: Check traffic item {} rx frame failed".format(TRAFFIC_2K_TE_POLICY))

    st.report_pass("test_case_passed")

@pytest.mark.community
@pytest.mark.community_pass
def test_srte_policy_2k_vrf_4k_policy_color_only_06():

    st.report_pass("test_case_passed")
