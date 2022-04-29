# -*- coding:utf-8 -*-
import pytest
import json

from spytest import st, tgapi, SpyTestDict
import apis.routing.route_map as RouteMap
from apis.common import redis
from bmp_cli import BMP_INS
from BGP.cli.bgp_cli import BGP_CLI
import re


# param
param_data = SpyTestDict()

# test data 
data = SpyTestDict()
data.as_num = 4200015154
data.remote_as_num = 4200015155
data.vrf = 'Vrf1'
data.ip4_addr = ["192.50.10.178", "192.50.10.179","192.168.1.1", "192.168.1.2", "192.168.2.1", "192.168.2.2", "192.168.3.1", "192.168.3.3",
                 "192.168.4.1", "192.168.4.2", "192.168.5.1", "192.168.5.2", "192.168.6.1", "192.168.6.2"]
data.ip4_addr_rt = ["192.168.1.0", "192.168.2.0", "192.168.3.0", "192.168.4.0", "192.168.5.0", "192.168.6.0"]
data.ip6_addr = ["2001::1", "2001::2", "3301::1", "3301::2", "4441::1", "4441::2", "5551::1", "5551::2", "6661::1",
                 "6661::2", "7771::1", "7771::2"]
data.ip6_addr_rt = ["2001::", "3301::", "4441::", "5551::", "6661::", "7771::"]
data.loopback_1 = ["11.11.11.1", "22.22.22.1", "33.33.33.1"]
data.loopback6_1 = ["7767:12::2", "6671:230f:12::f", "9109:2cd1:341::3"]
data.af_ipv4 = "ipv4"
data.af_ipv6 = "ipv6"
data.router_id = ["10.10.10.178","10.10.10.179", "20.10.10.178", "20.10.10.179"] 

data.keep_alive = 60
data.hold = 180

# bmp data
bmp_data = SpyTestDict()
bmp_data.host = '192.0.0.250'
bmp_data.port = '5555'
bmp_data.mintry = '100'
bmp_data.maxtry = '200'
bmp_data.targets = ['openbmp']


def set_test_dut():
    vars = st.get_testbed_vars()
    #st.log("vars {}".format(vars))
    data['d1'] = vars.D1
    data['d2'] = vars.D2

def config_depend_cli():

    data['d1_bgp'] = BGP_CLI(data['d1'], data, param_data)
    ## create router bgp as
    data['d1_bgp'].create_bgp_route(data.as_num)
    ### config bgp router id  
    data['d1_bgp'].config_bgp_router_id(data.router_id[0])
    ### create bgp ipv4 neighbor 
    data['d1_bgp'].create_neighbor_v4(data.ip4_addr[1], data.remote_as_num)

    ip_cmd = "cli -c 'configure terminal' -c 'interface Ethernet50' -c 'ip address {}/24'".format(data.ip4_addr[0])
    st.config(data['d1'], ip_cmd)

    data['d2_bgp'] = BGP_CLI(data['d2'], data, param_data)
    ## create router bgp as
    data['d2_bgp'].create_bgp_route(data.remote_as_num)
    ### config bgp router id  
    data['d2_bgp'].config_bgp_router_id(data.router_id[1])
    ### create bgp ipv4 neighbor 
    data['d2_bgp'].create_neighbor_v4(data.ip4_addr[0], data.as_num)
    ip_cmd = "cli -c 'configure terminal' -c 'interface Ethernet50' -c 'ip address {}/24'".format(data.ip4_addr[1])
    st.config(data['d2'], ip_cmd)

def restore_env():
    data['d1_bgp'].flush_neighbors()
    data['d1_bgp'].clear_bgp_router_id(data.router_id[0])
    data['d1_bgp'].flush_bgp_community_list()
    data['d1_bgp'].flush_bgp_aspath_access_lists()
    ip_cmd = "cli -c 'configure terminal' -c 'interface Ethernet50' -c 'no ip address {}/24'".format(data.ip4_addr[0])
    st.config(data['d1'], ip_cmd)
    data['d2_bgp'].flush_neighbors()
    data['d2_bgp'].clear_bgp_router_id(data.router_id[1])
    data['d2_bgp'].flush_bgp_community_list()
    data['d2_bgp'].flush_bgp_aspath_access_lists()
    ip_cmd = "cli -c 'configure terminal' -c 'interface Ethernet50' -c 'no ip address {}/24'".format(data.ip4_addr[1])
    st.config(data['d2'], ip_cmd)
    


@pytest.fixture(scope="module", autouse=True)
def cli_module_hooks(request):
    ########### module prologue #################
    st.log("pre mod config cli")
    st.ensure_min_topology("D1D2:1")
    set_test_dut()
    config_depend_cli()
    BMP_INS.bmp_server_data_read('openbmp.parsed.base_attribute')
    BMP_INS.bmp_server_data_read('openbmp.bmp_raw')
    BMP_INS.bmp_server_data_read('openbmp.parsed.collector')
    BMP_INS.bmp_server_data_read('openbmp.parsed.peer')
    BMP_INS.bmp_server_data_read('openbmp.parsed.router')
    BMP_INS.bmp_server_data_read('openbmp.parsed.unicast_prefix')
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


# bmp 消息类型case
# step1 配置bgp peer
# step2 bgp 下配置bmp 并连接 bmp server
# step3 bgp 建立连接
# check1 bmp 发送init 消息和peer up消息
# step4 拆除会话
# check2 bmp 发送peer down消息
# step5 重新建立连接， 传播路由
# check3 bmp 发送monitor 消息
# check4 show bmp ， bmp成功建立连接，并且有发送的字节统计
def test_bmp_msg_case():
    st.log("test_bmp_msg_case begin")

    # bgp config
    bgpcli_obj = data['d1_bgp']
    dut1 = data['d1']
    peer_ip = data.ip4_addr[1]
    st.log("config cli")    
    bgpcli_obj.config_neighbor(peer = peer_ip, address_family='true', activate='true',
        af_pro='ipv4', af_modifier='unicast')
    st.config(dut1, "cli -c 'configure terminal' -c 'router bgp {}' -c 'address-family ipv4 unicast' -c 'network 200.200.200.178/32 non-connected'"
        .format(data.as_num))

    bgpcli_obj = data['d2_bgp']
    dut2 = data['d2']
    peer_ip = data.ip4_addr[0]
    st.log("config cli") 

    st.config(dut2, "cli -c 'configure terminal' -c 'router bgp {}' -c 'no neighbor {} remote-as {}'"
        .format(data.remote_as_num, data.ip4_addr[0], data.as_num))
    st.wait(10)
    bgpcli_obj.create_neighbor_v4(data.ip4_addr[0], data.as_num)


    ### check init msg ###
    # change 192.0.0.178 
    topic1 = 'openbmp.parsed.router'
    topic2 = 'openbmp.parsed.peer'

    # config BMP
    bmp_ins = BMP_INS(dut1, data, param_data, data.as_num)
    bmp_ins.config_bmp_target(bmp_data.targets[0])
    bmp_ins.config_bmp_connect(bmp_data.host, bmp_data.port, bmp_data.mintry, bmp_data.maxtry, iscreate=False)
    st.wait(10)
    bmp_ins.config_bmp_connect(bmp_data.host, bmp_data.port, bmp_data.mintry, bmp_data.maxtry)

    bmp_ins.config_bmp_monitor('ipv4','post-policy')
    bmp_ins.config_bmp_monitor('ipv4','pre-policy')
    bmp_ins.config_bmp_monitor('ipv6','post-policy')
    bmp_ins.config_bmp_monitor('ipv6','pre-policy')  

    bgpcli_obj.config_neighbor(peer = peer_ip, address_family='true', activate='true',
        af_pro='ipv4', af_modifier='unicast')

    st.config(dut2, "cli -c 'configure terminal' -c 'router bgp {}' -c 'address-family ipv4 unicast' -c 'network 200.200.200.179/32 non-connected'"
        .format(data.remote_as_num))

    st.wait(60)

    ret = BMP_INS.match_bmp_msg(topic2, 'up', 'router_ip', '192.0.0.178')
    if not ret:
        st.report_fail("{} action {} key {} value {} is not expected ".format(topic2, 'up', 'router_ip', '192.0.0.178'))
    
    ret = BMP_INS.match_bmp_msg(topic1, 'init', 'ip_addr', '192.0.0.178')
    if not ret:
        st.report_fail("{} action {} key {} value {} is not expected ".format(topic1, 'init', 'ip_addr', '192.0.0.178'))
    
    ## check monitor 
    topic3 = 'openbmp.parsed.unicast_prefix'
    BMP_INS.bmp_server_data_read(topic3)

    st.config(dut2, "cli -c 'configure terminal' -c 'router bgp {}' -c 'address-family ipv4 unicast' -c 'no network 200.100.10.0/24'"
        .format(data.remote_as_num))

    # config ipv4 network
    st.config(dut2, "cli -c 'configure terminal' -c 'router bgp {}' -c 'address-family ipv4 unicast' -c 'network 200.100.10.0/24 non-connected'"
        .format(data.remote_as_num))

    ### check monitor msg ###
    st.wait(30)
    BMP_INS.read_bmp_data(topic3)
    ret = BMP_INS.match_bmp_msg(topic3, 'add', 'rib.prefix', '200.100.10.0')
    if not ret:
        st.report_fail("{} action {} key {} value {} is not expected - check1".format(topic3, 'add', 'rib.prefix', '200.100.10.0'))

    # config ipv4 network
    BMP_INS.bmp_server_data_read(topic3)

    st.config(dut2, "cli -c 'configure terminal' -c 'router bgp {}' -c 'address-family ipv4 unicast' -c 'no network 200.100.20.0/24'"
        .format(data.remote_as_num))

    st.config(dut2, "cli -c 'configure terminal' -c 'router bgp {}' -c 'address-family ipv4 unicast' -c 'network 200.100.20.0/24 non-connected'"
        .format(data.remote_as_num))

    ### check monitor msg ###
    st.wait(30)
    BMP_INS.read_bmp_data(topic3)
    ret = BMP_INS.match_bmp_msg(topic3, 'add', 'rib.prefix', '200.100.20.0')
    if not ret:
        st.report_fail("{} action {} key {} value {} is not expected - check2".format(topic3, 'add', 'rib.prefix', '200.100.20.0'))

    # del ipv4 network
    BMP_INS.bmp_server_data_read(topic3)
    st.config(dut2, "cli -c 'configure terminal' -c 'router bgp {}' -c 'address-family ipv4 unicast' -c 'no network 200.100.20.0/24'"
        .format(data.remote_as_num))

    ### check monitor msg ###
    st.wait(30)
    BMP_INS.read_bmp_data(topic3)
    ret = BMP_INS.match_bmp_msg(topic3, 'del', 'rib.prefix', '200.100.20.0')
    if not ret:
        st.report_fail("{} action {} key {} value {} is not expected - check2".format(topic3, 'del', 'rib.prefix', '200.100.20.0'))

    ### del peer
    BMP_INS.read_bmp_data(topic2)
    st.config(dut2, "cli -c 'configure terminal' -c 'router bgp {}' -c 'no neighbor {} remote-as {}'".format(data.remote_as_num,data.ip4_addr[0],data.as_num))
    ### check peer down ###
    st.wait(10)
    BMP_INS.read_bmp_data(topic2)

    ret = BMP_INS.match_bmp_msg(topic2, 'down', 'peer.peer_addr', data.ip4_addr[1])
    if not ret:
        st.report_fail("{} action {} key {} value {} is not expected - check2".format(topic2, 'del', 'peer.peer_addr', data.ip4_addr[1]))

    ## check show bmp
    bmp_map = bmp_ins.parse_show_bmp(vrf='default')
    st.log(bmp_map)

    if bmp_map['vrf'] != 'default':
        st.report_fail("show bmp check vrf failed ,vrf = {}".format(bmp_map['vrf']))

    if bmp_map['targets'][0]['mirrot_enable'] != 'disabled':
        st.report_fail("show bmp check mirrot_enable failed ,mirrot_enable = {}".format(bmp_map['targets'][0]['mirrot_enable']))

    if bmp_map['targets'][0]['conn_clients'] != '1':
        st.report_fail("show bmp check conn_clients failed ,conn_clients = {}".format(bmp_map['targets'][0]['conn_clients']))

    if bmp_map['targets'][0]['targets_name'] != bmp_data.targets[0]:
        st.report_fail("show bmp check targets_name failed ,targets_name = {}".format(bmp_map['targets'][0]['targets_name']))

    if len(bmp_map['targets'][0]['clients']) < 1 or int(bmp_map['targets'][0]['clients'][0]['bytesent']) < 10:
        st.report_fail("show bmp check bytesent failed ,bytesent = {}".format(bmp_map['targets'][0]['clients'][0]['bytesent']))

    if int(bmp_map['targets'][0]['clients'][0]['monsent']) < 1:
        st.report_fail("show bmp check monsent failed ,monsent = {}".format(bmp_map['targets'][0]['clients'][0]['monsent']))

    st.report_pass("test_case_passed")
    
    
# bmp vrf 消息类型case
# step1 Vrf1 配置bgp peer
# step2 bgp 下配置bmp 并连接 bmp server
# step3 bgp 建立连接
# check1 bmp 发送init 消息和peer up消息
# step4 拆除会话
# check2 bmp 发送peer down消息
# step5 重新建立连接， 传播路由
# check3 bmp 发送monitor 消息
# check4 show bmp ， bmp成功建立连接，并且有发送的字节统计
def test_bmp_msg_vrf_case():
    st.log("test_bmp_msg_vrf_case begin")

    # bgp config
    # 178 
    dut1 = data['d1']
    d1_bgp_vrf = BGP_CLI(dut1, data, param_data)
    peer_ip = data.ip4_addr[1]
    st.log("config cli")    
    st.config(dut1, "cli -c 'configure terminal' -c 'vrf Vrf1'")

    ip_cmd = "cli -c 'configure terminal' -c 'interface Ethernet50' -c 'vrf Vrf1' -c 'ip address {}/24'".format(data.ip4_addr[0])
    st.config(dut1, ip_cmd)

    ## create router bgp as
    vrf_as = "{} vrf {}".format(data.as_num, data.vrf)
    d1_bgp_vrf.create_bgp_route(vrf_as)
    ### config bgp router id  
    d1_bgp_vrf.config_bgp_router_id(data.router_id[2])
    ### create bgp ipv4 neighbor
    d1_bgp_vrf.create_neighbor_v4(data.ip4_addr[1], data.remote_as_num)
    st.wait(10)
    d1_bgp_vrf.config_neighbor(peer = peer_ip, address_family='true', activate='true',
        af_pro='ipv4', af_modifier='unicast')
    st.config(dut1, "cli -c 'configure terminal' -c 'router bgp {} vrf {}' -c 'address-family ipv4 unicast' -c 'network 200.200.200.178/32 non-connected'"
        .format(data.as_num, data.vrf))
        

    # 179
    dut2 = data['d2']
    d2_bgp_vrf = BGP_CLI(dut2, data, param_data)
    peer_ip = data.ip4_addr[0]
    st.log("config cli") 
    st.config(dut2, "cli -c 'configure terminal' -c 'vrf Vrf1'")

    ip_cmd = "cli -c 'configure terminal' -c 'interface Ethernet50' -c 'vrf Vrf1' -c 'ip address {}/24'".format(data.ip4_addr[1])
    st.config(dut2, ip_cmd)

    ## create router bgp as
    vrf_as = "{} vrf {}".format(data.remote_as_num, data.vrf)
    d2_bgp_vrf.create_bgp_route(vrf_as)
    ### config bgp router id  
    d2_bgp_vrf.config_bgp_router_id(data.router_id[3])
    ### create bgp ipv4 neighbor
    st.config(dut2, "cli -c 'configure terminal' -c 'router bgp {} vrf {}' -c 'no neighbor {} remote-as {}'"
        .format(data.remote_as_num, data.vrf, data.ip4_addr[0], data.as_num))
    st.wait(10)
    d2_bgp_vrf.create_neighbor_v4(data.ip4_addr[0], data.as_num)
    st.wait(10)

    ### check init msg ###
    topic1 = 'openbmp.parsed.router'
    topic2 = 'openbmp.parsed.peer'

    # config BMP
    bmp_ins = BMP_INS(dut2, data, param_data, vrf_as)
    bmp_ins.config_bmp_target(bmp_data.targets[0])
    bmp_ins.config_bmp_connect(bmp_data.host, bmp_data.port, bmp_data.mintry, bmp_data.maxtry, iscreate=False)
    st.wait(10)
    bmp_ins.config_bmp_connect(bmp_data.host, bmp_data.port, bmp_data.mintry, bmp_data.maxtry)

    bmp_ins.config_bmp_monitor('ipv4','post-policy')
    bmp_ins.config_bmp_monitor('ipv4','pre-policy')
    bmp_ins.config_bmp_monitor('ipv6','post-policy')
    bmp_ins.config_bmp_monitor('ipv6','pre-policy')  


    d2_bgp_vrf.config_neighbor(peer = peer_ip, address_family='true', activate='true',
        af_pro='ipv4', af_modifier='unicast')
    st.config(dut2, "cli -c 'configure terminal' -c 'router bgp {} vrf {}' -c 'address-family ipv4 unicast' -c 'network 200.200.200.179/32 non-connected'"
        .format(data.remote_as_num, data.vrf))

    st.wait(60)

    ret1 = BMP_INS.match_bmp_msg(topic2, 'first', 'router_ip', '192.0.0.178')
    ret2 = BMP_INS.match_bmp_msg(topic2, 'up', 'router_ip', '192.0.0.178')

    if not (ret1 or ret2):
        st.report_fail("{} action {} key {} value {} is not expected ".format(topic2, 'up', 'router_ip', '192.0.0.178'))
    
    ret = BMP_INS.match_bmp_msg(topic1, 'init', 'ip_addr', '192.0.0.178')
    if not ret:
        st.report_fail("{} action {} key {} value {} is not expected ".format(topic1, 'init', 'ip_addr', '192.0.0.178'))
    
    ## check monitor 
    topic3 = 'openbmp.parsed.unicast_prefix'
    BMP_INS.bmp_server_data_read(topic3)

    st.config(dut1, "cli -c 'configure terminal' -c 'router bgp {} vrf {}' -c 'address-family ipv4 unicast' -c 'no network 200.200.10.0/24'"
        .format(data.remote_as_num, data.vrf))

    # config ipv4 network
    st.config(dut1, "cli -c 'configure terminal' -c 'router bgp {} vrf {}' -c 'address-family ipv4 unicast' -c 'network 200.200.10.0/24 non-connected'"
        .format(data.remote_as_num, data.vrf))

    ### check monitor msg ###
    st.wait(30)
    BMP_INS.read_bmp_data(topic3)
    ret = BMP_INS.match_bmp_msg(topic3, 'add', 'rib.prefix', '200.200.10.0')
    if not ret:
        st.report_fail("{} action {} key {} value {} is not expected - check1".format(topic3, 'add', 'rib.prefix', '200.200.10.0'))

    # config ipv4 network
    BMP_INS.bmp_server_data_read(topic3)

    st.config(dut1, "cli -c 'configure terminal' -c 'router bgp {} vrf {}' -c 'address-family ipv4 unicast' -c 'no network 200.200.20.0/24'"
        .format(data.remote_as_num, data.vrf))

    st.config(dut1, "cli -c 'configure terminal' -c 'router bgp {} vrf {}' -c 'address-family ipv4 unicast' -c 'network 200.200.20.0/24 non-connected'"
        .format(data.remote_as_num, data.vrf))

    ### check monitor msg ###
    st.wait(30)
    BMP_INS.read_bmp_data(topic3)
    ret = BMP_INS.match_bmp_msg(topic3, 'add', 'rib.prefix', '200.200.20.0')
    if not ret:
        st.report_fail("{} action {} key {} value {} is not expected - check2".format(topic3, 'add', 'rib.prefix', '200.200.20.0'))

    # del ipv4 network
    BMP_INS.bmp_server_data_read(topic3)
    st.config(dut1, "cli -c 'configure terminal' -c 'router bgp {} vrf {}' -c 'address-family ipv4 unicast' -c 'no network 200.200.20.0/24'"
        .format(data.remote_as_num, data.vrf))

    ### check monitor msg ###
    st.wait(30)
    BMP_INS.read_bmp_data(topic3)
    ret = BMP_INS.match_bmp_msg(topic3, 'del', 'rib.prefix', '200.200.20.0')
    if not ret:
        st.report_fail("{} action {} key {} value {} is not expected - check2".format(topic3, 'del', 'rib.prefix', '200.200.20.0'))

    ### del peer
    BMP_INS.read_bmp_data(topic2)
    st.config(dut1, "cli -c 'configure terminal' -c 'router bgp {} vrf {}' -c 'no neighbor {} remote-as {}'".format(data.as_num, data.vrf, data.ip4_addr[0], data.remote_as_num))
    ### check peer down ###
    st.wait(10)
    BMP_INS.read_bmp_data(topic2)

    ret = BMP_INS.match_bmp_msg(topic2, 'down', 'peer.peer_addr', data.ip4_addr[1])
    if not ret:
        st.report_fail("{} action {} key {} value {} is not expected - check2".format(topic2, 'del', 'peer.peer_addr', data.ip4_addr[1]))

    ## check show bmp
    bmp_map = bmp_ins.parse_show_bmp(vrf='Vrf1')
    st.log(bmp_map)

    if bmp_map['vrf'] != 'Vrf1':
        st.report_fail("show bmp check vrf failed ,vrf = {}".format(bmp_map['vrf']))

    if bmp_map['targets'][0]['mirrot_enable'] != 'disabled':
        st.report_fail("show bmp check mirrot_enable failed ,mirrot_enable = {}".format(bmp_map['targets'][0]['mirrot_enable']))

    if bmp_map['targets'][0]['conn_clients'] != '1':
        st.report_fail("show bmp check conn_clients failed ,conn_clients = {}".format(bmp_map['targets'][0]['conn_clients']))

    if bmp_map['targets'][0]['targets_name'] != bmp_data.targets[0]:
        st.report_fail("show bmp check targets_name failed ,targets_name = {}".format(bmp_map['targets'][0]['targets_name']))

    if len(bmp_map['targets'][0]['clients']) < 1 or int(bmp_map['targets'][0]['clients'][0]['bytesent']) < 10:
        st.report_fail("show bmp check bytesent failed ,bytesent = {}".format(bmp_map['targets'][0]['clients'][0]['bytesent']))

    if int(bmp_map['targets'][0]['clients'][0]['monsent']) < 1:
        st.report_fail("show bmp check monsent failed ,monsent = {}".format(bmp_map['targets'][0]['clients'][0]['monsent']))
    

    st.report_pass("test_case_passed")
    