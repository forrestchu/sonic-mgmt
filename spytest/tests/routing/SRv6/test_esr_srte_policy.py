import os
import pytest
from spytest import st

import matplotlib
matplotlib.use('Agg')

from utilities.utils import retry_api

from esr_vars import * #all the variables used for vrf testcase
from esr_lib import *
from ixia_vars import *
from ixia_helper import *


data.srv6 = {}

dut1 = 'MC-58'
dut2 = 'MC-59'
data.my_dut_list = [dut1, dut2]
data.test_func_name = []
data.load_2k_vrf_config_done = False
data.load_2k_vrf_ixia_conf_done = False

@pytest.fixture(scope="module", autouse=True)
def esr_srte_policy_module_hooks(request):
    #add things at the start of this module
    ixia_controller_init()
    yield
    ixia_stop_all_protocols()
    ixia_controller_deinit()

@pytest.fixture(scope="module")
def check_bgp_state(request):
    output=st.show(dut1,'show bgp neighbors {}'.format('2000::178'), type='vtysh')
    bgp_state = output[0]['state']
    if bgp_state != 'Established':
        return False
    else:    
        return True

    if not retry_api(check_bgp_state, retry_count= 6, delay= 10):
        st.report_fail("pre check bgp state failed")

@pytest.fixture(scope="function", autouse=True)
def esr_srte_policy_func_hooks(request):
    if st.get_func_name(request) in data.test_func_name:
        st.log("esr_srte_policy_func_hooks enter ")
        if data.load_2k_vrf_config_done == False:
            load_json_config()
            data.load_2k_vrf_config_done = True
        if data.load_2k_vrf_ixia_conf_done == False:
            ixia_load_config(ESR_2K_VRF_CONFIG)
            ixia_start_all_protocols()
            st.wait(60)
            data.load_2k_vrf_ixia_conf_done = True
    yield
    pass

def load_json_config(filesuffix='2k_config'):
    curr_path = os.getcwd()

    json_file_dut1_2k_vrf = curr_path+"/routing/SRv6/esr_te_dut1_"+filesuffix+".json"
    st.apply_files(dut1, [json_file_dut1_2k_vrf], method="replace_configdb")

    json_file_dut2_2k_vrf = curr_path+"/routing/SRv6/esr_te_dut1_"+filesuffix+".json"
    st.apply_files(dut2, [json_file_dut2_2k_vrf], method="replace_configdb")

    st.wait(10)

    st.reboot([dut1, dut2])

    st.banner("%s json config loaded completed" % (filesuffix))

@pytest.mark.community
@pytest.mark.community_pass
def test_srte_policy_2k_vrf_01():


    st.report_pass("test_case_passed")

