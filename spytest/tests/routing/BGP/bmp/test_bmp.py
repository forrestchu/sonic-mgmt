# -*- coding:utf-8 -*-
import os
import pytest
from collections import OrderedDict

from spytest import st, tgapi, SpyTestDict
from spytest.utils import filter_and_select
from utilities.utils import retry_api
from apis.common import redis

import apis.common.asic as asicapi
import apis.switching.vlan as vapi
import apis.routing.ip as ipfeature
import apis.switching.mac as macapi
import apis.system.port as papi
import apis.routing.bgp as bgp_api
import apis.routing.arp as arp_obj
import apis.routing.bfd as bfdapi
from bmp_cli import BMP_INS
import re

data = SpyTestDict()

@pytest.fixture(scope="module", autouse=True)
def bmp_module_hooks(request):
    #add things at the start of this module
    global vars
    vars = st.ensure_min_topology("D1T1:2")
    data.start_ip_addr = "10.2.100.1/24"
    data.vlans = []
    data.dut1 = vars.D1
    data.dut2 = vars.D2

    data.dut1_start_ip_addr = "10.2.2.1"
    data.v6_start_ip_addr = "2100:0:2::1"
    data.neigh_v6_ip_addr = "2100:0:2::2"
    data.neigh_ip_addr = "10.2.2.2"
    data.dut1_ports = [vars.D1D2P1,vars.D1D2P2]
    data.dut2_ports = [vars.D2D1P1,vars.D2D1P2]
    data.as_num = 178
    data.remote_as_num = 200
    data.new_as_num = 300
    data.vrf = "bfd-test-12345678-abcdefg"

    BMP_INS.bmp_server_data_read('openbmp.parsed.base_attribute')
    BMP_INS.bmp_server_data_read('openbmp.bmp_raw')
    BMP_INS.bmp_server_data_read('openbmp.parsed.collector')
    BMP_INS.bmp_server_data_read('openbmp.parsed.peer')
    BMP_INS.bmp_server_data_read('openbmp.parsed.router')
    BMP_INS.bmp_server_data_read('openbmp.parsed.unicast_prefix')

    l3_base_config()

    yield

    l3_base_unconfig()
    BMP_INS.bmp_server_data_read('openbmp.parsed.base_attribute')
    BMP_INS.bmp_server_data_read('openbmp.bmp_raw')
    BMP_INS.bmp_server_data_read('openbmp.parsed.collector')
    BMP_INS.bmp_server_data_read('openbmp.parsed.peer')
    BMP_INS.bmp_server_data_read('openbmp.parsed.router')
    BMP_INS.bmp_server_data_read('openbmp.parsed.unicast_prefix')


def l3_base_config():
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]

    st.banner("Started doing the needed config.")

    # dut1 config
    ip_addr = data.dut1_start_ip_addr
    v6_ip_addr = data.v6_start_ip_addr

    command = "interface {}\n ip address {}/24\n exit\n".format(data.dut1_ports[0], ip_addr)
    st.config(dut1, command, skip_error_check=True, type='alicli', max_time=500)

    command = "interface {}\n ipv6 address {}/64\n exit\n".format(data.dut1_ports[0], v6_ip_addr)
    st.config(dut1, command, skip_error_check=True, type='alicli')
 
    command = "show ndp"
    st.show(dut1, command)

    # dut2 config

    ip_addr2 = data.neigh_ip_addr
    v6_ip_addr2 = data.neigh_v6_ip_addr
    command = "interface {}\n ip address {}/24\n exit\n".format(data.dut2_ports[0], ip_addr2)
    st.config(dut2, command, skip_error_check=True, type='alicli', max_time=500)

    command = "interface {}\n ipv6 address {}/64\n exit\n".format(data.dut2_ports[0], v6_ip_addr2)
    st.config(dut2, command, skip_error_check=True, type='alicli')
 
    command = "show ndp"
    st.show(dut2, command)

    st.banner("init ipv4 part")
    #bgp_api.create_bgp_router(dut, data.as_num, '')
    bgp_api.config_bgp(dut = dut1, router_id = '1.1.1.1', local_as=data.as_num, 
        neighbor=ip_addr2, remote_as=data.remote_as_num,  
        config_type_list =["neighbor", "activate"], config='yes', cli_type = "alicli")

    bgp_api.config_bgp(dut = dut2, router_id = '2.2.2.2', local_as=data.remote_as_num, 
        neighbor=ip_addr, remote_as=data.as_num,  
        config_type_list =["neighbor", "activate"], config='yes', cli_type = "alicli")

    st.log("BGP neighborship established.")

    st.banner("init ipv6 part")
  
def l3_base_unconfig():
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    st.log("remove l3 base config.")
    # bgp_api.config_bgp(dut = dut1, local_as=data.as_num, config = 'no', removeBGP='yes', config_type_list =["removeBGP"],cli_type = "alicli")
    # bgp_api.config_bgp(dut = dut2, local_as=data.remote_as_num, config = 'no',  removeBGP='yes', config_type_list =["removeBGP"],cli_type = "alicli")


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
        if output[i].get('donor_intf') == checkfield:
            exist = True
            if i + 1 < len(output):
                if output[i + 1].get('donor_intf') == checkval:
                    redis_cfg_checkpoint = True

    if checkval == 'null':
        redis_cfg_exist_checkpoint = False if exist else True
        if redis_cfg_exist_checkpoint != expect:
            st.report_fail("{} confg DB has {} config".format(checkpoint, checkfield))
    else:
        if redis_cfg_checkpoint != expect:
            st.report_fail("{} confg DB has no right {} config".format(checkpoint, checkfield))

def frr_config_checkpoint(obj, key, subkey, expect = True, checkpoint = ''):
    output = obj.show_frr_running_config_json()
    if key not in output:
        st.report_fail("{} frr config has no {} config".format(checkpoint, key))

    if expect == "null":
        if subkey in output[key]:
            st.report_fail("{} frr config has subkey {} config, expect null".format(checkpoint, subkey))
        else:
            return

    if subkey not in output[key]:
        st.report_fail("{} frr config has no subkey {} config".format(checkpoint, subkey))

    if output[key][subkey] != "true":
        st.report_fail("{} frr config subkey {} not equal to true".format(checkpoint, subkey))

def frr_config_checkpoint2(obj, key, subkey, subkey2, expect = True, checkpoint = ''):
    output = obj.show_frr_running_config_json()
    if key not in output:
        st.report_fail("{} frr config has no {} config".format(checkpoint, key))

    if expect == "null":
        if subkey in output[key]:
            st.report_fail("{} frr config has subkey {} config, expect null".format(checkpoint, subkey))
        else:
            return

    if subkey not in output[key]:
        st.report_fail("{} frr config has no subkey {} config".format(checkpoint, subkey))

    if subkey2 not in output[key][subkey]:
        st.report_fail("{} frr config has no subkey2 {} config".format(checkpoint, subkey2))

    if output[key][subkey][subkey2] != "true":
        st.report_fail("{} frr config subkey {} not equal to true".format(checkpoint, subkey))


def pid_exist_check(pattern, out, cmd):
    ret = pattern.findall(out)
    st.log("re match result:")
    st.log(ret)
    if ret is None or len(ret) == 0:
        st.report_fail("bgpd is not running, {} output is {}".format(cmd, out))
    st.log("bgpd is running.")

def check_show_bmp(pattern, out, cmd):
    ret = pattern.findall(out)
    st.log("re match result:")
    st.log(ret)
    if ret is None or len(ret) == 0:
        st.report_fail("{} show info is error : {}".format(cmd, out))
    st.log("show info is right.")

@pytest.mark.bmp
def test_bmp_global_case():
    st.log("test_bmp_global_case begin")
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    topic1 = 'openbmp.parsed.router'
    topic2 = 'openbmp.parsed.peer'
    topic3 = 'openbmp.parsed.unicast_prefix'

    dut2_mgmtip = st.get_mgmt_ip(dut2)

    st.log("config global bmp")
    st.config(dut2, "cli -c 'configure terminal' -c 'bmp' -c 'bmp target bmp01' -c 'bmp connect 21.135.167.180 port 5555 min-retry 100 max-retry 200'")

    st.config(dut2, "cli -c 'configure terminal' -c 'bmp' -c 'bmp target bmp01' -c 'bmp monitor ipv4 unicast adj-in pre-policy'")

    st.config(dut2, "cli -c 'configure terminal' -c 'bmp' -c 'bmp target bmp01' -c 'bmp monitor ipv4 unicast adj-in post-policy '")

    st.wait(30)

    st.log("check bmp establish session")

    ret1 = BMP_INS.match_bmp_msg(topic2, 'first', 'router_ip', dut2_mgmtip)
    ret2 = BMP_INS.match_bmp_msg(topic2, 'up', 'router_ip', dut2_mgmtip)

    if not (ret1 or ret2):
        st.report_fail("{} action {} key {} value {} is not expected ".format(topic2, 'up', 'router_ip', dut2_mgmtip))
    
    ret = BMP_INS.match_bmp_msg(topic1, 'init', 'ip_addr', dut2_mgmtip)
    if not ret:
        st.report_fail("{} action {} key {} value {} is not expected ".format(topic1, 'init', 'ip_addr', dut2_mgmtip))
    
    st.log("check bmp monitor")
    BMP_INS.bmp_server_data_read(topic3)
    st.config(dut1, "cli -c 'configure terminal' -c 'ip route  100.1.1.10/32 blackhole'")
    st.config(dut1, "cli -c 'configure terminal' -c 'router bgp 178' -c 'address-family ipv4 unicast' -c 'network 100.1.1.10/32 non-connected'")
    
    st.wait(30)
    BMP_INS.read_bmp_data(topic3)
    ret = BMP_INS.match_bmp_msg(topic3, 'add', 'rib.prefix', '100.1.1.10')
    if not ret:
        st.report_fail("{} action {} key {} value {} is not expected - check1".format(topic3, 'add', 'rib.prefix', '100.1.1.10'))

    pattern1 = re.compile(r'Targets "bmp01" Statistics:') 
    pattern2 = re.compile(r'BGP Peers monitored by BMP') 
    st.log("===============show bmp================")
    out = st.show(dut2, 'show bmp', skip_tmpl=True, type='vtysh')
    check_show_bmp(pattern1, out, 'show bmp')
    check_show_bmp(pattern2, out, 'show bmp')

    st.log("===============show bmp targets================")
    out = st.show(dut2, 'show bmp bmp01', skip_tmpl=True, type='vtysh' )
    check_show_bmp(pattern1, out, 'show bmp bmp01')
    check_show_bmp(pattern2, out, 'show bmp bmp01')


    # del bmp
    st.config(dut2, "cli -c 'configure terminal' -c 'bmp' -c 'no bmp target bmp01'")
    st.wait(5)
    st.config(dut2, "cli -c 'configure terminal' -c 'no bmp'")

    st.report_pass("test_case_passed")


@pytest.mark.bmp
def test_bmp_global_del_bgp_case():
    st.log("test_bmp_global_del_bgp_case begin")
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    topic1 = 'openbmp.parsed.router'
    topic2 = 'openbmp.parsed.peer'
    topic3 = 'openbmp.parsed.unicast_prefix'

    st.log("config global bmp")
    st.config(dut2, "cli -c 'configure terminal' -c 'bmp' -c 'bmp target bmp02' -c 'bmp connect 21.135.167.180 port 5555 min-retry 100 max-retry 200'")

    st.config(dut2, "cli -c 'configure terminal' -c 'bmp' -c 'bmp target bmp02' -c 'bmp monitor ipv4 unicast adj-in pre-policy'")

    st.config(dut2, "cli -c 'configure terminal' -c 'bmp' -c 'bmp target bmp02' -c 'bmp monitor ipv4 unicast adj-in post-policy '")

    st.wait(30)

    st.config(dut2, "cli -c 'configure terminal' -c 'vrf VRF01'")
    st.config(dut2, "cli -c 'configure terminal' -c 'router bgp 200 vrf VRF01' -c 'bgp router-id 10.10.10.10'")

    st.config(dut1, "cli -c 'configure terminal' -c 'ip route  100.1.1.11/32 blackhole'")
    st.config(dut1, "cli -c 'configure terminal' -c 'router bgp 178' -c 'address-family ipv4 unicast' -c 'network 100.1.1.11/32 non-connected'")
    
    st.wait(5)

    BMP_INS.read_bmp_data(topic3)
    ret = BMP_INS.match_bmp_msg(topic3, 'add', 'rib.prefix', '100.1.1.10')
    if not ret:
        st.report_fail("{} action {} key {} value {} is not expected - check1".format(topic3, 'add', 'rib.prefix', '100.1.1.11'))
    
    # del bgp ins
    st.config(dut2, "cli -c 'configure terminal' -c 'no router bgp 200 view VRF01'")

    st.wait(5)

    pattern = re.compile(r'\/usr\/lib\/frr\/bgpd') 
    cmd = "ps -ef | grep bgpd"
    out = st.show(dut2, cmd, skip_tmpl=True)
    pid_exist_check(pattern, out, cmd)

    # del bmp
    st.config(dut2, "cli -c 'configure terminal' -c 'bmp' -c 'no bmp target bmp02'")
    st.wait(5)
    st.config(dut2, "cli -c 'configure terminal' -c 'no bmp'")

    st.report_pass("test_case_passed")

@pytest.mark.bmp
def test_bmp_bgp_case():
    st.log("test_bmp_bgp_case begin")
    data.my_dut_list = st.get_dut_names()
    dut1 = data.my_dut_list[0]
    dut2 = data.my_dut_list[1]
    topic1 = 'openbmp.parsed.router'
    topic2 = 'openbmp.parsed.peer'
    topic3 = 'openbmp.parsed.unicast_prefix'

    dut2_mgmtip = st.get_mgmt_ip(dut2)

    st.log("config bgp bmp")
    st.config(dut2, "cli -c 'configure terminal' -c 'router bgp 200' -c 'bmp target bmp03' -c 'bmp connect 21.135.167.180 port 5555 min-retry 100 max-retry 200'")

    st.config(dut2, "cli -c 'configure terminal' -c 'router bgp 200' -c 'bmp target bmp03' -c 'bmp monitor ipv4 unicast adj-in pre-policy'")

    st.config(dut2, "cli -c 'configure terminal' -c 'router bgp 200' -c 'bmp target bmp03' -c 'bmp monitor ipv4 unicast adj-in post-policy '")

    st.wait(30)

    st.log("check bmp establish session")
    ret1 = BMP_INS.match_bmp_msg(topic2, 'first', 'router_ip', dut2_mgmtip)
    ret2 = BMP_INS.match_bmp_msg(topic2, 'up', 'router_ip', dut2_mgmtip)

    if not (ret1 or ret2):
        st.report_fail("{} action {} key {} value {} is not expected ".format(topic2, 'up', 'router_ip', dut2_mgmtip))
    
    ret = BMP_INS.match_bmp_msg(topic1, 'init', 'ip_addr', dut2_mgmtip)
    if not ret:
        st.report_fail("{} action {} key {} value {} is not expected ".format(topic1, 'init', 'ip_addr', dut2_mgmtip))
    
    st.log("check bmp monitor")
    BMP_INS.bmp_server_data_read(topic3)
    st.config(dut1, "cli -c 'configure terminal' -c 'ip route   200.1.1.10/32 blackhole'")
    st.config(dut1, "cli -c 'configure terminal' -c 'router bgp 178' -c 'address-family ipv4 unicast' -c 'network 200.1.1.10/32 non-connected'")
    
    st.wait(30)
    BMP_INS.read_bmp_data(topic3)
    ret = BMP_INS.match_bmp_msg(topic3, 'add', 'rib.prefix', '200.1.1.10')
    if not ret:
        st.report_fail("{} action {} key {} value {} is not expected - check1".format(topic3, 'add', 'rib.prefix', '200.1.1.10'))

    st.log("===============show bmp================")
    out = st.show(dut2, 'show bmp', skip_tmpl=True, type='vtysh')

    pattern1 = re.compile(r'Just support global bmp') 
    st.log("===============show bmp targets================")
    out = st.show(dut2, 'show bmp bmp03', skip_tmpl=True, type='vtysh' )
    check_show_bmp(pattern1, out, 'show bmp bmp03')

    # del bmp
    st.config(dut2, "cli -c 'configure terminal' -c 'router bgp 200' -c 'no bmp target bmp03'")

    st.report_pass("test_case_passed")
