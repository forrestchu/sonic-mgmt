import os
import copy
import pytest
import json
import difflib
import string
import random
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
from apis.common import redis

from esr_vars import * #all the variables used for vrf testcase
from esr_vars import data

def precheck_bgp_isolate(dut):

    cmd = "cli -c 'no page' -c 'show isolated_precheck'"
    output = st.show(dut, cmd)
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

def cli_show_json(dut, command, type='alicli'):
    output = st.show(dut, command, max_time=500, skip_error_check=True, skip_tmpl=True, type=type)
    json_str = json.dumps(output).encode('utf-8')
    last_pos = json_str.rfind('}')
    json_str = json_str[:(last_pos+1)].replace('true','"true"').replace("\\n","").replace("\\","").strip('"')
    try:
        return json.loads(json_str)
    except ValueError:
        st.log('cli_show_json: failed to convert json output')
        return {}

class json_cmp_result(object):
    "json_cmp result class for better assertion messages"

    def __init__(self):
        self.errors = []

    def add_error(self, error):
        "Append error message to the result"
        for line in error.splitlines():
            self.errors.append(line)

    def has_errors(self):
        "Returns True if there were errors, otherwise False."
        return len(self.errors) > 0

    def __str__(self):
        return '\n'.join(self.errors)

def get_textdiff(text1, text2, title1="", title2="", **opts):
    "Returns empty string if same or formatted diff"

    diff = '\n'.join(difflib.unified_diff(text1, text2,
           fromfile=title1, tofile=title2, **opts))
    # Clean up line endings
    diff = os.linesep.join([s for s in diff.splitlines() if s])
    return diff

def difflines(text1, text2, title1='', title2='', **opts):
    "Wrapper for get_textdiff to avoid string transformations."
    text1 = ('\n'.join(text1.rstrip().splitlines()) + '\n').splitlines(1)
    text2 = ('\n'.join(text2.rstrip().splitlines()) + '\n').splitlines(1)
    return get_textdiff(text1, text2, title1, title2, **opts)

def json_diff(d1, d2):
    """
    Returns a string with the difference between JSON data.
    """
    json_format_opts = {
        'indent': 4,
        'sort_keys': True,
    }
    dstr1 = json.dumps(d1, **json_format_opts)
    dstr2 = json.dumps(d2, **json_format_opts)
    return difflines(dstr2, dstr1, title1='Expected value', title2='Current value', n=0)

def _json_list_cmp(list1, list2, parent, result):
    "Handles list type entries."
    # Check second list2 type
    if not isinstance(list1, type([])) or not isinstance(list2, type([])):
        result.add_error(
            '{} has different type than expected '.format(parent) +
            '(have {}, expected {}):\n{}'.format(
                type(list1), type(list2), json_diff(list1, list2)))
        return

    # Check list size
    if len(list2) > len(list1):
        result.add_error(
            '{} too few items '.format(parent) +
            '(have {}, expected {}:\n {})'.format(
                len(list1), len(list2),
                json_diff(list1, list2)))
        return

    # List all unmatched items errors
    unmatched = []
    for expected in list2:
        matched = False
        for value in list1:
            if json_cmp({'json': value}, {'json': expected}) is None:
                matched = True
                break

        if not matched:
            unmatched.append(expected)

    # If there are unmatched items, error out.
    if unmatched:
        result.add_error(
            '{} value is different (\n{})'.format(
                parent, json_diff(list1, list2)))

def json_cmp(d1, d2):
    """
    JSON compare function. Receives two parameters:
    * `d1`: json value
    * `d2`: json subset which we expect

    Returns `None` when all keys that `d1` has matches `d2`,
    otherwise a string containing what failed.

    Note: key absence can be tested by adding a key with value `None`.
    """
    squeue = [(d1, d2, 'json')]
    result = json_cmp_result()

    for s in squeue:
        nd1, nd2, parent = s

        # Handle JSON beginning with lists.
        if isinstance(nd1, type([])) or isinstance(nd2, type([])):
            _json_list_cmp(nd1, nd2, parent, result)
            if result.has_errors():
                return result
            else:
                return None

        # Expect all required fields to exist.
        s1, s2 = set(nd1), set(nd2)
        s2_req = set([key for key in nd2 if nd2[key] is not None])
        diff = s2_req - s1
        if diff != set({}):
            result.add_error('expected key(s) {} in {} (have {}):\n{}'.format(
                str(list(diff)), parent, str(list(s1)), json_diff(nd1, nd2)))

        for key in s2.intersection(s1):
            # Test for non existence of key in d2
            if nd2[key] is None:
                result.add_error('"{}" should not exist in {} (have {}):\n{}'.format(
                    key, parent, str(s1), json_diff(nd1[key], nd2[key])))
                continue

            # If nd1 key is a dict, we have to recurse in it later.
            if isinstance(nd2[key], type({})):
                if not isinstance(nd1[key], type({})):
                    result.add_error(
                        '{}["{}"] has different type than expected '.format(parent, key) +
                        '(have {}, expected {}):\n{}'.format(
                            type(nd1[key]), type(nd2[key]), json_diff(nd1[key], nd2[key])))
                    continue
                nparent = '{}["{}"]'.format(parent, key)
                squeue.append((nd1[key], nd2[key], nparent))
                continue

            # Check list items
            if isinstance(nd2[key], type([])):
                _json_list_cmp(nd1[key], nd2[key], parent, result)
                continue

            # Compare JSON values
            if nd1[key] != nd2[key]:
                result.add_error(
                    '{}["{}"] value is different (\n{})'.format(
                        parent, key, json_diff(nd1[key], nd2[key])))
                continue

    if result.has_errors():
        return result

    return None

## check config db 
def configdb_checkpoint(dut, key, checkfield, checkval, expect = True, checkpoint = ''):
    command = redis.build(dut, redis.CONFIG_DB, 'hgetall "{}"'.format(key))
    output = st.show(dut, command)
    st.log(output)

    redis_cfg_checkpoint = False
    exist = False
    redis_cfg_exist_checkpoint = False if exist else True
    for i in range(len(output)):
        if output[i].get('donor_intf') == checkfield:
            exist = True
            if i+1 < len(output):
                if output[i+1].get('donor_intf') == checkval:
                    redis_cfg_checkpoint = True
            
    if checkval == 'null':
        redis_cfg_exist_checkpoint = False if exist else True
        if redis_cfg_exist_checkpoint != expect:
            st.report_fail("{} confg DB has {} config".format(checkpoint, checkfield))  
    else:
        if redis_cfg_checkpoint != expect:
            st.report_fail("{} confg DB has no right {} config".format(checkpoint, checkfield))

## check config db 
def configdb_onefield_checkpoint(dut, key, checkfield, checkval, expect = True, checkpoint = ''):
    command = redis.build(dut, redis.CONFIG_DB, 'hget "{}" "{}"'.format(key, checkfield))
    output = st.show(dut, command, skip_tmpl=True)
    if output is '':
        st.report_fail("{} confg DB has no right filed {}".format(checkpoint, checkfield))

    output = output.strip('"')
    last_pos = output.rfind('"')
    output = output[:last_pos]
    st.log(output)
    st.log(checkval)
    check = (checkval == output)
    st.log(check)

    if expect is not check:
        st.report_fail("{} confg DB has no right {} config".format(checkpoint, checkfield))

## check config db
def configdb_checkarray(dut, key, checkfield, checkval, expect = True, checkpoint = ''):
    command = redis.build(dut, redis.CONFIG_DB, 'hgetall "{}"'.format(key))
    output = st.show(dut, command)
    st.log(output)

    redis_cfg_checkpoint = False
    exist = False
    for i in range(len(output)):
        if output[i].get('donor_intf') == checkfield:
            exist = True
            if i+1 < len(output):
                vals = output[i+1].get('donor_intf').split(",")
                if checkval in vals:
                    redis_cfg_checkpoint = True

    if redis_cfg_checkpoint != expect:
        st.report_fail("{} confg DB has no right {} config".format(checkpoint, checkfield))

def appdb_checkpoint(dut, key, checkfield, checkval, expect = True, checkpoint = ''):
    command = redis.build(dut, redis.APPL_DB, 'hgetall "{}"'.format(key))
    output = st.show(dut, command)
    st.log(output)

    redis_cfg_checkpoint = False
    exist = False
    redis_cfg_exist_checkpoint = False if exist else True
    for i in range(len(output)):
        if output[i].get('donor_intf') == checkfield:
            exist = True
            if i+1 < len(output):
                if output[i+1].get('donor_intf') == checkval:
                    redis_cfg_checkpoint = True
            
    if checkval == 'null':
        redis_cfg_exist_checkpoint = False if exist else True
        if redis_cfg_exist_checkpoint != expect:
            st.report_fail("{} confg DB has {} config".format(checkpoint, checkfield))  
    else:
        if redis_cfg_checkpoint != expect:
            st.report_fail("{} confg DB has no right {} config".format(checkpoint, checkfield))

def appdb_onefield_checkpoint(dut, key, checkfield, checkval, expect = True, checkpoint = ''):
    command = redis.build(dut, redis.APPL_DB, 'hget "{}" "{}"'.format(key, checkfield))
    output = st.show(dut, command, skip_tmpl=True)
    if output is '':
        st.report_fail("{} app DB has no right filed {}".format(checkpoint, checkfield))

    output = output.strip('"')
    last_pos = output.rfind('"')
    output = output[:last_pos]
    st.log(output)
    st.log(checkval)
    check = (checkval == output)
    st.log(check)

    if expect is not check:
        st.report_fail("{} app DB has no right {} config".format(checkpoint, checkfield))

def appdb_get_onefield(dut, key, field):
    command = redis.build(dut, redis.APPL_DB, 'hget "{}" "{}"'.format(key, field))
    output = st.show(dut, command, skip_tmpl=True)
    if output is '':
        return None

    output = output.strip('"')
    last_pos = output.rfind('"')
    output = output[:last_pos]
    st.log(output)
    return output

## check vrf leran route nums
# show ip route vrf VRFNAME summary
# compare: 1 more than or equal , 0 equal, -1 less than

# show ip route vrf SX-XIAN-CM-TC29 summary
# Route Source         Routes               FIB  (vrf Vrf10050)
# connected            1                    1                    
# static               1                    1                    
# ------
# Totals               2                    2                    
# Totals - Dataplane   N/A                  2                    
 
# [{u'fib_ibgp': '', u'total': '2', u'fib_static': '1', u'fib_ebgp': '', u'ibgp': '', u'ebgp': '', 
# u'vrf': 'Vrf10050', u'fib_connected': '1', u'static': '1', u'fib_ospf': '', u'connected': '1', u'ospf': '', u'fib_total': '2'}]
def check_vrf_route_nums(dut, vrfname, expected_num, compare):
    cmd = "show ip route vrf {} summary".format(vrfname)
    result = st.show(dut, cmd, type='alicli')
    st.log(result)

    if result is not None:
        totals = result[0]['fib_total']
        if totals.isdigit():
            totals_num = string.atoi(totals)
            if totals_num >= expected_num and compare==1:
                return True
            elif totals_num == expected_num and compare==0:
                return True
            elif totals_num < expected_num and compare==-1:
                return True
            else:
                st.log("totals fib num is {} , expected is {}".format(totals_num, expected_num))
                return False
    return False

def check_vpn_route_nums(dut, expected_num, compare):
    cmd = "show bgp ipv4 vpn statistics"
    result = st.show(dut, cmd, type='alicli')
    st.log(result)

    if result is not None:
        totals = result[0]['totaladv']
        if totals.isdigit():
            totals_num = string.atoi(totals)
            if totals_num >= expected_num and compare==1:
                return True
            elif totals_num == expected_num and compare==0:
                return True
            elif totals_num < expected_num and compare==-1:
                return True
            else:
                st.log("totals adv route num is {} , expected is {}".format(totals_num, expected_num))
                return False
    return False

def get_random_array(start, end, num):
    ra = []
    for i in range(num):
        x = random.randint(start, end)
        ra.append(x)
    st.log(ra)
    return ra

def check_bgp_vrf_ipv4_uni_sid(dut, vrf, prefix, expected_sid):
    cmd = "cli -c 'no page' -c 'show bgp vrf {} ipv4 unicast {}'".format(vrf, prefix)
    result = st.show(dut, cmd)
    st.log(result)

    if result is not None and len(result) > 0:
        for e in result:
            sid = e['sid']
            if sid == expected_sid:
                st.log("sid check right {}".format(sid))
                return True
            else:
                st.log("sid is {} , expected_sid is {}".format(sid, expected_sid))
                # return False
    return False