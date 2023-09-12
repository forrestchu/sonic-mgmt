# -*- coding:utf-8 -*-
import pytest
import json
import re
import os

from spytest import st, tgapi, SpyTestDict
import apis.routing.bgp as bgpfeature
from apis.common import redis
from bgp_cli import BGP_CLI

# param
param_data = SpyTestDict()

# test data
data = SpyTestDict()
data.as_num = 100
data.remote_as_num = 200
data.ip4_addr = ["192.168.1.1", "192.168.1.2", "192.168.2.1", "192.168.2.2", "192.168.3.1", "192.168.3.3",
                 "192.168.4.1", "192.168.4.2", "192.168.5.1", "192.168.5.2", "192.168.6.1", "192.168.6.2"]
data.ip4_addr_rt = ["192.168.1.0", "192.168.2.0", "192.168.3.0", "192.168.4.0", "192.168.5.0", "192.168.6.0"]
data.ip6_addr = ["2001::1", "2001::2", "3301::1", "3301::2", "4441::1", "4441::2", "5551::1", "5551::2", "6661::1",
                 "6661::2", "7771::1", "7771::2"]
data.ip6_addr_rt = ["2001::", "3301::", "4441::", "5551::", "6661::", "7771::"]
data.loopback_1 = ["11.11.11.1", "22.22.22.1", "33.33.33.1"]
data.loopback6_1 = ["7767:12::2", "6671:230f:12::f", "9109:2cd1:341::3"]
data.af_ipv4 = "ipv4"
data.af_ipv6 = "ipv6"
data.router_id = "110.110.110.1"

data.keep_alive = 60
data.hold = 180

ALICLI_VIEW = "cli"
CONFIG_VIEW = "configure terminal"
ROUTE_BGP_VIEW = "router bgp {}"

IPV4_UNICAST_VIEW = "address-family ipv4 unicast"
IPV6_UNICAST_VIEW = "address-family ipv6 unicast"

def get_single_dut():
    vars = st.get_testbed_vars()
    data['dut'] = vars.D1

def config_depend_cli():
    data['bgpcli_obj'] = BGP_CLI(data['dut'], data, param_data)
    bgpcli_obj = data['bgpcli_obj']
    ## create router bgp as
    bgpcli_obj.create_bgp_route(data.as_num)
    ### config bgp router id
    bgpcli_obj.config_bgp_router_id(data.router_id)
    ### create bgp ipv4 neighbor
    bgpcli_obj.create_neighbor_v4(data.ip4_addr[0], data.remote_as_num)

def restore_env():
    bgpcli_obj = data['bgpcli_obj']
    bgpcli_obj.flush_neighbors()
    bgpcli_obj.clear_bgp_router_id(data.router_id)
    bgpcli_obj.flush_bgp_community_list()
    bgpcli_obj.flush_bgp_aspath_access_lists()

@pytest.fixture(scope="module", autouse=True)
def cli_module_hooks(request):
    ########### module prologue #################
    st.log("pre mod config cli")
    st.ensure_min_topology("D1")
    get_single_dut()
    config_depend_cli()
    yield
    ########### module epilogue #################
    st.log("post mod config cli")
    restore_env()

# @pytest.fixture(scope='class')
# def cli_class_hooks(request):
#     ########### class prologue #################
#     yield
#     ########### class epilogue #################

@pytest.fixture(scope="function", autouse=True)
def cli_function_hooks(request):
    ########### function prologue #################
    st.log("pre func config cli")
    yield
    ########### function epilogue #################
    st.log("psot func config cli")

## check config db
## 如果checkfield 值等于checkval， 返回true， 不等返回false。 与expect比较
## 预期checkfield不存在， checkval为字符串 'null' ，存在为false
def configdb_checkpoint(dut, key, checkfield, checkval, expect = True, checkpoint = ''):
    command = redis.build(dut, redis.CONFIG_DB, 'hgetall "{}"'.format(key))
    output = st.show(dut, command)
    st.log(output)

    redis_cfg_checkpoint = False
    exist = False
    redis_cfg_exist_checkpoint = False if exist else True
    for i in range(len(output)):
        st.log("======{}".format(output[i]))
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
## 检查checkfield的值（checkfield值是一个array）是否包含checkval， 并与expect比较，相等返回true， 不等返回false
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

def frr_config_checkpoint(obj, key, expect = True, checkpoint = ''):
    output_bgpd = obj.show_frr_bgp_running()
    st.log(output_bgpd)
    checkflag = True
    temp = output_bgpd
    for sub_key in key.split('|'):
        temp = temp.get(sub_key)
        st.log("subkey {} , val {}".format(sub_key, temp))
        if isinstance(temp,dict):
            continue
        elif temp == 'true':
            checkflag = True
            break
        else:
            checkflag = False
            break

    if checkflag != expect:
        st.report_fail("{} frr config has no {} config".format(checkpoint, key))


def zebra_config_checkpoint(obj, key, expect = True, checkpoint = ''):
    output_bgpd = obj.show_frr_running()
    st.log(output_bgpd)
    checkflag = True
    temp = output_bgpd
    for sub_key in key.split('|'):
        temp = temp.get(sub_key)
        st.log("subkey {} , val {}".format(sub_key, temp))
        if isinstance(temp,dict):
            continue
        elif temp == 'true':
            checkflag = True
            break
        else:
            checkflag = False
            break

    if checkflag != expect:
        st.report_fail("{} frr config has no {} config".format(checkpoint, key))


@pytest.mark.bgp_cli
def test_cli_bgp_remove_private_as_v4():
    st.log("test_cli_bgp_remove_private_as_v4 begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']
    peer_ip = data.ip4_addr[0]

    ### config cli ###
    st.log("config cli")

    bgpcli_obj.config_neighbor(peer = peer_ip, address_family='true', activate='true', remove_private_as='true',
        af_pro='ipv4', af_modifier='unicast')

    ### check config db ###
    st.log("check config db")

    ## hgetall BGP_NEIGHBOR|192.168.1.1|ipv4
    peerkey = "BGP_NEIGHBOR|{}|ipv4".format(peer_ip)
    configdb_checkpoint(dut, peerkey, 'remove_private_as', 'true', True, 'check1')

    ### check frr running-config ##
    st.log("check frr running-config")
    frr_key = "router bgp {}|address-family ipv4 unicast|neighbor {} remove-private-AS".format(bgpcli_obj.get_local_as() ,peer_ip)
    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check2')

    ### reboot and check config recovery ###
    st.log("reboot and check config recovery")
    ##bgpcli_obj.save_config_and_reboot()

    configdb_checkpoint(dut, peerkey, 'remove_private_as', 'true', True, 'check3')

    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check4')

    ### restore the environment
    st.log("restore the environment")
    bgpcli_obj.config_neighbor(peer = peer_ip, remove_private_as='false', address_family='true',
        af_pro='ipv4', af_modifier='unicast')
    configdb_checkpoint(dut, peerkey, 'remove_private_as', 'false', True, 'check5')
    frr_config_checkpoint(bgpcli_obj, frr_key, False, 'check6')

    # conflict check 
    bgpcli_obj.create_neighbor_v4(data.ip4_addr[-1], data.as_num)
    bgpcli_obj.config_neighbor_activate(IPV4_UNICAST_VIEW, data.ip4_addr[-1])
    bgpcli_obj.config_bgp_neighbor_route_reflector_client(IPV4_UNICAST_VIEW, data.ip4_addr[-1])
    key_configdb = "BGP_NEIGHBOR|{}|ipv4".format(data.ip4_addr[-1])
    configdb_checkpoint(dut, key_configdb, "remove_private_as", "null", True, "check7")

    st.report_pass("test_case_passed")

@pytest.mark.bgp_cli
def test_cli_bgp_ebgp_multihop_v4():
    st.log("test_cli_bgp_ebgp_multihop_v4 begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']
    peer_ip = data.ip4_addr[0]

    ### config cli ###
    st.log("config cli")
    bgpcli_obj.config_neighbor(peer = peer_ip, ebgp_multihop='true')

    ### check config db ###
    st.log("check config db")
    peerkey = "BGP_NEIGHBOR|{}|global".format(peer_ip)
    configdb_checkpoint(dut, peerkey, 'ebgp_multihop', '255', True, 'check1')

    ### check frr running-config ##
    st.log("check frr running-config")
    frr_key = "router bgp {}|neighbor {} ebgp-multihop {}".format(bgpcli_obj.get_local_as() ,peer_ip, '255')
    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check2')

    ### reboot and check config recovery ###
    st.log("reboot and check config recovery")
    ##bgpcli_obj.save_config_and_reboot()
    configdb_checkpoint(dut, peerkey, 'ebgp_multihop', '255', True, 'check3')
    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check4')

    ### restore the environment
    st.log("restore the environment")
    bgpcli_obj.config_neighbor(peer = peer_ip, ebgp_multihop='false')
    configdb_checkpoint(dut, peerkey, 'ebgp_multihop', 'null', True, 'check5')
    frr_config_checkpoint(bgpcli_obj, frr_key, False, 'check6')

    st.report_pass("test_case_passed")

@pytest.mark.bgp_cli
def test_cli_bgp_send_community_v4():
    st.log("test_cli_bgp_send_community_v4 begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']
    peer_ip = data.ip4_addr[0]

    ### config cli ###
    st.log("config cli")

    bgpcli_obj.config_neighbor(peer = peer_ip, address_family='true', activate='true', send_community='false',
        af_pro='ipv4', af_modifier='unicast')

    ### check config db ###
    st.log("check config db")

    ## hgetall BGP_NEIGHBOR|192.168.1.1|ipv4
    peerkey = "BGP_NEIGHBOR|{}|ipv4".format(peer_ip)
    configdb_checkpoint(dut, peerkey, 'send_community', 'false', True, 'check1')

    ### check frr running-config ##
    st.log("check frr running-config")
    frr_key = "router bgp {}|address-family ipv4 unicast|no neighbor {} send-community".format(bgpcli_obj.get_local_as() ,peer_ip)
    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check2')

    ### reboot and check config recovery ###
    st.log("reboot and check config recovery")
    ##bgpcli_obj.save_config_and_reboot()

    configdb_checkpoint(dut, peerkey, 'send_community', 'false', True, 'check3')

    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check4')

    ### restore the environment
    st.log("restore the environment")
    bgpcli_obj.config_neighbor(peer = peer_ip, send_community='true', address_family='true',
        af_pro='ipv4', af_modifier='unicast')
    configdb_checkpoint(dut, peerkey, 'send_community', 'true', True, 'check5')
    frr_config_checkpoint(bgpcli_obj, frr_key, False, 'check6')

    st.report_pass("test_case_passed")


@pytest.mark.bgp_cli
def test_cli_bgp_next_hop_self_v4():
    st.log("test_cli_bgp_next_hop_self_v4 begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']
    peer_ip = data.ip4_addr[0]

    ### config cli ###
    st.log("config cli")

    bgpcli_obj.config_neighbor(peer = peer_ip, address_family='true', activate='true', next_hop_self='true',
        af_pro='ipv4', af_modifier='unicast')

    ### check config db ###
    st.log("check config db")

    ## hgetall BGP_NEIGHBOR|192.168.1.1|ipv4
    peerkey = "BGP_NEIGHBOR|{}|ipv4".format(peer_ip)
    configdb_checkpoint(dut, peerkey, 'next_hop_self', 'true', True, 'check1')

    ### check frr running-config ##
    st.log("check frr running-config")
    frr_key = "router bgp {}|address-family ipv4 unicast|neighbor {} next-hop-self".format(bgpcli_obj.get_local_as() ,peer_ip)
    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check2')

    ### reboot and check config recovery ###
    st.log("reboot and check config recovery")
    ##bgpcli_obj.save_config_and_reboot()

    configdb_checkpoint(dut, peerkey, 'next_hop_self', 'true', True, 'check3')

    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check4')

    ### restore the environment
    st.log("restore the environment")
    bgpcli_obj.config_neighbor(peer = peer_ip, next_hop_self='false', address_family='true',
        af_pro='ipv4', af_modifier='unicast')
    configdb_checkpoint(dut, peerkey, 'next_hop_self', 'false', True, 'check5')
    frr_config_checkpoint(bgpcli_obj, frr_key, False, 'check6')

    st.report_pass("test_case_passed")

@pytest.mark.bgp_cli
def test_cli_bgp_bfd_v4():
    st.log("test_cli_bgp_bfd_v4 begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']
    peer_ip = data.ip4_addr[0]

    ### config cli ###
    st.log("config cli")

    bgpcli_obj.config_neighbor(peer = peer_ip, bfd='true')

    ### check config db ###
    st.log("check config db")

    ## hgetall BGP_NEIGHBOR|192.168.1.1|global
    peerkey = "BGP_NEIGHBOR|{}|global".format(peer_ip)
    configdb_checkpoint(dut, peerkey, 'bfd', 'true', True, 'check1')

    ### check frr running-config ##
    st.log("check frr running-config")

    if 'eSR' == os.getenv('SPYTEST_PROJECT'):
        frr_key = "router bgp {}|neighbor {} bfd 3 300 300".format(bgpcli_obj.get_local_as() ,peer_ip)
    else:
        frr_key = "router bgp {}|neighbor {} bfd".format(bgpcli_obj.get_local_as() ,peer_ip)

    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check2')

    ### reboot and check config recovery ###
    st.log("reboot and check config recovery")
    ##bgpcli_obj.save_config_and_reboot()

    configdb_checkpoint(dut, peerkey, 'bfd', 'true', True, 'check3')
    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check4')

    ### restore the environment
    st.log("restore the environment")
    bgpcli_obj.config_neighbor(peer = peer_ip, bfd='false')
    configdb_checkpoint(dut, peerkey, 'bfd', 'null', True, 'check5')
    frr_config_checkpoint(bgpcli_obj, frr_key, False, 'check6')

    st.report_pass("test_case_passed")

@pytest.mark.bgp_cli
def test_cli_bgp_bfd_with_param_v4():
    st.log("test_cli_bgp_bfd_with_param_v4 begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']
    peer_ip = data.ip4_addr[0]

    ### config cli ###
    st.log("config cli")

    bgpcli_obj.config_neighbor(peer = peer_ip, bfd='true',detect_multiplier=3,tx_timer=300,rx_timer=200)

    ### check config db ###
    st.log("check config db")

    ## hgetall BGP_NEIGHBOR|192.168.1.1|global
    peerkey = "BGP_NEIGHBOR|{}|global".format(peer_ip)
    configdb_checkpoint(dut, peerkey, 'bfd', 'true', True, 'check1-1')
    configdb_checkpoint(dut, peerkey, 'detect_multiplier', '3', True, 'check1-2')
    configdb_checkpoint(dut, peerkey, 'rx_timer', '300', True, 'check1-3')
    configdb_checkpoint(dut, peerkey, 'tx_timer', '200', True, 'check1-4')

    ### check frr running-config ##
    st.log("check frr running-config")
    frr_key = "router bgp {}|neighbor {} bfd {} {} {}".format(bgpcli_obj.get_local_as() ,peer_ip, 3, 300, 200)
    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check2')

    ### reboot and check config recovery ###
    st.log("reboot and check config recovery")
    ##bgpcli_obj.save_config_and_reboot()

    configdb_checkpoint(dut, peerkey, 'bfd', 'true', True, 'check3-1')
    configdb_checkpoint(dut, peerkey, 'detect_multiplier', '3', True, 'check3-2')
    configdb_checkpoint(dut, peerkey, 'rx_timer', '300', True, 'check3-3')
    configdb_checkpoint(dut, peerkey, 'tx_timer', '200', True, 'check3-4')
    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check4')

    ### restore the environment
    st.log("restore the environment")
    bgpcli_obj.config_neighbor(peer = peer_ip, bfd='false')
    configdb_checkpoint(dut, peerkey, 'bfd', 'null', True, 'check5-1')
    configdb_checkpoint(dut, peerkey, 'detect_multiplier', 'null', True, 'check5-2')
    configdb_checkpoint(dut, peerkey, 'rx_timer', 'null', True, 'check5-3')
    configdb_checkpoint(dut, peerkey, 'tx_timer', 'null', True, 'check5-4')
    frr_config_checkpoint(bgpcli_obj, frr_key, False, 'check6')

    st.report_pass("test_case_passed")

@pytest.mark.bgp_cli
def test_cli_bgp_allowas_in():
    st.log("test_cli_bgp_allowas_in begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']
    peer_ip = data.ip4_addr[0]

    ### config cli ###
    st.log("config cli")

    bgpcli_obj.config_neighbor(peer = peer_ip, address_family = 'true', allowas_in = 'origin',
        af_pro = 'ipv4', af_modifier = 'unicast')
    bgpcli_obj.config_neighbor(peer = peer_ip, address_family = 'true', allowas_in = '10',
        af_pro = 'ipv6', af_modifier = 'unicast')
    
    ### check config db ###
    st.log("check config db")

    ## hgetall BGP_NEIGHBOR|192.168.1.1|ipv4 
    peerkey = "BGP_NEIGHBOR|{}|ipv4".format(peer_ip)
    configdb_checkpoint(dut, peerkey, 'allowas_in', 'origin', True, 'check1-1')
    peerkey_num = "BGP_NEIGHBOR|{}|ipv6".format(peer_ip)
    configdb_checkpoint(dut, peerkey_num, 'allowas_in', '10', True, 'check1-2')

    ### check frr running-config ##
    st.log("check frr running-config")
    frr_key = "router bgp {}|address-family ipv4 unicast|neighbor {} allowas-in origin".format(bgpcli_obj.get_local_as(), peer_ip)
    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check2-1')
    frr_key_num = "router bgp {}|address-family ipv6 unicast|neighbor {} allowas-in 10".format(bgpcli_obj.get_local_as(), peer_ip)
    frr_config_checkpoint(bgpcli_obj, frr_key_num, True, 'check2-2')

    ### restore the environment
    st.log("restore the environment")
    bgpcli_obj.config_neighbor(peer = peer_ip, address_family = 'true', allowas_in = 'false',
        af_pro = 'ipv4', af_modifier = 'unicast')
    configdb_checkpoint(dut, peerkey, 'allowas_in', 'null', True, 'check3-1')
    frr_config_checkpoint(bgpcli_obj, frr_key, False, 'check4-1')
    bgpcli_obj.config_neighbor(peer = peer_ip, address_family = 'true', allowas_in = 'false',
        af_pro = 'ipv6', af_modifier = 'unicast')
    configdb_checkpoint(dut, peerkey_num, 'allowas_in', 'null', True, 'check3-2')
    frr_config_checkpoint(bgpcli_obj, frr_key_num, False, 'check4-2')

    st.report_pass("test_case_passed")

@pytest.mark.bgp_cli
def test_cli_bgp_reboot_config_recover():
    st.log("test_cli_bgp_reboot_config_recover begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']
    peer_ip = data.ip4_addr[0]

    ### config cli ###
    st.log("config cli")

    bgpcli_obj.config_neighbor(peer = peer_ip, bfd='true',detect_multiplier=3,tx_timer=300,rx_timer=200)
    bgpcli_obj.config_neighbor(peer = peer_ip, address_family='true', activate='true', remove_private_as='true',
        af_pro='ipv4', af_modifier='unicast', next_hop_self='true', ebgp_multihop='true',send_community='false', allowas_in = 'origin')
    bgpcli_obj.config_neighbor(peer = peer_ip, address_family = 'true', allowas_in = '10',
        af_pro = 'ipv6', af_modifier = 'unicast')

    ## hgetall BGP_NEIGHBOR|192.168.1.1|global
    peerkey = "BGP_NEIGHBOR|{}|global".format(peer_ip)

    ### reboot and check config recovery ###
    st.log("reboot and check config recovery")
    bgpcli_obj.save_config_and_reboot()

    ## bfd
    st.log("check config recovery of bfd")
    configdb_checkpoint(dut, peerkey, 'bfd', 'true', True, 'check1-1')
    configdb_checkpoint(dut, peerkey, 'detect_multiplier', '3', True, 'check1-2')
    configdb_checkpoint(dut, peerkey, 'rx_timer', '300', True, 'check1-3')
    configdb_checkpoint(dut, peerkey, 'tx_timer', '200', True, 'check1-4')
    frr_key = "router bgp {}|neighbor {} bfd {} {} {}".format(bgpcli_obj.get_local_as() ,peer_ip, 3, 300, 200)
    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check1-5')
    st.log("restore the environment")
    bgpcli_obj.config_neighbor(peer = peer_ip, bfd='false')

    ## ebgp_multihop
    frr_key = "router bgp {}|neighbor {} ebgp-multihop {}".format(bgpcli_obj.get_local_as() ,peer_ip, '255')
    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check3-1')
    configdb_checkpoint(dut, peerkey, 'ebgp_multihop', '255', True, 'check3-2')
    st.log("restore the environment")
    bgpcli_obj.config_neighbor(peer = peer_ip, ebgp_multihop='false')

    peerkey = "BGP_NEIGHBOR|{}|ipv4".format(peer_ip)
    peerkey_num = "BGP_NEIGHBOR|{}|ipv6".format(peer_ip)

    ## remove-private-AS
    frr_key = "router bgp {}|address-family ipv4 unicast|neighbor {} remove-private-AS".format(bgpcli_obj.get_local_as() ,peer_ip)
    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check2-1')
    configdb_checkpoint(dut, peerkey, 'remove_private_as', 'true', True, 'check2-2')
    st.log("restore the environment")
    bgpcli_obj.config_neighbor(peer = peer_ip, remove_private_as='false', address_family='true',
        af_pro='ipv4', af_modifier='unicast')

    ## send_community
    frr_key = "router bgp {}|address-family ipv4 unicast|no neighbor {} send-community".format(bgpcli_obj.get_local_as() ,peer_ip)
    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check4-1')
    configdb_checkpoint(dut, peerkey, 'send_community', 'false', True, 'check4-2')
    st.log("restore the environment")
    bgpcli_obj.config_neighbor(peer = peer_ip, send_community='true', address_family='true',
        af_pro='ipv4', af_modifier='unicast')

    ## next_hop_self
    frr_key = "router bgp {}|address-family ipv4 unicast|neighbor {} next-hop-self".format(bgpcli_obj.get_local_as() ,peer_ip)
    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check5-1')
    configdb_checkpoint(dut, peerkey, 'next_hop_self', 'true', True, 'check5-2')
    st.log("restore the environment")
    bgpcli_obj.config_neighbor(peer = peer_ip, next_hop_self='false', address_family='true',
        af_pro='ipv4', af_modifier='unicast')

    ## allowas_in
    frr_key = "router bgp {}|address-family ipv4 unicast|neighbor {} allowas-in origin".format(bgpcli_obj.get_local_as(), peer_ip)
    frr_key_num = "router bgp {}|address-family ipv6 unicast|neighbor {} allowas-in 10".format(bgpcli_obj.get_local_as(), peer_ip)
    frr_config_checkpoint(bgpcli_obj, frr_key, True, 'check6-1-1')
    frr_config_checkpoint(bgpcli_obj, frr_key_num, True, 'check6-1-2')
    configdb_checkpoint(dut, peerkey, 'allowas_in', 'origin', True, 'check6-2-1')
    configdb_checkpoint(dut, peerkey_num, 'allowas_in', '10', True, 'check6-2-2')
    st.log("restore the environment")
    bgpcli_obj.config_neighbor(peer = peer_ip, address_family = 'true', allowas_in = 'false',
        af_pro = 'ipv4', af_modifier = 'unicast')
    bgpcli_obj.config_neighbor(peer = peer_ip, address_family = 'true', allowas_in = 'false',
        af_pro = 'ipv6', af_modifier = 'unicast')

    st.report_pass("test_case_passed")

@pytest.mark.bgp_cli
@pytest.mark.bgp_community_list
def test_cli_bgp_community_list_normal():
    st.log("test_cli_bgp_community_list_normal begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    st.log("config cli:  normal cases")
    ###add case data
    if 'eSR' == os.getenv('SPYTEST_PROJECT'):
        item = [["50","deny","50:51","deny"],["60","permit","60:61","permit"],["150","deny","50:51 51:52","deny"],["250","permit","50:51 51:52 52:53","permit"],
                ["50","permit","51:52","permit"],["60","deny","61:62 63:64","deny"],["150","permit","51:52","permit"],["250","deny","50:51 51:52 52:53","deny"]]
    else:
        item = [["50","deny","50:51","deny@"],["60","permit","60:61","permit@"],["150","deny","50:51 51:52","deny@"],["250","permit","50:51 51:52 52:53","permit@"],
                ["50","permit","51:52","permit@"],["60","deny","61:62 63:64","deny@"],["150","permit","51:52","permit@"],["250","deny","50:51 51:52 52:53","deny@"]]

    ##1: add-check-del
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_community_list(item[i][0], item[i][1], item[i][2])

        if 'eSR' == os.getenv('SPYTEST_PROJECT'):
            ### check config db ###
            peerkey = "COMMUNITY_LIST|{}|seq|{}".format(item[i][0], 10)
            configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], True, 'check1-1')
        else:
            ### check config db ###
            peerkey = "COMMUNITY_LIST|{}".format(item[i][0])
            configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], True, 'check1-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if output[j].get('community_name_num') == item[i][0] and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == False:
            st.report_fail("check1-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

        if 'eSR' == os.getenv('SPYTEST_PROJECT'):
            bgpcli_obj.del_config_bgp_community_list(item[i][0], "", "")
        else:
            bgpcli_obj.del_config_bgp_community_list(item[i][0], item[i][1], item[i][2])

    st.log("Step1 Finish")

    ##2: add all - check all - del all
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_community_list(item[i][0], item[i][1], item[i][2])
    for i in range(len(item)):
        ### check config db ###
        if 'eSR' == os.getenv('SPYTEST_PROJECT'):
            peerkey = "COMMUNITY_LIST|{}|seq|{}".format(item[i][0], 10 if i < 4 else 20)
            configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], True, 'check2-1')
        else:
            peerkey = "COMMUNITY_LIST|{}".format(item[i][0])
            configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], True, 'check2-1')
        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if output[j].get('community_name_num') == item[i][0] and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == False:
            st.report_fail("check2-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))
    if 'eSR' == os.getenv('SPYTEST_PROJECT'):
        # flush
        for i in ["50", "60", "150", "250"]:
            bgpcli_obj.del_config_bgp_community_list(i, "", "")
    else:
        bgpcli_obj.flush_bgp_community_list()

    st.log("Step2 Finish")

    ##3: add all - del all - check all
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_community_list(item[i][0], item[i][1], item[i][2])

    if 'eSR' == os.getenv('SPYTEST_PROJECT'):
        # flush
        for i in ["50", "60", "150", "250"]:
            bgpcli_obj.del_config_bgp_community_list(i, "", "")
    else:
        bgpcli_obj.flush_bgp_community_list()

    for i in range(len(item)):
        ### check config db ###
        if 'eSR' == os.getenv('SPYTEST_PROJECT'):
            peerkey = "COMMUNITY_LIST|{}|seq|{}".format(item[i][0], 10 if i < 4 else 20)
            configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], False, 'check3-1')
        else:
            peerkey = "COMMUNITY_LIST|{}".format(item[i][0])
            configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], False, 'check3-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if output[j].get('community_name_num') == item[i][0] and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == True:
            st.report_fail("check3-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

    st.report_pass("test_case_passed")

@pytest.mark.bgp_cli
@pytest.mark.bgp_community_list
def test_cli_bgp_community_list_standard():
    st.log("test_cli_bgp_community_list_standard begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    st.log("config cli:  standard cases")
    ###add case data
    if 'eSR' == os.getenv('SPYTEST_PROJECT'):
        item = [["standard list1","deny","50:51","deny"],["standard list2","permit","60:61","permit"],["standard name1","deny","50:51 51:52","deny"],
                ["standard name2","permit","50:51 51:52 52:53","permit"],["standard list1","permit","51:52","permit"],["standard list2","deny","61:62 63:64","deny"],
                ["standard name1","permit","51:52","permit"],["standard name2","deny","50:51 51:52 52:53","deny"],
                ["standard 999","permit","51:52","permit"],["standard 23453","deny","50:51 51:52 52:53","deny"]]
    else:
        item = [["standard list1","deny","50:51","deny@"],["standard list2","permit","60:61","permit@"],["standard name1","deny","50:51 51:52","deny@"],
                ["standard name2","permit","50:51 51:52 52:53","permit@"],["standard list1","permit","51:52","permit@"],["standard list2","deny","61:62 63:64","deny@"],
                ["standard name1","permit","51:52","permit@"],["standard name2","deny","50:51 51:52 52:53","deny@"],
                ["standard 999","permit","51:52","permit@"],["standard 23453","deny","50:51 51:52 52:53","deny@"]]
    ##1: add-check-del
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_community_list(item[i][0], item[i][1], item[i][2])

        ### check config db ###
        if 'eSR' == os.getenv('SPYTEST_PROJECT'):
            ### check config db ###
            peerkey = "COMMUNITY_LIST|standard|{}|seq|{}".format(item[i][0].split()[1], 10)
            configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], True, 'check1-1')
        else:
            ### check config db ###
            peerkey = "COMMUNITY_LIST|{}|{}".format(item[i][0].split()[0], item[i][0].split()[1])
            configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], True, 'check1-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if (output[j].get('community_name_std') == item[i][0].split()[1] or output[j].get('community_name_num') == item[i][0].split()[1]) and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == False:
            st.report_fail("check1-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

        if 'eSR' == os.getenv('SPYTEST_PROJECT'):
            bgpcli_obj.del_config_bgp_community_list(item[i][0], "", "")
        else:
            bgpcli_obj.del_config_bgp_community_list(item[i][0], item[i][1], item[i][2])

    st.log("Step1 Finish")

    ##2: add all - check all - del all
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_community_list(item[i][0], item[i][1], item[i][2])
    for i in range(len(item)):
        ### check config db ###
        if 'eSR' == os.getenv('SPYTEST_PROJECT'):
            peerkey = "COMMUNITY_LIST|standard|{}|seq|{}".format(item[i][0].split()[1], 10 if (i < 4 or item[i][0] == "standard 999" or item[i][0]=="standard 23453") else 20)
            configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], True, 'check2-1')
        else:
            peerkey = "COMMUNITY_LIST|{}|{}".format(item[i][0].split()[0], item[i][0].split()[1])
            configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], True, 'check2-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if (output[j].get('community_name_std') == item[i][0].split()[1] or output[j].get('community_name_num') == item[i][0].split()[1]) and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == False:
            st.report_fail("check2-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

    if 'eSR' == os.getenv('SPYTEST_PROJECT'):
        # flush
        for i in ["standard list1", "standard list2", "standard name1", "standard name2", "standard 999", "standard 23453"]:
            bgpcli_obj.del_config_bgp_community_list(i, "", "")
    else:
        bgpcli_obj.flush_bgp_community_list()

    st.log("Step2 Finish")

    ##3: add all - del all - check all
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_community_list(item[i][0], item[i][1], item[i][2])

    if 'eSR' == os.getenv('SPYTEST_PROJECT'):
        # flush
        for i in ["standard list1", "standard list2", "standard name1", "standard name2", "standard 999", "standard 23453"]:
            bgpcli_obj.del_config_bgp_community_list(i, "", "")
    else:
        bgpcli_obj.flush_bgp_community_list()

    for i in range(len(item)):
        ### check config db ###

        if 'eSR' == os.getenv('SPYTEST_PROJECT'):
            peerkey = "COMMUNITY_LIST|standard|{}|seq|{}".format(item[i][0].split()[1], 10 if (i < 4 or item[i][0] == "standard 999" or item[i][0]=="standard 23453") else 20)
            configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], False, 'check3-1')
        else:
            peerkey = "COMMUNITY_LIST|{}|{}".format(item[i][0].split()[0], item[i][0].split()[1])
            configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], False, 'check3-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if (output[j].get('community_name_std') == item[i][0] or output[j].get('community_name_num') == item[i][0].split()[1]) and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == True:
            st.report_fail("check3-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

    st.report_pass("test_case_passed")

@pytest.mark.bgp_cli
@pytest.mark.bgp_community_list
def test_cli_bgp_community_list_expanded():
    st.log("test_cli_bgp_community_list_expanded begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    st.log("config cli:  expanded cases")
    ###add case data
    if 'eSR' == os.getenv('SPYTEST_PROJECT'):
        item = [["expanded list1","deny","50:51","deny"],["expanded list2","permit","60:61","permit"],["expanded name1","deny","50:51 51:52","deny"],
                ["expanded name2","permit","50:51 51:52 52:53","permit"],["expanded list1","permit","51:52","permit"],["expanded list2","deny","61:62 63:64","deny"],
                ["expanded name1","permit","51:52","permit"],["expanded name2","deny","50:51 51:52 52:53","deny"],
                ["expanded 999","permit","51:52","permit"],["expanded 23453","deny","50:51 51:52 52:53","deny"]]
    else:
        item = [["expanded list1","deny","50:51","deny@"],["expanded list2","permit","60:61","permit@"],["expanded name1","deny","50:51 51:52","deny@"],
                ["expanded name2","permit","50:51 51:52 52:53","permit@"],["expanded list1","permit","51:52","permit@"],["expanded list2","deny","61:62 63:64","deny@"],
                ["expanded name1","permit","51:52","permit@"],["expanded name2","deny","50:51 51:52 52:53","deny@"],
                ["expanded 999","permit","51:52","permit@"],["expanded 23453","deny","50:51 51:52 52:53","deny@"]]

    ##1: add-check-del
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_community_list(item[i][0], item[i][1], item[i][2])

        if 'eSR' == os.getenv('SPYTEST_PROJECT'):
            ### check config db ###
            peerkey = "COMMUNITY_LIST|expanded|{}|seq|{}".format(item[i][0].split()[1], 10)
            configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], True, 'check1-1')
        else:
            ### check config db ###
            peerkey = "COMMUNITY_LIST|{}|{}".format(item[i][0].split()[0], item[i][0].split()[1])
            configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], True, 'check1-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if (output[j].get('community_name_exp') == item[i][0].split()[1] or output[j].get('community_name_num') == item[i][0].split()[1]) and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == False:
            st.report_fail("check1-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

        if 'eSR' == os.getenv('SPYTEST_PROJECT'):
            bgpcli_obj.del_config_bgp_community_list(item[i][0], "", "")
        else:
            bgpcli_obj.del_config_bgp_community_list(item[i][0], item[i][1], item[i][2])

    st.log("Step1 Finish")

    ##2: add all - check all - del all
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_community_list(item[i][0], item[i][1], item[i][2])
    for i in range(len(item)):
        ### check config db ###
        if 'eSR' == os.getenv('SPYTEST_PROJECT'):
            peerkey = "COMMUNITY_LIST|expanded|{}|seq|{}".format(item[i][0].split()[1], 10 if (i < 4 or item[i][0] == "expanded 999" or item[i][0]=="expanded 23453") else 20)
            configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], True, 'check2-1')
        else:
            peerkey = "COMMUNITY_LIST|{}|{}".format(item[i][0].split()[0], item[i][0].split()[1])
            configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], True, 'check2-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if (output[j].get('community_name_exp') == item[i][0].split()[1] or output[j].get('community_name_num') == item[i][0].split()[1]) and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == False:
            st.report_fail("check2-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

    if 'eSR' == os.getenv('SPYTEST_PROJECT'):
        # flush
        for i in ["expanded list1", "expanded list2", "expanded name1", "expanded name2", "expanded 999", "expanded 23453"]:
            bgpcli_obj.del_config_bgp_community_list(i, "", "")
    else:
        bgpcli_obj.flush_bgp_community_list()

    st.log("Step2 Finish")

    ##3: add all - del all - check all
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_community_list(item[i][0], item[i][1], item[i][2])

    if 'eSR' == os.getenv('SPYTEST_PROJECT'):
        # flush
        for i in ["expanded list1", "expanded list2", "expanded name1", "expanded name2", "expanded 999", "expanded 23453"]:
            bgpcli_obj.del_config_bgp_community_list(i, "", "")
    else:
        bgpcli_obj.flush_bgp_community_list()

    for i in range(len(item)):
        ### check config db ###
        if 'eSR' == os.getenv('SPYTEST_PROJECT'):
            peerkey = "COMMUNITY_LIST|expanded|{}|seq|{}".format(item[i][0].split()[1], 10 if (i < 4 or item[i][0] == "standard 999" or item[i][0]=="standard 23453") else 20)
            configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], False, 'check3-1')
        else:
            peerkey = "COMMUNITY_LIST|{}|{}".format(item[i][0].split()[0], item[i][0].split()[1])
            configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], False, 'check3-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if (output[j].get('community_name_exp') == item[i][0] or output[j].get('community_name_num') == item[i][0].split()[1]) and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == True:
            st.report_fail("check3-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

    st.report_pass("test_case_passed")

@pytest.mark.bgp_cli
@pytest.mark.bgp_community_list
def test_cli_bgp_community_list_normal_array():
    st.log("test_cli_bgp_community_list_normal_array begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    st.log("config cli:  normal array cases")
    ###add case data
    item = [["50","deny","50:51","deny@"],["50","permit","60:61","permit@"],["150","deny","50:51 51:52","deny@"],["150","permit","50:51 51:52 52:53","permit@"],
            ["50","deny","51:52","deny@"],["50","permit","61:62 63:64","permit@"],["150","permit","51:52","permit@"],["150","deny","50:51 51:52 52:53","deny@"]]

    ##1: add-check-del
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_community_list(item[i][0], item[i][1], item[i][2])

        ### check config db ###
        peerkey = "COMMUNITY_LIST|{}".format(item[i][0])
        configdb_checkarray(dut, peerkey, item[i][3], item[i][2], True, 'check1-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if output[j].get('community_name_num') == item[i][0] and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == False:
            st.report_fail("check1-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

        bgpcli_obj.del_config_bgp_community_list(item[i][0], item[i][1], item[i][2])

    ##2: add all - check all - del all
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_community_list(item[i][0], item[i][1], item[i][2])
    for i in range(len(item)):
        ### check config db ###
        peerkey = "COMMUNITY_LIST|{}".format(item[i][0])
        configdb_checkarray(dut, peerkey, item[i][3], item[i][2], True, 'check2-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if output[j].get('community_name_num') == item[i][0] and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == False:
            st.report_fail("check2-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

    bgpcli_obj.flush_bgp_community_list()

    ##3: add all - del all - check all
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_community_list(item[i][0], item[i][1], item[i][2])

    bgpcli_obj.flush_bgp_community_list()

    for i in range(len(item)):
        ### check config db ###
        peerkey = "COMMUNITY_LIST|{}".format(item[i][0])
        configdb_checkarray(dut, peerkey, item[i][3], item[i][2], False, 'check3-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if output[j].get('community_name_num') == item[i][0] and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == True:
            st.report_fail("check3-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

    st.report_pass("test_case_passed")

@pytest.mark.bgp_cli
@pytest.mark.bgp_aspath_access_list
def test_cli_bgp_aspath_access_list():
    st.log("test_cli_bgp_aspath_access_list begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    st.log("config cli:  bgp as-path access-list cases")
    ###add case data
    item = [["500","deny","10010","deny@"],["name1","permit","100 300","permit@"],["list1","deny","233 205","deny@"],["xyz","permit","100 120","permit@"],
           ["500","permit","200220","permit@"],["name1","deny","100 500","deny@"],["list1","permit","100 20","permit@"],["xyz","deny","300 200","deny@"]]


    ##1: add-check-del
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_aspath_access_list(item[i][0], item[i][1], item[i][2])

        ### check config db ###
        peerkey = "ASPATH_ACCESS_LIST|{}".format(item[i][0])
        configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], True, 'check1-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if output[j].get('access_list_name') == item[i][0] and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == False:
            st.report_fail("check1-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

        bgpcli_obj.del_config_bgp_aspath_access_list(item[i][0], item[i][1], item[i][2])

    ##2: add all - check all - del all
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_aspath_access_list(item[i][0], item[i][1], item[i][2])
    for i in range(len(item)):
        ### check config db ###
        peerkey = "ASPATH_ACCESS_LIST|{}".format(item[i][0])
        configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], True, 'check2-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if output[j].get('access_list_name') == item[i][0] and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == False:
            st.report_fail("check2-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

    bgpcli_obj.flush_bgp_aspath_access_lists()

    ##3: add all - del all - check all
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_aspath_access_list(item[i][0], item[i][1], item[i][2])

    bgpcli_obj.flush_bgp_aspath_access_lists()

    for i in range(len(item)):
        ### check config db ###
        peerkey = "ASPATH_ACCESS_LIST|{}".format(item[i][0])
        configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], False, 'check3-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if output[j].get('access_list_name') == item[i][0] and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == True:
            st.report_fail("check3-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

    st.report_pass("test_case_passed")

@pytest.mark.bgp_cli
@pytest.mark.bgp_aspath_access_list
def test_cli_bgp_aspath_access_list_array():
    st.log("test_cli_bgp_aspath_access_list_array begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    st.log("config cli:  bgp as-path access-list cases")
    ###add case data
    item = [["500","deny","10010","deny@"],["500","permit","100 300","permit@"],["list1","deny","233 205","deny@"],["list1","permit","100 120","permit@"],
           ["500","permit","200220","permit@"],["500","deny","100 500","deny@"],["list1","permit","100 20","permit@"],["list1","deny","300 200","deny@"]]


    ##1: add-check-del
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_aspath_access_list(item[i][0], item[i][1], item[i][2])

        ### check config db ###
        peerkey = "ASPATH_ACCESS_LIST|{}".format(item[i][0])
        configdb_checkarray(dut, peerkey, item[i][3], item[i][2], True, 'check1-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if output[j].get('access_list_name') == item[i][0] and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == False:
            st.report_fail("check1-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

        bgpcli_obj.del_config_bgp_aspath_access_list(item[i][0], item[i][1], item[i][2])

    ##2: add all - check all - del all
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_aspath_access_list(item[i][0], item[i][1], item[i][2])
    for i in range(len(item)):
        ### check config db ###
        peerkey = "ASPATH_ACCESS_LIST|{}".format(item[i][0])
        configdb_checkarray(dut, peerkey, item[i][3], item[i][2], True, 'check2-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if output[j].get('access_list_name') == item[i][0] and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == False:
            st.report_fail("check2-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

    bgpcli_obj.flush_bgp_aspath_access_lists()

    ##3: add all - del all - check all
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_aspath_access_list(item[i][0], item[i][1], item[i][2])

    bgpcli_obj.flush_bgp_aspath_access_lists()

    for i in range(len(item)):
        ### check config db ###
        peerkey = "ASPATH_ACCESS_LIST|{}".format(item[i][0])
        configdb_checkarray(dut, peerkey, item[i][3], item[i][2], False, 'check3-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if output[j].get('access_list_name') == item[i][0] and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == True:
            st.report_fail("check3-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

    st.report_pass("test_case_passed")

@pytest.mark.bgp_cli
@pytest.mark.bgp_community_list
def test_cli_bgp_community_list_with_command_typo():
    st.log("test_cli_bgp_community_list_with_command_typo begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    st.log("config cli:  typo cases")
    ###add case data with errors
    item = [["50","denyy","50:51","deny@"],["60","ppermit","60:61","permit@"],["list1","deny","50:51 51:52","deny@"],
            ["50","permitt","51:52","permit@"],["60","ddeny","61:62 63:64","deny@"],["list1","permit","51:52","permit@"],
            ["250","permit","50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52","permit@"],
            ["250","deny","50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52","deny@"]]

    ##1: add-check-del
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_community_list(item[i][0], item[i][1], item[i][2])

        ### check config db ###
        peerkey = "COMMUNITY_LIST|{}".format(item[i][0])
        configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], False, 'check1-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if output[j].get('community_name_num') == item[i][0] and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == True:
            st.report_fail("check1-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

        bgpcli_obj.del_config_bgp_community_list(item[i][0], item[i][1], item[i][2])

    ##2: add all - check all - del all
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_community_list(item[i][0], item[i][1], item[i][2])
    for i in range(len(item)):
        ### check config db ###
        peerkey = "COMMUNITY_LIST|{}".format(item[i][0])
        configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], False, 'check2-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if output[j].get('community_name_num') == item[i][0] and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == True:
            st.report_fail("check2-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

    bgpcli_obj.flush_bgp_community_list()

    st.report_pass("test_case_passed")

@pytest.mark.bgp_cli
@pytest.mark.bgp_aspath_access_list
def test_cli_bgp_aspath_access_list_with_command_typo():
    st.log("test_cli_bgp_aspath_access_list_with_command_typo begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    st.log("config cli:  typo cases")
    ###add case data with errors
    item = [["50","denyy","50:51","deny@"],["60","ppermit","60:61","permit@"],["list1","deeny","50:51 51:52","deny@"],
            ["50","permitt","51:52","permit@"],["60","ddeny","61:62 63:64","deny@"],["list1","peermit","51:52","permit@"],
            ["list2","permit","50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52","permit@"],
            ["list2","deny","50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52 52:53 50:51 51:52","deny@"]]

    ##1: add-check-del
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_aspath_access_list(item[i][0], item[i][1], item[i][2])

        ### check config db ###
        peerkey = "ASPATH_ACCESS_LIST|{}".format(item[i][0])
        configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], False, 'check1-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if output[j].get('access_list_name') == item[i][0] and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == True:
            st.report_fail("check1-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

        bgpcli_obj.del_config_bgp_aspath_access_list(item[i][0], item[i][1], item[i][2])

    ##2: add all - check all - del all
    for i in range(len(item)):
        ### config cli ###
        bgpcli_obj.config_bgp_aspath_access_list(item[i][0], item[i][1], item[i][2])
    for i in range(len(item)):
        ### check config db ###
        peerkey = "ASPATH_ACCESS_LIST|{}".format(item[i][0])
        configdb_checkpoint(dut, peerkey, item[i][3], item[i][2], False, 'check2-1')

        ### check frr running-config ##
        output = st.show(dut, "show running-config bgpd", type='vtysh')
        st.log(output)

        result = False
        for j in range(len(output)):
            if output[j].get('access_list_name') == item[i][0] and output[j].get('param_type') == item[i][1] and output[j].get('param_val') == item[i][2]:
                result = True
                break

        if result == True:
            st.report_fail("check2-2: frr check failed: {} {} {}".format(item[i][0], item[i][1], item[i][2]))

    bgpcli_obj.flush_bgp_aspath_access_lists()

    st.report_pass("test_case_passed")

def cli_exist_check(pattern, out, cmd):
    ret = pattern.findall(out)
    st.log(ret)
    if ret is not None and len(ret) > 0:
        st.report_fail("{} output is {}".format(cmd, out))


## clear bgp vrf xxxxx
@pytest.mark.bgp_cli
def test_cli_clear_bgp_vrf_command():
    st.log("test_cli_clear_bgp_vrf_command begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    pattern = re.compile(r"% Unknown command")

    st.log("clear bgp vrf * cli test")
    cmd = "clear bgp vrf Default *"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default * in"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default * in prefix-filter"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default * out"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default * soft"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default * soft in"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default * soft out"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    st.log("clear bgp vrf peer-group cli test")
    cmd = "clear bgp vrf Default peer-group X1"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default peer-group X1 in"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default peer-group X1 in prefix-filter"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default peer-group X1 out"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default peer-group X1 soft"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default peer-group X1 soft in"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default peer-group X1 soft out"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)


    st.log("clear bgp vrf peer cli test")
    cmd = "clear bgp vrf Default 100"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default 1.1.1.1  in"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default 2000::1  in prefix-filter"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default testpeer out"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default external soft"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default 100 soft in"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default 1.1.1.1 soft out"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)


    st.log("clear bgp vrf address family * cli test")
    cmd = "clear bgp vrf Default ipv4 unicast 100"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default ipv4 unicast 1.1.1.1  in"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default ipv6 unicast 2000::1  in prefix-filter"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default ipv6 unicast testpeer out"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default ipv6 unicast external soft"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default ipv6 unicast 100 soft in"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default ipv4 unicast 1.1.1.1 soft out"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    st.log("clear bgp vrf address family peergroup cli test")
    cmd = "clear bgp vrf Default ipv4 unicast peer-group X1"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default ipv4 unicast peer-group X1  in"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default ipv4 unicast peer-group X1  in prefix-filter"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default ipv6 unicast peer-group X1 out"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default ipv6 unicast peer-group X1 soft"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default ipv6 unicast peer-group X1 soft in"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default ipv6 unicast peer-group X1 soft out"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    st.log("clear bgp vrf address family * cli test")
    cmd = "clear bgp vrf Default ipv4 unicast *"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default ipv4 unicast * in"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default ipv4 unicast * in prefix-filter"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default ipv6 unicast * out"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default ipv6 unicast * soft"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default ipv6 unicast * soft in"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    cmd = "clear bgp vrf Default ipv6 unicast * soft out"
    out = st.show(dut, cmd, type='alicli', skip_tmpl=True)
    cli_exist_check(pattern, out, cmd)

    st.report_pass("test_case_passed")


@pytest.mark.bgp_cli
def test_cli_bgp_distance():
    st.log("test_cli_bgp_distance begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    # case 1:
    st.log("test sub case 1...")
    bgpcli_obj.config_distance(IPV4_UNICAST_VIEW, "20 30 40")
    key_configdb = "BGP_PARAMETERS|{}|{}".format(data["as_num"], "ipv4")
    key_frr = "router bgp {}|{}|distance bgp {}".format(data["as_num"], IPV4_UNICAST_VIEW, "20 30 40")
    configdb_checkpoint(dut, key_configdb, "bgp_distance", "20 30 40", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_distance(IPV4_UNICAST_VIEW)
    configdb_checkpoint(dut, key_configdb, "bgp_distance", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    # case 2:
    st.log("test sub case 2...")
    bgpcli_obj.config_distance(IPV6_UNICAST_VIEW, "20 30 40")
    key_configdb = "BGP_PARAMETERS|{}|{}".format(data["as_num"], "ipv6")
    key_frr = "router bgp {}|{}|distance bgp {}".format(data["as_num"], IPV6_UNICAST_VIEW, "20 30 40")
    configdb_checkpoint(dut, key_configdb, "bgp_distance", "20 30 40", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_distance(IPV6_UNICAST_VIEW)
    configdb_checkpoint(dut, key_configdb, "bgp_distance", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    st.report_pass("test_case_passed")


@pytest.mark.bgp_cli
def test_cli_bgp_redistribute_vrf():
    st.log("test_cli_bgp_redistribute_vrf begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    # case 1:
    st.log("test sub case 1...")
    local_vrf = "Vrf1"
    redistribute_vrf = "Vrf2"
    bgpcli_obj.config_redistribute_vrf(IPV4_UNICAST_VIEW, local_vrf, redistribute_vrf)
    key_configdb = "BGP_PARAMETERS|{}|{}|{}".format(data["as_num"], "ipv4", local_vrf)
    key_frr = "router bgp {} vrf {}|{}|redistribute vrf {}".format(data["as_num"], local_vrf, IPV4_UNICAST_VIEW, redistribute_vrf)
    configdb_checkpoint(dut, key_configdb, "redistribute_vrf@", redistribute_vrf, True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_redistribute_vrf(IPV4_UNICAST_VIEW, local_vrf, redistribute_vrf)
    configdb_checkpoint(dut, key_configdb, "redistribute_vrf@", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    st.report_pass("test_case_passed")


@pytest.mark.bgp_cli
def test_cli_bgp_advertise_track_route():
    st.log("test_cli_bgp_advertise_track_route begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    # case 1:
    st.log("test sub case 1...")
    bgpcli_obj.create_neighbor_v6(data.ip6_addr[0], data.remote_as_num)
    bgpcli_obj.config_neighbor(peer = data.ip6_addr[0], address_family='true', activate='true', remove_private_as='true',
        af_pro='ipv6', af_modifier='unicast')

    bgpcli_obj.config_bgp_neighbor_advertise_track_route(IPV6_UNICAST_VIEW, data.ip6_addr[0], "test", "1::1")
    key_configdb = "BGP_NEIGHBOR|{}|{}".format(data.ip6_addr[0], "ipv6")
    key_frr = "router bgp {}|{}|neighbor {} advertise-map {} track {}".format(data["as_num"], IPV6_UNICAST_VIEW, data.ip6_addr[0], "test", "1::1")
    configdb_checkpoint(dut, key_configdb, "advertise_track_route", "{}|{}".format("test", "1::1"), True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_bgp_neighbor_advertise_track_route(IPV6_UNICAST_VIEW, data.ip6_addr[0], "test", "1::1")
    configdb_checkpoint(dut, key_configdb, "advertise_track_route", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    st.report_pass("test_case_passed")


@pytest.mark.bgp_cli
def test_cli_bgp_advertise_delay():
    st.log("test_cli_bgp_advertise_delay begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    # case 1:
    st.log("test sub case 1...")
    bgpcli_obj.config_bgp_advertise_delay(300)
    key_configdb = "BGP_GLOBAL_PARAMETERS|advertise_delay"
    key_frr = "bgp advertise-delay {}".format(300)
    configdb_checkpoint(dut, key_configdb, "delay_timer", "300", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_bgp_advertise_delay()
    configdb_checkpoint(dut, key_configdb, "delay_timer", "0", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    st.report_pass("test_case_passed")


@pytest.mark.bgp_cli
def test_cli_bgp_redistribute():
    st.log("test_cli_bgp_redistribute begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    # case 1:
    st.log("test sub case 1...")
    bgpcli_obj.config_bgp_redistribute_connected(IPV4_UNICAST_VIEW)
    key_configdb = "BGP_REDIST|connected|ipv4"
    key_frr = "router bgp {}|{}|redistribute connected".format(data["as_num"], IPV4_UNICAST_VIEW)
    configdb_checkpoint(dut, key_configdb, "NULL", "NULL", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_bgp_redistribute_connected(IPV4_UNICAST_VIEW)
    configdb_checkpoint(dut, key_configdb, "NULL", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    # case 2:
    st.log("test sub case 2...")
    bgpcli_obj.config_bgp_redistribute_static_route_map(IPV4_UNICAST_VIEW, "test")
    key_configdb = "BGP_REDIST|static|ipv4"
    key_frr = "router bgp {}|{}|redistribute static route-map {}".format(data["as_num"], IPV4_UNICAST_VIEW, "test")
    configdb_checkpoint(dut, key_configdb, "route_map", "test", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_bgp_redistribute_static(IPV4_UNICAST_VIEW)
    configdb_checkpoint(dut, key_configdb, "route_map", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    # case 3:
    st.log("test sub case 3...")
    bgpcli_obj.config_bgp_redistribute_kernel_metric(IPV4_UNICAST_VIEW, 10)
    key_configdb = "BGP_REDIST|kernel|ipv4"
    key_frr = "router bgp {}|{}|redistribute kernel metric {}".format(data["as_num"], IPV4_UNICAST_VIEW, 10)
    configdb_checkpoint(dut, key_configdb, "metric", "10", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_bgp_redistribute_kernel(IPV4_UNICAST_VIEW)
    configdb_checkpoint(dut, key_configdb, "metric", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    # case 4:
    st.log("test sub case 4...")
    bgpcli_obj.config_bgp_redistribute_static_route_map_with_metric(IPV6_UNICAST_VIEW, "test", 10)
    key_configdb = "BGP_REDIST|static|ipv6"
    key_frr = "router bgp {}|{}|redistribute static metric {} route-map {}".format(data["as_num"], IPV6_UNICAST_VIEW, 10, "test")
    configdb_checkpoint(dut, key_configdb, "route_map", "test", True, "check1")
    configdb_checkpoint(dut, key_configdb, "metric", "10", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_bgp_redistribute_static(IPV6_UNICAST_VIEW)
    configdb_checkpoint(dut, key_configdb, "route_map", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    st.report_pass("test_case_passed")


@pytest.mark.bgp_cli
def test_cli_network_non_connected():
    st.log("test_cli_network_non_connected begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    # case 1:
    st.log("test sub case 1...")
    bgpcli_obj.config_network_non_connected(IPV4_UNICAST_VIEW, "1.1.1.0/24")
    key_configdb = "BGP_NETWORK|{}|ipv4".format("1.1.1.0/24")
    key_frr = "router bgp {}|{}|network {} nonconnected".format(data["as_num"], IPV4_UNICAST_VIEW, "1.1.1.0/24")
    configdb_checkpoint(dut, key_configdb, "type", "non-connected", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_network_non_connected(IPV4_UNICAST_VIEW, "1.1.1.0/24")
    configdb_checkpoint(dut, key_configdb, "type", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    # case 2:
    st.log("test sub case 2...")
    bgpcli_obj.config_network_non_connected(IPV6_UNICAST_VIEW, "2000::/64")
    key_configdb = "BGP_NETWORK|{}|ipv6".format("2000::/64")
    key_frr = "router bgp {}|{}|network {} nonconnected".format(data["as_num"], IPV6_UNICAST_VIEW, "2000::/64")
    configdb_checkpoint(dut, key_configdb, "type", "non-connected", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_network_non_connected(IPV6_UNICAST_VIEW, "2000::/64")
    configdb_checkpoint(dut, key_configdb, "type", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    # case 3:
    st.log("test sub case 3...")
    bgpcli_obj.config_network_non_connected(IPV6_UNICAST_VIEW, "2000::/64", "test")
    key_configdb = "BGP_NETWORK|{}|ipv6".format("2000::/64")
    key_frr = "router bgp {}|{}|network {} route-map {} nonconnected".format(data["as_num"], IPV6_UNICAST_VIEW, "2000::/64", "test")
    configdb_checkpoint(dut, key_configdb, "type", "non-connected", True, "check1")
    configdb_checkpoint(dut, key_configdb, "route_map", "test", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_network_non_connected(IPV6_UNICAST_VIEW, "2000::/64")
    configdb_checkpoint(dut, key_configdb, "type", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    st.report_pass("test_case_passed")


@pytest.mark.bgp_cli
def test_cli_route_map_vpn():
    st.log("test_cli_route_map_vpn begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    # case 1:
    st.log("test sub case 1...")
    bgpcli_obj.config_route_map_vpn_import(IPV4_UNICAST_VIEW, "aa")
    key_configdb = "BGP_PARAMETERS|{}|ipv4".format(data["as_num"])
    key_frr = "router bgp {}|{}|route-map vpn import {}".format(data["as_num"], IPV4_UNICAST_VIEW, "aa")
    configdb_checkpoint(dut, key_configdb, "route_map_vpn_import", "aa", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_route_map_vpn_import(IPV4_UNICAST_VIEW, "aa")
    configdb_checkpoint(dut, key_configdb, "route_map_vpn_import", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    # case 2:
    st.log("test sub case 2...")
    bgpcli_obj.config_route_map_vpn_export(IPV4_UNICAST_VIEW, "aa")
    key_configdb = "BGP_PARAMETERS|{}|ipv4".format(data["as_num"])
    key_frr = "router bgp {}|{}|route-map vpn export {}".format(data["as_num"], IPV4_UNICAST_VIEW, "aa")
    configdb_checkpoint(dut, key_configdb, "route_map_vpn_export", "aa", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_route_map_vpn_export(IPV4_UNICAST_VIEW, "aa")
    configdb_checkpoint(dut, key_configdb, "route_map_vpn_export", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    # case 3:
    st.log("test sub case 3...")
    bgpcli_obj.config_route_map_vpn_import(IPV6_UNICAST_VIEW, "aa")
    key_configdb = "BGP_PARAMETERS|{}|ipv6".format(data["as_num"])
    key_frr = "router bgp {}|{}|route-map vpn import {}".format(data["as_num"], IPV6_UNICAST_VIEW, "aa")
    configdb_checkpoint(dut, key_configdb, "route_map_vpn_import", "aa", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_route_map_vpn_import(IPV6_UNICAST_VIEW, "aa")
    configdb_checkpoint(dut, key_configdb, "route_map_vpn_import", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    # case 4:
    st.log("test sub case 4...")
    bgpcli_obj.config_route_map_vpn_export(IPV6_UNICAST_VIEW, "aa")
    key_configdb = "BGP_PARAMETERS|{}|ipv6".format(data["as_num"])
    key_frr = "router bgp {}|{}|route-map vpn export {}".format(data["as_num"], IPV6_UNICAST_VIEW, "aa")
    configdb_checkpoint(dut, key_configdb, "route_map_vpn_export", "aa", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_route_map_vpn_export(IPV6_UNICAST_VIEW, "aa")
    configdb_checkpoint(dut, key_configdb, "route_map_vpn_export", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    st.report_pass("test_case_passed")


@pytest.mark.bgp_cli
def test_cli_bgp_route_map_delay():
    st.log("test_cli_bgp_route_map_delay begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    # case 1:
    st.log("test sub case 1...")
    bgpcli_obj.config_bgp_route_map_delay_timer("300")
    key_configdb = "BGP_GLOBAL_PARAMETERS|route_map_delay"
    key_frr = "bgp route-map delay-timer {}".format("300")
    configdb_checkpoint(dut, key_configdb, "delay_time", "300", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_bgp_route_map_delay_timer()
    configdb_checkpoint(dut, key_configdb, "delay_time", "0", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    st.report_pass("test_case_passed")


@pytest.mark.bgp_cli
def test_cli_bgp_bestpath_aspath():
    st.log("test_cli_bgp_bestpath_aspath begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    # case 1:
    st.log("test sub case 1...")
    bgpcli_obj.config_bgp_bestpath_aspath("confed")
    key_configdb = "BGP_PARAMETERS|{}|global".format(data["as_num"])
    key_frr = "router bgp {}|bgp bestpath as-path confed".format(data["as_num"])
    configdb_checkpoint(dut, key_configdb, "bgp_bestpath_aspath_confed", "true")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_bgp_bestpath_aspath("confed")
    configdb_checkpoint(dut, key_configdb, "bgp_bestpath_aspath_confed", "false", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    # case 2:
    st.log("test sub case 2...")
    bgpcli_obj.config_bgp_bestpath_aspath("ignore")
    key_configdb = "BGP_PARAMETERS|{}|global".format(data["as_num"])
    key_frr = "router bgp {}|bgp bestpath as-path ignore".format(data["as_num"])
    configdb_checkpoint(dut, key_configdb, "bgp_bestpath_aspath_ignore", "true")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_bgp_bestpath_aspath("ignore")
    configdb_checkpoint(dut, key_configdb, "bgp_bestpath_aspath_ignore", "false", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    # case 3:
    st.log("test sub case 3...")
    bgpcli_obj.config_bgp_bestpath_aspath("multipath-relax")
    key_configdb = "BGP_PARAMETERS|{}|global".format(data["as_num"])
    key_frr = "router bgp {}|bgp bestpath as-path multipath-relax".format(data["as_num"])
    configdb_checkpoint(dut, key_configdb, "bgp_bestpath_aspath_multipath_relax", "true")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_bgp_bestpath_aspath("multipath-relax")
    configdb_checkpoint(dut, key_configdb, "bgp_bestpath_aspath_multipath_relax", "false", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    st.report_pass("test_case_passed")


@pytest.mark.bgp_cli
def test_cli_bgp_extcommunity_list():
    st.log("test_cli_bgp_extcommunity_list begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    # case 1:
    st.log("test sub case 1...")
    bgpcli_obj.config_bgp_extcommunity_list_standard("aa", "permit", "rt 11:11")
    key_configdb = "EXTCOMMUNITY_LIST|standard|{}|seq|20".format("aa")
    key_frr = "bgp extcommunity-list standard {} seq 20 {} {}".format("aa", "permit", "rt 11:11")
    configdb_checkpoint(dut, key_configdb, "permit", "rt 11:11", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_bgp_extcommunity_list_standard("aa", "permit", "11:11")
    configdb_checkpoint(dut, key_configdb, "permit", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    # case 2:
    st.log("test sub case 2...")
    bgpcli_obj.config_bgp_extcommunity_list_expanded("aa", "permit", "rt 11:11")
    key_configdb = "EXTCOMMUNITY_LIST|expanded|{}|seq|20".format("aa")
    key_frr = "bgp extcommunity-list expanded {} seq 20 {} {}".format("aa", "permit", "rt 11:11")
    configdb_checkpoint(dut, key_configdb, "permit", "rt 11:11", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_bgp_extcommunity_list_expanded("aa", "permit", "rt 11:11")
    configdb_checkpoint(dut, key_configdb, "permit", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    st.report_pass("test_case_passed")


@pytest.mark.bgp_cli
def test_cli_bgp_network_import_check():
    st.log("test_cli_bgp_network_import_check begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    # case 1:
    st.log("test sub case 1...")
    bgpcli_obj.no_config_bgp_network_import_check()
    key_configdb = "BGP_PARAMETERS|{}|global".format(data["as_num"])
    key_frr = "router bgp {}|bgp network import-check".format(data["as_num"])
    configdb_checkpoint(dut, key_configdb, "bgp_network_import_check", "false", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check2")

    bgpcli_obj.config_bgp_network_import_check()
    configdb_checkpoint(dut, key_configdb, "bgp_network_import_check", "true", True, "check3")
    # frr_config_checkpoint(bgpcli_obj, key_frr, True, "check4")

    st.report_pass("test_case_passed")


@pytest.mark.bgp_cli
def test_cli_bgp_reflector_client():
    st.log("test_cli_bgp_reflector_client begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    # case 1:
    st.log("test sub case 1...")

    # create ibgp neighbor
    bgpcli_obj.create_neighbor_v4(data.ip4_addr[1], data["as_num"])
    bgpcli_obj.config_neighbor_activate(IPV4_UNICAST_VIEW, data.ip4_addr[1])
    bgpcli_obj.config_bgp_neighbor_route_reflector_client(IPV4_UNICAST_VIEW, data.ip4_addr[1])
    key_configdb = "BGP_NEIGHBOR|{}|ipv4".format(data.ip4_addr[1])
    key_frr = "router bgp {}|{}|neighbor {} route-reflector-client".format(data["as_num"], IPV4_UNICAST_VIEW, data.ip4_addr[1])
    configdb_checkpoint(dut, key_configdb, "rr_client", "true", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_bgp_neighbor_route_reflector_client(IPV4_UNICAST_VIEW, data.ip4_addr[1])
    configdb_checkpoint(dut, key_configdb, "rr_client", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    # conflict check 
    bgpcli_obj.create_neighbor_v4(data.ip4_addr[-3], data.remote_as_num)
    bgpcli_obj.config_neighbor_activate(IPV4_UNICAST_VIEW, data.ip4_addr[-3])
    bgpcli_obj.config_bgp_neighbor_route_reflector_client(IPV4_UNICAST_VIEW, data.ip4_addr[-3])
    key_configdb = "BGP_NEIGHBOR|{}|ipv4".format(data.ip4_addr[-3])
    key_frr = "router bgp {}|{}|neighbor {} route-reflector-client".format(data.remote_as_num, IPV4_UNICAST_VIEW, data.ip4_addr[-3])
    configdb_checkpoint(dut, key_configdb, "rr_client", "null", True, "check5")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check6")

    st.report_pass("test_case_passed")


@pytest.mark.bgp_cli
def test_cli_bgp_maximum_paths():
    st.log("test_cli_bgp_maximum_paths begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    # case 1:
    st.log("test sub case 1...")

    bgpcli_obj.config_bgp_maximum_paths(IPV4_UNICAST_VIEW, 10)
    key_configdb = "BGP_PARAMETERS|{}|ipv4".format(data["as_num"])
    key_frr = "router bgp {}|{}|maximum-paths ibgp {}".format(data["as_num"], IPV4_UNICAST_VIEW, 10)
    configdb_checkpoint(dut, key_configdb, "bgp_maximum_paths_ibgp", "10", True, "check1")
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_bgp_maximum_paths(IPV4_UNICAST_VIEW)
    configdb_checkpoint(dut, key_configdb, "bgp_maximum_paths_ibgp", "null", True, "check3")
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    st.report_pass("test_case_passed")


@pytest.mark.bgp_cli
def test_cli_ip_nht_bgp_route_map():
    st.log("test_cli_ip_nht_bgp_route_map begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    # case 1:
    st.log("test sub case 1...")
    bgpcli_obj.config_ip_nht_bgp_route_map(IPV4_UNICAST_VIEW, "test")
    key_configdb = "ZEBRA_PARAMETERS|ip"
    key_frr = "ip nht bgp route-map {}".format("test")
    configdb_checkpoint(dut, key_configdb, "nht@", "bgp|{}".format("test"), True, "check1")
    zebra_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_ip_nht_bgp_route_map(IPV4_UNICAST_VIEW, "test")
    configdb_checkpoint(dut, key_configdb, "nht@", "null", True, "check3")
    zebra_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    # case 2:
    st.log("test sub case 2...")
    bgpcli_obj.config_ip_nht_bgp_route_map(IPV6_UNICAST_VIEW, "test")
    key_configdb = "ZEBRA_PARAMETERS|ipv6"
    key_frr = "ipv6 nht bgp route-map {}".format("test")
    configdb_checkpoint(dut, key_configdb, "nht@", "bgp|{}".format("test"), True, "check1")
    zebra_config_checkpoint(bgpcli_obj, key_frr, True, "check2")

    bgpcli_obj.no_config_ip_nht_bgp_route_map(IPV6_UNICAST_VIEW, "test")
    configdb_checkpoint(dut, key_configdb, "nht@", "null", True, "check3")
    zebra_config_checkpoint(bgpcli_obj, key_frr, False, "check4")

    st.report_pass("test_case_passed")


@pytest.mark.bgp_cli
def test_cli_no_update_delay():
    st.log("test_cli_no_update_delay begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    # case 1:
    st.log("test sub case 1...")
    bgpcli_obj.config_bgp_update_delay(config='add')
    bgpcli_obj.config_bgp_update_delay(config='del')

    
    key_configdb = "BGP_PARAMETERS|100|global"
    configdb_checkpoint(dut, key_configdb, "bgp_router_id", data.router_id, True, "check1")

    st.report_pass("test_case_passed")

@pytest.mark.bgp_cli
def test_cli_show_bgp_community_list():
    st.log("test_cli_show_bgp_community_list begin")
    dut = data['dut']

    st.log("config bgp community-list")
    cmd = "cli -c 'config t' -c 'bgp community-list standard aaa seq 10 permit 1:100 2:200 3:300'"
    st.config(dut, cmd)
    cmd = "cli -c 'config t' -c 'bgp community-list standard bbb seq 10 permit 4:400 5:500 6:600'"
    st.config(dut, cmd)
    
    st.log("show bgp community-list")
    show_cmd = "cli -c 'show bgp community-list'"
    ret = st.show(dut, show_cmd,  skip_tmpl=True)
    if ('permit 1:100 2:200 3:300' not in ret) or ('permit 4:400 5:500 6:600' not in ret):
        st.report_fail("show bgp community-list check failed.")
    
    st.log("show bgp community-list aaa/bbb")
    show_cmd = "cli -c 'show bgp community-list aaa detail'"
    ret = st.show(dut, show_cmd,  skip_tmpl=True)
    if ('permit 1:100 2:200 3:300' not in ret):
        st.report_fail("show bgp community-list aaa check failed.")
    
    show_cmd = "cli -c 'show bgp community-list bbb detail'"
    ret = st.show(dut, show_cmd,  skip_tmpl=True)
    if ('permit 4:400 5:500 6:600' not in ret):
        st.report_fail("show bgp community-list bbb check failed.")
    st.report_pass("test_case_passed")

@pytest.mark.bgp_cli
def test_cli_del_vrf_bgp():
    st.log("test_cli_del_vrf_bgp begin")
    bgpcli_obj = data['bgpcli_obj']
    dut = data['dut']

    st.log("config vrf bgp instance")
    cmd = "cli -c 'config t' -c 'router bgp 100 vrf Vrf1'"
    st.config(dut, cmd)

    st.log("show frr running")

    key_frr = "router bgp 100 vrf Vrf1"
    frr_config_checkpoint(bgpcli_obj, key_frr, True, "check1")

    cmd = "cli -c 'config t' -c 'no router bgp 100 vrf Vrf1'"
    st.config(dut, cmd)
    frr_config_checkpoint(bgpcli_obj, key_frr, False, "check2")

    st.report_pass("test_case_passed")

