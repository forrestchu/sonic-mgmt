##################################################################################
#Script Title : VRF Lite
#Author       : Manisha Joshi
#Mail-id      : manisha.joshi@broadcom.com
#################################################################################

import pytest
from spytest import st,utils

from vrf_vars import * #all the variables used for vrf testcase
from vrf_vars import data

import apis.switching.portchannel as pc_api
import apis.routing.ip as ip_api
import apis.routing.vrf as vrf_api

@pytest.fixture(scope="module", autouse=True)
def vrf_basic_module_hooks():
    vars = st.ensure_min_topology("D1D2:1")
    data.dut_list = st.get_dut_names()
    data.dut1 = data.dut_list[0]
    data.d1_dut_ports = [vars.D1D2P1]

def test_configure_loopback_ip_in_vrf():
    result = 0

    # bind different Loopbacks to different VRFs
    vrf_api.bind_vrf_interface(data.dut1, vrf_name = vrf_name[0], intf_name = dut_loopbacks[0], skip_error = True, config = 'yes')
    vrf_api.bind_vrf_interface(data.dut1, vrf_name = vrf_name[1], intf_name = dut_loopbacks[1], skip_error = True, config = 'yes')

    # set same ip address for different Loopbacks in different VRFs
    if not ip_api.config_ip_addr_interface(data.dut1, dut_loopbacks[0], dut_loopback_ip, dut_loopback_ip_subnet, family="ipv4"):
        result += 1
        st.log('Failed to set ip addr for {}'.format(dut_loopbacks[0]))
    if not ip_api.config_ip_addr_interface(data.dut1, dut_loopbacks[1], dut_loopback_ip, dut_loopback_ip_subnet, family="ipv4"):
        result += 1
        st.log('Failed to set ip addr for {}'.format(dut_loopbacks[1]))

    # delete the ip address from different Loopbacks
    if not ip_api.delete_ip_interface(data.dut1, dut_loopbacks[0], dut_loopback_ip, dut_loopback_ip_subnet, family="ipv4"):
        result += 1
        st.log('Failed to delete ip addr for {}'.format(dut_loopbacks[0]))
    if not ip_api.delete_ip_interface(data.dut1, dut_loopbacks[1], dut_loopback_ip, dut_loopback_ip_subnet, family="ipv4"):
        result += 1
        st.log('Failed to delete ip addr for {}'.format(dut_loopbacks[1]))

    if result == 0:
        st.report_pass('test_case_passed')
    else:
        st.report_fail('test_case_failed')

def test_pc_subif_in_vrf():
    result = 0

    # create portchannel and member
    pc_api.create_portchannel(data.dut1, dut_portchannel_name)
    pc_api.add_portchannel_member(data.dut1, dut_portchannel_name, data.d1_dut_ports[0])

    # create PC subport
    command = "interface sub-interface {} {}\n".format(dut_portchannel_name, dut_sub_port_vlan)
    st.config(data.dut1, command, skip_error_check=True, type='alicli')

    # bind PC subport to vrf
    vrf_api.bind_vrf_interface(data.dut1, vrf_name = vrf_name[0], intf_name = dut_pc_subport, skip_error = True, config = 'yes')

    # set ip address for PC subport
    if not ip_api.config_ip_addr_interface(data.dut1, dut_pc_subport, dut_subport_ip, dut_subport_ip_subnet, family="ipv4"):
        result += 1
        st.log('Failed to set ip addr for {}'.format(dut_pc_subport))

    # check if the PC subport in VRF
    #output = vrf_api.get_vrf_verbose(dut = data.dut1, vrfname = vrf_name[0])
    #if dut_pc_subport not in output['interfaces']:
    #    st.log('{} is not in vrf {}'.format(dut_pc_subport, vrf_name[0]))
    #    result += 1

    # delete ip address for PC subport
    if not ip_api.delete_ip_interface(data.dut1, dut_pc_subport, dut_subport_ip, dut_subport_ip_subnet, family="ipv4"):
        result += 1
        st.log('Failed to delete ip addr for {}'.format(dut_pc_subport))

    # when there is PC subport, create another PortChannel
    pc_api.delete_portchannel_member(data.dut1, dut_portchannel_name, data.d1_dut_ports[0])
    pc_api.create_portchannel(data.dut1, dut_portchannel_name_2)
    pc_api.add_portchannel_member(data.dut1, dut_portchannel_name_2, data.d1_dut_ports[0])

    # delete PC subport
    command = "no interface sub-interface {} {}\n".format(dut_portchannel_name, dut_sub_port_vlan)
    st.config(data.dut1, command, skip_error_check=True, type='alicli')

    # delete portchannel
    pc_api.delete_portchannel(data.dut1, dut_portchannel_name_2)
    pc_api.delete_portchannel(data.dut1, dut_portchannel_name)

    if result == 0:
        st.report_pass('test_case_passed')
    else:
        st.report_fail('test_case_failed')