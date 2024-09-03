import os
import copy
import pytest
from collections import OrderedDict
from utilities import parallel

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
from mc_vars import * #all the variables used for vrf testcase
from mc_vars import data

def precheck_bgp_isolate(dut):

    cmd = "cli -c 'no page' -c 'show isolated_precheck'"
    output = st.show(dut, cmd)
    st.log(output)
    if len(output) == 0:
        st.error("Show OUTPUT is Empty")
        st.report_fail("bgp isolate precheck failed")

    for i in range(len(output)):
        if output[i]['precheck'] != 'success':
            st.error("vrf {} neighbor {} pre check failed".format(output[i]['vrf'],output[i]['neighbor']))
            return False
    
    return True

def check_bgp_isolate(dut, check_status):

    cmd = "cli -c 'no page' -c 'show isolated_bgp'"
    output = st.show(dut,cmd)
    if len(output) == 0:
        st.error("Show OUTPUT is Empty")
        st.report_fail("bgp isolate failed")

    for i in range(len(output)):
        if output[i]['status'] != check_status:
            st.error("vrf {} neighbor {} isolate failed".format(output[i]['vrf'],output[i]['neighbor']))
            return False
    
    return True


def precheck_bgp_advanced_isolate(dut):

    cmd = "cli -c 'no page' -c 'show advanced_isolated_precheck'"
    output = st.show(dut, cmd)
    st.log(output)
    if len(output) == 0:
        st.error("Show OUTPUT is Empty")
        st.report_fail("bgp isolate advanced precheck failed")

    for i in range(len(output)):
        if output[i]['precheck'] != 'success':
            st.error("vrf {} neighbor {} pre check failed".format(output[i]['vrf'],output[i]['neighbor']))
            return False
    
    return True

def check_bgp_advanced_isolate(dut, check_status):

    cmd = "cli -c 'no page' -c 'show advanced_isolated_bgp'"
    output = st.show(dut,cmd)
    if len(output) == 0:
        st.error("Show OUTPUT is Empty")
        st.report_fail("bgp isolate failed")

    for i in range(len(output)):
        if output[i]['status'] != check_status:
            st.error("vrf {} neighbor {} isolate failed".format(output[i]['vrf'],output[i]['neighbor']))
            return False
    
    return True


def bgp_permit_route_map_set(dut, local_as_id, vrf, group_name, map_name, as_path, config='yes'):

    command = "route-map {} permit 10\n".format(map_name)
    command += "set as-path prepend {}\n".format(as_path)
    command += "exit\n"
    command += "router bgp {} vrf {}\n".format(local_as_id, vrf)
    command += " address-family ipv4 unicast\n"
    if config == 'yes':
        command += "neighbor {} route-map {} out\n".format(group_name, map_name)
    else:
        command += "no neighbor {} route-map {} out\n".format(group_name, map_name)
    command += "exit\n"
    command += " address-family ipv6 unicast\n"
    group_v6_name = group_name + "-v6"
    if config == 'yes':
        command += "neighbor {} route-map {} out\n".format(group_v6_name, map_name)
    else:
        command += "no neighbor {} route-map {} out\n".format(group_v6_name, map_name)
    command += "exit\n"
    command += "exit\n"
    st.config(dut, command, skip_error_check=True, type='alicli')


def bgp_deny_route_map_apply(dut, local_as_id, vrf, group_name, map_name, config='yes'):

    command = "router bgp {} vrf {}\n".format(local_as_id, vrf)
    command += " address-family ipv4 unicast\n"
    if config == 'yes':
        command += "neighbor {} route-map {} out\n".format(group_name, map_name)
    else:
        command += "no neighbor {} route-map {} out\n".format(group_name, map_name)
    command += "exit\n"
    command += " address-family ipv6 unicast\n"
    group_v6_name = group_name + "-v6"
    if config == 'yes':
        command += "neighbor {} route-map {} out\n".format(group_v6_name, map_name)
    else:
        command += "no neighbor {} route-map {} out\n".format(group_v6_name, map_name)
    command += "exit\n"
    command += "exit\n"
    st.config(dut, command, skip_error_check=True, type='alicli')

def bgp_maximum_paths_set(dut, local_as_id, vrf, max_paths_num='64', config='yes'):

    command = "router bgp {} vrf {}\n".format(local_as_id, vrf)
    command += " address-family ipv4 unicast\n"
    if config == 'yes':
        command += "maximum-paths {}\n".format(max_paths_num)
    else:
        command += "no maximum-paths\n"
    command += "exit\n"
    command += " address-family ipv6 unicast\n"
    if config == 'yes':
        command += "maximum-paths {}\n".format(max_paths_num)
    else:
        command += "no maximum-paths\n"
    command += "exit\n"
    st.config(dut, command, skip_error_check=True, type='alicli')
    
def dut_load_bgp_ecmp_member(dut, local_as_id, nbr_as_id, vrf, ip_intf_list, ecmp_member_num, group_name, config='yes'):
    vrf_ip_list=[]
    vrf_ipv6_list=[]
    ecmp_scale_subintf_list = []

    for i in range(ecmp_member_num):
        subintf = int(data.dut_ecmp_scale_start_subintf) + i
        ecmp_scale_subintf_list.append(str(subintf))

    for ip in ip_intf_list:
        if ip['vrf'] == vrf and ip['interface'].startswith('Eth'):
            if ip['interface'].split('.')[1] in ecmp_scale_subintf_list:
                if ':' not in ip['ip']:
                    vrf_ip_list.append(ip['ip'].split('/')[0])
                else:
                    vrf_ipv6_list.append(ip['ip'].split('/')[0])

    dut_load_bgp_neigbor_to_peer_group(dut, local_as_id, nbr_as_id, vrf, vrf_ip_list, vrf_ipv6_list, group_name, config)

def dut_load_bgp_neigbor_to_peer_group(dut, local_as_id, nbr_as_id, vrf, vrf_ip_list, vrf_ipv6_list, group_name, config='yes'):
    if config == 'yes':
        command = "router bgp {} vrf {}\n".format(local_as_id, vrf)
        command += "neighbor {} peer-group\n".format(group_name)
        command += "neighbor {} remote-as {}\n".format(group_name, nbr_as_id)
        for ip in vrf_ip_list:
            command += "neighbor {} peer-group {}\n".format(ip, group_name)
        command += " address-family ipv4 unicast\n"
        command += "neighbor {} activate\n".format(group_name)
        command += "neighbor {} soft-reconfiguration inbound\n".format(group_name)
        command += "exit\n"
        command += "exit\n"
        st.config(dut, command, skip_error_check=True, type='alicli')

        command = "router bgp {} vrf {}\n".format(local_as_id, vrf)
        ipv6_group_name =  group_name + "-v6"
        command += "neighbor {} peer-group\n".format(ipv6_group_name)
        command += "neighbor {} remote-as {}\n".format(ipv6_group_name, nbr_as_id)
        for ip in vrf_ipv6_list:
            command += "neighbor {} peer-group {}\n".format(ip, ipv6_group_name)
        command += " address-family ipv6 unicast\n"
        command += "neighbor {} activate\n".format(ipv6_group_name)
        command += "neighbor {} soft-reconfiguration inbound\n".format(ipv6_group_name)
        command += "exit\n"
        command += "exit\n"
        st.config(dut, command, skip_error_check=True, type='alicli')

        st.show(dut,"show vrf")

        #command = "router bgp {} vrf {}\n".format(local_as_id, vrf)
        #command += "bgp bestpath compare-routerid\n"
        #st.config(dut, command, skip_error_check=True, type='vtysh')
    elif config == 'no':
        command = "router bgp {} vrf {}\n".format(local_as_id, vrf)
        for ip in vrf_ipv6_list:
            command += "no neighbor {} peer-group\n".format(ip)
        for ip in vrf_ip_list:
            command += "no neighbor {} peer-group\n".format(ip)
        command += "exit\n"
        st.config(dut, command, skip_error_check=True, type='alicli')

        st.show(dut,"show vrf")

def dut_load_bgp_isolate_peer_group(dut, local_as_id, nbr_as_id, vrf, nbr_ip_list, config='yes'):
    vrf_ip_list=[]
    vrf_ipv6_list=[]
    ecmp_scale_subintf_list = []

    for i in range(data.dut_isolate_group_num):
        subintf = int(data.dut_ecmp_scale_start_subintf) + i
        ecmp_scale_subintf_list.append(str(subintf))

    for ip in nbr_ip_list:
        if ip['vrf'] == vrf and ip['interface'].startswith('Eth'):
            if ip['interface'].split('.')[1] in ecmp_scale_subintf_list:
                if ':' not in ip['ip']:
                    vrf_ip_list.append(ip['ip'].split('/')[0])
                else:
                    vrf_ipv6_list.append(ip['ip'].split('/')[0])

    if config == 'yes':
        command = "router bgp {} vrf {}\n".format(local_as_id, vrf)
        groupid =0
        for ip in vrf_ip_list:
            group_name = 'isolate_' + str(groupid)
            groupid += 1
            command += "neighbor {} peer-group {}\n".format(ip, group_name)
        command += "exit\n"
        st.config(dut, command, skip_error_check=True, type='alicli')

        command = "router bgp {} vrf {}\n".format(local_as_id, vrf)
        groupid =0
        for ip in vrf_ipv6_list:
            group_name = 'isolate_v6_' + str(groupid)
            groupid += 1
            command += "neighbor {} peer-group {}\n".format(ip, group_name)
        command += "exit\n"
        st.config(dut, command, skip_error_check=True, type='alicli')
    elif config == 'no':
        command = "router bgp {} vrf {}\n".format(local_as_id, vrf)
        for ip in vrf_ip_list:
            command += "no neighbor {} peer-group\n".format(ip)
        command += "exit\n"
        st.config(dut, command, skip_error_check=True, type='alicli')

        command = "router bgp {} vrf {}\n".format(local_as_id, vrf)
        for ip in vrf_ipv6_list:
            command += "no neighbor {} peer-group\n".format(ip)
        command += "exit\n"
        st.config(dut, command, skip_error_check=True, type='alicli')

    st.show(dut, "show vrf")