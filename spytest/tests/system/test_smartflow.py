import pytest

from spytest import st, SpyTestDict
from utilities.common import random_vlan_list
from apis.common import redis
import time

smartflow_data = SpyTestDict()

def wait_for_smartflow_up(dut, max_time=0):
    t = time.time() + max_time
    while 1:
        output = st.show(dut, "ps aux | grep sbin/smartflow | grep -v grep", skip_tmpl=True)
        if 'smartflow' in output:
            return True
        time.sleep(3)
        if time.time() > t:
            st.log("wait for smartflow up timeout({}s)".format(max_time))
            return False
        

@pytest.fixture(scope="module", autouse=True)
def smartflow_module_hooks(request):
    global vars
    vars = st.ensure_min_topology("D1D2:1")
    init_vars()

    wait_for_smartflow_up(vars.D1, 60)
    wait_for_smartflow_up(vars.D2, 60)
    time.sleep(30)

    yield

@pytest.fixture(scope="function", autouse=True)
def smartflow_func_hooks(request):
    yield

def init_vars():
    smartflow_data.vlan_id = str(random_vlan_list()[0])
    smartflow_data.outer_ipv6_src = "2001:db8:1::1"
    smartflow_data.outer_ipv6_dst = "2001:db8:1::2"
    smartflow_data.inner_ipv6_src = "2001:db8:1::3"
    smartflow_data.inner_ipv6_dst = "2001:db8:1::4"
    smartflow_data.outer_ipv4_src = "10.10.10.1"
    smartflow_data.outer_ipv4_dst = "10.10.10.2"
    smartflow_data.inner_ipv4_src = "10.10.10.3"
    smartflow_data.inner_ipv4_dst = "10.10.10.4"
    smartflow_data.vxlan_src_port = "14789"
    smartflow_data.vxlan_dst_port = "4789"
    smartflow_data.vni = "2499"
    smartflow_data.src_port = "1133"
    smartflow_data.dst_port = "1134"

def test_smartflow():
    p1_str = 'Ether()/Dot1Q(vlan={})/IPv6(src="{}",dst="{}")'.format(smartflow_data.vlan_id, smartflow_data.outer_ipv6_src, smartflow_data.outer_ipv6_dst)
    p2_str = 'Ether()/IPv6(src="{}",dst="{}")/IPv6ExtHdrRouting()/IP(src="{}",dst="{}")/UDP(sport={},dport={})'.format(smartflow_data.outer_ipv6_src, smartflow_data.outer_ipv6_dst, smartflow_data.inner_ipv4_src, smartflow_data.inner_ipv4_dst, smartflow_data.src_port, smartflow_data.dst_port)
    p3_str = 'Ether()/Dot1Q(vlan={})/IP(src="{}",dst="{}")/UDP(sport={},dport={})/VXLAN(vni={})/Ether()/IPv6(src="{}",dst="{}")/TCP(sport={},dport={})'.format(smartflow_data.vlan_id, smartflow_data.outer_ipv4_src, smartflow_data.outer_ipv4_dst, smartflow_data.vxlan_src_port, smartflow_data.vxlan_dst_port, smartflow_data.vni, smartflow_data.inner_ipv6_src, smartflow_data.inner_ipv6_dst, smartflow_data.src_port, smartflow_data.dst_port)
    p4_str = 'Ether()/IP(src="{}",dst="{}")/TCP(sport={},dport={})'.format(smartflow_data.outer_ipv4_src, smartflow_data.outer_ipv4_dst, smartflow_data.src_port, smartflow_data.dst_port)

    cmd = '''python -c 'from scapy.all import *; p1 = {}; p2 = {}; p3 = {}; p4 = {}; pkts = [p1, p2, p3, p4]; sendp(pkts, count=10, inter=0.01, iface="{}")' '''.format(p1_str, p2_str, p3_str, p4_str, vars.D1D2P1)
    st.config(vars.D1, cmd)

    cmd = "show smartflow flow drop counter"
    output = st.show(vars.D2, cmd, type='alicli')
    st.log(output)
    for flow in output:
        if flow["inport"] == vars.D2D1P1 + '.' + smartflow_data.vlan_id and \
            flow["srcip"] == smartflow_data.outer_ipv6_src and \
            flow["dstip"] == smartflow_data.outer_ipv6_dst and \
            flow["innerdscp"] == "":
            p1_str=""
        elif flow["inport"] == vars.D2D1P1 and \
            flow["srcip"] == smartflow_data.outer_ipv6_src and \
            flow["dstip"] == smartflow_data.outer_ipv6_dst and \
            flow["innerdscp"].startswith("SRv6VPNTunnel") and \
            flow["innersrcip"] == smartflow_data.inner_ipv4_src and \
            flow["innerdstip"] == smartflow_data.inner_ipv4_dst and \
            flow["innerprotocol"] == "UDP" and \
            flow["innersrcport"] == smartflow_data.src_port and \
            flow["innerdstport"] == smartflow_data.dst_port:
            p2_str=""
        elif flow["inport"] == vars.D2D1P1 + '.' + smartflow_data.vlan_id and \
            flow["srcip"] == smartflow_data.outer_ipv4_src and \
            flow["dstip"] == smartflow_data.outer_ipv4_dst and \
            flow["innerdscp"] == "VxlanTunnel" and \
            flow["innersrcip"] == smartflow_data.inner_ipv6_src and \
            flow["innerdstip"] == smartflow_data.inner_ipv6_dst and \
            flow["innerprotocol"] == "TCP" and \
            flow["innersrcport"] == smartflow_data.src_port and \
            flow["innerdstport"] == smartflow_data.dst_port:
            p3_str=""
        elif flow["inport"] == vars.D2D1P1 and \
            flow["srcip"] == smartflow_data.outer_ipv4_src and \
            flow["dstip"] == smartflow_data.outer_ipv4_dst and \
            flow["innerdscp"] == "":
            p4_str=""

    if p1_str or p2_str or p3_str or p4_str:
        st.report_fail("smartflow flow drop counter is not expected")

    st.report_pass("test_case_passed")