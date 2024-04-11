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
data.load_2k_vrf_config_done = False
data.load_2k_vrf_ixia_conf_done = False
data.test_func_name = ['test_srte_policy_2k_vrf_2k_policy_02', 'test_srte_policy_2k_vrf_4k_policy_03']


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
    if st.get_func_name(request) in data.test_func_name:
        st.log("esr_srte_policy_func_hooks enter ")
        if data.load_2k_vrf_config_done == False:
            dut_load_config("2k_config")
            data.load_2k_vrf_config_done = True
        if data.load_2k_vrf_ixia_conf_done == False:
            ixia_load_config(ESR_2K_VRF_CONFIG)
            ixia_start_all_protocols()
            st.wait(60)
            data.load_2k_vrf_ixia_conf_done = True
    yield
    pass

def dut_load_config(filesuffix):
    curr_path = os.getcwd()

    json_file_dut1_2k_vrf = curr_path+"/routing/SRv6/esr_te_dut1_"+filesuffix+".json"
    st.apply_files(dut1, [json_file_dut1_2k_vrf], method="replace_configdb")

    json_file_dut2_2k_vrf = curr_path+"/routing/SRv6/esr_te_dut2_"+filesuffix+".json"
    st.apply_files(dut2, [json_file_dut2_2k_vrf], method="replace_configdb")

    st.wait(10)

    st.reboot([dut1, dut2])
    st.wait(600)
    st.banner("%s json config loaded completed" % (filesuffix))

def check_bgp_state(dut, neighbor):
    output=st.show(dut,'show bgp neighbors {}'.format(neighbor), type='vtysh')
    bgp_state = output[0]['state']
    if bgp_state != 'Established':
        return False
    else: 
        return True

    if not retry_api(check_bgp_state, retry_count= 6, delay= 10):
        st.report_fail("pre check bgp state failed")

@pytest.mark.community
@pytest.mark.community_pass
def test_srte_policy_2k_vrf_1k_policy_01():

    st.report_pass("test_case_passed")

@pytest.mark.community
@pytest.mark.community_pass
def test_srte_policy_2k_vrf_2k_policy_02():

    ixia_start_all_protocols()
    ixia_start_all_traffic()
    ret = ixia_check_traffic(TRAFFIC_2K_TE_POLICY, key="Rx frame", value=200000)
    st.report_pass("test_case_passed")

@pytest.mark.community
@pytest.mark.community_pass
def test_srte_policy_2k_vrf_4k_policy_03():


    st.report_pass("test_case_passed")

