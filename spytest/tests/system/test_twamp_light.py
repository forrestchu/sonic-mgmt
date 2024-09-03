import pytest

from spytest import st, SpyTestDict
import apis.routing.ip as ipapi
import string

twamp_data = SpyTestDict()

@pytest.fixture(scope="module", autouse=True)
def twamp_light_module_hooks(request):
    global vars
    vars = st.ensure_min_topology("D1D2:1")
    init_vars()

    yield

@pytest.fixture(scope="function", autouse=True)
def twamp_light_func_hooks(request):
    yield

def init_vars():
    twamp_data.clear()
    twamp_data.ip1 = "fd00::1"
    twamp_data.ip2 = "fd00::2"
    twamp_data.mask = "64"
    twamp_data.rfl1_name = "rfl1"
    twamp_data.snd1_name = "snd1"
    twamp_data.snd2_name = "snd2"
    twamp_data.rfl1_port = "1863"
    twamp_data.snd1_port = "1862"
    twamp_data.snd2_port = "2862"

def check_twamp_session_status(dut, session_name, status):
    cmd = "show twamp-light session name {}".format(session_name)
    output = st.show(dut, cmd, type='alicli')
    st.log(output)
    
    if output is not None and output[0]['status'] == status:
        return True
    return False

# compare: 1 more than or equal , 0 equal, -1 less than
def check_twamp_statistics_pkts(dut, session_name, check_val, compare):
    cmd = "show twamp-light statistics name {}".format(session_name)
    output = st.show(dut, cmd, type='alicli')
    st.log(output)

    if output is not None and abs(string.atoi(output[0]["txpkts"]) - string.atoi(output[0]["rxpkts"])) <= 3:
        num = string.atoi(output[0]["txpkts"])
        if num >= check_val and compare == 1:
            return True
        elif num == check_val and compare == 0:
            return True
        elif num < check_val and compare == -1:
            return True
        st.log("twamp statistics pkts error, expected {} (compare {}), actual {}".format(check_val, compare, num))
        return False
    return False

def test_twamp_light():
    if not ipapi.config_ip_addr_interface(vars.D1, interface_name=vars.D1D2P1, ip_address=twamp_data.ip1,
                                          subnet=twamp_data.mask, family="ipv6", config='add'):
        st.report_fail("config ip for DUT1 failed")
    if not ipapi.config_ip_addr_interface(vars.D2, interface_name=vars.D2D1P1, ip_address=twamp_data.ip2,
                                          subnet=twamp_data.mask, family="ipv6", config='add'):
        st.report_fail("config ip for DUT2 failed")

    # config twamp reflector rfl1
    cmd = "cli -c 'configure terminal' -c 'twamp-light session-reflector add {} reflector-ip {} reflector-port {}'".format(twamp_data.rfl1_name, twamp_data.ip2, twamp_data.rfl1_port)
    st.config(vars.D2, cmd)

    # config twamp sender snd1
    cmd = "cli -c 'configure terminal' -c 'twamp-light session-sender continuous add {} sender-ip {} reflector-ip {} monitor_time 30 tx_interval 10 timeout 1 sender-port {} reflector-port {}'".format(twamp_data.snd1_name, twamp_data.ip1, twamp_data.ip2, twamp_data.snd1_port, twamp_data.rfl1_port)
    st.config(vars.D1, cmd)

    # config twamp sender snd2
    cmd = "cli -c 'configure terminal' -c 'twamp-light session-sender packet-count add {} sender-ip {} reflector-ip {} packet_count 300 tx_interval 100 timeout 1 sender-port {} reflector-port {}'".format(twamp_data.snd2_name, twamp_data.ip1, twamp_data.ip2, twamp_data.snd2_port, twamp_data.rfl1_port)
    st.config(vars.D1, cmd)

    # start all twamp sessions
    cmd = "cli -c 'configure terminal' -c 'twamp-light session-sender start all'"
    st.config(vars.D1, cmd)
    if not check_twamp_session_status(vars.D1, twamp_data.snd1_name, "active") or not check_twamp_session_status(vars.D1, twamp_data.snd2_name, "active"):
        st.report_fail("start twamp sessions failed")
    st.wait(40)

    if not check_twamp_session_status(vars.D1, twamp_data.snd1_name, "inactive") or not check_twamp_session_status(vars.D1, twamp_data.snd2_name, "inactive"):
        st.report_fail("twamp session status error, should be inactive")
    if not check_twamp_statistics_pkts(vars.D1, twamp_data.snd1_name, 1500, 1) or not check_twamp_statistics_pkts(vars.D1, twamp_data.snd2_name, 300, 0):
        st.report_fail("twamp statistics error")

    cmd = "cli -c 'configure terminal' -c 'twamp-light remove all'"
    st.config(vars.D1, cmd)
    st.config(vars.D2, cmd)

    cmd = "show twamp-light session"
    output = st.show(vars.D1, cmd, type='alicli')
    st.log(output)
    if output is None or len(output) != 0:
        st.report_fail("remove twamp sessions for DUT1 failed")

    output = st.show(vars.D2, cmd, type='alicli')
    st.log(output)
    if output is None or len(output) != 0:
        st.report_fail("remove twamp sessions for DUT2 failed")

    st.report_pass("test_case_passed")